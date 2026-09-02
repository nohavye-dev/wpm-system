"""Data access layer implementing the tool semantics (spec doc sections 2-6).

Kept framework-agnostic (plain sqlite3) so it can be unit-tested and reused
outside the MCP transport layer. Every tunable number comes from a
DomainSettings instance (config/settings.py) rather than module constants,
so the same code works whether settings were loaded from defaults or from
JSON.

Split by responsibility across the package: this module holds the
transactional Repository class; read-only listing/stats live in
queries.py, pure retrieval-scoring helpers in retrieval.py, db
export/generate/reembed operations in lifecycle.py, and the embedding-model
compatibility guard in model_guard.py.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from wpm_mcp_server.config.settings import DomainSettings
from wpm_mcp_server.core.enums import (
    EntryStatus,
    EntryType,
    EventType,
    EvidenceType,
    RelationType,
)
from wpm_mcp_server.core.errors import WpmError
from wpm_mcp_server.core.scoring import (
    apply_evidence,
    base_confidence_for_source,
    now_iso,
)
from wpm_mcp_server.infra.database import META_EMBEDDING_MODEL, set_meta
from wpm_mcp_server.infra.embeddings import EmbeddingProvider
from wpm_mcp_server.storage import queries
from wpm_mcp_server.storage.model_guard import ensure_embedding_model
from wpm_mcp_server.storage.retrieval import (
    apply_token_budget,
    collect_conflicts_batch,
    score_entries_batch,
)


@dataclass
class Repository:
    conn: sqlite3.Connection
    embedder: EmbeddingProvider
    settings: DomainSettings = field(default_factory=DomainSettings)
    model_name: str | None = None

    def __post_init__(self) -> None:
        if self.model_name:
            ensure_embedding_model(self.conn, self.model_name)

    # --- store_entry -----------------------------------------------------
    def store_entry(
        self, *, type_: str, content: str, source: str, session_id: str | None = None
    ) -> dict[str, Any]:
        entry_type = EntryType(type_)  # raises ValueError -> caller maps to MCP error
        entry_id = str(uuid.uuid4())
        timestamp = now_iso()
        provenance_score = base_confidence_for_source(source, self.settings)

        self.conn.execute(
            """
            INSERT INTO entries
                (id, type, content, source, provenance_score, validation_score,
                 last_validated_at, created_at)
            VALUES (?, ?, ?, ?, ?, 0.0, ?, ?)
            """,
            (entry_id, entry_type.value, content, source, provenance_score, timestamp, timestamp),
        )
        self._log_event(
            entry_id,
            EventType.CREATED,
            evidence_type=None,
            evidence_ref=None,
            session_id=session_id,
        )

        embedding = self.embedder.embed(content)
        self.conn.execute(
            "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
            (entry_id, json.dumps(embedding)),
        )
        if self.model_name:
            set_meta(self.conn, META_EMBEDDING_MODEL, self.model_name)

        similar = self._process_similar_entries(entry_id, embedding)

        self.conn.commit()
        return {
            "entry_id": entry_id,
            "type": entry_type.value,
            "provenance_score": provenance_score,
            "confidence": provenance_score,
            "potential_contradictions": [
                {
                    "entry_id": s["entry_id"],
                    "similarity": s["similarity"],
                    "type": s["type"],
                    "content": s["content"][:100],
                }
                for s in similar
                if s["entry_id"] != entry_id
                and s["similarity"] >= self.settings.expansion.contradiction_alert_threshold
            ],
        }

    def _process_similar_entries(
        self, entry_id: str, embedding: list[float]
    ) -> list[dict[str, Any]]:
        """Query vector index for entries similar to the new embedding.
        Create implicit 'related' links above auto_link_similarity_threshold.
        Return the full list (including self) for contradiction detection."""
        threshold = self.settings.expansion.auto_link_similarity_threshold
        rows = self.conn.execute(
            """
            SELECT ve.entry_id, e.type, e.content, ve.distance
            FROM vec_entries ve
            JOIN entries e ON e.id = ve.entry_id
            WHERE ve.embedding MATCH ? AND k = ?
            ORDER BY ve.distance
            """,
            (json.dumps(embedding), self.settings.expansion.top_n_candidates),
        ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            other_id = row["entry_id"]
            similarity = 1.0 - row["distance"]
            results.append(
                {
                    "entry_id": other_id,
                    "type": row["type"],
                    "content": row["content"],
                    "similarity": round(similarity, 4),
                }
            )
            if other_id != entry_id and similarity >= threshold:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO entry_links (source_id, target_id, relation_type, weight)
                    VALUES (?, ?, ?, ?)
                    """,
                    (entry_id, other_id, RelationType.RELATED.value, similarity),
                )
        return results

    # --- query_context -----------------------------------------------------
    def query_context(
        self,
        *,
        query: str,
        min_confidence: float = 0.0,
        token_budget: int = 2000,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        query_embedding = self.embedder.embed(query)

        candidates = self.conn.execute(
            """
            SELECT entry_id, distance
            FROM vec_entries
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance
            """,
            (json.dumps(query_embedding), self.settings.expansion.top_n_candidates),
        ).fetchall()

        direct_ids = {row["entry_id"]: (1.0 - row["distance"]) for row in candidates}
        qualified_direct = {
            eid for eid, sim in direct_ids.items() if sim >= self.settings.retrieval.min_similarity
        }

        # --- expansion: 1 hop via entry_links (Lot 2A: single batched query) ---
        expanded: dict[str, float] = {}
        if direct_ids:
            placeholders = ",".join("?" for _ in direct_ids)
            ids = list(direct_ids.keys())
            rows = self.conn.execute(
                f"""
                SELECT source_id, target_id, relation_type, weight FROM entry_links
                WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
                """,
                (*ids, *ids),
            ).fetchall()
            for row in rows:
                s, t, w = row["source_id"], row["target_id"], row["weight"]
                for entry_id, other_id in ((s, t), (t, s)):
                    if entry_id not in direct_ids:
                        continue
                    if other_id in qualified_direct or other_id == entry_id:
                        continue
                    hop_score = direct_ids[entry_id] * self.settings.expansion.hop_decay * w
                    expanded[other_id] = max(expanded.get(other_id, 0.0), hop_score)

        direct_matches = score_entries_batch(self.conn, self.settings, direct_ids, is_direct=True)
        related_context = score_entries_batch(self.conn, self.settings, expanded, is_direct=False)

        # direct_matches must be strong hits: below the similarity floor an
        # entry is noise even with min_confidence=0 (the default). related_context
        # has its own confidence floor (expansion.min_confidence) instead.
        direct_matches = [
            e
            for e in direct_matches
            if e
            and e["confidence"] >= min_confidence
            and e["similarity"] >= self.settings.retrieval.min_similarity
        ]
        related_context = [
            e
            for e in related_context
            if e
            and e["confidence"] >= self.settings.expansion.min_confidence
            and e["confidence"] >= min_confidence
        ]

        direct_matches.sort(key=lambda e: e["score"], reverse=True)
        related_context.sort(key=lambda e: e["score"], reverse=True)

        direct_matches, related_context = apply_token_budget(
            direct_matches, related_context, token_budget
        )

        conflicts = collect_conflicts_batch(self.conn, [e["entry_id"] for e in direct_matches])

        for e in direct_matches:
            self._log_event(
                e["entry_id"],
                EventType.REFERENCED,
                evidence_type=None,
                evidence_ref=None,
                session_id=session_id,
            )
        self.conn.commit()

        return {
            "direct_matches": direct_matches,
            "related_context": related_context,
            "conflicts": conflicts,
        }

    # --- validate_entry / contradict_entry -----------------------------------------------------
    def validate_entry(
        self,
        *,
        entry_id: str,
        evidence_type: str,
        evidence_ref: str,
        session_id: str,
    ) -> dict[str, Any]:
        return self._apply_validation_event(
            entry_id=entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
            session_id=session_id,
            is_contradiction=False,
            conflicting_entry_id=None,
        )

    def contradict_entry(
        self,
        *,
        entry_id: str,
        conflicting_entry_id: str,
        evidence_type: str,
        evidence_ref: str,
    ) -> dict[str, Any]:
        for eid in (entry_id, conflicting_entry_id):
            if self.conn.execute("SELECT 1 FROM entries WHERE id = ?", (eid,)).fetchone() is None:
                raise WpmError(f"entry not found: {eid}")

        result = self._apply_validation_event(
            entry_id=entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
            session_id=None,
            is_contradiction=True,
            conflicting_entry_id=conflicting_entry_id,
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO entry_links (source_id, target_id, relation_type, weight)
            VALUES (?, ?, ?, 1.0)
            """,
            (entry_id, conflicting_entry_id, RelationType.CONTRADICTS.value),
        )
        self.conn.commit()
        return result

    def _apply_validation_event(
        self,
        *,
        entry_id: str,
        evidence_type: str,
        evidence_ref: str,
        session_id: str | None,
        is_contradiction: bool,
        conflicting_entry_id: str | None,
    ) -> dict[str, Any]:
        ev_type = EvidenceType(evidence_type)  # raises ValueError on invalid value

        row = self.conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise WpmError(f"entry not found: {entry_id}")

        if ev_type == EvidenceType.AGENT_REASONING:
            # Logged for traceability but excluded from the score (section 4).
            self._log_event(
                entry_id,
                EventType.CONTRADICTED if is_contradiction else EventType.VALIDATED,
                evidence_type=ev_type,
                evidence_ref=evidence_ref,
                session_id=session_id,
            )
            self.conn.commit()
            return {
                "entry_id": entry_id,
                "validation_score": row["validation_score"],
                "note": "agent_reasoning excluded from score",
            }

        if (
            session_id
            and not is_contradiction
            and self._is_duplicate_validation(entry_id, session_id)
        ):
            return {
                "entry_id": entry_id,
                "validation_score": row["validation_score"],
                "note": "deduplicated: already validated in this session window",
            }

        new_score = apply_evidence(
            current_validation_score=row["validation_score"],
            evidence_type=ev_type,
            is_contradiction=is_contradiction,
            settings=self.settings,
        )

        self.conn.execute(
            "UPDATE entries SET validation_score = ?, last_validated_at = ? WHERE id = ?",
            (new_score, now_iso(), entry_id),
        )
        self._log_event(
            entry_id,
            EventType.CONTRADICTED if is_contradiction else EventType.VALIDATED,
            evidence_type=ev_type,
            evidence_ref=evidence_ref,
            session_id=session_id,
        )
        self.conn.commit()

        return {
            "entry_id": entry_id,
            "validation_score": round(new_score, 4),
            "conflicting_entry_id": conflicting_entry_id,
        }

    def _is_duplicate_validation(self, entry_id: str, session_id: str) -> bool:
        cutoff = (
            datetime.now(UTC) - timedelta(seconds=self.settings.validation.dedup_window_seconds)
        ).isoformat()
        row = self.conn.execute(
            """
            SELECT 1 FROM entry_events
            WHERE entry_id = ? AND session_id = ? AND event_type = ? AND timestamp >= ?
            LIMIT 1
            """,
            (entry_id, session_id, EventType.VALIDATED.value, cutoff),
        ).fetchone()
        return row is not None

    # --- link_entries -----------------------------------------------------
    def link_entries(
        self, *, source_id: str, target_id: str, relation_type: str, weight: float = 1.0
    ) -> dict[str, Any]:
        rel = RelationType(relation_type)
        for eid in (source_id, target_id):
            if self.conn.execute("SELECT 1 FROM entries WHERE id = ?", (eid,)).fetchone() is None:
                raise WpmError(f"entry not found: {eid}")

        self.conn.execute(
            """
            INSERT INTO entry_links (source_id, target_id, relation_type, weight)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET weight = excluded.weight
            """,
            (source_id, target_id, rel.value, weight),
        )
        self.conn.commit()
        return {
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": rel.value,
            "weight": weight,
        }

    # --- pin_entry / deprecate_entry / restore_entry -------------------------
    def pin_entry(self, *, entry_id: str) -> dict[str, Any]:
        return self._set_status(entry_id, EntryStatus.PINNED, EventType.PINNED)

    def deprecate_entry(self, *, entry_id: str) -> dict[str, Any]:
        return self._set_status(entry_id, EntryStatus.DEPRECATED, EventType.DEPRECATED)

    def restore_entry(self, *, entry_id: str) -> dict[str, Any]:
        return self._set_status(entry_id, EntryStatus.ACTIVE, EventType.RESTORED)

    def _set_status(
        self, entry_id: str, status: EntryStatus, event_type: EventType
    ) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise WpmError(f"entry not found: {entry_id}")
        self.conn.execute("UPDATE entries SET status = ? WHERE id = ?", (status.value, entry_id))
        self._log_event(
            entry_id, event_type, evidence_type=None, evidence_ref=None, session_id=None
        )
        self.conn.commit()
        return {"entry_id": entry_id, "status": status.value}

    # --- get_stats ---------------------------------------------------------
    def get_stats(self) -> dict[str, Any]:
        """Read-only diagnostic: memory health overview."""
        return queries.compute_stats(self.conn, self.settings)

    def list_entries(
        self,
        *,
        type: str | None = None,
        status: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Paginated, filterable listing of entries with current confidence."""
        return queries.list_entries(
            self.conn,
            self.settings,
            type=type,
            status=status,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            limit=limit,
            offset=offset,
        )

    def _log_event(
        self,
        entry_id: str,
        event_type: EventType,
        *,
        evidence_type: EvidenceType | None,
        evidence_ref: str | None,
        session_id: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO entry_events (id, entry_id, event_type, evidence_type, evidence_ref, session_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                entry_id,
                event_type.value,
                evidence_type.value if evidence_type else None,
                evidence_ref,
                session_id,
                now_iso(),
            ),
        )

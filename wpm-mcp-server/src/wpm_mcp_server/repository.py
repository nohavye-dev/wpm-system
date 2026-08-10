"""Data access layer implementing the tool semantics (spec doc sections 2-6).

Kept framework-agnostic (plain sqlite3) so it can be unit-tested and reused
outside the MCP transport layer. Every tunable number comes from a
DomainSettings instance (settings.py) rather than module constants, so the
same code works whether settings were loaded from defaults or from JSON.
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from wpm_mcp_server.domain import EntryType, EventType, EvidenceType, RelationType
from wpm_mcp_server.embeddings import EmbeddingProvider
from wpm_mcp_server.scoring import apply_evidence, base_confidence_for_source, confidence_at, now_iso
from wpm_mcp_server.settings import DomainSettings


class WpmError(Exception):
    """Raised for domain-level errors (e.g. missing entry, stale evidence)."""


@dataclass
class Repository:
    conn: sqlite3.Connection
    embedder: EmbeddingProvider
    settings: DomainSettings = field(default_factory=DomainSettings)

    # --- store_entry -----------------------------------------------------
    def store_entry(self, *, type_: str, content: str, source: str) -> dict[str, Any]:
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
        self._log_event(entry_id, EventType.CREATED, evidence_type=None, evidence_ref=None, session_id=None)

        embedding = self.embedder.embed(content)
        self.conn.execute(
            "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
            (entry_id, json.dumps(embedding)),
        )

        self._auto_link_by_similarity(entry_id, embedding)

        self.conn.commit()
        return {
            "entry_id": entry_id,
            "type": entry_type.value,
            "provenance_score": provenance_score,
            "confidence": provenance_score,
        }

    def _auto_link_by_similarity(self, entry_id: str, embedding: list[float]) -> None:
        """Create implicit 'related' links to existing entries above a
        similarity threshold (spec section 4: implicit links from
        similarity vs explicit links via link_entries)."""
        threshold = self.settings.expansion.auto_link_similarity_threshold
        rows = self.conn.execute(
            """
            SELECT entry_id, distance
            FROM vec_entries
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance
            """,
            (json.dumps(embedding), self.settings.expansion.top_n_candidates),
        ).fetchall()

        for row in rows:
            other_id = row["entry_id"]
            if other_id == entry_id:
                continue
            similarity = 1.0 - row["distance"]  # cosine distance -> similarity
            if similarity >= threshold:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO entry_links (source_id, target_id, relation_type, weight)
                    VALUES (?, ?, ?, ?)
                    """,
                    (entry_id, other_id, RelationType.RELATED.value, similarity),
                )

    # --- query_context -----------------------------------------------------
    def query_context(
        self,
        *,
        query: str,
        min_confidence: float = 0.0,
        token_budget: int = 2000,
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

        # --- expansion: 1 hop via entry_links (section 6) ---
        expanded: dict[str, float] = {}
        for entry_id, similarity in direct_ids.items():
            for link in self.conn.execute(
                """
                SELECT target_id, relation_type, weight FROM entry_links WHERE source_id = ?
                UNION
                SELECT source_id, relation_type, weight FROM entry_links WHERE target_id = ?
                """,
                (entry_id, entry_id),
            ).fetchall():
                other_id = link["target_id"] if "target_id" in link.keys() else link[0]
                if other_id in direct_ids or other_id == entry_id:
                    continue
                hop_score = similarity * self.settings.expansion.hop_decay * link["weight"]
                expanded[other_id] = max(expanded.get(other_id, 0.0), hop_score)

        direct_matches = [self._score_entry(eid, sim, is_direct=True) for eid, sim in direct_ids.items()]
        related_context = [self._score_entry(eid, sim, is_direct=False) for eid, sim in expanded.items()]

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
            if e and e["confidence"] >= self.settings.expansion.min_confidence and e["confidence"] >= min_confidence
        ]

        direct_matches.sort(key=lambda e: e["score"], reverse=True)
        related_context.sort(key=lambda e: e["score"], reverse=True)

        direct_matches, related_context = self._apply_token_budget(direct_matches, related_context, token_budget)

        conflicts = self._collect_conflicts([e["entry_id"] for e in direct_matches])

        for e in direct_matches:
            self._log_event(e["entry_id"], EventType.REFERENCED, evidence_type=None, evidence_ref=None, session_id=None)
        self.conn.commit()

        return {
            "direct_matches": direct_matches,
            "related_context": related_context,
            "conflicts": conflicts,
        }

    def _score_entry(self, entry_id: str, similarity: float, *, is_direct: bool) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None

        confidence = confidence_at(
            entry_type=EntryType(row["type"]),
            provenance_score=row["provenance_score"],
            validation_score=row["validation_score"],
            last_validated_at=row["last_validated_at"],
            settings=self.settings,
        )
        centrality = self._centrality(entry_id)

        score = (
            self.settings.retrieval.weight_similarity * similarity
            + self.settings.retrieval.weight_confidence * confidence
            + self.settings.retrieval.weight_centrality * centrality
        )

        return {
            "entry_id": entry_id,
            "type": row["type"],
            "content": row["content"],
            "source": row["source"],
            "similarity": round(similarity, 4),
            "confidence": round(confidence, 4),
            "centrality": round(centrality, 4),
            "score": round(score, 4),
            "is_direct": is_direct,
        }

    def _centrality(self, entry_id: str) -> float:
        row = self.conn.execute(
            "SELECT COUNT(*) as c, COALESCE(SUM(weight), 0) as w FROM entry_links WHERE target_id = ?",
            (entry_id,),
        ).fetchone()
        # Simple bounded transform: diminishing returns past a few links.
        return min(1.0, math.log1p(row["w"]) / 3.0)

    def _apply_token_budget(
        self, direct: list[dict[str, Any]], related: list[dict[str, Any]], token_budget: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        def approx_tokens(entry: dict[str, Any]) -> int:
            return max(1, len(entry["content"]) // 4)

        kept_direct: list[dict[str, Any]] = []
        kept_related: list[dict[str, Any]] = []
        used = 0
        for entry in direct:
            cost = approx_tokens(entry)
            if used + cost > token_budget:
                break
            kept_direct.append(entry)
            used += cost
        for entry in related:
            cost = approx_tokens(entry)
            if used + cost > token_budget:
                break
            kept_related.append(entry)
            used += cost
        return kept_direct, kept_related

    def _collect_conflicts(self, entry_ids: list[str]) -> list[dict[str, Any]]:
        conflicts = []
        for entry_id in entry_ids:
            rows = self.conn.execute(
                """
                SELECT target_id as other_id FROM entry_links
                WHERE source_id = ? AND relation_type = ?
                UNION
                SELECT source_id as other_id FROM entry_links
                WHERE target_id = ? AND relation_type = ?
                """,
                (entry_id, RelationType.CONTRADICTS.value, entry_id, RelationType.CONTRADICTS.value),
            ).fetchall()
            for row in rows:
                conflicts.append({"entry_id": entry_id, "contradicted_by": row["other_id"]})
        return conflicts

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
            return {"entry_id": entry_id, "validation_score": row["validation_score"], "note": "agent_reasoning excluded from score"}

        if session_id and not is_contradiction and self._is_duplicate_validation(entry_id, session_id):
            return {"entry_id": entry_id, "validation_score": row["validation_score"], "note": "deduplicated: already validated in this session window"}

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
            datetime.now(timezone.utc) - timedelta(seconds=self.settings.validation.dedup_window_seconds)
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
    def link_entries(self, *, source_id: str, target_id: str, relation_type: str, weight: float = 1.0) -> dict[str, Any]:
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
        return {"source_id": source_id, "target_id": target_id, "relation_type": rel.value, "weight": weight}

    # --- shared -----------------------------------------------------
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

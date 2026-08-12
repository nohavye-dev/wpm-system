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

from wpm_mcp_server.domain import EntryStatus, EntryType, EventType, EvidenceType, RelationType
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

        similar = self._process_similar_entries(entry_id, embedding)

        self.conn.commit()
        return {
            "entry_id": entry_id,
            "type": entry_type.value,
            "provenance_score": provenance_score,
            "confidence": provenance_score,
            "potential_contradictions": [
                {"entry_id": s["entry_id"], "similarity": s["similarity"],
                 "type": s["type"], "content": s["content"][:100]}
                for s in similar
                if s["entry_id"] != entry_id
                and s["similarity"] >= self.settings.expansion.contradiction_alert_threshold
            ],
        }

    def _process_similar_entries(self, entry_id: str, embedding: list[float]) -> list[dict[str, Any]]:
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
            results.append({
                "entry_id": other_id,
                "type": row["type"],
                "content": row["content"],
                "similarity": round(similarity, 4),
            })
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
            eid
            for eid, sim in direct_ids.items()
            if sim >= self.settings.retrieval.min_similarity
        }

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
                if other_id in qualified_direct or other_id == entry_id:
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
        row = self.conn.execute(
            "SELECT * FROM entries WHERE id = ? AND status != ?",
            (entry_id, EntryStatus.DEPRECATED.value),
        ).fetchone()
        if row is None:
            return None

        confidence = confidence_at(
            entry_type=EntryType(row["type"]),
            provenance_score=row["provenance_score"],
            validation_score=row["validation_score"],
            last_validated_at=row["last_validated_at"],
            status=row["status"],
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
            "status": row["status"],
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
        deprecated = set(
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM entries WHERE status = ?",
                (EntryStatus.DEPRECATED.value,),
            ).fetchall()
        )
        for entry_id in entry_ids:
            if entry_id in deprecated:
                continue
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
                if row["other_id"] not in deprecated:
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

    # --- pin_entry / deprecate_entry / restore_entry -------------------------
    def pin_entry(self, *, entry_id: str) -> dict[str, Any]:
        return self._set_status(entry_id, EntryStatus.PINNED, EventType.PINNED)

    def deprecate_entry(self, *, entry_id: str) -> dict[str, Any]:
        return self._set_status(entry_id, EntryStatus.DEPRECATED, EventType.DEPRECATED)

    def restore_entry(self, *, entry_id: str) -> dict[str, Any]:
        return self._set_status(entry_id, EntryStatus.ACTIVE, EventType.RESTORED)

    def _set_status(self, entry_id: str, status: EntryStatus, event_type: EventType) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise WpmError(f"entry not found: {entry_id}")
        self.conn.execute("UPDATE entries SET status = ? WHERE id = ?", (status.value, entry_id))
        self._log_event(entry_id, event_type, evidence_type=None, evidence_ref=None, session_id=None)
        self.conn.commit()
        return {"entry_id": entry_id, "status": status.value}
    # --- get_stats ---------------------------------------------------------
    def get_stats(self) -> dict[str, Any]:
        """Read-only diagnostic: memory health overview."""

        total = self.conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]

        by_type = {
            row["type"]: row["c"]
            for row in self.conn.execute(
                "SELECT type, COUNT(*) AS c FROM entries GROUP BY type"
            ).fetchall()
        }

        never_validated = [
            {
                "entry_id": row["id"],
                "type": row["type"],
                "content": row["content"][:200],
            }
            for row in self.conn.execute(
                """
                SELECT e.id, e.type, e.content
                FROM entries e
                LEFT JOIN entry_events ev ON ev.entry_id = e.id AND ev.event_type = 'validated'
                WHERE ev.id IS NULL
                """
            ).fetchall()
        ]

        contradictions = [
            {"source_id": row["source_id"], "target_id": row["target_id"]}
            for row in self.conn.execute(
                """
                SELECT source_id, target_id FROM entry_links
                WHERE relation_type = 'contradicts'
                """
            ).fetchall()
        ]

        rows = self.conn.execute(
            "SELECT id, type, content, provenance_score, validation_score, last_validated_at, status FROM entries"
        ).fetchall()

        entries_with_confidence = []
        for row in rows:
            conf = confidence_at(
                entry_type=EntryType(row["type"]),
                provenance_score=row["provenance_score"],
                validation_score=row["validation_score"],
                last_validated_at=row["last_validated_at"],
                status=row["status"],
                settings=self.settings,
            )
            entries_with_confidence.append(
                {
                    "entry_id": row["id"],
                    "type": row["type"],
                    "status": row["status"],
                    "content": row["content"][:200],
                    "confidence": round(conf, 4),
                }
            )

        entries_with_confidence.sort(key=lambda e: e["confidence"])
        lowest = entries_with_confidence[:5]

        distribution = {"high": 0, "medium": 0, "low": 0}
        for e in entries_with_confidence:
            c = e["confidence"]
            if c >= 0.7:
                distribution["high"] += 1
            elif c >= 0.3:
                distribution["medium"] += 1
            else:
                distribution["low"] += 1

        recent = [
            {
                "entry_id": row["entry_id"],
                "event_type": row["event_type"],
                "timestamp": row["timestamp"],
            }
            for row in self.conn.execute(
                "SELECT entry_id, event_type, timestamp FROM entry_events "
                "ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
        ]

        return {
            "total_entries": total,
            "by_type": by_type,
            "confidence_distribution": distribution,
            "never_validated": never_validated,
            "active_contradictions": contradictions,
            "lowest_confidence": lowest,
            "recent_activity": recent,
        }

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

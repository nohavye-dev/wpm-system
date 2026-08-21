"""Pure read-side retrieval helpers used by Repository.query_context.

Each function takes an open connection and DomainSettings explicitly;
nothing here writes to the database.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any

from wpm_mcp_server.config.settings import DomainSettings
from wpm_mcp_server.core.enums import EntryStatus, EntryType, RelationType
from wpm_mcp_server.core.scoring import confidence_at


def score_entry(
    conn: sqlite3.Connection,
    settings: DomainSettings,
    entry_id: str,
    similarity: float,
    *,
    is_direct: bool,
) -> dict[str, Any] | None:
    row = conn.execute(
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
        settings=settings,
    )
    entry_centrality = centrality(conn, entry_id)

    score = (
        settings.retrieval.weight_similarity * similarity
        + settings.retrieval.weight_confidence * confidence
        + settings.retrieval.weight_centrality * entry_centrality
    )

    return {
        "entry_id": entry_id,
        "type": row["type"],
        "content": row["content"],
        "source": row["source"],
        "status": row["status"],
        "similarity": round(similarity, 4),
        "confidence": round(confidence, 4),
        "centrality": round(entry_centrality, 4),
        "score": round(score, 4),
        "is_direct": is_direct,
    }


def centrality(conn: sqlite3.Connection, entry_id: str) -> float:
    row = conn.execute(
        "SELECT COUNT(*) as c, COALESCE(SUM(weight), 0) as w FROM entry_links WHERE target_id = ?",
        (entry_id,),
    ).fetchone()
    # Simple bounded transform: diminishing returns past a few links.
    return min(1.0, math.log1p(row["w"]) / 3.0)


def apply_token_budget(
    direct: list[dict[str, Any]],
    related: list[dict[str, Any]],
    token_budget: int,
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


def collect_conflicts(conn: sqlite3.Connection, entry_ids: list[str]) -> list[dict[str, Any]]:
    conflicts = []
    deprecated = set(
        row["id"]
        for row in conn.execute(
            "SELECT id FROM entries WHERE status = ?",
            (EntryStatus.DEPRECATED.value,),
        ).fetchall()
    )
    for entry_id in entry_ids:
        if entry_id in deprecated:
            continue
        rows = conn.execute(
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

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


def centrality_map(conn: sqlite3.Connection, entry_ids: list[str]) -> dict[str, float]:
    """Batch centrality for many entries (Lot 2A: avoids N queries)."""
    if not entry_ids:
        return {}
    placeholders = ",".join("?" for _ in entry_ids)
    rows = conn.execute(
        f"SELECT target_id, COALESCE(SUM(weight), 0) as w FROM entry_links WHERE target_id IN ({placeholders}) GROUP BY target_id",
        tuple(entry_ids),
    ).fetchall()
    out: dict[str, float] = {row["target_id"]: min(1.0, math.log1p(row["w"]) / 3.0) for row in rows}
    for eid in entry_ids:
        out.setdefault(eid, 0.0)
    return out


def fetch_entries_map(conn: sqlite3.Connection, entry_ids: list[str]) -> dict[str, sqlite3.Row]:
    """Batch fetch non-deprecated entries by id (Lot 2A)."""
    if not entry_ids:
        return {}
    placeholders = ",".join("?" for _ in entry_ids)
    rows = conn.execute(
        f"SELECT * FROM entries WHERE id IN ({placeholders}) AND status != ?",
        (*entry_ids, EntryStatus.DEPRECATED.value),
    ).fetchall()
    return {row["id"]: row for row in rows}


def score_entries_batch(
    conn: sqlite3.Connection,
    settings: DomainSettings,
    similarities: dict[str, float],
    *,
    is_direct: bool,
) -> list[dict[str, Any]]:
    """Score many entries with 2 queries total (entries + centrality)."""
    if not similarities:
        return []
    ids = list(similarities.keys())
    entries = fetch_entries_map(conn, ids)
    cent_map = centrality_map(conn, ids)
    scored: list[dict[str, Any] | None] = []
    for eid, sim in similarities.items():
        row = entries.get(eid)
        if row is None:
            continue
        confidence = confidence_at(
            entry_type=EntryType(row["type"]),
            provenance_score=row["provenance_score"],
            validation_score=row["validation_score"],
            last_validated_at=row["last_validated_at"],
            status=row["status"],
            settings=settings,
        )
        entry_centrality = cent_map.get(eid, 0.0)
        score = (
            settings.retrieval.weight_similarity * sim
            + settings.retrieval.weight_confidence * confidence
            + settings.retrieval.weight_centrality * entry_centrality
        )
        scored.append(
            {
                "entry_id": eid,
                "type": row["type"],
                "content": row["content"],
                "source": row["source"],
                "status": row["status"],
                "similarity": round(sim, 4),
                "confidence": round(confidence, 4),
                "centrality": round(entry_centrality, 4),
                "score": round(score, 4),
                "is_direct": is_direct,
            }
        )
    return [e for e in scored if e is not None]


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
    """Legacy per-entry version kept for compat; delegates to batch."""
    return collect_conflicts_batch(conn, entry_ids)


def collect_conflicts_batch(conn: sqlite3.Connection, entry_ids: list[str]) -> list[dict[str, Any]]:
    """Batch version (Lot 2A): 2 queries instead of N+1."""
    if not entry_ids:
        return []
    deprecated = set(
        row["id"]
        for row in conn.execute(
            "SELECT id FROM entries WHERE status = ?",
            (EntryStatus.DEPRECATED.value,),
        ).fetchall()
    )
    filtered = [eid for eid in entry_ids if eid not in deprecated]
    if not filtered:
        return []
    placeholders = ",".join("?" for _ in filtered)
    rows = conn.execute(
        f"""
            SELECT source_id as a, target_id as b FROM entry_links
            WHERE relation_type = ? AND (source_id IN ({placeholders}) OR target_id IN ({placeholders}))
            """,
        (RelationType.CONTRADICTS.value, *filtered, *filtered),
    ).fetchall()
    # Build map entry_id -> list/other_ids, but return flat list as before
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        a, b = row["a"], row["b"]
        for entry_id, other in ((a, b), (b, a)):
            if entry_id in filtered and other not in deprecated:
                # Only emit if entry_id was in the requested set
                # (avoids duplicating both directions when both are in filtered)
                # but keep original flat format: each link once per requested entry
                if entry_id in set(filtered):
                    conflicts.append({"entry_id": entry_id, "contradicted_by": other})
        # The above double counts; deduplicate by tracking (entry_id, other)
    # Deduplicate while preserving order of discovery
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for c in conflicts:
        key = (c["entry_id"], c["contradicted_by"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    # Filter to only include conflicts where entry_id was requested and other not deprecated
    # (legacy returned one row per requested entry_id per link, even if other also in filtered)
    return deduped

"""Read-only queries: memory-health stats and paginated listing.

Plain functions over an open connection so they stay testable and
reusable independently of the Repository class.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from wpm_mcp_server.config.settings import DomainSettings
from wpm_mcp_server.core.enums import EntryStatus, EntryType
from wpm_mcp_server.core.scoring import confidence_at


def compute_stats(conn: sqlite3.Connection, settings: DomainSettings) -> dict[str, Any]:
    """Read-only diagnostic: memory health overview."""

    total = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]

    by_type = {
        row["type"]: row["c"]
        for row in conn.execute(
            "SELECT type, COUNT(*) AS c FROM entries GROUP BY type"
        ).fetchall()
    }

    never_validated = [
        {
            "entry_id": row["id"],
            "type": row["type"],
            "content": row["content"][:200],
        }
        for row in conn.execute(
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
        for row in conn.execute(
            """
            SELECT source_id, target_id FROM entry_links
            WHERE relation_type = 'contradicts'
            """
        ).fetchall()
    ]

    rows = conn.execute(
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
            settings=settings,
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
        for row in conn.execute(
            "SELECT entry_id, event_type, timestamp FROM entry_events "
            "ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
    ]

    pin_candidates_rows = conn.execute(
        """
        SELECT e.id, e.type, e.provenance_score, e.validation_score,
               e.last_validated_at, e.status, COUNT(ev.id) AS validation_count
        FROM entries e
        JOIN entry_events ev ON ev.entry_id = e.id AND ev.event_type = 'validated'
        WHERE e.status = 'active' AND e.type IN ('archi_decision', 'convention')
        GROUP BY e.id
        HAVING validation_count >= 3
        """
    ).fetchall()
    pin_candidates = [
        row["id"] for row in pin_candidates_rows
        if confidence_at(
            entry_type=EntryType(row["type"]), provenance_score=row["provenance_score"],
            validation_score=row["validation_score"], last_validated_at=row["last_validated_at"],
            status=row["status"], settings=settings,
        ) > 0.7
    ]

    stats = {
        "total_entries": total,
        "by_type": by_type,
        "confidence_distribution": distribution,
        "never_validated": never_validated,
        "active_contradictions": contradictions,
        "lowest_confidence": lowest,
        "recent_activity": recent,
    }
    if pin_candidates:
        stats["pin_candidates"] = pin_candidates
        stats["reminder"] = (
            f"{len(pin_candidates)} entries validated 3+ times could be "
            "pinned via pin_entry."
        )
    return stats


def list_entries(
conn: sqlite3.Connection,
settings: DomainSettings,
*,
type: str | None = None,
status: str | None = None,
min_confidence: float | None = None,
max_confidence: float | None = None,
limit: int = 50,
offset: int = 0,
) -> dict[str, Any]:
    """Paginated, filterable listing of entries with current confidence."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    where_parts = []
    params: list[Any] = []

    if status is not None:
        where_parts.append("status = ?")
        params.append(status)
    else:
        where_parts.append("status != ?")
        params.append(EntryStatus.DEPRECATED.value)

    if type is not None:
        where_parts.append("type = ?")
        params.append(type)

    where_clause = "WHERE " + " AND ".join(where_parts)

    rows = conn.execute(
        f"SELECT id, type, content, source, provenance_score, validation_score, last_validated_at, status, created_at FROM entries {where_clause}",
        params,
    ).fetchall()

    entries_with_confidence = []
    for row in rows:
        conf = confidence_at(
            entry_type=EntryType(row["type"]),
            provenance_score=row["provenance_score"],
            validation_score=row["validation_score"],
            last_validated_at=row["last_validated_at"],
            status=row["status"],
            settings=settings,
        )
        if min_confidence is not None and conf < min_confidence:
            continue
        if max_confidence is not None and conf > max_confidence:
            continue
        entries_with_confidence.append({
            "entry_id": row["id"],
            "type": row["type"],
            "content": row["content"][:200],
            "source": row["source"],
            "status": row["status"],
            "confidence": round(conf, 4),
            "created_at": row["created_at"],
        })

    entries_with_confidence.sort(key=lambda e: e["confidence"], reverse=True)
    total = len(entries_with_confidence)
    page = entries_with_confidence[offset : offset + limit]

    return {"entries": page, "total": total, "limit": limit, "offset": offset}

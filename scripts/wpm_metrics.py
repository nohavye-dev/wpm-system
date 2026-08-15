#!/usr/bin/env python3
"""Measure wpm rule compliance from a wpm database.

Reads a wpm database and reports three observable, server-side proxies:

- rule 5 (dedup-before-write): for each session_id, how many entries were
  stored without a preceding query_context (REFERENCED event);
- rule 8 (evidence hierarchy): the proportion of validate_entry calls using
  agent_reasoning vs. external evidence;
- rule 3/reliability: the proportion of entries never validated, or
  validated only by agent_reasoning.

Usage: python3 wpm_metrics.py <path-to-wpm.db>
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict


def analyze(rows: list[tuple]) -> dict:
    sessions = defaultdict(
        lambda: {
            "stores": 0,
            "stores_without_prior_query": 0,
            "referenced_events": 0,
            "first_query_before_first_store": None,
            "_queried_since_last_store": False,
        }
    )
    for session_id, event_type in rows:
        key = session_id or "unknown"
        s = sessions[key]
        if event_type == "referenced":
            s["referenced_events"] += 1
            s["_queried_since_last_store"] = True
            if s["first_query_before_first_store"] is None:
                s["first_query_before_first_store"] = True
        elif event_type == "created":
            s["stores"] += 1
            if not s["_queried_since_last_store"]:
                s["stores_without_prior_query"] += 1
            s["_queried_since_last_store"] = False
            if s["first_query_before_first_store"] is None:
                s["first_query_before_first_store"] = False
    for s in sessions.values():
        s.pop("_queried_since_last_store", None)
    return sessions


def analyze_evidence_types(rows: list[tuple]) -> dict:
    """rows: (event_type, evidence_type) from entry_events."""
    counts = defaultdict(int)
    for event_type, evidence_type in rows:
        if event_type == "validated":
            counts[evidence_type or "unknown"] += 1
    total = sum(counts.values())
    return {
        "counts": dict(counts),
        "agent_reasoning_rate": (
            round(counts.get("agent_reasoning", 0) / total, 4) if total else None
        ),
    }


def analyze_never_validated(entry_rows: list[tuple], event_rows: list[tuple]) -> dict:
    """entry_rows: (id,); event_rows: (entry_id, event_type, evidence_type)."""
    validated = defaultdict(set)
    for entry_id, event_type, evidence_type in event_rows:
        if event_type == "validated":
            validated[entry_id].add(evidence_type or "unknown")

    total = len(entry_rows)
    never = sum(1 for (entry_id,) in entry_rows if entry_id not in validated)
    agent_reasoning_only = sum(
        1
        for (entry_id,) in entry_rows
        if entry_id in validated and validated[entry_id] == {"agent_reasoning"}
    )
    return {
        "total_entries": total,
        "never_validated": never,
        "agent_reasoning_only": agent_reasoning_only,
        "never_validated_rate": round(never / total, 4) if total else None,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)

    db_path = sys.argv[1]
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT session_id, event_type FROM entry_events ORDER BY rowid ASC"
        ).fetchall()
        evidence_rows = conn.execute(
            "SELECT event_type, evidence_type FROM entry_events"
        ).fetchall()
        entry_rows = conn.execute("SELECT id FROM entries").fetchall()
        event_rows = conn.execute(
            "SELECT entry_id, event_type, evidence_type FROM entry_events"
        ).fetchall()
    finally:
        conn.close()

    sessions = analyze(rows)
    total_stores = sum(s["stores"] for s in sessions.values())
    total_violations = sum(s["stores_without_prior_query"] for s in sessions.values())

    summary = {
        "sessions": {k: v for k, v in sorted(sessions.items())},
        "totals": {
            "sessions": len(sessions),
            "stores": total_stores,
            "stores_without_prior_query": total_violations,
            "violation_rate": (
                round(total_violations / total_stores, 4) if total_stores else None
            ),
        },
        "evidence_types": analyze_evidence_types(evidence_rows),
        "validation_coverage": analyze_never_validated(entry_rows, event_rows),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

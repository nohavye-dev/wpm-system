#!/usr/bin/env python3
"""Measure wpm rule-5 (dedup-before-write) compliance from entry_events.

Reads a wpm database and, for each session_id seen in entry_events, reports
how many entries were stored without a preceding query_context (REFERENCED
event) in the same session — the observable, server-side proxy for the
MEMORY FIRST / DEDUP BEFORE WRITING rules. Mirrors the in-memory enforcement
used by the store_entry tool: a store is a violation when no query_context
has occurred since the previous store.

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
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

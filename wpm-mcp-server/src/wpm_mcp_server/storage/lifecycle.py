"""Database lifecycle operations: export, re-embed, generate from JSON."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

from wpm_mcp_server.config.settings import DomainSettings
from wpm_mcp_server.infra.database import META_EMBEDDING_MODEL, set_meta
from wpm_mcp_server.infra.embeddings import EmbeddingProvider


def export_db(conn: sqlite3.Connection) -> dict[str, Any]:
    """Export all entries, events and links as a JSON-serializable dict.

    Embeddings (vec_entries) are intentionally excluded — they are
    regenerated on import by generate_db().
    """
    entries = [dict(row) for row in conn.execute("SELECT * FROM entries").fetchall()]
    events = [dict(row) for row in conn.execute("SELECT * FROM entry_events").fetchall()]
    links = [dict(row) for row in conn.execute("SELECT * FROM entry_links").fetchall()]
    return {"entries": entries, "entry_events": events, "entry_links": links}


def reembed_all(
    conn: sqlite3.Connection,
    embedder: EmbeddingProvider,
    model_name: str,
) -> dict[str, Any]:
    """Re-embed every stored entry's content in place.

    Vector spaces are model-specific, so after switching embedding models
    every entry must be re-embedded (not just new ones). Entries keep their
    id/type/source/status; only vec_entries is rewritten. The model marker
    is stamped so ensure_embedding_model passes on next use.
    """
    rows = conn.execute("SELECT id, content FROM entries").fetchall()
    for row in rows:
        embedding = embedder.embed(row["content"])
        conn.execute("DELETE FROM vec_entries WHERE entry_id = ?", (row["id"],))
        conn.execute(
            "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
            (row["id"], json.dumps(embedding)),
        )
    set_meta(conn, META_EMBEDDING_MODEL, model_name)
    conn.commit()
    return {"reembedded": len(rows), "model": model_name}


def generate_db(
    db_path: str | Path,
    json_data: dict[str, Any],
    embedder: EmbeddingProvider,
    settings: DomainSettings | None = None,
    model_name: str | None = None,
) -> None:
    """Create a new database at *db_path* from exported JSON data.

    Entries, events and links are inserted as-is (preserving original IDs).
    Embeddings are regenerated from each entry's content via *embedder*.
    When *model_name* is given, the embedding-model marker is stamped.
    """
    from wpm_mcp_server.infra import database as wdb

    conn = wdb.connect(str(db_path))

    entries = json_data.get("entries", [])
    events = json_data.get("entry_events", [])
    links = json_data.get("entry_links", [])

    for entry in entries:
        conn.execute(
            """
            INSERT INTO entries
                (id, type, content, source, provenance_score, validation_score,
                 last_validated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"],
                entry["type"],
                entry["content"],
                entry["source"],
                entry["provenance_score"],
                entry["validation_score"],
                entry["last_validated_at"],
                entry["created_at"],
            ),
        )
        try:
            conn.execute(
                "UPDATE entries SET status = ? WHERE id = ?",
                (entry.get("status", "active"), entry["id"]),
            )
        except sqlite3.OperationalError as exc:
            _logger.debug("status update skipped for %s: %s", entry.get("id"), exc)

        embedding = embedder.embed(entry["content"])
        conn.execute(
            "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
            (entry["id"], json.dumps(embedding)),
        )

    for event in events:
        conn.execute(
            """
            INSERT INTO entry_events (id, entry_id, event_type, evidence_type, evidence_ref, session_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                event["entry_id"],
                event["event_type"],
                event.get("evidence_type"),
                event.get("evidence_ref"),
                event.get("session_id"),
                event["timestamp"],
            ),
        )

    for link in links:
        conn.execute(
            """
            INSERT OR IGNORE INTO entry_links (source_id, target_id, relation_type, weight)
            VALUES (?, ?, ?, ?)
            """,
            (link["source_id"], link["target_id"], link["relation_type"], link.get("weight", 1.0)),
        )

    if model_name is not None:
        set_meta(conn, META_EMBEDDING_MODEL, model_name)

    conn.commit()
    conn.close()

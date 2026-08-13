"""SQLite connection management and schema (spec doc, section 2)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import sqlite_vec

from wpm_mcp_server.domain import EMBEDDING_DIM

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    provenance_score REAL NOT NULL,
    validation_score REAL NOT NULL DEFAULT 0.0,
    last_validated_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entry_events (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES entries(id),
    event_type TEXT NOT NULL,
    evidence_type TEXT,
    evidence_ref TEXT,
    session_id TEXT,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entry_events_entry_id ON entry_events(entry_id);
CREATE INDEX IF NOT EXISTS idx_entry_events_session_id ON entry_events(session_id);

CREATE TABLE IF NOT EXISTS entry_links (
    source_id TEXT NOT NULL REFERENCES entries(id),
    target_id TEXT NOT NULL REFERENCES entries(id),
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (source_id, target_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_entry_links_source ON entry_links(source_id);
CREATE INDEX IF NOT EXISTS idx_entry_links_target ON entry_links(target_id);
"""

VEC_TABLE_SQL_TEMPLATE = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
    entry_id TEXT PRIMARY KEY,
    embedding FLOAT[{dim}] distance_metric=cosine
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with sqlite-vec loaded and the schema ensured."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript(SCHEMA_SQL)
    conn.execute(VEC_TABLE_SQL_TEMPLATE.format(dim=EMBEDDING_DIM))
    try:
        conn.execute(
            "ALTER TABLE entries ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def resolve_within_root(db_path: str | Path, root: str | Path | None = None) -> Path:
    """Resolve db_path, requiring it to be strictly inside `root`.

    Relative paths are resolved against `root`, not the process cwd — since
    the MCP host (not the server) decides the working directory, callers pass
    the project root explicitly (usually the directory that holds
    wpm.config.json) so the containment guarantee holds regardless of how the
    host launched the server. `root` defaults to the current working
    directory. The root itself is rejected too: a directory can never be
    opened as a SQLite database (sqlite3 fails with "unable to open database
    file"), so an early, clear error beats a crash at connect time.
    """
    raw = str(db_path)
    if raw.endswith(os.sep):
        raise RuntimeError(
            f"db_path {raw!r} must be a file path, not a directory "
            "(trailing separator)"
        )
    root_real = os.path.realpath(str(root or os.getcwd()))
    if os.path.isabs(raw):
        resolved = os.path.realpath(raw)
    else:
        resolved = os.path.realpath(os.path.join(root_real, raw))
    if resolved == root_real:
        raise RuntimeError(
            f"db_path {str(db_path)!r} must be a file inside the project, not "
            f"the project root directory itself ({root_real})"
        )
    if not resolved.startswith(root_real + os.sep):
        raise RuntimeError(
            f"db_path {str(db_path)!r} must live inside the project "
            f"directory ({root_real})"
        )
    return Path(resolved)


# Backwards-compatible alias kept for the CLI and older callers.
resolve_within_cwd = resolve_within_root

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

    conn.executescript(SCHEMA_SQL)
    conn.execute(VEC_TABLE_SQL_TEMPLATE.format(dim=EMBEDDING_DIM))
    conn.commit()
    return conn


def resolve_within_cwd(db_path: str | Path) -> Path:
    """Resolve db_path, requiring it to be strictly inside the cwd.

    The server is launched with cwd = project root, so this guarantees the
    database always lives under the project directory. The project root
    itself is rejected too: a directory can never be opened as a SQLite
    database (sqlite3 fails with "unable to open database file"), so an
    early, clear error beats a crash at connect time.
    """
    raw = str(db_path)
    if raw.endswith(os.sep):
        raise RuntimeError(
            f"db_path {raw!r} must be a file path, not a directory "
            "(trailing separator)"
        )
    resolved = os.path.realpath(raw)
    cwd = os.path.realpath(os.getcwd())
    if resolved == cwd:
        raise RuntimeError(
            f"db_path {str(db_path)!r} must be a file inside the project, not "
            f"the project root directory itself ({cwd})"
        )
    if not resolved.startswith(cwd + os.sep):
        raise RuntimeError(
            f"db_path {str(db_path)!r} must live inside the current working "
            f"directory ({cwd})"
        )
    return Path(resolved)

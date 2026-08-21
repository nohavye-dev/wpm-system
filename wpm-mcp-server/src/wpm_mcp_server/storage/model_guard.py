"""Guard against embedding-model mismatches between db and runtime.

Embedding vector spaces are model-specific: querying or storing against a
db whose vectors came from another model silently degrades retrieval.
"""

from __future__ import annotations

import sqlite3

from wpm_mcp_server.infra.database import META_EMBEDDING_MODEL, get_meta


def ensure_embedding_model(conn: sqlite3.Connection, model_name: str) -> None:
    """Fail fast when a database's embeddings were produced by another model.

    Embedding vector spaces are model-specific: querying or storing against
    a db whose vectors came from a different model silently degrades
    retrieval. When the db is empty there is nothing to protect (the first
    store stamps the marker). A missing marker on a populated db means it
    predates model tracking — the operator must re-embed before use.
    """
    count = conn.execute("SELECT COUNT(*) AS c FROM vec_entries").fetchone()["c"]
    if count == 0:
        return
    stored = get_meta(conn, META_EMBEDDING_MODEL)
    if stored == model_name:
        return
    detail = f"'{stored}'" if stored else "unknown (pre-migration)"
    raise RuntimeError(
        f"wpm: this database's embeddings were produced by embedding model "
        f"{detail}, but the active model is '{model_name}'. The two vector "
        f"spaces are incompatible — run 'wpm reembed' at the project root "
        "to re-embed every entry before continuing."
    )

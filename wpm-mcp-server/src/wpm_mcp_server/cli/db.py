"""DB path helpers with containment guarantee."""

from __future__ import annotations

from pathlib import Path

from wpm_mcp_server.infra import database as db


def resolve_project_db(raw: str) -> Path:
    """Validate db_path lives inside the current project; return resolved Path."""
    return db.resolve_within_root(raw, Path.cwd())


def resolve_wpm_config() -> Path:
    return Path.cwd() / "wpm.config.json"

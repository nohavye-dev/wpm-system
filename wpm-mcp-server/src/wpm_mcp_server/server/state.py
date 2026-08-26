"""Import-time bootstrap and process-wide runtime state.

The server is active when it can resolve a database path — from
wpm.config.json (relative to its own location, not the host's cwd) or
WPM_DB_PATH. Without one it stays inert: it starts and lists its tools,
but every tool returns a clear "not activated" error.

This module also owns the single-process session state: the server runs
stdio (one process per session), so a single generated id labels this
session's events in entry_events, and an in-memory flag records whether a
query_context has occurred since the last store_entry — the signal behind
the rule-5 (dedup before write) reminder.
"""

import os
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from wpm_mcp_server.config.settings import load_settings, resolve_response_language
from wpm_mcp_server.infra import database as db
from wpm_mcp_server.infra.embeddings import get_provider, resolve_model_name
from wpm_mcp_server.prompts.memory_rules import build_memory_usage_rules
from wpm_mcp_server.prompts.mode import push_mode
from wpm_mcp_server.prompts.verification import compile_verification_patterns
from wpm_mcp_server.storage.repository import Repository
from wpm_mcp_server.storage.users import (
    UserRepository,
    connect_users_db,
    resolve_users_db_path,
)

NOT_ACTIVATED_MESSAGE = (
    "wpm is not activated in this project: run 'wpm enable' at the project "
    "root (writes wpm.config.json) and launch this MCP server with the "
    "project as its working directory (or set WPM_DB_PATH)."
)

_config_path = Path(os.environ.get("WPM_CONFIG_PATH", "wpm.config.json"))
_has_config = _config_path.exists()
CONFIG_DIR = _config_path.resolve().parent if _has_config else Path.cwd()

SETTINGS = load_settings(_config_path)


def _current_user_language() -> str | None:
    """Current profile language (if any) — overrides config's
    response_language at resolution time, without touching any prompt text.

    Resolved once at import (server start), like wpm.config.json.
    A mid-session `wpm current-user` switch takes effect for the
    <current-user> block on the next turn (fresh read / push), but the
    language clause baked into SERVER_INSTRUCTIONS only refreshes on restart
    — the block remains authoritative.
    """
    try:
        profile = UserRepository(
            connect_users_db(resolve_users_db_path())
        ).get_current_user()
        return (profile or {}).get("language")
    except Exception:
        return None


_response_language = resolve_response_language(
    _current_user_language() or SETTINGS.response_language,
    os.environ.get("WPM_RESPONSE_LANGUAGE"),
)
SERVER_INSTRUCTIONS = build_memory_usage_rules(
    _response_language, pull_instructions=not push_mode()
)

_db_path = os.environ.get("WPM_DB_PATH") or SETTINGS.db_path
if _db_path:
    DB_PATH = db.resolve_within_root(_db_path, CONFIG_DIR)
else:
    DB_PATH = None

mcp = FastMCP(
    name="wpm-server",
    instructions=SERVER_INSTRUCTIONS,
)

_repo: Repository | None = None
_users_repo: UserRepository | None = None
_project_rules_cache: str | None = None

SESSION_ID = str(uuid.uuid4())
_queried_since_last_store = False

# Safety valve for behavioral observations (the prompt is deliberately
# encouraging; this is the hard cap). Process lifetime == one session.
OBSERVATION_SESSION_LIMIT = 20
_observation_count = 0

VERIFICATION_PATTERNS, _invalid_patterns = compile_verification_patterns(
    SETTINGS.verification_command_patterns or []
)


def get_repo() -> Repository:
    global _repo
    if _repo is None:
        if DB_PATH is None:
            raise RuntimeError(NOT_ACTIVATED_MESSAGE)
        conn = db.connect(DB_PATH)
        embedder = get_provider()
        _repo = Repository(
            conn=conn,
            embedder=embedder,
            settings=SETTINGS.domain,
            model_name=resolve_model_name(),
        )
    return _repo


def get_users_repo() -> UserRepository:
    """Lazy singleton for the global user-profiles store.

    Deliberately independent from DB_PATH / project activation: profiles
    are global, so the user tools work even when the server runs without
    an activated project (the memory tools then stay inert).
    """
    global _users_repo
    if _users_repo is None:
        _users_repo = UserRepository(connect_users_db(resolve_users_db_path()))
    return _users_repo


def queried_since_last_store() -> bool:
    """Whether a query_context happened since the last store_entry."""
    return _queried_since_last_store


def mark_context_queried() -> None:
    global _queried_since_last_store
    _queried_since_last_store = True


def reset_queried_flag() -> None:
    global _queried_since_last_store
    _queried_since_last_store = False


def observation_budget_available() -> bool:
    return _observation_count < OBSERVATION_SESSION_LIMIT


def count_observation() -> None:
    global _observation_count
    _observation_count += 1


def get_cached_project_rules() -> str | None:
    return _project_rules_cache


def set_cached_project_rules(block: str) -> None:
    global _project_rules_cache
    _project_rules_cache = block


async def on_memory_mutated(ctx: Context | None) -> None:
    """Drop the project-rules cache and tell subscribed clients to reload it."""
    set_cached_project_rules(None)
    try:
        session = ctx.session
        if session is not None:
            await session.send_resource_updated("wpm://project-rules")
    except Exception:
        # Notification is best-effort — the resource itself is always fresh
        # on the next read.
        pass

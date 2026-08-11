"""FastMCP server exposing the memory tools (spec doc, section 7).

Usage rules (language, evidence requirements, non-deletion) are embedded
directly in tool descriptions rather than only in AGENTS.md, per spec
section 8 ("diffusion via le MCP, pas l'AGENTS.md") — the agent sees them
every time it inspects or calls a tool, not just once at session start.
"""

import os

from mcp.server.fastmcp import FastMCP

from wpm_mcp_server import db
from wpm_mcp_server.embeddings import get_provider
from wpm_mcp_server.repository import WpmError, Repository
from wpm_mcp_server.settings import load_settings

_settings = load_settings()
_db_path = os.environ.get("WPM_DB_PATH") or _settings.db_path
if not _db_path:
    raise RuntimeError(
        "wpm.config.json: 'db_path' is required and has no default. "
        "Set 'db_path' in wpm.config.json or export WPM_DB_PATH."
    )
DB_PATH = db.resolve_within_cwd(_db_path)

mcp = FastMCP(
    name="wpm-server",
    instructions=(
        "Persistent, confidence-weighted project memory. "
        "All entry content MUST be written in English, regardless of the "
        "conversation language, for embedding consistency. "
        "validate_entry and contradict_entry REQUIRE an evidence_type and "
        "evidence_ref grounded in something external and checkable "
        "(a test result, a file, another entry) — never validate on "
        "reasoning alone. Contradicted entries are never deleted, only "
        "down-weighted and flagged."
    ),
)

_repo: Repository | None = None


def get_repo() -> Repository:
    global _repo
    if _repo is None:
        conn = db.connect(DB_PATH)
        model = os.environ.get("WPM_EMBEDDING_MODEL")
        embedder = get_provider(model)
        _repo = Repository(conn=conn, embedder=embedder, settings=_settings.domain)
    return _repo


@mcp.tool(
    description=(
        "Store a new memory entry (doc, archi_decision, learning, convention, "
        "or bug_pattern). CONTENT MUST BE IN ENGLISH. "
        "'source' should be one of: official_doc, observed_code, "
        "tool_execution, agent_inference (unknown sources get a neutral "
        "default confidence). Returns the new entry_id and its initial "
        "confidence — this entry starts unvalidated; call validate_entry "
        "with real evidence once it is confirmed."
    )
)
def store_entry(type: str, content: str, source: str) -> dict:
    try:
        return get_repo().store_entry(type_=type, content=content, source=source)
    except ValueError as exc:
        return {"error": True, "message": f"invalid type: {exc}"}


@mcp.tool(
    description=(
        "Hybrid retrieval: vector similarity + confidence weighting + graph "
        "centrality, plus 1-hop graph expansion for associative recall "
        "(spec section 6). Query text should be in English for best "
        "similarity matching. Returns direct_matches (strong hits), "
        "related_context (associative, lower-confidence recall via linked "
        "entries), and conflicts (entries with an active 'contradicts' "
        "link) — always check conflicts before relying on a direct_match."
    )
)
def query_context(query: str, min_confidence: float = 0.0, token_budget: int = 2000) -> dict:
    return get_repo().query_context(query=query, min_confidence=min_confidence, token_budget=token_budget)


@mcp.tool(
    description=(
        "Record EXTERNAL, CHECKABLE evidence that an entry was confirmed. "
        "evidence_type must be one of: execution_verified (test/build/command "
        "ran with expected result — strongest), cross_reference (confirmed "
        "independently by another source), reuse_without_failure (reused "
        "without issue — weak, capped), agent_reasoning (no external proof — "
        "logged but does NOT move the score, do not use this to inflate "
        "confidence). evidence_ref should point to what proves it (a test "
        "log, a file path, another entry_id). session_id is required for "
        "dedup: repeated validation of the same entry within one session "
        "only counts once."
    )
)
def validate_entry(entry_id: str, evidence_type: str, evidence_ref: str, session_id: str) -> dict:
    try:
        return get_repo().validate_entry(
            entry_id=entry_id, evidence_type=evidence_type, evidence_ref=evidence_ref, session_id=session_id
        )
    except (ValueError, WpmError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Record that entry_id is contradicted by conflicting_entry_id, with "
        "external evidence (same evidence_type rules as validate_entry). "
        "NEVER deletes either entry — only lowers entry_id's validation_score "
        "(contradiction lowers the score faster than a confirmation raises "
        "it) and creates a visible 'contradicts' link so future "
        "query_context calls surface the conflict instead of hiding it."
    )
)
def contradict_entry(entry_id: str, conflicting_entry_id: str, evidence_type: str, evidence_ref: str) -> dict:
    try:
        return get_repo().contradict_entry(
            entry_id=entry_id,
            conflicting_entry_id=conflicting_entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
        )
    except (ValueError, WpmError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Create or update an EXPLICIT link between two entries. relation_type "
        "must be one of: related, contradicts, depends_on, refines. Implicit "
        "'related' links are created automatically by store_entry above a "
        "similarity threshold — use this tool for relationships the "
        "similarity search would not infer on its own (e.g. a dependency "
        "between an architecture decision and a convention)."
    )
)
def link_entries(source_id: str, target_id: str, relation_type: str, weight: float = 1.0) -> dict:
    try:
        return get_repo().link_entries(
            source_id=source_id, target_id=target_id, relation_type=relation_type, weight=weight
        )
    except (ValueError, WpmError) as exc:
        return {"error": True, "message": str(exc)}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

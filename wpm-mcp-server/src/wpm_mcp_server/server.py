"""Memory server (FastMCP): tools, resources, instructions.

One of two complementary layers. OpenCode is the single target host, so
wpm splits its behavior between:

- this MCP layer (declarative, read by the model): a reduced set of usage
  rules in initialize.instructions (3 golden rules + a handful of standing
  policies, re-readable via the wpm://memory-rules resource), tool
  descriptions, JSON schemas, and targeted `tool_result` reminders;
- the wpm-opencode-plugin layer (event-driven, triggered by the host):
  `experimental.chat.system.transform`, `experimental.session.compacting`,
  `tool.execute.before/after`, and `event` (`session.idle`).

Project rules/conventions are exposed as the wpm://project-rules resource,
recomputed from memory and invalidated (with a resources/updated
notification) on every mutation. record_execution remains a tool, but rule
16 is primarily enforced deterministically by the plugin's
tool.execute.after hook (which shells out to `wpm record-execution`), so it
no longer depends on the model remembering to call this tool.

Host-agnostic activation: the server is active when it can resolve a database
path — from wpm.config.json (relative to its own location, not the host's
cwd) or WPM_DB_PATH. Without one it stays inert: it starts and lists its
tools, but every tool returns a clear "not activated" error.
"""

import os
import uuid
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from wpm_mcp_server import db
from wpm_mcp_server.behavior import (
    build_language_note,
    build_memory_usage_rules,
    PROJECT_RULES_QUERY,
    PROJECT_RULES_TOKEN_BUDGET,
    VERIFICATION_COMMAND_PATTERNS,
    build_project_rules_block,
    compile_verification_patterns,
    format_project_rules,
    looks_like_verification_command,
)
from wpm_mcp_server.embeddings import get_provider
from wpm_mcp_server.repository import WpmError, Repository
from wpm_mcp_server.settings import load_settings, resolve_response_language

EntryType = Literal[
    "doc", "archi_decision", "insight", "convention",
    "bug_pattern", "execution_result",
]
EntrySource = Literal[
    "official_doc", "observed_code", "tool_execution", "agent_inference",
]

NOT_ACTIVATED_MESSAGE = (
    "wpm is not activated in this project: run 'wpm enable' at the project "
    "root (writes wpm.config.json) and launch this MCP server with the "
    "project as its working directory (or set WPM_DB_PATH)."
)

_config_path = Path(os.environ.get("WPM_CONFIG_PATH", "wpm.config.json"))
_has_config = _config_path.exists()
_config_dir = _config_path.resolve().parent if _has_config else Path.cwd()

_settings = load_settings(_config_path)

_response_language = resolve_response_language(
    _settings.response_language, os.environ.get("WPM_RESPONSE_LANGUAGE")
)
_memory_usage_rules = build_memory_usage_rules(_response_language)
_language_note = build_language_note(_response_language)

_db_path = os.environ.get("WPM_DB_PATH") or _settings.db_path
if _db_path:
    DB_PATH = db.resolve_within_root(_db_path, _config_dir)
else:
    DB_PATH = None

mcp = FastMCP(
    name="wpm-server",
    instructions=_memory_usage_rules,
)

_repo: Repository | None = None
_project_rules_cache: str | None = None

# Session tracking: the server runs stdio (one process per session), so a
# single generated id labels this session's events in entry_events, and an
# in-memory flag records whether a query_context has occurred since the last
# store_entry — the signal behind the rule-5 (dedup before write) reminder.
_session_id = str(uuid.uuid4())
_queried_since_last_store = False

_REMINDER_DEDUP = (
    "potential_contradictions found: compare the candidate contents and prefer "
    "validate_entry on an existing near-duplicate over creating a new entry"
)
_REMINDER_MEMORY_FIRST = (
    "MEMORY FIRST: run query_context on this topic before storing to avoid a duplicate"
)
_REMINDER_VALIDATE = (
    "this entry is unvalidated: call validate_entry with external evidence once it is confirmed"
)
_REMINDER_CONFLICTS = (
    "conflicts found: check them before relying on a direct_match — never "
    "present a contested fact as settled without flagging it"
)

_verification_patterns, _invalid_patterns = compile_verification_patterns(
    _settings.verification_command_patterns or []
)


def get_repo() -> Repository:
    global _repo
    if _repo is None:
        if DB_PATH is None:
            raise RuntimeError(NOT_ACTIVATED_MESSAGE)
        conn = db.connect(DB_PATH)
        model = os.environ.get("WPM_EMBEDDING_MODEL")
        embedder = get_provider(model)
        _repo = Repository(conn=conn, embedder=embedder, settings=_settings.domain)
    return _repo


async def _on_memory_mutated(ctx: Context | None) -> None:
    """Drop the project-rules cache and tell subscribed clients to reload it."""
    global _project_rules_cache
    _project_rules_cache = None
    try:
        session = ctx.session
        if session is not None:
            await session.send_resource_updated("wpm://project-rules")
    except Exception:
        # Notification is best-effort — the resource itself is always fresh
        # on the next read.
        pass


# --- tools -----------------------------------------------------------------

@mcp.tool(
    description=(
        "Store one durable memory entry. CONTENT MUST BE IN ENGLISH. "
        "type: doc=explanatory content | archi_decision=structural choice "
        "(observed or decided) | convention=consistent naming/style/process "
        "rule | insight=discovered understanding, durable for weeks (not a "
        "decision) | bug_pattern=known issue+cause WITH PROOF | "
        "execution_result=use record_execution instead, not this tool. "
        "source: official_doc=read & cited | observed_code=seen directly in "
        "code | tool_execution=actually ran a command | agent_inference=your "
        "deduction, no direct proof. "
        "Immediately BEFORE this call, run query_context on the topic: if a "
        "near-duplicate already exists, call validate_entry on it instead of "
        "creating a duplicate. Only store facts still true and useful in "
        "weeks. Returns the new entry_id and its initial confidence — this "
        "entry starts unvalidated; call validate_entry with real evidence "
        "once it is confirmed." + _language_note
    )
)
async def store_entry(ctx: Context, type: EntryType, content: str, source: EntrySource) -> dict:
    global _queried_since_last_store
    try:
        result = get_repo().store_entry(
            type_=type, content=content, source=source, session_id=_session_id
        )
        reminders = []
        if result.get("potential_contradictions"):
            reminders.append(_REMINDER_DEDUP)
        elif not _queried_since_last_store:
            reminders.append(_REMINDER_MEMORY_FIRST)
        reminders.append(_REMINDER_VALIDATE)
        result["reminder"] = " ".join(reminders)
        _queried_since_last_store = False
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        if isinstance(exc, ValueError):
            return {"error": True, "message": f"invalid type: {exc}"}
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Hybrid retrieval: vector similarity + confidence weighting + graph "
        "centrality, plus 1-hop graph expansion for associative recall. "
        "WHEN you are about to read a file, run grep, or search the codebase "
        "with bash/glob, call this tool BEFORE doing so (MEMORY FIRST); call "
        "it too at the start of every substantive answer. Query text "
        "should be in English for best similarity matching. Returns "
        "direct_matches (strong hits), related_context (associative, "
        "lower-confidence recall via linked entries), and conflicts (entries "
        "with an active 'contradicts' link) — always check conflicts before "
        "relying on a direct_match." + _language_note
    )
)
def query_context(query: str, min_confidence: float = 0.0, token_budget: int = 2000) -> dict:
    global _queried_since_last_store
    try:
        result = get_repo().query_context(
            query=query,
            min_confidence=min_confidence,
            token_budget=token_budget,
            session_id=_session_id,
        )
        _queried_since_last_store = True
        reminders = []
        if result.get("related_context"):
            reminders.append(
                "related_context is 1-hop associative recall — lower "
                "confidence than direct_matches, mention it cautiously."
            )
        if result.get("conflicts"):
            reminders.append(_REMINDER_CONFLICTS)
        if reminders:
            result["reminder"] = " ".join(reminders)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


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
        "only counts once." + _language_note
    )
)
async def validate_entry(
    ctx: Context, entry_id: str, evidence_type: str, evidence_ref: str, session_id: str
) -> dict:
    try:
        result = get_repo().validate_entry(
            entry_id=entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
            session_id=session_id,
        )
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Record that entry_id is contradicted by conflicting_entry_id, with "
        "external evidence (same evidence_type rules as validate_entry). "
        "NEVER deletes either entry — only lowers entry_id's validation_score "
        "(contradiction lowers the score faster than a confirmation raises "
        "it) and creates a visible 'contradicts' link so future "
        "query_context calls surface the conflict instead of hiding it." + _language_note
    )
)
async def contradict_entry(
    ctx: Context, entry_id: str, conflicting_entry_id: str, evidence_type: str, evidence_ref: str
) -> dict:
    try:
        result = get_repo().contradict_entry(
            entry_id=entry_id,
            conflicting_entry_id=conflicting_entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
        )
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Create or update an EXPLICIT link between two entries. relation_type "
        "must be one of: related, contradicts, depends_on, refines. Implicit "
        "'related' links are created automatically by store_entry above a "
        "similarity threshold — use this tool for relationships the "
        "similarity search would not infer on its own (e.g. a dependency "
        "between an architecture decision and a convention)." + _language_note
    )
)
async def link_entries(
    ctx: Context, source_id: str, target_id: str, relation_type: str, weight: float = 1.0
) -> dict:
    try:
        result = get_repo().link_entries(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
        )
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Capture the result of a test/build/lint command as memory: stores an "
        "execution_result entry (source=tool_execution) and, on success, validates it "
        "as execution_verified in a single call. The command must look like a "
        "verification command (pytest, npm/pnpm/yarn/bun test or build, "
        "dotnet/cargo/go test or build, make/mix/flutter/mvn/gradle/sbt test, "
        "vitest, jest, deno test, tox, phpunit, rake test, compileall, "
        "py_compile, bash -n, shellcheck, tsc --noEmit, ruff check, mypy, "
        "eslint, plus any configured verification_command_patterns). Call "
        "this right after running such a command — do not use it for trivial "
        "commands (ls, cat, echo, grep, git status) whose exit 0 proves "
        "nothing. session_id must be the current session id." + _language_note
    )
)
async def record_execution(ctx: Context, command: str, succeeded: bool, session_id: str) -> dict:
    try:
        if not looks_like_verification_command(command, _verification_patterns):
            return {
                "error": True,
                "message": (
                    "command does not match a verification pattern; if it is "
                    "still meaningful evidence, use store_entry + validate_entry "
                    "manually instead"
                ),
            }
        repo = get_repo()
        content = "\n".join(
            [
                f"Command executed: {command}",
                f"Result: {'success' if succeeded else 'failure'}",
                f"Directory: {_config_dir}",
            ]
        )
        store_result = repo.store_entry(
            type_="execution_result", content=content, source="tool_execution", session_id=_session_id
        )
        entry_id = store_result["entry_id"]
        if succeeded:
            validation = repo.validate_entry(
                entry_id=entry_id,
                evidence_type="execution_verified",
                evidence_ref=command,
                session_id=session_id,
            )
        else:
            validation = {"note": "left unvalidated (command failed)"}
        await _on_memory_mutated(ctx)
        return {
            "entry_id": entry_id,
            "type": "execution_result",
            "stored": True,
            "validation": validation,
        }
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Pin an entry so its confidence NEVER decays. USE WHEN: a fundamental "
        "architecture decision that defines the project, a convention that is "
        "company/project policy, or an entry that has been validated repeatedly "
        "across many sessions and is now considered settled. DO NOT use for: "
        "recent insights, bug patterns that may be fixed, entries with active "
        "contradictions. Pinning is reversible via restore_entry." + _language_note
    )
)
async def pin_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().pin_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Mark an entry as deprecated — excluded from all future queries. "
        "USE WHEN: an entry has been conclusively contradicted and the newer "
        "entry is confirmed, the code/module it references no longer exists, "
        "or it describes a bug pattern that has been fixed. DO NOT use for: "
        "entries you are unsure about. Deprecation is reversible via "
        "restore_entry, but prefer caution." + _language_note
    )
)
async def deprecate_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().deprecate_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Restore a pinned or deprecated entry back to active status. "
        "USE WHEN: a deprecation was premature, the entry is relevant again, "
        "or a pin is no longer warranted." + _language_note
    )
)
async def restore_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().restore_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Paginated, filterable list of memory entries with current confidence. "
        "Excludes deprecated entries by default (set status='deprecated' to "
        "include them). Optional filters: type (doc/archi_decision/insight/"
        "convention/bug_pattern/execution_result), status (active/pinned/deprecated), "
        "min_confidence, max_confidence. limit max 200, default 50. "
        "Sorted by confidence descending. Returns entries + total for pagination." + _language_note
    )
)
def list_entries(type: str | None = None, status: str | None = None,
                 min_confidence: float | None = None, max_confidence: float | None = None,
                 limit: int = 50, offset: int = 0) -> dict:
    try:
        return get_repo().list_entries(
            type=type, status=status,
            min_confidence=min_confidence, max_confidence=max_confidence,
            limit=limit, offset=offset,
        )
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Review memory health: total entries by type, confidence distribution "
        "(low <0.3 / medium 0.3-0.7 / high >0.7), entries never validated, "
        "active contradictions, 5 lowest-confidence entries, and the last 10 "
        "events. Read-only diagnostic — use this before relying heavily on "
        "memory, or when you suspect stale/contradicted entries." + _language_note
    )
)
def get_memory_stats() -> dict:
    try:
        return get_repo().get_stats()
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


# --- resources --------------------------------------------------------------

@mcp.resource(
    "wpm://project-rules",
    name="Project rules and conventions",
    description=(
        "The project's high-confidence conventions and architecture decisions, "
        "recomputed from persistent memory. Read this at session start and "
        "re-read it when memory is updated."
    ),
    mime_type="text/markdown",
)
def project_rules() -> str:
    global _project_rules_cache
    if _project_rules_cache is not None:
        return _project_rules_cache
    if DB_PATH is None:
        return ""
    try:
        result = get_repo().query_context(
            query=PROJECT_RULES_QUERY,
            min_confidence=_settings.confidence_threshold,
            token_budget=PROJECT_RULES_TOKEN_BUDGET,
        )
        text = format_project_rules(result)
        block = build_project_rules_block(text)
        _project_rules_cache = block
        return block
    except (ValueError, WpmError, RuntimeError):
        return ""


@mcp.resource(
    "wpm://memory-rules",
    name="Memory usage rules",
    description=(
        "The memory usage rules: golden rules + standing policies. Same "
        "content as the server instructions — the full per-tool detail lives "
        "in each tool description; re-read it there at the moment of "
        "the decision."
    ),
    mime_type="text/markdown",
)
def memory_rules() -> str:
    return _memory_usage_rules


@mcp.resource(
    "wpm://verification-commands",
    name="Verification command patterns",
    description=(
        "The command patterns that count as strong proof (execution_verified) "
        "for record_execution: their success means something was verified. "
        "Check this list before deciding whether a command result is evidence."
    ),
    mime_type="text/markdown",
)
def verification_commands() -> str:
    lines = [
        "Commands whose successful execution counts as strong proof "
        "(execution_verified) for record_execution:",
    ]
    lines += [f"- {p}" for p in VERIFICATION_COMMAND_PATTERNS]
    lines.append("")
    lines.append(
        "Do NOT use record_execution for trivial commands (ls, cat, echo, "
        "grep, git status/diff): exit 0 on those proves nothing."
    )
    return "\n".join(lines)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

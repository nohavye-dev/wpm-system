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
    build_memory_usage_rules,
    PROJECT_RULES_QUERY,
    PROJECT_RULES_TOKEN_BUDGET,
    VERIFICATION_COMMAND_PATTERNS,
    build_project_rules_block,
    compile_verification_patterns,
    format_project_rules,
    looks_like_verification_command,
)
from wpm_mcp_server.embeddings import get_provider, resolve_model_name
from wpm_mcp_server.repository import WpmError, Repository
from wpm_mcp_server.settings import load_settings, resolve_response_language
from wpm_mcp_server.prompt_entities import PromptTask

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
    PromptTask("Memory deduplication reminder")
    .add_instruction(
        "Potential contradictions were found: compare the candidate contents and prefer validating an existing near-duplicate with validate_entry instead of creating a new entry.",
    )
    .to_string()
)

_REMINDER_MEMORY_FIRST = (
    PromptTask("Memory first reminder")
    .add_instruction(
        "MEMORY FIRST: call query_context on this topic before storing a new entry to check for existing or near-duplicate knowledge.",
    )
    .to_string()
)

_REMINDER_VALIDATE = (
    PromptTask("Memory validation reminder")
    .add_instruction(
        "This entry is currently unvalidated: call validate_entry with external, checkable evidence once the entry has been independently confirmed.",
    )
    .add_constraint(
        "Do not use agent reasoning alone as validation evidence.",
    )
    .to_string()
)

_REMINDER_CONFLICTS = (
    PromptTask("Memory conflict reminder")
    .add_instruction(
        "Conflicts were found: inspect them before relying on a direct_match.",
        "If the evidence remains contested, explicitly flag the conflict instead of presenting the fact as settled.",
    )
    .to_string()
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
        embedder = get_provider()
        _repo = Repository(
            conn=conn,
            embedder=embedder,
            settings=_settings.domain,
            model_name=resolve_model_name(),
        )
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

_STORE_ENTRY_PROMPT = (
    PromptTask("store_entry")
    .add_instruction(
        "Store exactly one durable memory entry, written in its native language as it emerged (e.g. French, keeping technical EN/FR code-switching verbatim — function names, technical terms).",
        "type: doc = explanatory project content; archi_decision = structural choice (observed or decided); convention = consistent naming/style/process rule; insight = discovered understanding durable for weeks (not a decision); bug_pattern = known issue and its cause, supported by proof; execution_result = use record_execution instead.",
        "source: official_doc = cited from an official project document; observed_code = directly observed in source code; tool_execution = confirmed by running a command or tool; agent_inference = deduction without direct external proof.",
        "Only store facts expected to remain true and useful for weeks; content must be factual, concise, self-contained, and understandable without the surrounding conversation.",
        "Immediately before calling store_entry, call query_context on the same topic.",
        "If query_context reveals a near-duplicate entry, call validate_entry on the existing entry instead of creating a duplicate when the current evidence confirms it.",
        "Every newly stored entry starts unvalidated; once independently confirmed, call validate_entry with real, external, checkable evidence.",
    )
    .add_constraint(
        "Do not store temporary observations, transient task state, speculative assumptions, or conversational context.",
        "Do not validate or increase an entry's confidence using agent reasoning alone.",
    )
    .to_string()
)

_QUERY_CONTEXT_PROMPT = (
    PromptTask("query_context")
    .add_instruction(
        "Retrieve relevant project memory via hybrid retrieval (vector similarity, confidence weighting, graph centrality, 1-hop expansion).",
        "Call query_context before reading a file, running grep, or searching the codebase on the relevant topic, and at the start of every substantive answer.",
        "Write the query in the same language as the memory it targets — the embedding model is multilingual, so queries match best when they share the language of the stored content.",
        "Use direct_matches as the primary source of relevant memory; always inspect conflicts before relying on any direct_match.",
        "Use related_context for associative recall from linked entries, but treat it as lower-confidence context, not a strong direct_match.",
        "Treat an entry with an active contradicts relationship as potentially unreliable until resolved.",
        "Use min_confidence to exclude entries below the required threshold, and token_budget to control the amount of context returned.",
    )
    .add_constraint(
        "Do not assume that the absence of a result means the information does not exist in the project.",
        "Do not translate a native-language query into English: the multilingual model matches best in the original language.",
    )
    .to_string()
)

_VALIDATE_ENTRY_PROMPT = (
    PromptTask("validate_entry")
    .add_instruction(
        "Record external, checkable evidence that a memory entry has been confirmed.",
        "evidence_type: execution_verified = a test/build/command/tool execution produced the expected result (strongest); cross_reference = independently confirmed by another source; reuse_without_failure = reused successfully, weak evidence subject to the confidence cap; agent_reasoning = reasoning without external proof, recorded for traceability but MUST NOT increase confidence.",
        "Set evidence_ref to the concrete source supporting the validation (test log, file path, command output, or another entry_id).",
        "Use session_id to deduplicate repeated validation of the same entry within the same session.",
        "Before validating, ensure the evidence actually supports the specific claim stored in the entry.",
    )
    .add_constraint(
        "Do not claim an entry is validated when the supplied evidence does not directly support its content.",
        "Do not use vague or unverifiable evidence_ref when a concrete source is available.",
        "Do not treat reuse_without_failure as equivalent to execution_verified or cross_reference.",
    )
    .to_string()
)

_CONTRADICT_ENTRY_PROMPT = (
    PromptTask("contradict_entry")
    .add_instruction(
        "Record that entry_id is contradicted by conflicting_entry_id, using the same evidence_type rules as validate_entry.",
        "Use evidence_ref to identify the concrete evidence supporting the contradiction (test log, file path, command output, or another entry_id).",
        "Lower entry_id's validation_score (a stronger reduction than the corresponding confirmation increase) and create a visible 'contradicts' link between the two entries.",
        "Preserve both entries so future query_context calls surface the contradiction and no historical or contextual information is lost.",
    )
    .add_constraint(
        "Never delete or hide entry_id or conflicting_entry_id.",
        "Do not create a contradiction based solely on agent reasoning, or without evidence supporting the conflict.",
        "Do not treat a contradiction as proof that either entry is automatically correct.",
    )
    .to_string()
)

_LINK_ENTRIES_PROMPT = (
    PromptTask("link_entries")
    .add_instruction(
        "Create or update an explicit relationship between two memory entries.",
        "relation_type: related = meaningfully related; contradicts = conflicting information; depends_on = source depends on target; refines = source adds precision, detail, or clarification to target.",
        "Preserve the direction of directional relationships (depends_on, refines).",
        "Use explicit links only for relationships semantic similarity would not reliably discover (e.g. a dependency between an archi_decision and a convention); implicit 'related' links are created automatically by store_entry.",
        "Use weight for relationship strength (default 1.0); update an existing relationship instead of duplicating it.",
    )
    .add_constraint(
        "Do not create a relationship when there is no meaningful semantic or structural connection between the entries.",
        "Do not use this tool to replace, merge, delete, or modify the content of either entry.",
        "Do not choose a relation_type merely because it is convenient; pick the one that accurately describes the relationship.",
    )
    .to_string()
)

_RECORD_EXECUTION_PROMPT = (
    PromptTask("record_execution")
    .add_instruction(
        "Capture the result of a verification command as durable memory.",
        "Store the result as an execution_result entry with source=tool_execution; when succeeded, also validate it as execution_verified in the same operation.",
        "Call record_execution immediately after running a qualifying verification command (e.g. pytest, npm test, cargo build; see the wpm://verification-commands resource for the full list).",
        "Use succeeded to record the outcome; a failed command is preserved as evidence without being validated.",
        "Use the current session_id for every record.",
    )
    .add_constraint(
        "Do not use this tool for trivial or inspection commands (ls, cat, echo, grep, git status/diff) — exit 0 on those proves nothing.",
        "Do not claim execution_verified unless the command actually ran and succeeded.",
        "Do not use agent reasoning as a substitute for actually running the command.",
        "Do not use a fabricated, stale, or unrelated session_id.",
    )
    .to_string()
)

_PIN_ENTRY_PROMPT = (
    PromptTask("pin_entry")
    .add_instruction(
        "Pin a memory entry so its confidence never decays; reserve for durable project knowledge that should stay authoritative and stable.",
        "Pin when the entry is a fundamental architecture decision, an established convention acting as policy, or knowledge independently validated repeatedly across sessions.",
        "Before pinning, verify the content is still valid and has no active contradiction; pinning is reversible via restore_entry.",
    )
    .add_constraint(
        "Do not pin recent or insufficiently validated insights, temporary bug patterns, or entries with active contradictions.",
        "Do not pin merely because an entry is frequently retrieved or important to the current task, nor solely to prevent confidence decay.",
        "Do not use pinning as a substitute for validation, or pin based solely on agent reasoning.",
    )
    .to_string()
)

_DEPRECATE_ENTRY_PROMPT = (
    PromptTask("deprecate_entry")
    .add_instruction(
        "Mark a memory entry as deprecated so it is excluded from future query_context results.",
        "Deprecate only with sufficient external evidence: the entry is conclusively contradicted (with the newer entry independently confirmed), describes an element that no longer exists, or is a bug pattern conclusively fixed.",
        "Prefer caution: leave an uncertain entry active and record a contradiction or validation instead; deprecation is reversible via restore_entry.",
    )
    .add_constraint(
        "Do not deprecate merely because an entry is old, currently unused, superseded by a newer entry, or may be incorrect.",
        "Do not deprecate based solely on agent reasoning, or with an unresolved contradiction.",
        "Do not use deprecation as a replacement for contradict_entry, or to hide uncertainty.",
    )
    .to_string()
)

_RESTORE_ENTRY_PROMPT = (
    PromptTask("restore_entry")
    .add_instruction(
        "Restore a pinned or deprecated memory entry to active status, preserving its existing history and evidence rather than creating a replacement.",
        "Restore a deprecated entry when the deprecation was premature or no longer justified (verify the original reason is no longer valid); restore a pinned entry when it is no longer stable or authoritative enough to stay pinned.",
        "After restoring, treat the entry's validity as normal and re-evaluate it through validation and contradiction mechanisms.",
    )
    .add_constraint(
        "Do not restore merely because an entry may be useful, or simply to undo a previous operation without reassessing its validity.",
        "Do not restore based solely on agent reasoning, and do not assume restoration makes the content validated or correct.",
    )
    .to_string()
)

_LIST_ENTRIES_PROMPT = (
    PromptTask("list_entries")
    .add_instruction(
        "List memory entries with their current confidence, sorted by confidence descending, with pagination and optional filters.",
        "By default return only active and pinned entries; set status='deprecated' to include deprecated ones.",
        "type filter accepts: doc, archi_decision, insight, convention, bug_pattern, execution_result; status filter accepts: active, pinned, deprecated.",
        "Use min_confidence / max_confidence to bound the confidence range, limit (default 50, max 200) for page size, and offset to page; preserve filters across pages.",
        "Use the returned total to detect additional pages.",
        "Use list_entries to inspect, enumerate, audit, or paginate through memory — not to retrieve entries semantically related to a topic (use query_context).",
    )
    .add_constraint(
        "Do not infer that a high confidence score means an entry is correct; confidence reflects validation state, and ordering is by confidence, not relevance.",
    )
    .to_string()
)

@mcp.tool(
    description=_STORE_ENTRY_PROMPT
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
    description=_QUERY_CONTEXT_PROMPT
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
    description=_VALIDATE_ENTRY_PROMPT
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
    description=_CONTRADICT_ENTRY_PROMPT
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
    description=_LINK_ENTRIES_PROMPT
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
    description=_RECORD_EXECUTION_PROMPT
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
    description=_PIN_ENTRY_PROMPT
)
async def pin_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().pin_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=_DEPRECATE_ENTRY_PROMPT
)
async def deprecate_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().deprecate_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=_RESTORE_ENTRY_PROMPT
)
async def restore_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().restore_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=_LIST_ENTRIES_PROMPT
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
        "memory, or when you suspect stale/contradicted entries."
    )
)
def get_memory_stats() -> dict:
    try:
        return get_repo().get_stats()
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


# --- resources --------------------------------------------------------------

_PROJECT_RULES_PROMPT_RESOURCE = (
    PromptTask("project_rules")
    .add_instruction(
        "High-confidence project conventions and architecture decisions derived from persistent memory.",
        "Read at session start; re-read after memory changes when conventions or architecture decisions may be affected.",
        "Treat rules as derived knowledge, not immutable facts — verify against current evidence when they conflict with the project state.",
    )
    .to_string()
)

_MEMORY_RULES_PROMPT_RESOURCE = (
    PromptTask("memory_rules")
    .add_instruction(
        "The complete memory usage rules (Golden Rules + standing policies).",
        "Re-read when the rules have been diluted by context growth or compaction.",
        "For tool-specific operational details, consult the relevant tool description at the moment of decision.",
    )
    .to_string()
)

_VERIFICATION_COMMANDS_PROMPT_RESOURCE = (
    PromptTask("verification_commands")
    .add_instruction(
        "The configured command patterns that qualify as strong execution_verified evidence for record_execution.",
        "Consult before recording a command result as verification evidence; only matching patterns qualify.",
    )
    .to_string()
)

@mcp.resource(
    "wpm://project-rules",
    name="Project rules and conventions",
    description=_PROJECT_RULES_PROMPT_RESOURCE,
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
    description=_MEMORY_RULES_PROMPT_RESOURCE,
    mime_type="text/markdown",
)
def memory_rules() -> str:
    return _memory_usage_rules


@mcp.resource(
    "wpm://verification-commands",
    name="Verification command patterns",
    description=_VERIFICATION_COMMANDS_PROMPT_RESOURCE,
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

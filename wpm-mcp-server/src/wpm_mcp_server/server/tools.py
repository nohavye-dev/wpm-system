"""MCP tool handlers: thin transport wrappers over the Repository.

Each handler delegates to the repository, assembles any reminder text from
server.prompts, and normalizes expected errors into {"error": True, ...}
payloads. Mutations additionally trigger the project-rules cache
invalidation / resource-update notification via state.on_memory_mutated.
"""

from typing import Literal

from mcp.server.fastmcp.server import Context

from wpm_mcp_server.core.errors import WpmError
from wpm_mcp_server.prompts import looks_like_verification_command
from wpm_mcp_server.server import prompts, state
from wpm_mcp_server.server.state import mcp

EntryType = Literal[
    "doc", "archi_decision", "insight", "convention",
    "bug_pattern", "execution_result",
]
EntrySource = Literal[
    "official_doc", "observed_code", "tool_execution", "agent_inference",
]


@mcp.tool(
    description=prompts.STORE_ENTRY_PROMPT
)
async def store_entry(ctx: Context, type: EntryType, content: str, source: EntrySource) -> dict:
    try:
        result = state.get_repo().store_entry(
            type_=type, content=content, source=source, session_id=state.SESSION_ID
        )
        reminders = []
        if result.get("potential_contradictions"):
            reminders.append(prompts.REMINDER_DEDUP)
        elif not state.queried_since_last_store():
            reminders.append(prompts.REMINDER_MEMORY_FIRST)
        reminders.append(prompts.REMINDER_VALIDATE)
        result["reminder"] = " ".join(reminders)
        state.reset_queried_flag()
        await state.on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        if isinstance(exc, ValueError):
            return {"error": True, "message": f"invalid type: {exc}"}
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.QUERY_CONTEXT_PROMPT
)
def query_context(query: str, min_confidence: float = 0.0, token_budget: int = 2000) -> dict:
    try:
        result = state.get_repo().query_context(
            query=query,
            min_confidence=min_confidence,
            token_budget=token_budget,
            session_id=state.SESSION_ID,
        )
        state.mark_context_queried()
        reminders = []
        if result.get("related_context"):
            reminders.append(prompts.REMINDER_RELATED_CONTEXT)
        if result.get("conflicts"):
            reminders.append(prompts.REMINDER_CONFLICTS)
        if reminders:
            result["reminder"] = " ".join(reminders)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.VALIDATE_ENTRY_PROMPT
)
async def validate_entry(
    ctx: Context, entry_id: str, evidence_type: str, evidence_ref: str, session_id: str
) -> dict:
    try:
        result = state.get_repo().validate_entry(
            entry_id=entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
            session_id=session_id,
        )
        await state.on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.CONTRADICT_ENTRY_PROMPT
)
async def contradict_entry(
    ctx: Context, entry_id: str, conflicting_entry_id: str, evidence_type: str, evidence_ref: str
) -> dict:
    try:
        result = state.get_repo().contradict_entry(
            entry_id=entry_id,
            conflicting_entry_id=conflicting_entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
        )
        await state.on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.LINK_ENTRIES_PROMPT
)
async def link_entries(
    ctx: Context, source_id: str, target_id: str, relation_type: str, weight: float = 1.0
) -> dict:
    try:
        result = state.get_repo().link_entries(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
        )
        await state.on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.RECORD_EXECUTION_PROMPT
)
async def record_execution(ctx: Context, command: str, succeeded: bool, session_id: str) -> dict:
    try:
        if not looks_like_verification_command(command, state.VERIFICATION_PATTERNS):
            return {
                "error": True,
                "message": (
                    "command does not match a verification pattern; if it is "
                    "still meaningful evidence, use store_entry + validate_entry "
                    "manually instead"
                ),
            }
        repo = state.get_repo()
        content = "\n".join(
            [
                f"Command executed: {command}",
                f"Result: {'success' if succeeded else 'failure'}",
                f"Directory: {state.CONFIG_DIR}",
            ]
        )
        store_result = repo.store_entry(
            type_="execution_result", content=content, source="tool_execution", session_id=state.SESSION_ID
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
        await state.on_memory_mutated(ctx)
        return {
            "entry_id": entry_id,
            "type": "execution_result",
            "stored": True,
            "validation": validation,
        }
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.PIN_ENTRY_PROMPT
)
async def pin_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = state.get_repo().pin_entry(entry_id=entry_id)
        await state.on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.DEPRECATE_ENTRY_PROMPT
)
async def deprecate_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = state.get_repo().deprecate_entry(entry_id=entry_id)
        await state.on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.RESTORE_ENTRY_PROMPT
)
async def restore_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = state.get_repo().restore_entry(entry_id=entry_id)
        await state.on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.LIST_ENTRIES_PROMPT
)
def list_entries(type: str | None = None, status: str | None = None,
                 min_confidence: float | None = None, max_confidence: float | None = None,
                 limit: int = 50, offset: int = 0) -> dict:
    try:
        return state.get_repo().list_entries(
            type=type, status=status,
            min_confidence=min_confidence, max_confidence=max_confidence,
            limit=limit, offset=offset,
        )
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.GET_MEMORY_STATS_PROMPT
)
def get_memory_stats() -> dict:
    try:
        return state.get_repo().get_stats()
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.GET_USER_PROMPT
)
def get_user() -> dict:
    try:
        profile = state.get_users_repo().get_current_user()
        if profile is None:
            return {"current": False, "message": "no current user profile"}
        return {"current": True, "profile": profile}
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


def _pointer_gate(repo) -> dict | None:
    """Shared pre-check: a current user must exist.

    Returns an error payload when the gate fails, None when the call may
    proceed. Guards live at call time (not registration time) so CLI
    toggles take effect on the very next turn without a server restart.
    """
    from wpm_mcp_server.storage.users import NO_CURRENT_USER_MESSAGE

    if repo.get_current_name() is None:
        return {"error": True, "message": NO_CURRENT_USER_MESSAGE}
    return None


def _inferred_capture_gate(repo) -> dict | None:
    """Extra gate for inferred recordings only.

    Declared statements (human preferences) are never blocked by the
    capture flag nor by the session budget.
    """
    if not repo.observations_enabled():
        return {
            "error": True,
            "disabled": True,
            "message": (
                "user observation capture is disabled — "
                "run 'wpm user-observations on'"
            ),
        }
    if not state.observation_budget_available():
        return {
            "error": True,
            "message": (
                f"observation budget exhausted for this session "
                f"(limit {state.OBSERVATION_SESSION_LIMIT}) — stop "
                "recording for now"
            ),
        }
    return None


@mcp.tool(
    description=prompts.RECORD_USER_OBSERVATION_PROMPT
)
def record_user_observation(
    content: str,
    source: str = "inferred",
    category: str | None = None,
    reinforce_id: int | None = None,
    replaces_id: int | None = None,
) -> dict:
    try:
        repo = state.get_users_repo()
        gated = _pointer_gate(repo)
        if gated is not None:
            return gated
        if source == "inferred":
            gated = _inferred_capture_gate(repo)
            if gated is not None:
                return gated
        result = repo.record_user_observation(
            content,
            source=source,
            category=category,
            reinforce_id=reinforce_id,
            replaces_id=replaces_id,
        )
        if source == "inferred":
            state.count_observation()
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=prompts.GET_USER_OBSERVATIONS_PROMPT
)
def get_user_observations() -> dict:
    """Listing is pointer-gated only: it stays available even when inferred
    capture is off, so declared statements can still be deduplicated and
    superseded."""
    try:
        repo = state.get_users_repo()
        gated = _pointer_gate(repo)
        if gated is not None:
            return gated
        observations = repo.get_user_observations()
        return {"observations": observations, "total": len(observations)}
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}

"""MCP resource handlers: re-readable agent-facing documents.

- wpm://project-rules: recomputed from memory on read and cached until the
  next mutation (invalidated by state.on_memory_mutated).
- wpm://memory-rules: the initialize.instructions text, re-readable.
- wpm://verification-commands: the patterns that qualify as strong
  execution_verified evidence for record_execution.
"""

from wpm_mcp_server.core.errors import WpmError
from wpm_mcp_server.prompts import (
    PROJECT_RULES_QUERY,
    PROJECT_RULES_TOKEN_BUDGET,
    VERIFICATION_COMMAND_PATTERNS,
    build_project_rules_block,
    format_project_rules,
)
from wpm_mcp_server.server import prompts, state
from wpm_mcp_server.server.state import mcp


@mcp.resource(
    "wpm://project-rules",
    name="Project rules and conventions",
    description=prompts.PROJECT_RULES_PROMPT_RESOURCE,
    mime_type="text/markdown",
)
def project_rules() -> str:
    cached = state.get_cached_project_rules()
    if cached is not None:
        return cached
    if state.DB_PATH is None:
        return ""
    try:
        result = state.get_repo().query_context(
            query=PROJECT_RULES_QUERY,
            min_confidence=state.SETTINGS.confidence_threshold,
            token_budget=PROJECT_RULES_TOKEN_BUDGET,
        )
        text = format_project_rules(result)
        block = build_project_rules_block(text)
        state.set_cached_project_rules(block)
        return block
    except (ValueError, WpmError, RuntimeError):
        return ""


@mcp.resource(
    "wpm://memory-rules",
    name="Memory usage rules",
    description=prompts.MEMORY_RULES_PROMPT_RESOURCE,
    mime_type="text/markdown",
)
def memory_rules() -> str:
    return state.SERVER_INSTRUCTIONS


@mcp.resource(
    "wpm://verification-commands",
    name="Verification command patterns",
    description=prompts.VERIFICATION_COMMANDS_PROMPT_RESOURCE,
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

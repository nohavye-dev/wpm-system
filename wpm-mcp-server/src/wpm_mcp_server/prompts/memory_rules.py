"""Memory usage rules injected through initialize.instructions.

A reduced set — 3 golden rules + standing policies — with the full rule
detail living in tool descriptions. The response-language clause is
appended to the English base template (these are agent instructions).
Rules are pushed into context every turn by the plugin.
"""

from __future__ import annotations

from wpm_mcp_server.prompts.entities import PromptContext, PromptTask


def build_memory_usage_rules(
    response_language: str | None = None,
) -> str:
    """Render the usage rules, appending the language hint when non-empty."""
    return _build_memory_usage_rules(_response_clause(response_language))


def _build_memory_usage_rules(response_clause: str) -> str:
    """Render the usage rules, appending the language hint when non-empty."""
    ctx = PromptContext(tag="wpm-memory-rules").add_purpose(
        "Maintain your own persistent weighted memory (via the wpm MCP server) to recover, persist, and validate durable knowledge."
    )
    ctx.add_instruction(
        "These rules apply to every turn and every tool-enabled workflow; the Golden Rules are mandatory and have priority over all other rules.",
    )
    if response_clause:
        ctx.add_instruction(response_clause)
    startup_steps = [
        "If no <wpm-memory-recall> was pushed this turn or it is insufficient, "
        "call query_context for the current topic before reading any project file.",
        "Store each durable fact as soon as it emerges.",
        "Validate a stored fact with external evidence once independently confirmed.",
    ]
    return (
        ctx.add_task(
            PromptTask("Golden Rules")
            .add_instruction(
                "MEMORY FIRST: If no <wpm-memory-recall> was pushed this turn or it is insufficient, "
                "call query_context with a reformulated query before reading a file, searching the codebase, or starting a substantive answer.",
                "WRITE AS YOU GO: Immediately call store_entry whenever a durable fact emerges (decisions, conventions, confirmed test results, bug patterns, other knowledge likely to remain useful) — do not defer writes until the end of a task.",
                "PROOF BEFORE VALIDATION: Obtain external, checkable evidence (test output, logs, file paths, source code, documentation, or another relevant entry) before validate_entry or contradict_entry.",
            )
            .add_constraint(
                "Do not artificially increase the confidence or score of a memory entry.",
            )
        )
        .add_task(
            PromptTask("Startup sequence")
            .add_instruction(
                "At session start, in order:",
                *(f"{number}. {step}" for number, step in enumerate(startup_steps, 1)),
            )
            .add_constraint(
                "Do not reorder these startup steps unless a tool is unavailable or the host prevents the operation.",
            )
        )
        .add_task(
            PromptTask("Standing policies").add_instruction(
                "Prioritize reliability over completeness: prefer an underpopulated memory to one polluted with incorrect, duplicated, or artificially strengthened information.",
                "Memory is your own state, not the project's: writing it never modifies the project. Use memory write tools whenever a durable fact emerges; if the host blocks a write, retry immediately.",
                "When a <current-user> block is present in context, treat it as authoritative for who you are talking to and apply its preferences (language, stated preferences); re-consult get_user after compaction or when in doubt.",
                "When the user states a preference (source=declared) or you notice a pattern about them — habit, workflow, knowledge, context, communication style, or personal trait (source=inferred) — record it with record_user_observation, checking get_user_observations first to reinforce existing patterns or supersede contradicted preferences. Record silently; do not announce it.",
                "For entry types, source selection, deduplication, evidence hierarchy, query-result handling, pinning, deprecation, linking, native-language content, end-of-session persistence, and execution recording, consult the relevant tool description at the moment of decision.",
            )
        )
        .to_string()
    )


def _response_clause(response_language: str | None) -> str:
    """Rule-3 output-language clause, injected into English prose."""
    if response_language:
        return (
            "your conversational responses, summaries, and reports MUST be "
            f"written in {response_language}, regardless of the language used "
            "in memory or in these instructions"
        )
    return (
        "your conversational responses, summaries, and reports MUST use the "
        "same language as the user asking questions — do not switch to English "
        "for output"
    )


MEMORY_USAGE_RULES = build_memory_usage_rules()

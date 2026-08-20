"""Behavioral content and pure helpers for the MCP layer.

Holds the usage rules injected through initialize.instructions (a reduced
set — 3 golden rules + standing policies — with the full rule detail living
in tool descriptions), the verification-command patterns powering
record_execution, and the project-rules formatting used by the
wpm://project-rules resource.

Kept in English on purpose: these are agent instructions. Stored memory
content is written in its native language (the embedding model is
multilingual), so this module must stay free of import side effects so it
can be unit-tested without booting the MCP server.
"""

from __future__ import annotations

import re
from wpm_mcp_server.prompt_entities import PromptContext, PromptTask

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
    return (
        ctx.add_task(
            PromptTask("Golden Rules")
            .add_instruction(
                "MEMORY FIRST: Call query_context on the relevant topic before reading a file, searching the codebase, or starting a substantive answer.",
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
                "1. Read the wpm://project-rules resource.",
                "2. Call query_context for the current topic before reading any project file.",
                "3. Store each durable fact as soon as it emerges.",
                "4. Validate a stored fact with external evidence once independently confirmed.",
            )
            .add_constraint(
                "Do not reorder these startup steps unless a tool is unavailable or the host prevents the operation.",
            )
        )
        .add_task(
            PromptTask("Standing policies")
            .add_instruction(
                "Prioritize reliability over completeness: prefer an underpopulated memory to one polluted with incorrect, duplicated, or artificially strengthened information.",
                "Memory is your own state, not the project's: writing it never modifies the project, so memory tools are allowed in every mode — plan mode's read-only rule only protects project files. Use memory write tools whenever a durable fact emerges; if the host blocks a write, retry immediately or switch modes.",
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


def build_memory_usage_rules(response_language: str | None = None) -> str:
    """Render the usage rules with the configured output-language clause.

    The base template stays English (these are agent instructions); the
    response-language clause is always appended — fixed when a language is
    configured, otherwise the user-language/do-not-switch clause.
    """
    return _build_memory_usage_rules(_response_clause(response_language))


MEMORY_USAGE_RULES = build_memory_usage_rules()


PROJECT_RULES_QUERY = (
    "What are the project rules and conventions: commit message format, "
    "dependency and package management, coding style, testing strategy, "
    "architecture decisions and documentation standards?"
)

PROJECT_RULES_TOKEN_BUDGET = 800

MAX_PROJECT_RULES_CHARS = 6000

VERIFICATION_COMMAND_PATTERNS: list[str] = [
    r"\bpytest\b",
    r"\bnpm\s+(run\s+)?test\b",
    r"\bnpm\s+run\s+build\b",
    r"\bpnpm\s+(run\s+)?test\b",
    r"\bpnpm\s+(run\s+)?build\b",
    r"\byarn\s+test\b",
    r"\byarn\s+build\b",
    r"\bbun\s+(run\s+)?test\b",
    r"\bbun\s+run\s+build\b",
    r"\bdotnet\s+test\b",
    r"\bdotnet\s+build\b",
    r"\bcargo\s+test\b",
    r"\bcargo\s+build\b",
    r"\bgo\s+test\b",
    r"\bgo\s+build\b",
    r"\bmake\s+test\b",
    r"\bmix\s+test\b",
    r"\bflutter\s+test\b",
    r"\bmvn\s+test\b",
    r"\bgradle\s+test\b",
    r"\bsbt\s+test\b",
    r"\bvitest\b",
    r"\bjest\b",
    r"\bdeno\s+test\b",
    r"\btox\b",
    r"\bphpunit\b",
    r"\brake\s+test\b",
    r"\bcompileall\b",
    r"\bpy_compile\b",
    r"\bbash\s+-n\b",
    r"\bshellcheck\b",
    r"\btsc\s+--noEmit\b",
    r"\bruff\s+check\b",
    r"\bmypy\b",
    r"\beslint\b",
]


def compile_verification_patterns(
    extra: list[str],
) -> tuple[list[re.Pattern[str]], list[str]]:
    """Compile the built-in plus the config-provided verification patterns.

    Returns (valid_patterns, invalid_sources): invalid custom regexes are
    skipped rather than crashing the server — they are reported to the
    caller so it can surface a warning.
    """
    patterns: list[re.Pattern[str]] = []
    invalid: list[str] = []
    for source in VERIFICATION_COMMAND_PATTERNS:
        try:
            patterns.append(re.compile(source))
        except re.error:  # pragma: no cover - built-ins are static
            invalid.append(source)
    for source in extra:
        try:
            patterns.append(re.compile(source))
        except re.error:
            invalid.append(source)
    return patterns, invalid


def looks_like_verification_command(command: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(command) for p in patterns)


def format_project_rules(result: dict) -> str:
    """Render query_context results as a structured Markdown project-rules block.

    Direct matches are rendered as project rules and related context as
    supporting context. Empty memory yields an empty block.
    """
    lines: list[str] = []

    direct_matches = result.get("direct_matches", [])
    related_context = result.get("related_context", [])

    if direct_matches:
        lines.extend([
            "## Rules",
            "",
        ])

        for entry in direct_matches:
            content = entry.get("content", "").strip()
            if content:
                lines.append(
                    f"  - [{entry.get('type')}] {content} "
                    f"(confidence {entry.get('confidence')})"
                )

    if related_context:
        if lines:
            lines.append("")

        lines.extend([
            "## Supporting context",
            "",
        ])

        for entry in related_context:
            content = entry.get("content", "").strip()
            if content:
                lines.append(
                    f"  - [{entry.get('type')}] {content} "
                    f"(supporting, confidence {entry.get('confidence')})"
                )

    if not lines:
        return ""

    text = "\n".join(lines)
    return text[:MAX_PROJECT_RULES_CHARS]


def build_project_rules_block(text: str) -> str:
    if not text or not text.strip():
        return ""

    return f"<project-rules>\n{text}\n</project-rules>"

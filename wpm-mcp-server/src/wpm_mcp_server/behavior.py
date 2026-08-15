"""Behavioral content and pure helpers for the MCP layer.

Holds the usage rules injected through initialize.instructions (a reduced
set — 3 golden rules + standing policies — with the full rule detail living
in tool/prompt descriptions), the verification-command patterns powering
record_execution, and the project-rules formatting used by the
wpm://project-rules resource.

Kept in English on purpose: stored content must be English (embedding
consistency), and this module must stay free of import side effects so it
can be unit-tested without booting the MCP server.
"""

from __future__ import annotations

import re

_MEMORY_USAGE_RULES_TEMPLATE = """<wpm-memory-rules>
You have access to the project's persistent weighted memory via the wpm MCP
server (store_entry, query_context, validate_entry, contradict_entry,
link_entries, get_memory_stats, pin_entry, deprecate_entry, restore_entry,
list_entries, record_execution). Follow these rules every turn.

GOLDEN RULES — the three non-negotiable principles, in priority order:

1. MEMORY FIRST. WHEN you are about to read a file or search the codebase,
   DO call query_context on the topic BEFORE reading. The answer may already
   be in memory (e.g. a known bug pattern is recoverable via query_context
   instead of re-reading the code). WHEN you start any substantive answer,
   DO query the current topic before answering from reasoning alone.

2. WRITE AS YOU GO. WHEN a durable fact emerges — a decision taken, a
   convention identified, a test result, an understood bug pattern — DO call
   store_entry immediately. DO NOT defer persistence to the end of the task:
   unpersisted facts are silently lost at context compaction.

3. PROOF BEFORE VALIDATION. WHEN you validate_entry or contradict_entry, DO
   provide external, checkable evidence (a test log, a file path, another
   entry). NEVER use agent_reasoning to raise a score.

STARTUP SEQUENCE — at session start, in this order:

1. Read the wpm://project-rules resource to load the project's conventions.
2. Call query_context on the current topic before reading any file.
3. Store every durable fact as soon as it emerges (store_entry).
4. Validate each stored fact with external evidence (validate_entry) once it
   is confirmed.

STANDING POLICIES (apply across all tools, not tied to a single call):

1. RELIABILITY OVER COMPLETENESS. A wrong or artificially boosted entry is
   worse than a missing one. Prefer an underpopulated memory to a
   polluted one.

2. WRITE MEMORY ANYTIME. Memory write tools MUST be used whenever a
   durable fact emerges — in plan mode, build mode, or any other mode.
   Plan mode is NOT a reason to defer persistence. If the host blocks the
   write, retry immediately or switch to a build/agent mode.

Every other rule (type/source selection, dedup, evidence hierarchy,
reading query results, pin/deprecate, links, English-only content,
end-of-session persistence, recording executions) lives in the description
of the relevant tool or prompt — re-read it there at the moment of the
decision.

OUTPUT LANGUAGE. {response_clause}
</wpm-memory-rules>"""


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

    The base template stays English (stored content must be English); only
    the output-language clause varies. None = follow the user's language.
    """
    return _MEMORY_USAGE_RULES_TEMPLATE.format(
        response_clause=_response_clause(response_language)
    )


MEMORY_USAGE_RULES = build_memory_usage_rules()


def build_language_note(response_language: str | None) -> str:
    """Short suffix for tool descriptions so the output language is re-read
    at every tool-call decision. Empty when auto (rule 3 already covers it),
    so a fixed language does not add noise to the descriptions."""
    if not response_language:
        return ""
    return (
        f" Respond to the user in {response_language} — your conversational "
        f"responses, summaries and reports must be written in "
        f"{response_language}."
    )


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
    """Render a query_context result as a readable project-rules block.

    Direct matches first (highest confidence, exact hits); related context
    appended as associative recall. Empty memory yields an empty block.
    """
    lines: list[str] = []
    for entry in result.get("direct_matches", []):
        content = entry.get("content", "").strip()
        if content:
            lines.append(
                f"- [{entry.get('type')}] {content} "
                f"(confidence {entry.get('confidence')})"
            )
    for entry in result.get("related_context", []):
        content = entry.get("content", "").strip()
        if content:
            lines.append(
                f"- [{entry.get('type')}] {content} "
                f"(related, confidence {entry.get('confidence')})"
            )
    if not lines:
        return ""
    text = "\n".join(lines)
    return text[:MAX_PROJECT_RULES_CHARS]


def build_project_rules_block(text: str) -> str:
    if not text or not text.strip():
        return ""
    return f"<project-rules>\n{text}\n</project-rules>"

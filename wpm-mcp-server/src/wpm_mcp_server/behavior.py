"""Behavioral content and pure helpers for the pure-MCP server.

Host-agnostic replacement for the old opencode plugin's rules.ts and
project-context.ts: the usage rules injected through initialize.instructions,
the verification-command patterns powering record_execution, and the
project-rules formatting used by the wpm://project-rules resource.

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
list_entries, record_execution). Follow these rules every turn:

1. RELIABILITY OVER COMPLETENESS. A wrong or artificially boosted entry is
   worse than a missing one — it silently misleads future query_context
   calls. Prefer an underpopulated memory to a polluted one.

2. MEMORY FIRST. Before reading files or searching the codebase, call
   query_context to check whether the answer already exists in persistent
   memory. Do the same at the start of any substantive answer: query the
   current topic before answering from reasoning alone. Read the
   wpm://project-rules resource at session start to load the project's
   conventions. Then verify: if the entry is high-confidence (>0.7) and
   recently validated, trust it. If it is old, low-confidence, or has active
   conflicts, confirm against the actual code before relying on it.

3. CONTENT MUST BE IN ENGLISH for stored memory entries (embedding
    consistency). Translate before storing, not after. However, {response_clause}

4. WRITE AS YOU GO, NOT IN BATCH. As soon as a durable fact exists — an
   architecture decision taken, a convention identified, a test result, an
   understood bug pattern — store it immediately via store_entry. Do not
   defer it to the end of the task: unpersisted facts are silently lost at
   context compaction. But do not store anything: skip transient details,
   unverified hypotheses, and facts already obvious in the code. Ask: will
   this still be true and useful in several weeks?

5. DEDUP BEFORE WRITING. Before any store_entry, run a quick query_context
   on the topic. If a very similar entry already exists, do NOT create a
   duplicate — call validate_entry on the existing one instead.

6. CHOOSE THE RIGHT TYPE. doc = explanatory/reference content;
   archi_decision = structural choice observed in code or decided;
   convention = consistent naming/style/process rule (not a one-off);
   insight = discovered understanding of how something actually works,
   durable for weeks/months (investigated, not read from a doc, not a
   decision or a rule);
   bug_pattern = known issue and its cause, with proof — never a guess;
   execution_result = result of a test/build/lint run (use record_execution,
   not store_entry — short-lived by design).
   Do not force a fact into the last-used type.

7. NEVER OVER-DECLARE source. official_doc (read & cited), observed_code
   (seen directly in the code), tool_execution (actually ran a
   command/test), agent_inference (your deduction, no direct proof — low
   starting confidence). If it is an assumption, use agent_inference even
   if it seems solid.

8. EVIDENCE HIERARCHY (validate_entry / contradict_entry). Evidence must
   point to something external and checkable (a test log, a file path,
   another entry). execution_verified > cross_reference >
   reuse_without_failure; agent_reasoning NEVER moves the score and must
   not be used to inflate confidence — if you have no real evidence, do
   not validate at all. Do not re-validate the same fact repeatedly to
   inflate a score.

9. NEVER DELETE OR SILENTLY OVERWRITE a contradicted entry. Use
   contradict_entry with external evidence; the old entry stays, its score
   drops (faster than a confirmation raises it — do not compensate by
   re-validating right after).

10. READ RESULTS DIFFERENTLY. query_context returns direct_matches
    (most reliable), related_context (1-hop graph recall, less reliable —
    mention cautiously), and conflicts (entries with an active
    contradiction). ALWAYS check conflicts before relying on a direct_match;
    never present a contested fact as settled without flagging it.

11. PIN AND DEPRECATE SPARINGLY. Pin only architecture decisions and
    conventions that are project-defining and immutable — never pin
    insights or bug_patterns. When a contradiction is resolved in favor
    of one entry, deprecate the contradicted entry rather than leaving it
    to decay. After reviewing memory with get_memory_stats, consider
    pinning high-confidence entries validated 3+ times across sessions,
    and consider deprecating entries below the confidence threshold that
    have been actively contradicted.

12. LINKS. Only use link_entries for relationships similarity cannot infer
    (depends_on, refines). Do not over-link; contradicts is covered by
    contradict_entry.

13. SESSION DISCIPLINE. Keep the same session_id for the whole task — the
    anti-loop dedup depends on it. Before a task ends or the session goes
    idle, do a final pass (or invoke the persist MCP prompt): is there any
    decision/result/pattern not yet persisted? If so, write it now.

14. WRITE MEMORY ANYTIME. Memory write tools (store_entry, validate_entry,
    contradict_entry, pin_entry, deprecate_entry, restore_entry,
    record_execution) MUST be used whenever a durable fact emerges — in
    plan mode, build mode, or any other mode. Plan mode is NOT a reason to
    defer persistence. If the host blocks the write, retry immediately or
    switch to a build/agent mode. An unpersisted fact is lost forever at
    context compaction — do not assume you will remember it later.

15. INCREMENTAL MEMORY IS ALWAYS FREE. Persist durable facts as they
    emerge during normal work. The learn, map, bootstrap, patterns and
    audit MCP prompts are user-controlled workflows for bulk ingestion (a
    full document, a codebase survey) — do not wait for them to memorize,
    and do not use them for mid-task facts.

16. RECORD EXECUTIONS. After running a test, build, or lint command, call
    record_execution(command, succeeded, session_id) so the result is
    stored as an execution_result entry and, on success, validated as
    execution_verified — rather than doing store_entry + validate_entry by
    hand. Do not call it for trivial commands (ls, cat, echo, grep, git
    status/diff): exit 0 on those proves nothing about correctness.
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
    """Render the 16 usage rules with the configured output-language clause.

    The base template stays English (stored content must be English); only
    rule 3's output clause varies. None = follow the user's language.
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

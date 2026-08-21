"""Verification-command patterns powering record_execution.

A command whose execution matches one of these patterns counts as strong
execution_verified evidence; custom patterns from config are merged in by
compile_verification_patterns().
"""

from __future__ import annotations

import re


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

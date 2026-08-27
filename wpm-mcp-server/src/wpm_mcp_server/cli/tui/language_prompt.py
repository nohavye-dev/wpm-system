"""Language prompt with prompt_toolkit (Lot 2B-B)."""

from __future__ import annotations

import sys

from wpm_mcp_server.core.constants import SUPPORTED_LANGUAGES, match_languages


def prompt_language() -> str:
    """Interactive prefix autocomplete over SUPPORTED_LANGUAGES."""
    # Fallback for non-TTY / CI
    if not sys.stdin.isatty():
        print("Choose your language (English name, e.g. 'french'):")
        while True:
            try:
                value = input("> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nwpm: aborted")
                sys.exit(0)
            if value in SUPPORTED_LANGUAGES:
                return value
            if value:
                print(f"wpm: unknown language '{value}' — examples: {', '.join(SUPPORTED_LANGUAGES[:10])} ...")
        return value  # unreachable

    # Try prompt_toolkit, fallback to plain input if not installed
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.completion import WordCompleter
    except ImportError:
        return _fallback_plain()

    completer = WordCompleter(SUPPORTED_LANGUAGES, ignore_case=True, sentence=True)
    try:
        result = pt_prompt(
            "Choose your language: ",
            completer=completer,
            complete_while_typing=True,
        )
    except (EOFError, KeyboardInterrupt):
        print("\nwpm: aborted")
        sys.exit(0)
    value = result.strip().lower()
    if value in SUPPORTED_LANGUAGES:
        return value
    # Allow free-form but validate via match_languages
    matches = match_languages(value, limit=1)
    if matches and matches[0] == value:
        return value
    if value and value not in SUPPORTED_LANGUAGES:
        print(f"wpm: unknown language '{value}' — using as-is")
    return value or "english"


def _fallback_plain() -> str:
    print("Choose your language (English name, e.g. 'french'):")
    while True:
        try:
            value = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nwpm: aborted")
            sys.exit(0)
        if value in SUPPORTED_LANGUAGES:
            return value
        if value:
            print(f"wpm: unknown language '{value}' — examples: {', '.join(SUPPORTED_LANGUAGES[:10])} ...")

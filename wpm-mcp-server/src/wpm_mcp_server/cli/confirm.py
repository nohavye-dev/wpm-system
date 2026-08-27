"""Confirmation prompt helper (Lot 2B: deduplicate 4 clones)."""

from __future__ import annotations


def confirm(prompt: str, default: bool = False) -> bool:
    """Ask y/N, return True only on y/yes (default False = N)."""
    try:
        answer = input(prompt)
    except (EOFError, KeyboardInterrupt):
        answer = ""
    normalized = answer.strip().lower()
    if normalized in ("y", "yes"):
        return True
    if normalized == "" and default:
        return True
    return False

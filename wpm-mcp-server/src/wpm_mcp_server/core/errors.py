"""Domain-level exception types."""

from __future__ import annotations


class WpmError(Exception):
    """Raised for domain-level errors (e.g. missing entry, stale evidence)."""

"""Pure domain layer: enums, constants, errors, confidence scoring.

No I/O and no external service dependencies — everything here is safe to
unit-test in isolation.
"""

from wpm_mcp_server.core.constants import EMBEDDING_DIM
from wpm_mcp_server.core.enums import (
    EntryStatus,
    EntryType,
    EventType,
    EvidenceType,
    RelationType,
)
from wpm_mcp_server.core.errors import WpmError

__all__ = [
    "EMBEDDING_DIM",
    "EntryStatus",
    "EntryType",
    "EventType",
    "EvidenceType",
    "RelationType",
    "WpmError",
]

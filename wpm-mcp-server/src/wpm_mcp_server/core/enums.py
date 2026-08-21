"""Domain enums shared across the memory MCP server.

Tunable scoring/retrieval parameters used to live here as module-level
constants; they now live in config/settings.py (with JSON override support)
so they can be tuned without touching code. See DomainSettings there for
the values that used to be defined in this file.
"""

from __future__ import annotations

from enum import StrEnum


class EntryType(StrEnum):
    DOC = "doc"
    ARCHI_DECISION = "archi_decision"
    INSIGHT = "insight"
    CONVENTION = "convention"
    BUG_PATTERN = "bug_pattern"
    EXECUTION_RESULT = "execution_result"


class EvidenceType(StrEnum):
    EXECUTION_VERIFIED = "execution_verified"
    CROSS_REFERENCE = "cross_reference"
    REUSE_WITHOUT_FAILURE = "reuse_without_failure"
    AGENT_REASONING = "agent_reasoning"


class RelationType(StrEnum):
    RELATED = "related"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"
    REFINES = "refines"


class EventType(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    CONTRADICTED = "contradicted"
    REFERENCED = "referenced"
    PINNED = "pinned"
    DEPRECATED = "deprecated"
    RESTORED = "restored"


class EntryStatus(StrEnum):
    ACTIVE = "active"
    PINNED = "pinned"
    DEPRECATED = "deprecated"

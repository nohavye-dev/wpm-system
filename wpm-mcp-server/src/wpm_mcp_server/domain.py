"""Domain enums shared across the memory MCP server.

Tunable scoring/retrieval parameters used to live here as module-level
constants; they now live in settings.py (with JSON override support) so
they can be tuned without touching code. See settings.py's DomainSettings
for the values that used to be defined in this file.
"""

from __future__ import annotations

from enum import StrEnum


class EntryType(StrEnum):
    DOC = "doc"
    ARCHI_DECISION = "archi_decision"
    LEARNING = "learning"
    CONVENTION = "convention"
    BUG_PATTERN = "bug_pattern"


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


# Not exposed via JSON config: changing it requires re-embedding every
# existing entry (a stored vector's dimension can't change in place), so
# it's a deployment-time decision, not a runtime tuning knob.
EMBEDDING_DIM = 384

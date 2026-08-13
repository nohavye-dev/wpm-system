"""JSON configuration loading, layered over hardcoded defaults.

wpm.config.json at the project root is the primary place to configure
the server: where the database lives, the project-rules confidence
threshold, extra verification command patterns. The "domain" section
(scoring/retrieval tuning, spec sections 3-6) is deliberately separate
and optional — most users will never need to touch it; it's
advanced/expert configuration.

Config file location: WPM_CONFIG_PATH env var, or "wpm.config.json"
in the current working directory if unset. Environment variables
(WPM_DB_PATH etc.) still override the file when set, for quick local
overrides without editing the file — but the file is the primary,
documented way to configure a project.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from wpm_mcp_server.domain import EntryType, EvidenceType


# --- Section: domain (advanced) ------------------------------------------------
@dataclass
class ProvenanceSettings:
    base_confidence: dict[str, float] = field(
        default_factory=lambda: {
            "official_doc": 0.9,
            "observed_code": 0.75,
            "tool_execution": 0.7,
            "agent_inference": 0.35,
        }
    )
    default: float = 0.5


@dataclass
class DecaySettings:
    lambda_per_type: dict[str, float] = field(
        default_factory=lambda: {
            # Half-lives (time for confidence to halve), calibrated against
            # external anchors — see new_spec/calibration-heuristique.md.
            EntryType.ARCHI_DECISION.value: 0.00008,   # ~1 year
            EntryType.CONVENTION.value: 0.00016,       # ~6 months
            EntryType.DOC.value: 0.00021,              # ~4.5 months (indicative)
            EntryType.LEARNING.value: 0.004,           # ~7 days
            EntryType.BUG_PATTERN.value: 0.0016,       # ~18 days (measured)
        }
    )
    default_lambda: float = 0.001


@dataclass
class EvidenceSettings:
    confirm_weight: dict[str, float] = field(
        default_factory=lambda: {
            EvidenceType.EXECUTION_VERIFIED.value: 0.25,
            EvidenceType.CROSS_REFERENCE.value: 0.15,
            EvidenceType.REUSE_WITHOUT_FAILURE.value: 0.05,
            EvidenceType.AGENT_REASONING.value: 0.0,
        }
    )
    contradict_weight: dict[str, float] = field(
        default_factory=lambda: {
            EvidenceType.EXECUTION_VERIFIED.value: 0.4,
            EvidenceType.CROSS_REFERENCE.value: 0.25,
            EvidenceType.REUSE_WITHOUT_FAILURE.value: 0.1,
            EvidenceType.AGENT_REASONING.value: 0.0,
        }
    )


@dataclass
class ValidationSettings:
    score_min: float = 0.0
    score_max: float = 1.0
    dedup_window_seconds: int = 60 * 30


@dataclass
class RetrievalSettings:
    weight_similarity: float = 0.5
    weight_confidence: float = 0.35
    weight_centrality: float = 0.15
    min_similarity: float = 0.1


@dataclass
class ExpansionSettings:
    hop_decay: float = 0.5
    min_confidence: float = 0.3
    top_n_candidates: int = 20
    auto_link_similarity_threshold: float = 0.82
    contradiction_alert_threshold: float = 0.92


@dataclass
class DomainSettings:
    """Advanced scoring/retrieval tuning (spec sections 3-6). Optional —
    leave this section out of wpm.config.json entirely unless you
    specifically need to tune it."""

    provenance: ProvenanceSettings = field(default_factory=ProvenanceSettings)
    decay: DecaySettings = field(default_factory=DecaySettings)
    evidence: EvidenceSettings = field(default_factory=EvidenceSettings)
    validation: ValidationSettings = field(default_factory=ValidationSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    expansion: ExpansionSettings = field(default_factory=ExpansionSettings)


@dataclass
class Settings:
    # Basic, everyday settings — top level, not nested under a sub-section.
    db_path: str | None = None
    # Optional, default 0.5. Used by the wpm://project-rules resource as the
    # minimum confidence below which an entry is not injected into the
    # project-rules block recomputed at each session.
    confidence_threshold: float = 0.5
    # Optional, default [] (no additions). List of extra regex patterns
    # ADDED to the built-in VERIFICATION_COMMAND_PATTERNS for which shell
    # commands count as strong proof (execution_verified). Used by the
    # record_execution tool.
    verification_command_patterns: list[str] | None = None

    # Advanced — see DomainSettings docstring.
    domain: DomainSettings = field(default_factory=DomainSettings)


def _merge_mapping(current: dict[Any, Any], overrides: dict[Any, Any], path: str) -> None:
    """Recursively merge a dict of overrides into an existing mapping.

    Absent keys keep their current value (the documented "replace only what
    you need" semantics), so e.g. overriding just `base_confidence.official_doc`
    preserves the other source defaults instead of wiping them out. Nested
    dicts merge recursively; any other value is replaced.
    """
    if not isinstance(overrides, dict):
        raise ValueError(f"{path}: expected an object, got {type(overrides).__name__}")

    for key, value in overrides.items():
        existing = current.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            _merge_mapping(existing, value, f"{path}.{key}")
        else:
            current[key] = value


def _merge_dataclass(instance: Any, overrides: dict[str, Any], path: str) -> None:
    """Recursively apply a dict of overrides onto a dataclass instance,
    in place. Unknown keys raise (so a typo in the JSON is visible instead
    of quietly having no effect). Dict fields merge recursively, so a
    partial override keeps the unmentioned keys (see _merge_mapping)."""
    if not isinstance(overrides, dict):
        raise ValueError(f"{path}: expected an object, got {type(overrides).__name__}")

    valid_names = {f.name for f in fields(instance)}
    for key, value in overrides.items():
        if key not in valid_names:
            raise ValueError(f"{path}.{key}: unknown config key")
        current = getattr(instance, key)
        if is_dataclass(current):
            _merge_dataclass(current, value, f"{path}.{key}")
        elif isinstance(current, dict) and isinstance(value, dict):
            _merge_mapping(current, value, f"{path}.{key}")
        else:
            setattr(instance, key, value)


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from JSON, layered over the defaults above.

    A missing file, or a file with only some sections/keys present, is
    fine — anything not specified keeps its default. An unknown key
    raises, so a typo doesn't fail silently.
    """
    settings = Settings()

    path = Path(config_path or os.environ.get("WPM_CONFIG_PATH", "wpm.config.json"))
    if not path.exists():
        return settings

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")

    for section_name, override in raw.items():
        if not hasattr(settings, section_name):
            raise ValueError(f"{path}: unknown top-level key '{section_name}'")
        current = getattr(settings, section_name)
        if is_dataclass(current):
            _merge_dataclass(current, override, section_name)
        else:
            # Plain scalar top-level field (currently just db_path and
            # confidence_threshold).
            setattr(settings, section_name, override)

    _validate_settings(settings)
    return settings


def _validate_settings(settings: Settings) -> None:
    """Fail fast on an out-of-range/mistyped scalar instead of silently
    misbehaving downstream (confidence_threshold feeds the project-rules
    resource and is documented as a confidence value in [0, 1])."""
    ct = settings.confidence_threshold
    if isinstance(ct, bool) or not isinstance(ct, (int, float)):
        raise ValueError(
            f"confidence_threshold: expected a number between 0 and 1, "
            f"got {ct!r}"
        )
    if not 0.0 <= ct <= 1.0:
        raise ValueError(
            f"confidence_threshold: expected a value between 0 and 1, got {ct}"
        )

    patterns = settings.verification_command_patterns
    if patterns is not None:
        if not isinstance(patterns, list) or not all(
            isinstance(p, str) and p.strip() for p in patterns
        ):
            raise ValueError(
                "verification_command_patterns: expected a list of non-empty "
                f"strings, got {patterns!r}"
            )

"""Confidence calculation and evidence application (spec doc, sections 3-4).

All tunable numbers are read from a Settings instance (settings.py),
passed in explicitly rather than imported as module constants, so the
same functions work whether settings came from defaults or from JSON.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from wpm_mcp_server.domain import EntryType, EvidenceType
from wpm_mcp_server.settings import DomainSettings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def base_confidence_for_source(source: str, settings: DomainSettings) -> float:
    return settings.provenance.base_confidence.get(source, settings.provenance.default)


def confidence_at(
    *,
    entry_type: EntryType,
    provenance_score: float,
    validation_score: float,
    last_validated_at: str,
    status: str = "active",
    settings: DomainSettings,
    now: datetime | None = None,
) -> float:
    """confidence(t) = base_confidence * exp(-lambda * (t - last_validated))

    base_confidence here combines provenance and accumulated validation:
    provenance sets the floor, validation_score raises it, both decay
    together with time since last validation (spec section 3).

    Pinned entries skip decay entirely — their confidence remains at
    base = min(1.0, provenance + validation) indefinitely.
    """
    base = min(1.0, provenance_score + validation_score)
    if status == "pinned":
        return base
    now = now or datetime.now(timezone.utc)
    last_validated = datetime.fromisoformat(last_validated_at)
    if last_validated.tzinfo is None:
        last_validated = last_validated.replace(tzinfo=timezone.utc)

    elapsed_seconds = max(0.0, (now - last_validated).total_seconds())
    lam = settings.decay.lambda_per_type.get(entry_type.value, settings.decay.default_lambda)

    decay = math.exp(-lam * (elapsed_seconds / 3600.0))  # lambda tuned per hour
    return base * decay


def apply_evidence(
    *,
    current_validation_score: float,
    evidence_type: EvidenceType,
    is_contradiction: bool,
    settings: DomainSettings,
) -> float:
    """Update validation_score given one piece of evidence.

    Asymmetric on purpose: contradictions move the score more than
    confirmations of equivalent evidence strength (falsifiability
    principle, spec section 4).
    """
    if is_contradiction:
        delta = -settings.evidence.contradict_weight.get(evidence_type.value, 0.0)
    else:
        delta = settings.evidence.confirm_weight.get(evidence_type.value, 0.0)

    updated = current_validation_score + delta
    return max(settings.validation.score_min, min(settings.validation.score_max, updated))

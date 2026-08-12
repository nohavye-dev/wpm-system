import sys
sys.path.insert(0, "src")

import math
from datetime import datetime, timedelta, timezone

from wpm_mcp_server.domain import EntryType, EvidenceType
from wpm_mcp_server.scoring import (
    apply_evidence,
    base_confidence_for_source,
    confidence_at,
    now_iso,
)
from wpm_mcp_server.settings import DomainSettings

norms = DomainSettings()

# --- base_confidence_for_source ---

assert base_confidence_for_source("official_doc", norms) == 0.9
assert base_confidence_for_source("observed_code", norms) == 0.75
assert base_confidence_for_source("tool_execution", norms) == 0.7
assert base_confidence_for_source("agent_inference", norms) == 0.35
# Unknown source falls back to default
assert base_confidence_for_source("nonexistent_source", norms) == 0.5
print("OK: base_confidence_for_source matches provenance defaults")

# --- confidence_at: no decay immediately ---

now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
last = "2026-01-01T12:00:00+00:00"

c = confidence_at(
    entry_type=EntryType.CONVENTION,
    provenance_score=0.5,
    validation_score=0.0,
    last_validated_at=last,
    settings=norms,
    now=now,
)
assert abs(c - 0.5) < 1e-9, f"expected 0.5 got {c}"
print("OK: confidence_at zero elapsed = base score only")

# --- confidence_at: base + validation ---

c2 = confidence_at(
    entry_type=EntryType.ARCHI_DECISION,
    provenance_score=0.5,
    validation_score=0.3,
    last_validated_at=last,
    settings=norms,
    now=now,
)
assert abs(c2 - 0.8) < 1e-9, f"expected 0.8 got {c2}"
print("OK: confidence_at = provenance + validation at t=0")

# --- confidence_at: score clamped to 1.0 ---

c3 = confidence_at(
    entry_type=EntryType.DOC,
    provenance_score=0.9,
    validation_score=0.5,
    last_validated_at=last,
    settings=norms,
    now=now,
)
assert abs(c3 - 1.0) < 1e-9, f"expected 1.0 got {c3}"
print("OK: confidence_at clamps base to 1.0")

# --- confidence_at: decay after one hour ---

one_hour_later = now + timedelta(hours=1)
lam = norms.decay.lambda_per_type["convention"]  # 0.003
expected_decay = 0.8 * math.exp(-lam * 1.0)  # one hour

c4 = confidence_at(
    entry_type=EntryType.CONVENTION,
    provenance_score=0.5,
    validation_score=0.3,
    last_validated_at=last,
    settings=norms,
    now=one_hour_later,
)
assert abs(c4 - expected_decay) < 1e-8, f"expected {expected_decay} got {c4}"
print("OK: confidence_at decays correctly after 1h")

# --- confidence_at: default lambda for unknown type ---

c5 = confidence_at(
    entry_type=EntryType.DOC,
    provenance_score=0.4,
    validation_score=0.1,
    last_validated_at="2026-01-01T11:00:00+00:00",
    settings=norms,
    now=now,
)
# doc lambda = 0.004, elapsed = 1h
expected5 = 0.5 * math.exp(-0.004 * 1.0)
assert abs(c5 - expected5) < 1e-8, f"expected {expected5} got {c5}"
print("OK: confidence_at uses entry type lambda from config")

# --- confidence_at: naive timestamps treated as UTC ---

c_naive = confidence_at(
    entry_type=EntryType.CONVENTION,
    provenance_score=0.5,
    validation_score=0.0,
    last_validated_at="2026-01-01T12:00:00",
    settings=norms,
    now=now,
)
assert abs(c_naive - 0.5) < 1e-9
print("OK: confidence_at treats naive timestamp as UTC")

# --- apply_evidence: confirmation ---

v1 = apply_evidence(
    current_validation_score=0.0,
    evidence_type=EvidenceType.EXECUTION_VERIFIED,
    is_contradiction=False,
    settings=norms,
)
assert v1 == 0.25, f"expected 0.25 got {v1}"
print("OK: apply_evidence EXECUTION_VERIFIED adds 0.25")

v2 = apply_evidence(
    current_validation_score=0.25,
    evidence_type=EvidenceType.CROSS_REFERENCE,
    is_contradiction=False,
    settings=norms,
)
assert v2 == 0.4, f"expected 0.4 got {v2}"  # 0.25 + 0.15
print("OK: apply_evidence stacks confirmations")

# --- apply_evidence: contradiction ---

v3 = apply_evidence(
    current_validation_score=0.4,
    evidence_type=EvidenceType.EXECUTION_VERIFIED,
    is_contradiction=True,
    settings=norms,
)
assert v3 == 0.0, f"expected 0.0 got {v3}"  # 0.4 - 0.4 = 0.0
print("OK: apply_evidence contradiction subtracts more than confirmation adds")

# --- apply_evidence: clamped to bounds ---

v4 = apply_evidence(
    current_validation_score=-10.0,
    evidence_type=EvidenceType.CROSS_REFERENCE,
    is_contradiction=True,
    settings=norms,
)
assert v4 == 0.0, f"expected 0.0 got {v4}"
print("OK: apply_evidence clamped to score_min (0.0)")

v5 = apply_evidence(
    current_validation_score=0.95,
    evidence_type=EvidenceType.EXECUTION_VERIFIED,
    is_contradiction=False,
    settings=norms,
)
assert v5 == 1.0, f"expected 1.0 got {v5}"
print("OK: apply_evidence clamped to score_max (1.0)")

# --- apply_evidence: agent_reasoning has zero weight ---

v6 = apply_evidence(
    current_validation_score=0.0,
    evidence_type=EvidenceType.AGENT_REASONING,
    is_contradiction=False,
    settings=norms,
)
assert v6 == 0.0, f"expected 0.0 got {v6}"
print("OK: apply_evidence AGENT_REASONING has zero confirm weight")

v7 = apply_evidence(
    current_validation_score=0.5,
    evidence_type=EvidenceType.AGENT_REASONING,
    is_contradiction=True,
    settings=norms,
)
assert v7 == 0.5, f"expected 0.5 got {v7}"  # 0.5 - 0.0
print("OK: apply_evidence AGENT_REASONING has zero contradict weight")

# --- confidence_at: pinned entries never decay ---

c_pinned = confidence_at(
    entry_type=EntryType.ARCHI_DECISION,
    provenance_score=0.5,
    validation_score=0.25,
    last_validated_at="2026-01-01T12:00:00+00:00",
    status="pinned",
    settings=norms,
    now=one_hour_later,
)
assert abs(c_pinned - 0.75) < 1e-9, f"expected 0.75 got {c_pinned}"
print("OK: confidence_at pinned entry skips decay entirely")

# --- now_iso ---

ts = now_iso()
assert ts.endswith("+00:00") or "Z" in ts or ts.count(":") >= 2  # ISO-ish
print("OK: now_iso returns ISO8601 timestamp")

print("ALL SCORING TESTS OK")

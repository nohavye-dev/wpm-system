import sys

sys.path.insert(0, "src")

from wpm_mcp_server.config import DomainSettings
from wpm_mcp_server.core import (
    EMBEDDING_DIM,
    EntryType,
    EventType,
    EvidenceType,
    RelationType,
)

norms = DomainSettings()

# --- EMBEDDING_DIM ---
assert EMBEDDING_DIM == 384, f"expected 384, got {EMBEDDING_DIM}"
print("OK: EMBEDDING_DIM = 384")

# --- EntryType enums match decay config keys ---
for t in EntryType:
    assert t.value in norms.decay.lambda_per_type, (
        f"EntryType {t.value} missing from decay.lambda_per_type"
    )
print("OK: all EntryTypes have decay lambda configured")

# --- EvidenceType enums match evidence config keys ---
for e in EvidenceType:
    assert e.value in norms.evidence.confirm_weight, (
        f"EvidenceType {e.value} missing from evidence.confirm_weight"
    )
    assert e.value in norms.evidence.contradict_weight, (
        f"EvidenceType {e.value} missing from evidence.contradict_weight"
    )
print("OK: all EvidenceTypes have confirm and contradict weights")

# --- EvidenceType enums match base_confidence keys ---
known_provenance_sources = {"official_doc", "observed_code", "tool_execution", "agent_inference"}
for s in known_provenance_sources:
    assert s in norms.provenance.base_confidence, (
        f"source {s} missing from provenance.base_confidence"
    )
print("OK: all known provenance sources mapped")

# --- RelationType values match what repository.py expects ---
assert RelationType.RELATED.value == "related"
assert RelationType.CONTRADICTS.value == "contradicts"
assert RelationType.DEPENDS_ON.value == "depends_on"
assert RelationType.REFINES.value == "refines"
print("OK: RelationType values match expected strings")

# --- EventType values ---
assert EventType.CREATED.value == "created"
assert EventType.VALIDATED.value == "validated"
assert EventType.CONTRADICTED.value == "contradicted"
assert EventType.REFERENCED.value == "referenced"
print("OK: EventType values match expected strings")

# --- validation score bounds are sane ---
assert 0.0 <= norms.validation.score_min <= 1.0
assert 0.0 <= norms.validation.score_max <= 1.0
assert norms.validation.score_min < norms.validation.score_max
print("OK: validation score bounds are sane")

# --- retrieval weights sum to 1.0 ---
rw = (
    norms.retrieval.weight_similarity
    + norms.retrieval.weight_confidence
    + norms.retrieval.weight_centrality
)
assert abs(rw - 1.0) < 0.01, f"retrieval weights sum to {rw}, expected ~1.0"
print("OK: retrieval weights normalize to ~1.0")

# --- decay lambdas are positive ---
for lam in norms.decay.lambda_per_type.values():
    assert lam > 0, f"decay lambda {lam} must be positive"
assert norms.decay.default_lambda > 0
print("OK: all decay lambdas are positive")

# --- evidence weights are asymmetric (contradict >= confirm) ---
for e in EvidenceType:
    confirm = norms.evidence.confirm_weight[e.value]
    contradict = norms.evidence.contradict_weight[e.value]
    assert contradict >= confirm, (
        f"{e.value}: contradict weight ({contradict}) must be >= confirm weight ({confirm})"
    )
print("OK: evidence weights are asymmetric (contradict >= confirm)")

# --- expansion params are sane ---
assert 0.0 < norms.expansion.hop_decay <= 1.0
assert 0.0 <= norms.expansion.min_confidence <= 1.0
assert norms.expansion.top_n_candidates > 0
assert 0.0 < norms.expansion.auto_link_similarity_threshold <= 1.0
print("OK: expansion params are within sane ranges")

print("ALL DOMAIN TESTS OK")

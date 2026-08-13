import sys
sys.path.insert(0, "src")

import json
import tempfile
import os

from wpm_mcp_server.settings import load_settings

# 1. No file -> defaults
s = load_settings("/tmp/does_not_exist.json")
assert s.domain.retrieval.weight_similarity == 0.5
assert s.domain.retrieval.min_similarity == 0.1
assert s.domain.decay.lambda_per_type["archi_decision"] == 0.00008
assert s.confidence_threshold == 0.5
print("OK: defaults when no file")

# 2. Partial override -> only specified keys change, rest keep defaults
partial = {"domain": {"retrieval": {"weight_similarity": 0.7}}}
tmp = tempfile.mktemp(suffix=".json")
with open(tmp, "w") as f:
    json.dump(partial, f)
s2 = load_settings(tmp)
assert s2.domain.retrieval.weight_similarity == 0.7
assert s2.domain.retrieval.weight_confidence == 0.35  # untouched default
assert s2.domain.retrieval.min_similarity == 0.1  # untouched default
assert s2.domain.decay.lambda_per_type["archi_decision"] == 0.00008  # untouched
print("OK: partial override merges correctly, rest stays default")
os.remove(tmp)

# 2b. Partial override of a DICT field merges, does NOT wipe the other keys
partial_dict = {"domain": {"provenance": {"base_confidence": {"official_doc": 0.95}}}}
tmp_dict = tempfile.mktemp(suffix=".json")
with open(tmp_dict, "w") as f:
    json.dump(partial_dict, f)
sd = load_settings(tmp_dict)
assert sd.domain.provenance.base_confidence["official_doc"] == 0.95  # overridden
assert sd.domain.provenance.base_confidence["observed_code"] == 0.75  # preserved
assert sd.domain.provenance.base_confidence["tool_execution"] == 0.7  # preserved
assert sd.domain.provenance.base_confidence["agent_inference"] == 0.35  # preserved
print("OK: dict field partial override merges, other keys preserved")
os.remove(tmp_dict)

# 2c. Nested dict override (add a new custom source key) keeps defaults
partial_nested = {"domain": {"provenance": {"base_confidence": {"client_email": 0.8}}}}
tmp_nested = tempfile.mktemp(suffix=".json")
with open(tmp_nested, "w") as f:
    json.dump(partial_nested, f)
sn = load_settings(tmp_nested)
assert sn.domain.provenance.base_confidence["client_email"] == 0.8
assert sn.domain.provenance.base_confidence["official_doc"] == 0.9  # preserved
print("OK: adding a custom source key keeps default keys")
os.remove(tmp_nested)

# 2d. confidence_threshold out of range -> raises
for bad_ct in (1.5, -0.1, "0.6"):
    tmp_ct = tempfile.mktemp(suffix=".json")
    with open(tmp_ct, "w") as f:
        json.dump({"db_path": ".wpm/wpm.db", "confidence_threshold": bad_ct}, f)
    try:
        load_settings(tmp_ct)
        raise AssertionError(f"should have raised for confidence_threshold={bad_ct!r}")
    except ValueError as exc:
        print(f"OK: out-of-range confidence_threshold {bad_ct!r} raised:", exc)
    os.remove(tmp_ct)

# 3. Full example file loads without error
s3 = load_settings("wpm.config.example.json")
assert s3.domain.provenance.base_confidence["official_doc"] == 0.9
print("OK: full example file loads")

# 4. Unknown top-level section -> raises
bad = {"not_a_real_section": {}}
tmp2 = tempfile.mktemp(suffix=".json")
with open(tmp2, "w") as f:
    json.dump(bad, f)
try:
    load_settings(tmp2)
    raise AssertionError("should have raised")
except ValueError as exc:
    print("OK: unknown section raised:", exc)
os.remove(tmp2)

# 5. Unknown nested key -> raises
bad2 = {"domain": {"retrieval": {"typo_key": 1.0}}}
tmp3 = tempfile.mktemp(suffix=".json")
with open(tmp3, "w") as f:
    json.dump(bad2, f)
try:
    load_settings(tmp3)
    raise AssertionError("should have raised")
except ValueError as exc:
    print("OK: unknown nested key raised:", exc)
os.remove(tmp3)

# 6. End-to-end: repository actually uses overridden settings
from wpm_mcp_server import db
from wpm_mcp_server.repository import Repository

import hashlib

class _StubEmbedder:
    dim = 384

    def embed(self, text: str) -> list[float]:
        import math
        vec = [0.0] * self.dim
        for i in range(self.dim):
            digest = hashlib.sha256(f"{text}:{i}".encode()).digest()
            vec[i] = (int.from_bytes(digest[:4], "big") % 1000 - 500) / 500.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm > 0 else vec

tmp_db = tempfile.mktemp(suffix=".db")
conn = db.connect(tmp_db)

custom = {"domain": {"provenance": {"default": 0.99}}}
tmp4 = tempfile.mktemp(suffix=".json")
with open(tmp4, "w") as f:
    json.dump(custom, f)
settings = load_settings(tmp4).domain

repo = Repository(conn=conn, embedder=_StubEmbedder(), settings=settings)
result = repo.store_entry(type_="learning", content="test with custom default provenance", source="unknown_source_not_in_table")
assert result["provenance_score"] == 0.99, result
print("OK: repository actually applies overridden settings, got provenance_score =", result["provenance_score"])

os.remove(tmp_db)
os.remove(tmp4)

# 7. New structure: confidence_threshold is a top-level optional scalar
config7 = {"db_path": "/custom/path/wpm.db", "confidence_threshold": 0.6}
tmp5 = tempfile.mktemp(suffix=".json")
with open(tmp5, "w") as f:
    json.dump(config7, f)
s5 = load_settings(tmp5)
assert s5.db_path == "/custom/path/wpm.db"
assert s5.confidence_threshold == 0.6
assert s5.domain.retrieval.weight_similarity == 0.5  # domain untouched, still default
print("OK: confidence_threshold is a top-level optional scalar, domain still defaults when omitted")
os.remove(tmp5)

# 7b. Old top-level "plugin" key now raises (unknown top-level key)
bad4 = {"db_path": "/custom/path/wpm.db", "plugin": {"mcp_command": "uv", "confidence_threshold": 0.6}}
tmp5b = tempfile.mktemp(suffix=".json")
with open(tmp5b, "w") as f:
    json.dump(bad4, f)
try:
    load_settings(tmp5b)
    raise AssertionError("should have raised")
except ValueError as exc:
    print("OK: old top-level 'plugin' key raised:", exc)
os.remove(tmp5b)

# 8. idle_nudge: removed with the plugin's session.idle hook — the key now
# raises as unknown, so a stale config does not silently keep working
try:
    tmp_idle = tempfile.mktemp(suffix=".json")
    with open(tmp_idle, "w") as f:
        json.dump({"db_path": ".wpm/wpm.db", "idle_nudge": True}, f)
    load_settings(tmp_idle)
    raise AssertionError("should have raised for removed idle_nudge")
except ValueError as exc:
    print("OK: removed idle_nudge key raised:", exc)
os.remove(tmp_idle)

# 9. verification_command_patterns: default None, loads a list, non-list or
# non-string elements raise
s11 = load_settings("/tmp/does_not_exist.json")
assert s11.verification_command_patterns is None
print("OK: verification_command_patterns defaults to None (no additions)")

patterns = [r"\bmy-custom-runner\b", r"\bpytest\b"]
tmp_pat = tempfile.mktemp(suffix=".json")
with open(tmp_pat, "w") as f:
    json.dump({"db_path": ".wpm/wpm.db", "verification_command_patterns": patterns}, f)
s11b = load_settings(tmp_pat)
assert s11b.verification_command_patterns == patterns
print("OK: verification_command_patterns list loads")
os.remove(tmp_pat)

for bad_pat in (["pytest", 3], [""], ["  "], "pytest", {"re": "x"}):
    tmp_pat_bad = tempfile.mktemp(suffix=".json")
    with open(tmp_pat_bad, "w") as f:
        json.dump({"verification_command_patterns": bad_pat}, f)
    try:
        load_settings(tmp_pat_bad)
        raise AssertionError(f"should have raised for {bad_pat!r}")
    except ValueError as exc:
        print(f"OK: bad verification_command_patterns {bad_pat!r} raised:", exc)
    os.remove(tmp_pat_bad)

# 10. old "embedding" section now raises (unknown top-level key)
bad_embedding = {"embedding": {"provider": "sentence_transformers"}}
tmp_emb = tempfile.mktemp(suffix=".json")
with open(tmp_emb, "w") as f:
    json.dump(bad_embedding, f)
try:
    load_settings(tmp_emb)
    raise AssertionError("should have raised")
except ValueError as exc:
    print("OK: removed 'embedding' section raised:", exc)
os.remove(tmp_emb)

print("ALL SETTINGS TESTS OK")

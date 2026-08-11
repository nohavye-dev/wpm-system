import sys
sys.path.insert(0, "src")

import tempfile, os
from wpm_mcp_server import db
from wpm_mcp_server.repository import Repository
from wpm_mcp_server.embeddings import EmbeddingProvider

import hashlib

class _StubEmbedder(EmbeddingProvider):
    dim = 384
    def embed(self, text: str) -> list[float]:
        import math
        vec = [0.0] * self.dim
        for i in range(self.dim):
            digest = hashlib.sha256(f"{text}:{i}".encode()).digest()
            vec[i] = (int.from_bytes(digest[:4], "big") % 1000 - 500) / 500.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm > 0 else vec

tmp = tempfile.mktemp(suffix=".db")
conn = db.connect(tmp)
repo = Repository(conn=conn, embedder=_StubEmbedder())

# 1. store a few entries
e1 = repo.store_entry(type_="archi_decision", content="Use Parameter Object pattern for large constructors in C# services", source="agent_inference")
e2 = repo.store_entry(type_="convention", content="Parameter objects for constructors should be immutable records", source="observed_code")
e3 = repo.store_entry(type_="bug_pattern", content="MassImport pipeline fails silently when Astech API returns partial payload", source="tool_execution")
print("stored:", e1, e2, e3)

# 2. explicit link
link = repo.link_entries(source_id=e2["entry_id"], target_id=e1["entry_id"], relation_type="depends_on")
print("linked:", link)

# 3. query
result = repo.query_context(query="constructor parameter object pattern C# services")
print("direct_matches:", len(result["direct_matches"]))
print("related_context:", len(result["related_context"]))
for m in result["direct_matches"]:
    print("  direct:", m["entry_id"][:8], m["type"], round(m["score"], 3), round(m["confidence"], 3))
for m in result["related_context"]:
    print("  related:", m["entry_id"][:8], m["type"], round(m["score"], 3))

# 4. validate with real evidence
v1 = repo.validate_entry(entry_id=e1["entry_id"], evidence_type="execution_verified", evidence_ref="test_suite_run_142", session_id="sess-1")
print("validated:", v1)

# 4b. duplicate validation same session -> should dedup
v1b = repo.validate_entry(entry_id=e1["entry_id"], evidence_type="execution_verified", evidence_ref="test_suite_run_142", session_id="sess-1")
print("validated (dup, should note dedup):", v1b)

# 4c. agent_reasoning should not move score
v1c = repo.validate_entry(entry_id=e1["entry_id"], evidence_type="agent_reasoning", evidence_ref="i think so", session_id="sess-1")
print("validated (agent_reasoning, should be excluded):", v1c)

# 5. contradict
v2 = repo.contradict_entry(entry_id=e2["entry_id"], conflicting_entry_id=e3["entry_id"], evidence_type="cross_reference", evidence_ref="entry_id:" + e3["entry_id"])
print("contradicted:", v2)

# 6. query again, confidence for e1 should now be higher (validated), conflicts should show for e2
result2 = repo.query_context(query="parameter object pattern")
print("conflicts:", result2["conflicts"])

# 7. error paths
try:
    repo.store_entry(type_="not_a_type", content="x", source="agent_inference")
except ValueError as exc:
    print("OK, invalid type raised:", exc)

try:
    repo.link_entries(source_id="nonexistent", target_id=e1["entry_id"], relation_type="related")
except Exception as exc:
    print("OK, missing entry raised:", exc)

os.remove(tmp)
print("ALL OK")

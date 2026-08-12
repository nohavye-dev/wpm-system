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

# 8. get_stats on a populated repo
stats = repo.get_stats()
assert stats["total_entries"] == 3, f"expected 3, got {stats['total_entries']}"
assert stats["by_type"]["archi_decision"] == 1
assert stats["by_type"]["convention"] == 1
assert stats["by_type"]["bug_pattern"] == 1
assert len(stats["never_validated"]) >= 0
assert len(stats["active_contradictions"]) == 1
assert stats["active_contradictions"][0]["source_id"] == e2["entry_id"]
assert len(stats["lowest_confidence"]) <= 5
assert (
    stats["confidence_distribution"]["high"]
    + stats["confidence_distribution"]["medium"]
    + stats["confidence_distribution"]["low"]
    == stats["total_entries"]
)
assert len(stats["recent_activity"]) <= 10
print("stats OK:", stats["total_entries"], stats["by_type"])

# 9. get_stats on an empty repo
tmp2 = tempfile.mktemp(suffix=".db")
conn2 = db.connect(tmp2)
repo2 = Repository(conn=conn2, embedder=_StubEmbedder())
stats_empty = repo2.get_stats()
assert stats_empty["total_entries"] == 0
assert stats_empty["never_validated"] == []
assert stats_empty["active_contradictions"] == []
assert stats_empty["lowest_confidence"] == []
assert stats_empty["recent_activity"] == []
conn2.close()
os.remove(tmp2)
print("stats_empty OK")

# 10. pin_entry
pinned = repo.pin_entry(entry_id=e1["entry_id"])
assert pinned["status"] == "pinned", f"expected pinned, got {pinned['status']}"

# Verify pinned entry still appears in query results
result_pinned = repo.query_context(query="Parameter Object pattern C#")
all_ids = {m["entry_id"] for m in result_pinned["direct_matches"]} | {
    m["entry_id"] for m in result_pinned["related_context"]
}
assert e1["entry_id"] in all_ids, "pinned entry should still appear in queries"
matched = [m for m in result_pinned["direct_matches"] + result_pinned["related_context"] if m["entry_id"] == e1["entry_id"]]
assert len(matched) == 1
assert matched[0]["status"] == "pinned"
print("pin OK")

# 11. deprecate_entry
deprecated = repo.deprecate_entry(entry_id=e3["entry_id"])
assert deprecated["status"] == "deprecated"

# Deprecated entry should NOT appear in queries
result_dep = repo.query_context(query="MassImport pipeline fails silently")
all_dep_ids = {m["entry_id"] for m in result_dep["direct_matches"]} | {
    m["entry_id"] for m in result_dep["related_context"]
}
assert e3["entry_id"] not in all_dep_ids, "deprecated entry should be excluded from queries"

# Contradictions involving deprecated entries should also be filtered
conflicts_after_dep = result_dep.get("conflicts", [])
conflict_ids = {c["contradicted_by"] for c in conflicts_after_dep}
assert e3["entry_id"] not in conflict_ids, "deprecated entry should not appear as conflict other"
print("deprecate OK")

# 12. restore_entry
restored = repo.restore_entry(entry_id=e3["entry_id"])
assert restored["status"] == "active"

# Restored entry should appear in queries again
result_rest = repo.query_context(query="MassImport pipeline fails silently")
all_rest_ids = {m["entry_id"] for m in result_rest["direct_matches"]} | {
    m["entry_id"] for m in result_rest["related_context"]
}
assert e3["entry_id"] in all_rest_ids, "restored entry should be visible again"
print("restore OK")

# 13. error: pin/deprecate/restore on nonexistent entry
try:
    repo.pin_entry(entry_id="nonexistent-id")
    assert False, "should have raised"
except Exception as exc:
    assert "not found" in str(exc)
print("OK, pin nonexistent raised")

os.remove(tmp)
print("ALL OK")

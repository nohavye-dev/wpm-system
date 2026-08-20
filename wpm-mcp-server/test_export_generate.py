import sys
sys.path.insert(0, "src")

import tempfile, os, json, hashlib, math
from wpm_mcp_server import db
from wpm_mcp_server.repository import Repository, export_db, generate_db
from wpm_mcp_server.embeddings import EmbeddingProvider


class _StubEmbedder(EmbeddingProvider):
    dim = 384
    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for i in range(self.dim):
            digest = hashlib.sha256(f"{text}:{i}".encode()).digest()
            vec[i] = (int.from_bytes(digest[:4], "big") % 1000 - 500) / 500.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm > 0 else vec


embedder = _StubEmbedder()

# 1. Create a populated source database
src_db = tempfile.mktemp(suffix=".db")
conn = db.connect(src_db)
repo = Repository(conn=conn, embedder=embedder)

e1 = repo.store_entry(type_="archi_decision", content="Use Parameter Object pattern for large constructors in C# services", source="observed_code")
e2 = repo.store_entry(type_="convention", content="Parameter objects for constructors should be immutable records", source="observed_code")
e3 = repo.store_entry(type_="bug_pattern", content="MassImport pipeline fails silently when Astech API returns partial payload", source="tool_execution")

repo.link_entries(source_id=e2["entry_id"], target_id=e1["entry_id"], relation_type="depends_on")

v1 = repo.validate_entry(entry_id=e1["entry_id"], evidence_type="execution_verified", evidence_ref="test_run_1", session_id="sess-1")
conn.close()

# 2. Export
data = export_db(db.connect(src_db))
assert "entries" in data
assert "entry_events" in data
assert "entry_links" in data
assert len(data["entries"]) == 3, f"expected 3 entries, got {len(data['entries'])}"
assert len(data["entry_links"]) == 1, f"expected 1 link, got {len(data['entry_links'])}"
assert len(data["entry_events"]) > 0, "expected events"

# Verify no embedding data leaked into the export
for entry in data["entries"]:
    assert "embedding" not in entry, "embedding should not be in export"
    assert entry["content"], f"entry {entry['id']} has empty content"

print(f"export OK: {len(data['entries'])} entries, {len(data['entry_events'])} events, {len(data['entry_links'])} links")

# 3. Generate a new database from the export
gen_db = tempfile.mktemp(suffix=".db")
generate_db(db_path=gen_db, json_data=data, embedder=embedder)

# 4. Verify the generated database
conn2 = db.connect(gen_db)

# Entries
rows = conn2.execute("SELECT * FROM entries").fetchall()
assert len(rows) == 3, f"expected 3 entries in generated db, got {len(rows)}"

# IDs preserved
gen_ids = {row["id"] for row in rows}
orig_ids = {e["entry_id"] for e in [e1, e2, e3]}
assert gen_ids == orig_ids, f"IDs not preserved: {gen_ids} != {orig_ids}"

# Content preserved
for row in rows:
    if row["id"] == e1["entry_id"]:
        assert row["content"] == "Use Parameter Object pattern for large constructors in C# services"
        assert row["type"] == "archi_decision"
        assert row["source"] == "observed_code"
    elif row["id"] == e2["entry_id"]:
        assert row["content"] == "Parameter objects for constructors should be immutable records"
    elif row["id"] == e3["entry_id"]:
        assert row["content"] == "MassImport pipeline fails silently when Astech API returns partial payload"

# Events preserved
events = conn2.execute("SELECT * FROM entry_events").fetchall()
assert len(events) > 0, "no events in generated db"

# Links preserved
links = conn2.execute("SELECT * FROM entry_links").fetchall()
assert len(links) == 1, f"expected 1 link, got {len(links)}"
assert links[0]["source_id"] == e2["entry_id"]
assert links[0]["target_id"] == e1["entry_id"]
assert links[0]["relation_type"] == "depends_on"

# 5. Verify embeddings were generated (vector search works)
from wpm_mcp_server.settings import DomainSettings
repo2 = Repository(conn=conn2, embedder=embedder, settings=DomainSettings())
result = repo2.query_context(query="Use Parameter Object pattern for large constructors in C# services")
assert len(result["direct_matches"]) > 0, "vector search returned no results on generated db"
print(f"vector search on generated db: {len(result['direct_matches'])} direct matches")

conn2.close()

# 6. Round-trip: export the generated db and compare entries + links
data2 = export_db(db.connect(gen_db))
assert len(data2["entries"]) == len(data["entries"])
assert len(data2["entry_links"]) == len(data["entry_links"])
# events may differ because query_context creates 'referenced' events

# Same IDs and content
orig_entries = sorted(data["entries"], key=lambda e: e["id"])
gen_entries = sorted(data2["entries"], key=lambda e: e["id"])
for o, g in zip(orig_entries, gen_entries):
    assert o["id"] == g["id"]
    assert o["content"] == g["content"]
    assert o["type"] == g["type"]

print("round-trip export->generate->export: OK")

# Cleanup
os.unlink(src_db)
os.unlink(gen_db)
print("all export/generate tests passed")

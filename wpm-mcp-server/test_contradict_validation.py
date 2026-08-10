import sys
sys.path.insert(0, "src")

import tempfile, os
from wpm_mcp_server import db
from wpm_mcp_server.embeddings import get_default_provider
from wpm_mcp_server.repository import Repository, WpmError

tmp = tempfile.mktemp(suffix=".db")
conn = db.connect(tmp)
repo = Repository(conn=conn, embedder=get_default_provider())

# 1. bogus conflicting_entry_id -> WpmError
e1 = repo.store_entry(type_="learning", content="SQLite virtual tables support TEXT primary keys", source="agent_inference")
try:
    repo.contradict_entry(entry_id=e1["entry_id"], conflicting_entry_id="does-not-exist", evidence_type="cross_reference", evidence_ref="ref-x")
    print("FAIL: expected WpmError for bogus conflicting_entry_id")
    raise SystemExit(1)
except WpmError as exc:
    print("OK, bogus conflicting_entry_id raised:", exc)

# 2. positive case: two entries, contradict one by the other succeeds
e2 = repo.store_entry(type_="learning", content="SQLite virtual tables do not support TEXT primary keys", source="observed_code")
v = repo.contradict_entry(entry_id=e2["entry_id"], conflicting_entry_id=e1["entry_id"], evidence_type="cross_reference", evidence_ref="entry_id:" + e1["entry_id"])
print("contradicted:", v)
assert v["entry_id"] == e2["entry_id"]
assert v["conflicting_entry_id"] == e1["entry_id"]

os.remove(tmp)
print("ALL OK")

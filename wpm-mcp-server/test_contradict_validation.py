import sys

sys.path.insert(0, "src")

import hashlib
import os
import tempfile

from wpm_mcp_server.infra import database as db
from wpm_mcp_server.infra.embeddings import EmbeddingProvider
from wpm_mcp_server.storage import Repository, WpmError


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

# 1. bogus conflicting_entry_id -> WpmError
e1 = repo.store_entry(
    type_="insight",
    content="SQLite virtual tables support TEXT primary keys",
    source="agent_inference",
)
try:
    repo.contradict_entry(
        entry_id=e1["entry_id"],
        conflicting_entry_id="does-not-exist",
        evidence_type="cross_reference",
        evidence_ref="ref-x",
    )
    print("FAIL: expected WpmError for bogus conflicting_entry_id")
    raise SystemExit(1)
except WpmError as exc:
    print("OK, bogus conflicting_entry_id raised:", exc)

# 2. positive case: two entries, contradict one by the other succeeds
e2 = repo.store_entry(
    type_="insight",
    content="SQLite virtual tables do not support TEXT primary keys",
    source="observed_code",
)
v = repo.contradict_entry(
    entry_id=e2["entry_id"],
    conflicting_entry_id=e1["entry_id"],
    evidence_type="cross_reference",
    evidence_ref="entry_id:" + e1["entry_id"],
)
print("contradicted:", v)
assert v["entry_id"] == e2["entry_id"]
assert v["conflicting_entry_id"] == e1["entry_id"]

os.remove(tmp)
print("ALL OK")

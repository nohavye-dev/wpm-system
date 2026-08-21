import sys
sys.path.insert(0, "src")

import os
import tempfile

from wpm_mcp_server.infra import database as db
from wpm_mcp_server.core import EMBEDDING_DIM

# --- connect creates the database file ---
tmp = tempfile.mktemp(suffix=".db")
try:
    os.remove(tmp)
except FileNotFoundError:
    pass

conn = db.connect(tmp)
assert os.path.exists(tmp), "db file should exist after connect"
print("OK: connect creates the database file")

# --- foreign keys are enabled ---
fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
assert fk == 1, f"foreign_keys should be ON, got {fk}"
print("OK: foreign_keys PRAGMA is ON")

# --- WAL mode is set ---
wal_attempt = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
# SQLite may return "wal" or "wal;" (due to older sqlite3 wrappers)
assert wal_attempt.startswith("wal"), f"journal_mode should be WAL, got {wal_attempt!r}"
print("OK: journal_mode is WAL")

# --- schema tables exist ---
tables = {
    r[0]
    for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
}
assert "entries" in tables, "entries table should exist"
assert "entry_events" in tables, "entry_events table should exist"
assert "entry_links" in tables, "entry_links table should exist"
assert "vec_entries" in tables, "vec_entries virtual table should exist"
print("OK: all schema tables created")

# --- entries table has correct columns ---
cols = {
    r[1]
    for r in conn.execute("PRAGMA table_info('entries')").fetchall()
}
expected = {"id", "type", "content", "source", "provenance_score",
            "validation_score", "last_validated_at", "created_at"}
assert cols >= expected, f"entries table missing columns: {expected - cols}"
print("OK: entries table columns correct")

# --- vec_entries is a vec0 virtual table with correct dim ---
import json

conn.execute(
    "INSERT INTO entries (id, type, content, source, provenance_score, "
    "validation_score, last_validated_at, created_at) "
    "VALUES ('test-1', 'insight', 'hello', 'agent_inference', 0.35, 0.0, "
    "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
)
vec = [0.0] + [0.01] * (EMBEDDING_DIM - 1)  # non-zero for cosine stability
conn.execute(
    "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
    ("test-1", json.dumps(vec)),
)
conn.commit()
print("OK: vec_entries accepts 384-dim embedding")

# --- vec0 virtual tables don't enforce foreign keys ---
# (this is expected — vec0 'REFERENCES entries(id)' is documentation only;
#  referential integrity for vec_entries is handled by Repository.store_entry
#  which always inserts into entries BEFORE vec_entries)
conn.execute(
    "INSERT INTO vec_entries (entry_id, embedding) VALUES (?, ?)",
    ("nonexistent-entry", json.dumps(vec)),
)
conn.commit()
conn.execute("DELETE FROM vec_entries WHERE entry_id = 'nonexistent-entry'")
conn.commit()
print("OK: vec_entries accepts orphan rows (vec0 FK is not enforced, as expected)")

# --- foreign key on entry_events references entries ---
try:
    conn.execute(
        "INSERT INTO entry_events (id, entry_id, event_type, timestamp) "
        "VALUES ('ev-1', 'nonexistent', 'created', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    raise AssertionError("should have raised IntegrityError")
except Exception as exc:
    assert "FOREIGN KEY" in str(exc).upper() or "constraint" in str(exc).lower(), (
        f"expected FK constraint violation, got {exc}"
    )
print("OK: entry_events foreign key constraint enforced")

# --- foreign key on entry_links references entries ---
try:
    conn.execute(
        "INSERT INTO entry_links (source_id, target_id, relation_type, weight) "
        "VALUES ('nonexistent', 'test-1', 'related', 1.0)"
    )
    conn.commit()
    raise AssertionError("should have raised IntegrityError")
except Exception as exc:
    assert "FOREIGN KEY" in str(exc).upper() or "constraint" in str(exc).lower(), (
        f"expected FK constraint violation, got {exc}"
    )
print("OK: entry_links foreign key constraint enforced (source)")

try:
    conn.execute(
        "INSERT INTO entry_links (source_id, target_id, relation_type, weight) "
        "VALUES ('test-1', 'nonexistent', 'related', 1.0)"
    )
    conn.commit()
    raise AssertionError("should have raised IntegrityError")
except Exception as exc:
    assert "FOREIGN KEY" in str(exc).upper() or "constraint" in str(exc).lower(), (
        f"expected FK constraint violation, got {exc}"
    )
print("OK: entry_links foreign key constraint enforced (target)")

# --- connect is idempotent ---
conn2 = db.connect(tmp)
assert conn2.execute("SELECT 1 FROM entries WHERE id = 'test-1'").fetchone() is not None
conn2.close()
print("OK: connect is idempotent (repeated calls don't break schema)")

conn.close()
os.remove(tmp)

print("ALL DB TESTS OK")

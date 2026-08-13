import sys
sys.path.insert(0, "src")

import os
import shutil
import tempfile

from wpm_mcp_server import db

# Unit-test the containment rule enforced at server startup (server.py resolves
# DB_PATH via db.resolve_within_root against the project root — the directory
# holding wpm.config.json — not the host's cwd, so the guarantee holds no
# matter how the MCP host launched the server). Importing db directly avoids
# the module-level side effects of importing server.py.

orig_cwd = os.getcwd()
tmp = tempfile.mkdtemp(prefix="wpm-cstr-")
try:
    os.chdir(tmp)

    # 1. relative path inside root -> allowed
    inside = db.resolve_within_root("wpm/wpm.db", root=tmp)
    assert str(inside) == os.path.realpath(os.path.join(tmp, "wpm/wpm.db")), inside
    print("OK, relative inside root:", inside)

    # 2. absolute path inside root -> allowed
    abs_inside = db.resolve_within_root(os.path.join(tmp, "data", "mem.db"), root=tmp)
    assert str(abs_inside) == os.path.realpath(os.path.join(tmp, "data", "mem.db")), abs_inside
    print("OK, absolute inside root:", abs_inside)

    # 2b. root is explicit and independent of cwd: run from a different
    #     directory and the same relative path still resolves inside root.
    else_cwd = tempfile.mkdtemp(prefix="wpm-else-")
    os.chdir(else_cwd)
    elsewhere = db.resolve_within_root("wpm/wpm.db", root=tmp)
    assert str(elsewhere) == os.path.realpath(os.path.join(tmp, "wpm/wpm.db")), elsewhere
    print("OK, resolved against root regardless of cwd:", elsewhere)
    os.chdir(tmp)

    # 3. the root itself (a directory, never a valid SQLite file) -> rejected
    try:
        db.resolve_within_root(tmp, root=tmp)
        print("FAIL: expected RuntimeError for root itself")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, root itself rejected:", exc)

    # 4. relative path escaping via .. -> rejected
    try:
        db.resolve_within_root("../escaped.db", root=tmp)
        print("FAIL: expected RuntimeError for ../escaped.db")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, ../escaped.db rejected:", exc)

    # 5. absolute path outside root -> rejected
    outside = tempfile.mkdtemp(prefix="wpm-outside-")
    try:
        db.resolve_within_root(os.path.join(outside, "wpm.db"), root=tmp)
        print("FAIL: expected RuntimeError for outside path")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, absolute outside rejected:", exc)

    # 6. sibling whose name starts with root (prefix, not a directory) -> rejected
    sibling = tmp + "-sibling"
    try:
        db.resolve_within_root(os.path.join(sibling, "wpm.db"), root=tmp)
        print("FAIL: expected RuntimeError for sibling-prefix path")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, sibling-prefix path rejected:", exc)

    # 7. symlink inside root pointing outside -> rejected (realpath follows it)
    os.symlink(outside, os.path.join(tmp, "escaped-link"))
    try:
        db.resolve_within_root("escaped-link/wpm.db", root=tmp)
        print("FAIL: expected RuntimeError for symlink escape")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, symlink escape rejected:", exc)

    # 8. trailing separator -> rejected (a db_path must name a file)
    try:
        db.resolve_within_root(".wpm/wpm.db/", root=tmp)
        print("FAIL: expected RuntimeError for trailing-slash path")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, trailing-slash path rejected:", exc)

    # 9. no root argument -> defaults to cwd (backwards-compatible alias)
    backcompat = db.resolve_within_cwd("wpm/wpm.db")
    assert str(backcompat) == os.path.realpath(os.path.join(tmp, "wpm/wpm.db")), backcompat
    print("OK, default root = cwd (resolve_within_cwd alias):", backcompat)

finally:
    os.chdir(orig_cwd)
    shutil.rmtree(tmp, ignore_errors=True)

print("ALL OK")

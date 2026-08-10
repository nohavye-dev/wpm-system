import sys
sys.path.insert(0, "src")

import os
import shutil
import tempfile

from wpm_mcp_server import db

# Unit-test the containment rule enforced at server startup (server.py resolves
# DB_PATH via db.resolve_within_cwd against Path.cwd(), so an escaping db_path
# raises RuntimeError before the server starts). Importing db directly avoids
# the module-level side effects of importing server.py.

orig_cwd = os.getcwd()
tmp = tempfile.mkdtemp(prefix="wpm-cstr-")
try:
    os.chdir(tmp)

    # 1. relative path inside cwd -> allowed
    inside = db.resolve_within_cwd("wpm/wpm.db")
    assert str(inside) == os.path.realpath(os.path.join(tmp, "wpm/wpm.db")), inside
    print("OK, relative inside cwd:", inside)

    # 2. absolute path inside cwd -> allowed
    abs_inside = db.resolve_within_cwd(os.path.join(tmp, "data", "mem.db"))
    assert str(abs_inside) == os.path.realpath(os.path.join(tmp, "data", "mem.db")), abs_inside
    print("OK, absolute inside cwd:", abs_inside)

    # 3. the cwd itself (a directory, never a valid SQLite file) -> rejected
    try:
        db.resolve_within_cwd(tmp)
        print("FAIL: expected RuntimeError for cwd itself")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, cwd itself rejected:", exc)

    # 4. relative path escaping via .. -> rejected
    try:
        db.resolve_within_cwd("../escaped.db")
        print("FAIL: expected RuntimeError for ../escaped.db")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, ../escaped.db rejected:", exc)

    # 5. absolute path outside cwd -> rejected
    outside = tempfile.mkdtemp(prefix="wpm-outside-")
    try:
        db.resolve_within_cwd(os.path.join(outside, "wpm.db"))
        print("FAIL: expected RuntimeError for outside path")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, absolute outside rejected:", exc)

    # 6. sibling whose name starts with cwd (prefix, not a directory) -> rejected
    sibling = tmp + "-sibling"
    try:
        db.resolve_within_cwd(os.path.join(sibling, "wpm.db"))
        print("FAIL: expected RuntimeError for sibling-prefix path")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, sibling-prefix path rejected:", exc)

    # 7. symlink inside cwd pointing outside -> rejected (realpath follows it)
    os.symlink(outside, os.path.join(tmp, "escaped-link"))
    try:
        db.resolve_within_cwd("escaped-link/wpm.db")
        print("FAIL: expected RuntimeError for symlink escape")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, symlink escape rejected:", exc)

    # 8. trailing separator -> rejected (a db_path must name a file)
    try:
        db.resolve_within_cwd(".wpm/wpm.db/")
        print("FAIL: expected RuntimeError for trailing-slash path")
        raise SystemExit(1)
    except RuntimeError as exc:
        print("OK, trailing-slash path rejected:", exc)

finally:
    os.chdir(orig_cwd)
    shutil.rmtree(tmp, ignore_errors=True)

print("ALL OK")

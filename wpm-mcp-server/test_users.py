"""User profiles: path resolution, repository semantics, CLI wiring.

Script-style test (module-level asserts + prints), collected by conftest.
Covers the global users.db store: XDG/override path precedence, the user
entity (name/language/introduction), the unified observations table
(declared preferences + inferred patterns, reinforcement and
supersession), the current-user pointer, and the wpm CLI subcommands
(new-user, list-users, current-user, remove-user, user-observations,
remove-user-observation).
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Isolation: every scenario below runs against a throwaway store.
_tmp = tempfile.mkdtemp()
os.environ["WPM_USERS_DB_PATH"] = os.path.join(_tmp, "users.db")
os.environ.pop("XDG_CONFIG_HOME", None)

from wpm_mcp_server.storage.users import (  # noqa: E402
    UserRepository,
    connect_users_db,
    normalize_name,
    resolve_users_db_path,
)
from wpm_mcp_server.core.constants import (  # noqa: E402
    SUPPORTED_LANGUAGES,
    match_languages,
)
from wpm_mcp_server.prompts.user_profile import (  # noqa: E402
    RECURRENCE_THRESHOLD,
    build_current_user_block,
    format_current_user,
)


def check(label, cond, detail=""):
    if cond:
        print(f"  OK  {label}")
    else:
        raise AssertionError(f"FAIL {label}" + (f": {detail}" if detail else ""))


# ── path resolution ─────────────────────────────────────────────────────

check("override wins", str(resolve_users_db_path()) == os.environ["WPM_USERS_DB_PATH"])

os.environ.pop("WPM_USERS_DB_PATH", None)
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp, "xdg")
expected_xdg = Path(_tmp) / "xdg" / "wpm-system" / "users.db"
check("XDG_CONFIG_HOME honored", resolve_users_db_path() == expected_xdg)

os.environ.pop("XDG_CONFIG_HOME", None)
home_default = Path.home() / ".config" / "wpm-system" / "users.db"
check("falls back to ~/.config/wpm-system", resolve_users_db_path() == home_default)

os.environ["WPM_USERS_DB_PATH"] = os.path.join(_tmp, "users.db")

# ── language matcher ────────────────────────────────────────────────────

check("matcher: prefix, case-insensitive", match_languages("FR")[0] == "french")
check("matcher: empty query -> no matches", match_languages("") == [])
check("matcher: full list non-empty", len(SUPPORTED_LANGUAGES) > 40)

# ── repository semantics ────────────────────────────────────────────────

conn = connect_users_db(os.environ["WPM_USERS_DB_PATH"])
repo = UserRepository(conn)

check("normalize preserves case, collapses spaces", normalize_name("  Noha   A ") == "Noha A")
try:
    normalize_name("none")
    check("normalize rejects reserved 'none'", False)
except ValueError:
    check("normalize rejects reserved 'none'", True)

r1 = repo.save_user("Noha", language="french", introduction="dev full-stack")
check("first save reports created", r1["created"] is True, f"got {r1}")
check("save makes the profile current", repo.get_current_user()["name"] == "Noha")
check("language stored", r1["profile"]["language"] == "french")
check("introduction stored", r1["profile"]["introduction"] == "dev full-stack")

# Update: omitted fields keep their value; name is matched case-insensitively.
r2 = repo.save_user("noha", language="english")
check("second save reports updated", r2["created"] is False)
check("merge keeps unmentioned fields", r2["profile"]["introduction"] == "dev full-stack")
check("merge applies new values", r2["profile"]["language"] == "english")

repo.save_user("Marc", language="english")
check("saving another user switches current", repo.get_current_name() == "Marc")
check("get_user matches by raw casing", repo.get_user("mArc")["name"] == "Marc")

repo.set_current_user("nOha")
check("set_current_user normalizes and switches", repo.get_current_name() == "Noha")
try:
    repo.set_current_user("ghost")
    check("set_current_user rejects unknown", False)
except Exception:
    check("set_current_user rejects unknown", True)

removed = repo.remove_user("NOHA")
check("remove reports was_current", removed["was_current"] is True)
check("pointer cleared when removing current", repo.get_current_name() is None)

repo.set_current_user("Marc")

# ── unified observations (declared preferences + inferred patterns) ─────

try:
    repo.record_user_observation("no category given", source="inferred")
    check("inferred requires valid category", False)
except ValueError:
    check("inferred requires valid category", True)
try:
    repo.record_user_observation("junk category", source="inferred", category="free_form_junk")
    check("unknown category rejected", False)
except ValueError:
    check("unknown category rejected", True)
try:
    repo.record_user_observation("some content", source="bogus")
    check("unknown source rejected", False)
except ValueError:
    check("unknown source rejected", True)
try:
    repo.record_user_observation("", source="declared")
    check("empty content rejected", False)
except ValueError:
    check("empty content rejected", True)

o1 = repo.record_user_observation(
    "confuses rebase and merge semantics", source="inferred", category="workflow"
)
check("inferred created with count 1",
      o1["created"] is True and o1["observation"]["count"] == 1
      and o1["observation"]["source"] == "inferred", f"got {o1}")
o2 = repo.record_user_observation(
    "prefers terse commit messages", source="inferred", category="habit",
    reinforce_id=o1["observation"]["id"]
)
check("reinforce bumps count instead of duplicating",
      o2["created"] is False and o2["observation"]["count"] == 2, f"got {o2}")
check("reinforce refreshes content and category",
      o2["observation"]["content"] == "prefers terse commit messages"
      and o2["observation"]["category"] == "habit")
o3 = repo.record_user_observation(
    "wants honest pushback on ideas", source="inferred", category="personal"
)
try:
    repo.record_user_observation("y", source="inferred", category="habit",
                                 reinforce_id=99999)
    check("reinforce unknown id rejected", False)
except Exception:
    check("reinforce unknown id rejected", True)

# declared preferences: no category, never reinforced, always listed
d1 = repo.record_user_observation("talk to me more simply", source="declared")
check("declared created without category",
      d1["created"] is True and d1["observation"]["source"] == "declared"
      and d1["observation"]["category"] is None
      and d1["observation"]["count"] == 1, f"got {d1}")
try:
    repo.record_user_observation("x", source="declared",
                                 reinforce_id=o1["observation"]["id"])
    check("reinforce rejected on a declared recording", False)
except ValueError as exc:
    check("reinforce rejected on a declared recording", "reinforce" in str(exc), str(exc))
try:
    repo.record_user_observation("w", source="inferred", category="habit",
                                 replaces_id=d1["observation"]["id"])
    check("replaces rejected from an inferred recording", False)
except ValueError as exc:
    check("replaces rejected from an inferred recording", "declared" in str(exc), str(exc))

rows = repo.get_user_observations()
check("listing holds both sources before supersession",
      len(rows) == 3
      and sum(1 for r in rows if r["source"] == "declared") == 1
      and sum(1 for r in rows if r["source"] == "inferred") == 2, f"got {rows}")

# contradictory declaration supersedes the old one (hard delete)
d2 = repo.record_user_observation("be very detailed in explanations", source="declared")
d3 = repo.record_user_observation(
    "keep explanations short", source="declared", replaces_id=d2["observation"]["id"]
)
check("replacement reports the replaced id",
      d3.get("replaced") == d2["observation"]["id"], f"got {d3}")
try:
    repo.record_user_observation("ghost replacement", source="declared", replaces_id=99999)
    check("replace unknown declared id rejected", False)
except Exception:
    check("replace unknown declared id rejected", True)

declared_now = [r for r in repo.get_user_observations() if r["source"] == "declared"]
check("only surviving declarations remain",
      sorted(r["content"] for r in declared_now)
      == ["keep explanations short", "talk to me more simply"], f"got {declared_now}")

# ── rendering ───────────────────────────────────────────────────────────

check("empty profile renders to empty string", format_current_user(None) == "")
all_rows = repo.get_user_observations()
declared_rows = [r for r in all_rows if r["source"] == "declared"]
inferred_recurring = [
    r for r in all_rows
    if r["source"] == "inferred" and r["count"] >= RECURRENCE_THRESHOLD
]
check("threshold filters singletons", len(inferred_recurring) == 1,
      f"got {inferred_recurring}")

block = build_current_user_block(
    format_current_user(repo.get_current_user(), declared_rows, inferred_recurring)
)
check("block is tagged", block.startswith("<current-user>") and block.endswith("</current-user>"))
check("block carries identity", "name: Marc" in block and "respond in: english" in block, block)
check("block carries full declared section",
      "## User preferences" in block
      and "keep explanations short" in block
      and "talk to me more simply" in block, block)
check("block groups inferred by category with freshness",
      "### Habit" in block and "(seen x2, last " in block, block)
check("singletons excluded from block", "honest pushback" not in block)

# cascade: observations die with their user
repo.save_user("Temp")
tid = repo.record_user_observation(
    "temporary pattern", source="inferred", category="workflow"
)["observation"]["id"]
tdid = repo.record_user_observation("temp wants x", source="declared")["observation"]["id"]
repo.remove_user("Temp")
leftover_obs = repo.conn.execute("SELECT 1 FROM observations WHERE id=?", (tid,)).fetchone()
leftover_declared = repo.conn.execute(
    "SELECT 1 FROM observations WHERE id=?", (tdid,)
).fetchone()
check("removing a user cascades inferred observations", leftover_obs is None)
check("removing a user cascades declared statements", leftover_declared is None)
repo.set_current_user("Marc")

# ── capture flag ────────────────────────────────────────────────────────

check("capture enabled by default", repo.observations_enabled() is True)
repo.set_observations_enabled(False)
check("flag off round-trips", repo.observations_enabled() is False)
repo.set_observations_enabled(True)
check("flag on round-trips", repo.observations_enabled() is True)

# ── CLI wiring (subprocess, isolated store) ─────────────────────────────

_here = os.path.dirname(os.path.abspath(__file__))
cli_env = dict(os.environ)
cli_env["PYTHONPATH"] = os.path.join(_here, "src")
wpm_script = os.path.join(_here, "..", "scripts", "wpm")


def run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, wpm_script, *args],
        env=cli_env, capture_output=True, text=True, input=stdin,
    )


res = run_cli("list-users")
check("CLI list-users exits 0", res.returncode == 0, res.stderr)
check("CLI list-users shows marc", "Marc" in res.stdout, res.stdout)

res = run_cli("current-user")
check("CLI current-user shows current", "Marc" in res.stdout, res.stdout)

res = run_cli("current-user", "marc")
check("CLI switch to same name (case-insensitive) works", res.returncode == 0, res.stdout)

res = run_cli("current-user", "--language")
check("CLI current-user --language prints token", res.stdout.strip() == "english", repr(res.stdout))

res = run_cli("current-user", "ghost")
check("CLI unknown switch fails with known list",
      res.returncode == 1 and "ghost" in res.stdout and "Marc" in res.stdout, res.stdout)

# new-user: piped stdin (non-TTY fallback) -> created + current
res = run_cli("new-user", stdin="Alice\nfrench\nAI researcher\ny\n")
check("CLI new-user creates profile",
      res.returncode == 0 and "created" in res.stdout, res.stderr + res.stdout)
check("CLI new-user sets current", run_cli("current-user").stdout.startswith("current user: Alice"))
check("CLI new-user stored language", run_cli("current-user", "--language").stdout.strip() == "french")

# new-user: same name again -> updated
res = run_cli("new-user", stdin="Alice\nfrench\n\ny\n")
check("CLI new-user updates existing", res.returncode == 0 and "updated" in res.stdout, res.stdout)

# new-user: abort at confirmation
res = run_cli("new-user", stdin="Bob\nenglish\n\nn\n")
check("CLI new-user abort keeps nothing",
      res.returncode == 0 and "aborted" in res.stdout
      and not any(u["name"] == "Bob" for u in repo.get_users()), res.stdout)

# observations were recorded for Marc during the repo tests: switch back.
run_cli("current-user", "marc")
res = run_cli("user-observations")
check("CLI user-observations lists declared group first",
      res.returncode == 0
      and "declared preferences:" in res.stdout
      and "terse commit" in res.stdout,
      res.stdout)
check("CLI user-observations shows counts for inferred",
      "x2" in res.stdout, res.stdout)

res = run_cli("user-observations", "off")
check("CLI toggle off", repo.observations_enabled() is False and "disabled" in res.stdout)
res = run_cli("user-observations", "on")
check("CLI toggle on", repo.observations_enabled() is True)

res = run_cli("remove-user", "marc", "--yes")
check("CLI remove-user --yes removes", res.returncode == 0 and "removed" in res.stdout, res.stdout)

print("\nAll user-profile checks passed.")

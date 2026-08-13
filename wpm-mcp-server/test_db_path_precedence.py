import json
import os
import subprocess
import sys
import tempfile

# Case A: only wpm.config.json sets db_path -> server should use it
workdir_a = tempfile.mkdtemp()
db_path_a = os.path.join(workdir_a, "from_json.db")
with open(os.path.join(workdir_a, "wpm.config.json"), "w") as f:
    json.dump({"db_path": db_path_a}, f)

env_a = dict(os.environ)
env_a.pop("WPM_DB_PATH", None)
env_a["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
subprocess.run(
    [sys.executable, "-c", "from wpm_mcp_server.server import DB_PATH; print(DB_PATH)"],
    cwd=workdir_a,
    env=env_a,
    check=True,
)

# Case B: env var WPM_DB_PATH set too -> env wins over JSON
db_path_b_env = os.path.join(workdir_a, "from_env.db")
env_b = dict(env_a)
env_b["WPM_DB_PATH"] = db_path_b_env
result = subprocess.run(
    [sys.executable, "-c", "from wpm_mcp_server.server import DB_PATH; print(DB_PATH)"],
    cwd=workdir_a,
    env=env_b,
    check=True,
    capture_output=True,
    text=True,
)
printed = result.stdout.strip()
assert printed == db_path_b_env, f"expected env var to win, got {printed}"
print("OK: env var WPM_DB_PATH overrides wpm.config.json db_path ->", printed)

# Case C: no db_path anywhere -> the server stays inert (DB_PATH is None,
# tools return a clear "not activated" error) instead of crashing at import.
workdir_c = tempfile.mkdtemp()
with open(os.path.join(workdir_c, "wpm.config.json"), "w") as f:
    json.dump({"confidence_threshold": 0.6}, f)

env_c = dict(os.environ)
env_c.pop("WPM_DB_PATH", None)
env_c["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
result_c = subprocess.run(
    [sys.executable, "-c", "from wpm_mcp_server.server import DB_PATH; print(DB_PATH)"],
    cwd=workdir_c,
    env=env_c,
    capture_output=True,
    text=True,
)
assert result_c.returncode == 0, f"expected inert startup, got rc={result_c.returncode}: {result_c.stderr}"
assert result_c.stdout.strip() == "None", f"expected DB_PATH=None, got {result_c.stdout.strip()}"
print("OK: missing db_path starts inert (DB_PATH=None)")

# Case D: WPM_CONFIG_PATH points at a config elsewhere, server launched from a
# different cwd -> db_path must resolve relative to the CONFIG's directory,
# not the host's cwd (the pure-MCP guarantee).
workdir_d = tempfile.mkdtemp()
config_d = os.path.join(workdir_d, "wpm.config.json")
with open(config_d, "w") as f:
    json.dump({"db_path": ".wpm/rel.db"}, f)
env_d = dict(os.environ)
env_d.pop("WPM_DB_PATH", None)
env_d["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
env_d["WPM_CONFIG_PATH"] = config_d
result_d = subprocess.run(
    [sys.executable, "-c", "from wpm_mcp_server.server import DB_PATH; print(DB_PATH)"],
    cwd=tempfile.mkdtemp(),
    env=env_d,
    capture_output=True,
    text=True,
)
expected_d = os.path.realpath(os.path.join(workdir_d, ".wpm/rel.db"))
assert result_d.returncode == 0, f"unexpected failure: {result_d.stderr}"
assert result_d.stdout.strip() == expected_d, f"expected {expected_d}, got {result_d.stdout.strip()}"
print("OK: db_path resolved relative to config dir, not the host cwd ->", result_d.stdout.strip())

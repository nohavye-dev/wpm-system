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

# Case C: no db_path anywhere -> server must fail with a clear error
workdir_c = tempfile.mkdtemp()
with open(os.path.join(workdir_c, "wpm.config.json"), "w") as f:
    json.dump({"confidence_threshold": 0.6}, f)

env_c = dict(os.environ)
env_c.pop("WPM_DB_PATH", None)
env_c["PYTHONPATH"] = os.path.join(os.getcwd(), "src")
result_c = subprocess.run(
    [sys.executable, "-c", "from wpm_mcp_server.server import DB_PATH"],
    cwd=workdir_c,
    env=env_c,
    capture_output=True,
    text=True,
)
assert result_c.returncode != 0, f"expected failure, got returncode {result_c.returncode}"
assert "db_path" in result_c.stderr, f"expected 'db_path' in stderr, got: {result_c.stderr}"
print("OK: missing db_path raises")

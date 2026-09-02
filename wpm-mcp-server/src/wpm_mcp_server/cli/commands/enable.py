from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from wpm_mcp_server.cli.confirm import confirm
from wpm_mcp_server.cli.db import resolve_project_db, resolve_wpm_config
from wpm_mcp_server.cli.paths import DATA_DIR


def cmd_enable(db_dir: str | None, assume_yes: bool) -> None:
    config_path = resolve_wpm_config()
    exists = config_path.exists()

    data: dict = {}
    if exists:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    if not data.get("db_path"):
        data["db_path"] = f"{db_dir}/wpm.db" if db_dir else ".wpm/wpm.db"

    schema_file = Path(DATA_DIR) / "wpm.config.schema.json"
    if schema_file.exists():
        data.setdefault("$schema", str(schema_file))

    resolved = resolve_project_db(data["db_path"])

    if not assume_yes and not confirm(
        f"Write {config_path} with db_path={data['db_path']}? [y/N] "
    ):
        print("wpm: aborted — nothing written")
        sys.exit(0)

    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    rel_path = os.path.relpath(str(resolved), str(Path.cwd()))
    db_dir_path = os.path.dirname(rel_path)
    if db_dir_path and db_dir_path != ".":
        (Path.cwd() / db_dir_path).mkdir(parents=True, exist_ok=True)
        gitignore_entry = db_dir_path + os.sep
    else:
        gitignore_entry = os.path.basename(rel_path)

    gitignore = Path.cwd() / ".gitignore"
    if not gitignore.exists() or gitignore_entry not in gitignore.read_text(encoding="utf-8"):
        with gitignore.open("a", encoding="utf-8") as f:
            f.write(f"# weighted persistent memory\n{gitignore_entry}\n")

    from wpm_mcp_server.infra import database as wdb

    conn = wdb.connect(str(resolved))
    conn.close()

    print(f"wpm: activated (wpm.config.json written, db_path={data['db_path']})")
    print("wpm: the MCP server is registered by the OpenCode plugin — restart opencode")

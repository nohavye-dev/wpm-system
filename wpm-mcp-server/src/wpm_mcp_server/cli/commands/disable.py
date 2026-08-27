from __future__ import annotations

import json

from wpm_mcp_server.cli.db import resolve_wpm_config


def cmd_disable() -> None:
    config_path = resolve_wpm_config()
    db_path = None
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        db_path = data.get("db_path")
        config_path.unlink()
    print("wpm: wpm.config.json removed")
    if db_path:
        print(f"note: the database at {db_path} was NOT deleted")
    print("note: remove the 'wpm' MCP server entry from your host")
    print("      configuration (opencode.json) — it stays active until then")

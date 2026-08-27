from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wpm_mcp_server.cli._silence import silence_third_party
from wpm_mcp_server.cli.db import resolve_wpm_config


def cmd_export(args: argparse.Namespace) -> None:
    config_path = resolve_wpm_config()
    if not config_path.exists():
        print("wpm: not activated here. Run 'wpm enable' first.", file=sys.stderr)
        sys.exit(1)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_path_raw = config.get("db_path", "")
    if not db_path_raw:
        print("wpm: db_path not set in wpm.config.json", file=sys.stderr)
        sys.exit(1)

    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path_raw).resolve()

    if not db_path.exists():
        print(f"wpm: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    silence_third_party()

    from wpm_mcp_server.infra import database as db
    from wpm_mcp_server.storage import export_db

    conn = db.connect(str(db_path))
    data = export_db(conn)
    conn.close()

    output = json.dumps(data, indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
        total = len(data["entries"]) + len(data["entry_events"]) + len(data["entry_links"])
        print(f"wpm: exported {total} records to {out_path}")
    else:
        print(output)

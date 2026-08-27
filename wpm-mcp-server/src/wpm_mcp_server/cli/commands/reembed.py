from __future__ import annotations

import json
import sys

from wpm_mcp_server.cli._silence import silence_third_party
from wpm_mcp_server.cli.db import resolve_project_db, resolve_wpm_config


def cmd_reembed() -> None:
    config_path = resolve_wpm_config()
    if not config_path.exists():
        print("wpm: not activated here. Run 'wpm enable' first.", file=sys.stderr)
        sys.exit(1)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_path_raw = config.get("db_path", "")
    if not db_path_raw:
        print("wpm: db_path not set in wpm.config.json", file=sys.stderr)
        sys.exit(1)

    db_path = resolve_project_db(db_path_raw)
    if not db_path.exists():
        print(f"wpm: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    silence_third_party()

    from wpm_mcp_server.infra import database as db
    from wpm_mcp_server.infra.embeddings import get_provider, resolve_model_name
    from wpm_mcp_server.storage import reembed_all

    model = resolve_model_name()
    print(f"wpm: loading embedding model '{model}'...")
    embedder = get_provider()

    conn = db.connect(str(db_path))
    result = reembed_all(conn, embedder, model)
    conn.close()

    print(f"wpm: re-embedded {result['reembedded']} entries with model '{result['model']}'")

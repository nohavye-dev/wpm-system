from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from wpm_mcp_server.cli._silence import silence_third_party
from wpm_mcp_server.cli.db import resolve_wpm_config


def _print_text(result: dict) -> None:
    direct = result.get("direct_matches", [])
    related = result.get("related_context", [])
    conflicts = result.get("conflicts", [])

    if direct:
        print(f"Direct matches ({len(direct)}):")
        for m in direct:
            eid = m["entry_id"][:8]
            typ = m["type"]
            conf = m["confidence"]
            score = m.get("score", conf)
            status = m.get("status", "active")
            content = m["content"].replace("\n", " ")[:80]
            print(f"  {eid}  {typ:<16} {conf:.2f}  {score:.2f}  {status:<9} {content}")
        print()

    if related:
        print(f"Related context ({len(related)}):")
        for m in related:
            eid = m["entry_id"][:8]
            typ = m["type"]
            score = m.get("score", 0)
            status = m.get("status", "active")
            content = m["content"].replace("\n", " ")[:80]
            print(f"  {eid}  {typ:<16} {score:.2f}  {status:<9} {content}")
        print()

    if conflicts:
        print("Conflicts:")
        for c in conflicts:
            src = c["entry_id"][:8]
            tgt = c["contradicted_by"][:8]
            print(f"  {src}  ↔  {tgt}")
    else:
        action = any([direct, related])
        if action:
            print("Conflicts: none")


def cmd_search(args: argparse.Namespace) -> None:
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

    from wpm_mcp_server.config import load_settings
    from wpm_mcp_server.infra import database as db
    from wpm_mcp_server.infra.embeddings import get_provider, resolve_model_name
    from wpm_mcp_server.storage import Repository

    settings = load_settings(config_path)
    os.chdir(str(Path.cwd()))
    conn = db.connect(str(db_path))
    try:
        repo = Repository(
            conn=conn,
            embedder=get_provider(),
            settings=settings.domain,
            model_name=resolve_model_name(),
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    result = repo.query_context(
        query=args.query,
        min_confidence=args.min_confidence or 0.0,
        token_budget=999_999,
    )
    conn.close()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_text(result)

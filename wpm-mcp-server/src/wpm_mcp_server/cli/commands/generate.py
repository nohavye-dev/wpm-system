from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wpm_mcp_server.cli._silence import silence_third_party
from wpm_mcp_server.cli.db import resolve_wpm_config


def cmd_generate(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"wpm: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    raw = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not all(k in raw for k in ("entries", "entry_events", "entry_links")):
        print("wpm: invalid export file — expected keys: entries, entry_events, entry_links", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    silence_third_party()

    from wpm_mcp_server.config import load_settings
    from wpm_mcp_server.infra.embeddings import get_provider, resolve_model_name
    from wpm_mcp_server.storage import generate_db

    config_path = resolve_wpm_config()
    settings = load_settings(config_path)

    print("wpm: loading embedding model...")
    embedder = get_provider()

    generate_db(
        db_path=str(output_path),
        json_data=raw,
        embedder=embedder,
        settings=settings.domain,
        model_name=resolve_model_name(),
    )

    n_entries = len(raw["entries"])
    n_events = len(raw["entry_events"])
    n_links = len(raw["entry_links"])
    print(f"wpm: generated database at {output_path}")
    print(f"     {n_entries} entries, {n_events} events, {n_links} links — embeddings regenerated")

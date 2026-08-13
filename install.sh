#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wpm-system"
GLOBAL_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"

if [ "${1:-}" = "uninstall" ]; then
  if [ -x "$BIN_DIR/wpm" ]; then
    exec "$BIN_DIR/wpm" uninstall
  fi
  if [ -x "$BUNDLE_DIR/scripts/wpm" ]; then
    exec "$BUNDLE_DIR/scripts/wpm" uninstall
  fi
  printf 'wpm is not installed\n' >&2
  exit 1
fi

printf 'creating server venv...\n'
python3 -m venv "$DATA_DIR/venv"
"$DATA_DIR/venv/bin/python" -m pip install --upgrade pip
"$DATA_DIR/venv/bin/python" -m pip install "$BUNDLE_DIR/wpm-mcp-server"

printf 'pre-downloading embedding model (~80 MB)...\n'
"$DATA_DIR/venv/bin/python" -c "
from huggingface_hub import hf_hub_download
repo = 'sentence-transformers/all-MiniLM-L6-v2'
for f in ['tokenizer.json', 'onnx/model.onnx']:
    try:
        p = hf_hub_download(repo, f)
        print(f'cached: {p}')
    except Exception as e:
        print(f'warning: could not cache {f}: {e}')
" || printf 'warning: model pre-download failed (will download on first use)\n'

printf 'installing global commands...\n'
mkdir -p "$GLOBAL_CONFIG_DIR/commands"
cp "$BUNDLE_DIR/wpm-commands"/wpm-doc.md "$BUNDLE_DIR/wpm-commands"/wpm-code.md "$BUNDLE_DIR/wpm-commands"/wpm-review.md "$BUNDLE_DIR/wpm-commands"/wpm-bootstrap.md "$BUNDLE_DIR/wpm-commands"/wpm-patterns.md "$GLOBAL_CONFIG_DIR/commands/"

printf 'installing wpm command...\n'
mkdir -p "$BIN_DIR"
cp "$BUNDLE_DIR/scripts/wpm" "$BIN_DIR/wpm"
chmod +x "$BIN_DIR/wpm"
sed -i "1s|^#!/usr/bin/env python3|#!$DATA_DIR/venv/bin/python3|" "$BIN_DIR/wpm"

printf 'wpm installed. In each project: wpm enable --write-config\n'
printf 'then add the MCP server snippet printed by "wpm enable" to your host config.\n'
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  printf 'add %s to your PATH\n' "$BIN_DIR"
fi

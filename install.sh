#!/usr/bin/env bash
set -euo pipefail

SOURCE_REF="${WPM_SOURCE_REF:-main}"
REPO_URL="${WPM_REPO_URL:-https://github.com/nohavye-dev/wpm-system}"
SOURCE_TARBALL="${WPM_SOURCE_TARBALL:-$REPO_URL/archive/refs/heads/$SOURCE_REF.tar.gz}"
SOURCE_SHA256SUMS="${WPM_SOURCE_SHA256SUMS:-$REPO_URL/raw/$SOURCE_REF/SHA256SUMS}"

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" && pwd 2>/dev/null || true)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wpm-system"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"

if [ ! -f "$BUNDLE_DIR/wpm-mcp-server/pyproject.toml" ]; then
  printf 'source bundle not found locally — downloading from %s (%s)...\n' "$REPO_URL" "$SOURCE_REF"
  if ! command -v curl >/dev/null 2>&1; then
    printf 'curl is required to install directly from GitHub\n' >&2
    exit 1
  fi
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  curl -fsSL "$SOURCE_TARBALL" -o "$TMP_DIR/source.tar.gz"
  curl -fsSL "$SOURCE_SHA256SUMS" -o "$TMP_DIR/SHA256SUMS"
  tar -xz -C "$TMP_DIR" -f "$TMP_DIR/source.tar.gz" --strip-components=1
  if ! (cd "$TMP_DIR" && sha256sum -c SHA256SUMS --status); then
    printf 'checksum verification failed — the downloaded source bundle was corrupted or tampered with\n' >&2
    exit 1
  fi
  BUNDLE_DIR="$TMP_DIR"
  if [ ! -f "$BUNDLE_DIR/wpm-mcp-server/pyproject.toml" ]; then
    printf 'invalid source bundle\n' >&2
    exit 1
  fi
fi

printf 'creating server venv...\n'
python3 -m venv "$DATA_DIR/venv"
"$DATA_DIR/venv/bin/python" -m pip install --upgrade pip
"$DATA_DIR/venv/bin/python" -m pip install "$BUNDLE_DIR/wpm-mcp-server"

printf 'pre-downloading embedding model (~120 MB)...\n'
"$DATA_DIR/venv/bin/python" -c "
from huggingface_hub import hf_hub_download
import platform
repo = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
machine = platform.machine().lower()
if machine in ('arm64', 'aarch64'):
    onnx_file = 'onnx/model_qint8_arm64.onnx'
elif machine in ('x86_64', 'amd64'):
    onnx_file = 'onnx/model_quint8_avx2.onnx'
else:
    onnx_file = 'onnx/model.onnx'
for f in ['tokenizer.json', onnx_file]:
    try:
        p = hf_hub_download(repo, f)
        print(f'cached: {p}')
    except Exception as e:
        print(f'warning: could not cache {f}: {e}')
" || printf 'warning: model pre-download failed (will download on first use)\n'

printf 'installing wpm command...\n'
mkdir -p "$BIN_DIR"
cp "$BUNDLE_DIR/scripts/wpm" "$BIN_DIR/wpm"
chmod +x "$BIN_DIR/wpm"
sed -i "1s|^#!/usr/bin/env python3|#!$DATA_DIR/venv/bin/python3|" "$BIN_DIR/wpm"

printf 'installing config schema (editor validation)...\n'
cp "$BUNDLE_DIR/wpm-mcp-server/wpm.config.schema.json" "$DATA_DIR/wpm.config.schema.json"

printf 'installing OpenCode plugin (global)...\n'
cp "$BUNDLE_DIR/wpm-opencode-plugin/plugin.ts" "$DATA_DIR/plugin.ts"
cp -r "$BUNDLE_DIR/wpm-opencode-plugin/wpm-lib" "$DATA_DIR/wpm-lib"
PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/plugins"
mkdir -p "$PLUGIN_DIR"
cp "$BUNDLE_DIR/wpm-opencode-plugin/plugin.ts" "$PLUGIN_DIR/wpm-plugin.ts"
cp -r "$BUNDLE_DIR/wpm-opencode-plugin/wpm-lib" "$PLUGIN_DIR/wpm-lib"

printf 'wpm installed. In each project: wpm enable\n'
printf 'the MCP server is registered automatically by the plugin (no opencode.json entry needed)\n'
printf 'restart opencode after enabling a project\n'
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  printf 'add %s to your PATH\n' "$BIN_DIR"
fi

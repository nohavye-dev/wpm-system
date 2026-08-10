#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wpm-system"
GLOBAL_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"

usage() {
  printf 'usage: wpm enable | wpm disable | wpm uninstall\n' >&2
}

enable() {
  local project="$PWD"
  local db_path
  db_path="$(python3 - "$project/wpm.config.json" "$project" <<'PYEOF'
import json
import os
import sys
path = sys.argv[1]
project = sys.argv[2]
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
if not data.get("db_path"):
    data["db_path"] = ".wpm/wpm.db"
db_path = data["db_path"]
if db_path.endswith(os.sep):
    sys.stderr.write("wpm: error: db_path must be a file (no trailing separator)\n")
    sys.exit(1)
resolved = os.path.realpath(os.path.join(project, db_path))
root = os.path.realpath(project)
if resolved == root:
    sys.stderr.write("wpm: error: db_path must be a file, not the project root directory\n")
    sys.exit(1)
if not resolved.startswith(root + os.sep):
    sys.stderr.write("wpm: error: db_path must live inside the project directory\n")
    sys.exit(1)
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(db_path)
PYEOF
)"
  local db_dir rel_path="" gitignore_entry=""
  case "$db_path" in
    /*) rel_path="${db_path#"$project/"}" ;;
    *) rel_path="$db_path" ;;
  esac

  db_dir="$(dirname "$rel_path")"
  if [ "$db_dir" = "." ]; then
    mkdir -p "$project"
    gitignore_entry="$(basename "$rel_path")"
  else
    mkdir -p "$project/$db_dir"
    gitignore_entry="$db_dir/"
  fi
  local gitignore="$project/.gitignore"
  if [ ! -f "$gitignore" ] || ! grep -qE "^${gitignore_entry}$" "$gitignore"; then
    printf '# weighted persistent memory\n%s\n' "$gitignore_entry" >> "$gitignore"
  fi
  printf 'wpm: activated (wpm.config.json written, db_path=%s)\n' "$db_path"
  printf 'restart opencode for the change to take effect\n'
}

disable() {
  local project="$PWD"
  if [ -f "$project/wpm.config.json" ]; then
    rm "$project/wpm.config.json"
  fi
  printf 'wpm: deactivated\n'
  printf 'note: the database (see db_path in the removed config) was NOT deleted\n'
}

uninstall() {
  rm -rf "$GLOBAL_CONFIG_DIR/plugins/wpm-plugin"
  rm -f "$GLOBAL_CONFIG_DIR/commands/wpm-doc.md" "$GLOBAL_CONFIG_DIR/commands/wpm-code.md"
  if [ -f "$GLOBAL_CONFIG_DIR/package.json" ]; then
    python3 - "$GLOBAL_CONFIG_DIR/package.json" <<'PYEOF'
import json
import os
import sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
deps = data.get("dependencies")
if isinstance(deps, dict):
    deps.pop("@opencode-ai/plugin", None)
    deps.pop("@modelcontextprotocol/sdk", None)
    if not deps:
        data.pop("dependencies", None)
if not data:
    os.remove(path)
else:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
PYEOF
  fi
  rmdir "$GLOBAL_CONFIG_DIR/plugins" 2>/dev/null || true
  rmdir "$GLOBAL_CONFIG_DIR/commands" 2>/dev/null || true
  rm -rf "$DATA_DIR"
  rm -f "$BIN_DIR/wpm"
  printf 'wpm: fully uninstalled\n'
}

case "${1:-}" in
  enable) enable ;;
  disable) disable ;;
  uninstall) uninstall ;;
  *) usage; exit 1 ;;
esac

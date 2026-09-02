#!/usr/bin/env bash
set -euo pipefail

# setup-dev.sh — environnement dev complet pour wpm-system (fresh clone)
# Usage: bash scripts/setup-dev.sh  (depuis la racine du repo)
# Prérequis: Python >=3.11, Bun 1.4.0, sha256sum

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/wpm-mcp-server/.venv"
PYTHON="${PYTHON:-python3}"

echo "[setup-dev] Python: $($PYTHON --version)"
echo "[setup-dev] Bun: $(bun --version 2>/dev/null || echo 'non trouvé — installez Bun 1.4.0')"

# 1. venv Python
if [ ! -d "$VENV" ]; then
  echo "[setup-dev] création venv $VENV"
  $PYTHON -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip -q
echo "[setup-dev] pip install -e wpm-mcp-server[dev]"
"$VENV/bin/pip" install -e "$ROOT/wpm-mcp-server[dev]" -q

# 2. plugin
echo "[setup-dev] bun install wpm-opencode-plugin"
bun install --cwd "$ROOT/wpm-opencode-plugin" --silent

# 3. pre-commit (ruff-format + schema + checksums)
echo "[setup-dev] pre-commit install"
"$VENV/bin/pre-commit" install

# 4. vérifs
echo "[setup-dev] vérifications..."
"$VENV/bin/ruff" format --check "$ROOT/wpm-mcp-server"
"$ROOT/wpm-opencode-plugin/node_modules/.bin/tsc" --noEmit --project "$ROOT/wpm-opencode-plugin/tsconfig.json"
echo "[setup-dev] tsc OK"
python "$ROOT/scripts/generate_config_schema.py" --check
echo "[setup-dev] schema OK"

# mypy manuel (non bloquant)
echo "[setup-dev] mypy (manuel, non bloquant)..."
if "$VENV/bin/mypy" "$ROOT/wpm-mcp-server/src" --ignore-missing-imports --show-error-codes; then
  echo "[setup-dev] mypy OK"
else
  echo "[setup-dev] mypy: warnings (voir ci-dessus) — non bloquant"
fi

echo "[setup-dev] prêt — hooks: ruff-format + schema + checksums"
echo "  manuel: $VENV/bin/ruff check wpm-mcp-server | $VENV/bin/mypy wpm-mcp-server/src"

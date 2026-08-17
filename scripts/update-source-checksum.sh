#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v sha256sum >/dev/null 2>&1; then
  printf 'error: sha256sum is required\n' >&2
  exit 1
fi

TMP_INDEX="$(mktemp)"
trap 'rm -f "$TMP_INDEX"' EXIT
GIT_INDEX_FILE="$TMP_INDEX" git read-tree HEAD
GIT_INDEX_FILE="$TMP_INDEX" git add -A

GIT_INDEX_FILE="$TMP_INDEX" git ls-files -z \
  | grep -zvxE '^SHA256SUMS$|^scripts/update-source-checksum\.sh$' \
  | xargs -0 sha256sum \
  > SHA256SUMS.tmp
mv SHA256SUMS.tmp SHA256SUMS

printf 'SHA256SUMS updated (%s files)\n' "$(wc -l < SHA256SUMS)"

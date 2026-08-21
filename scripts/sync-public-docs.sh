#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WPM_SITE_DIR="${WPM_SITE_DIR:-$REPO_ROOT/../wpm-site}"
PUBLIC_DOCS="$REPO_ROOT/docs/public"
SITE_DOCS="$WPM_SITE_DIR/docs"
DEFAULT_MSG="docs: sync public docs from wpm-system"

usage() {
  echo "Usage: $(basename "$0") [-m <commit message>]" >&2
  exit 1
}

die() {
  echo "ERREUR: $*" >&2
  exit 1
}

msg="$DEFAULT_MSG"
while getopts ":m:h" opt; do
  case "$opt" in
    m) msg="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

[ -d "$PUBLIC_DOCS" ] || die "dossier source introuvable: $PUBLIC_DOCS"
[ -d "$WPM_SITE_DIR/.git" ] || die "wpm-site introuvable ou pas un repo git: $WPM_SITE_DIR"

branch="$(git -C "$REPO_ROOT" branch --show-current)"
[ "$branch" = "main" ] || die "wpm-system n'est pas sur main (branche actuelle: $branch)"

if [ -n "$(git -C "$WPM_SITE_DIR" status --porcelain)" ]; then
  git -C "$WPM_SITE_DIR" status --short
  die "wpm-site contient des modifications non commitées, synchronisation annulée."
fi

echo "Vérification de la connectivité vers origin (wpm-site)..."
if ! timeout 15 git -C "$WPM_SITE_DIR" ls-remote origin HEAD >/dev/null 2>&1; then
  die "réseau indisponible: impossible de joindre origin de wpm-site (timeout 15s), synchronisation annulée."
fi

rsync -a --delete "$PUBLIC_DOCS/" "$SITE_DOCS/"

if [ -z "$(git -C "$WPM_SITE_DIR" status --porcelain)" ]; then
  echo "Aucun changement à synchroniser, wpm-site est déjà à jour."
  exit 0
fi

echo "Changements détectés dans wpm-site :"
git -C "$WPM_SITE_DIR" status --short

git -C "$WPM_SITE_DIR" add docs
git -C "$WPM_SITE_DIR" commit -m "$msg"
git -C "$WPM_SITE_DIR" push origin HEAD
echo "Synchronisation terminée et poussée sur origin."

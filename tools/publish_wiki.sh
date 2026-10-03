#!/usr/bin/env bash
# Publish docs/wiki/*.md to the GitHub wiki.
#
# The pages live in the repo so the test suite can pin them; the wiki is a
# separate git repository that only this script writes. Run it from a checkout
# of main after the pages change:
#
#   bash tools/publish_wiki.sh                 # haksanlulz/GUDBUS
#   WIKI_REMOTE=<url> bash tools/publish_wiki.sh
#
# The wiki repository exists only after its first page is created in the web
# UI; until then the clone below fails.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
REMOTE=${WIKI_REMOTE:-https://github.com/haksanlulz/GUDBUS.wiki.git}
SRC="$ROOT/docs/wiki"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git clone -q "$REMOTE" "$TMP/wiki"
# Mirror: pages removed from docs/wiki are removed from the wiki too.
find "$TMP/wiki" -maxdepth 1 -name '*.md' -delete
cp "$SRC"/*.md "$TMP/wiki/"

cd "$TMP/wiki"
git add -A
if git diff --cached --quiet; then
    echo "wiki already matches docs/wiki"
    exit 0
fi
rev=$(git -C "$ROOT" rev-parse --short HEAD)
git commit -q -m "Sync from docs/wiki at $rev"
git push -q origin HEAD
echo "wiki published from $rev"

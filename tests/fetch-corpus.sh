#!/usr/bin/env bash
# Fetch the pinned test corpus into tests/corpus/.
#
# Deliberately not run by tests/run.sh. A suite that reaches the network is a
# suite that fails on a train, and one that silently downloads 25 MB the first
# time you run it is worse. Fetching is a thing you ask for.
#
# Idempotent: a source already sitting at its pinned commit is left alone, so
# re-running this costs one rev-parse per source.
set -eu
cd "$(dirname "$0")"
PINS=corpus.txt
DEST=corpus

mkdir -p "$DEST"
while read -r name url commit; do
  case "${name:-#}" in ''|'#'*) continue ;; esac
  dir="$DEST/$name"
  if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" = "$commit" ]; then
    printf '  %-16s already at %s\n' "$name" "${commit:0:8}"
    continue
  fi
  printf '  %-16s fetching %s\n' "$name" "${commit:0:8}"
  rm -rf "$dir"
  git init -q "$dir"
  git -C "$dir" remote add origin "$url"
  git -C "$dir" fetch -q --depth 1 origin "$commit"
  git -C "$dir" checkout -q FETCH_HEAD
done < "$PINS"

printf '  %s documents under %s/\n' \
  "$(find "$DEST" -name '*.md' -not -path '*/.git/*' | wc -l | tr -d ' ')" "$DEST"

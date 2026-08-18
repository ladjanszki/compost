#!/usr/bin/env bash
# Every suite, in one command. Needs pandoc on PATH.
set -u
cd "$(dirname "$0")/.."
fail=0
for t in test_records test_sabotage test_store test_views test_citations \
         test_bleach_session test_session test_session_views; do
  out=$(python3 -m "tests.$t" 2>&1) || fail=1
  printf "%-24s %s\n" "$t" "$(printf '%s' "$out" | tail -1)"
done
exit $fail

#!/usr/bin/env bash
# Every suite, in one command. Needs pandoc on PATH.
#
# Each suite's LAST line is its verdict and every verdict starts "N/M ". That is
# checked here rather than remembered: test_records used to print a coverage
# histogram after its verdict, so `tail -1` reported the histogram and hid the
# 520/520 the whole record format rests on.
set -u
cd "$(dirname "$0")/.."
fail=0
for t in test_records test_sabotage test_store test_views test_citations \
         test_bleach_session test_session test_session_views test_lookup \
         test_serve test_manpage; do
  out=$(python3 -m "tests.$t" 2>&1) || fail=1
  last=$(printf '%s' "$out" | tail -1)
  case "$last" in
    [0-9]*/[0-9]*\ *) ;;
    *) last="no verdict line: $last"; fail=1 ;;
  esac
  printf "%-24s %s\n" "$t" "$last"
done
exit $fail

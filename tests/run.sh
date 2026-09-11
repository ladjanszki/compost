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
for t in test_records test_sabotage test_store test_digest test_views test_citations \
         test_bleach_session test_session test_session_views test_lookup \
         test_serve test_manpage test_grammar test_layer test_draw test_response test_loop \
         test_dj_prepare test_v01_dictionary test_query test_extras \
         test_mapping_totality test_aota test_sections test_lists; do
  out=$(python3 -m "tests.$t" 2>&1) || fail=1
  last=$(printf '%s' "$out" | tail -1)
  case "$last" in
    [0-9]*/[0-9]*\ *) ;;
    *) last="no verdict line: $last"; fail=1 ;;
  esac
  printf "%-24s %s\n" "$t" "$last"
done

# Which tier just ran. Without this the board looks identical either way, and
# "520/520" and "5/5" are the same shape — a green run on 1% of the material
# should never be indistinguishable from the real thing.
if [ -d tests/corpus ] && [ -n "$(ls -A tests/corpus 2>/dev/null)" ]; then
  n=$(find tests/corpus -name '*.md' -not -path '*/.git/*' | wc -l | tr -d ' ')
  printf "%-24s %s\n" "corpus" "present, $n documents"
else
  printf "%-24s %s\n" "corpus" "ABSENT — smoke set only; ./tests/fetch-corpus.sh to fetch it"
fi
exit $fail

# kgb — look up a block by handle.
#
#   source tools/kgb.sh
#   kgb 6dec66c3
#   kgb '{#6dec66c3}'      # braces, # and +++ are stripped
#
# Prints the block, then everything that cites it.
# Reads site/blocks.json, so run `kg render` first if the base has changed.

kgb() {
  local h f
  h=$(printf '%s' "$1" | tr -d '{}#+@' | cut -c1-8)
  f="${KG_HOME:-$PWD}/site/blocks.json"
  [ -f "$f" ] || { echo "no $f — run kg render" >&2; return 1; }

  jq -r --arg h "$h" '
    (
      [.[] | select(.handle == $h)] as $b
      | if ($b | length) == 0 then "no block \($h)"
        else $b[0] | "{#\(.handle)}  \(.type) · \(.author // "-") · \(.source)\n\n\(.text)\n"
        end
    ),
    (
      [.[] | select((.cites // []) | index($h))] as $c
      | if ($c | length) == 0 then "-- cited by nothing --"
        else "-- cited by \($c | length) --\n"
             + ([$c[] | "  {#\(.handle)} (\(.author // "-")) "
                        + (.text[0:88] | gsub("\n"; " "))] | join("\n"))
        end
    )
  ' "$f"
}

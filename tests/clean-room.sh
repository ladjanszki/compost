#!/usr/bin/env bash
# What ./tests/run.sh cannot tell you: whether somebody else could start.
#
# The suites test the program. This tests the *contributor experience* — that a
# clone of what is actually pushed, a fresh env from environment.yml, and the
# documented commands produce a working tool. None of that is covered by any
# suite, and it is exactly where a cold reader got stuck: the quickstart used to
# open with `conda activate compost` and never say how the env was made.
#
# Takes minutes, because it builds a conda environment. Not wired into run.sh
# and not automated: run it before tagging a version, which is the only moment
# the answer matters. See DEVELOPMENT.md.
#
# With --with-agent it also asks a fresh Claude, in the clone, what it can work
# out from CLAUDE.md alone. That is the one failure this script cannot otherwise
# see: the commands below are the *correct* sequence, hardcoded, so they pass
# whether or not CLAUDE.md ever mentions them. A reader following the document
# is the only thing that notices a missing step. Costs an API call, so it is
# opt-in.
#
#   ./tests/clean-room.sh [--with-agent] [env-name] [repo-url]
set -u
WITH_AGENT=0
if [ "${1:-}" = "--with-agent" ]; then WITH_AGENT=1; shift; fi
ENVNAME="${1:-compost-cleanroom}"
URL="${2:-$(git -C "$(dirname "$0")/.." remote get-url origin 2>/dev/null || echo https://github.com/ladjanszki/compost.git)}"
ROOT="$(mktemp -d)"

CONDA_BASE="$(conda info --base 2>/dev/null)" || { echo "conda not found"; exit 1; }
# shellcheck disable=SC1091
. "$CONDA_BASE/etc/profile.d/conda.sh"

ok=0; bad=0
step() { printf '\n== %s\n' "$*"; }
check() { if [ "$1" -eq 0 ]; then echo "  PASS  $2"; ok=$((ok+1));
          else echo "  FAIL  $2"; bad=$((bad+1)); fi; }
cleanup() {
  conda deactivate 2>/dev/null || true
  conda env remove -n "$ENVNAME" -y >/dev/null 2>&1
  rm -rf "$ROOT"
}
trap cleanup EXIT

step "clone $URL"
git clone -q "$URL" "$ROOT/compost"; check $? "clone"
cd "$ROOT/compost" || exit 1
echo "  HEAD: $(git log --oneline -1)"

step "environment.yml -> conda env"
conda env remove -n "$ENVNAME" -y >/dev/null 2>&1
conda env create -q -f environment.yml -n "$ENVNAME" >/dev/null 2>&1; check $? "env created"
conda activate "$ENVNAME"; check $? "env activated"
echo "  $(python -V 2>&1) | $(pandoc --version | head -1)"

step "pip install -e ."
pip install -q -e . >/dev/null 2>&1; check $? "installed"
command -v compost >/dev/null; check $? "compost on PATH"

step "suites on a bare clone"
out=$(./tests/run.sh); [ $? -eq 0 ]; check $? "green without the corpus"
echo "$out" | tail -2 | sed 's/^/  /'
echo "$out" | grep -q "corpus  *ABSENT"; check $? "runner says the corpus is absent"

step "fetch the pinned corpus"
./tests/fetch-corpus.sh >/dev/null 2>&1; check $? "fetch"

step "suites with the corpus"
out=$(./tests/run.sh); [ $? -eq 0 ]; check $? "green with the corpus"
echo "$out" | tail -2 | sed 's/^/  /'
echo "$out" | grep -q "corpus  *present"; check $? "runner says the corpus is present"
if echo "$out" | grep -q "skipped"; then false; else true; fi
check $? "nothing left skipped"

step "the CLI, end to end"
W="$ROOT/base"; mkdir -p "$W"; cd "$W" || exit 1
compost init >/dev/null; check $? "init"
cp "$ROOT/compost/README.md" .
compost digest --as=notes README.md >/dev/null; check $? "digest --as=notes"
cp "$ROOT/compost/tests/fixtures/sessions/session-smoke.jsonl" s.jsonl
compost digest --as=claude-code-transcript s.jsonl >/dev/null
check $? "digest --as=claude-code-transcript"
pandoc -f commonmark_x-smart-attributes-fancy_lists -t json README.md > ast.json
compost digest --as=pandoc-ast ast.json >/dev/null; check $? "digest --as=pandoc-ast"
# The route is never inferred, so a bare file is a usage error and not a guess.
if compost digest README.md >/dev/null 2>&1; then false; else true; fi
check $? "digest without --as is refused"
compost ls >/dev/null;    check $? "ls"
compost check >/dev/null; check $? "check"
compost render >/dev/null; check $? "render"
# Graph filenames are minted, so the file holding a document is found by
# reading the records rather than by guessing a name from the source.
G=$(python3 -c "
import glob, json
for f in glob.glob('.compost/graph/*.jsonl'):
    for l in open(f):
        d = json.loads(l)
        if d.get('type') == 'Header':
            print(d['guid']); raise SystemExit")
compost lookup "$G" >/dev/null; check $? "lookup resolves a full guid"
if compost lookup "${G:0:8}" >/dev/null 2>&1; then false; else true; fi
check $? "lookup refuses a prefix"
compost serve >/dev/null 2>&1 & SP=$!
sleep 2
curl -sf -o /dev/null http://127.0.0.1:7373/; check $? "serve answers"
curl -s -D- -o /dev/null http://127.0.0.1:7373/ \
  | grep -qi 'cache-control: no-store'; check $? "responses are not cacheable"
kill $SP 2>/dev/null; wait $SP 2>/dev/null

step "the docs describe only what shipped"
cd "$ROOT/compost" || exit 1
# A TODO heading that *starts with* a version name is a section claiming to be
# that release. If the tag exists and the heading is not marked done, the file
# is presenting unshipped work as shipped — which is what happened when a
# planning bucket called "v0.2.1" was still full of open items on the day
# v0.2.1 was tagged. Headings that merely mention a version in prose are fine.
stale=$(grep -nE '^#+ +v[0-9][0-9A-Za-z.-]*' TODO.md | while IFS= read -r line; do
  ver=$(echo "$line" | sed -E 's/^[0-9]+:#+ +(v[0-9][0-9A-Za-z.-]*).*/\1/')
  if git rev-parse -q --verify "refs/tags/$ver" >/dev/null && ! echo "$line" | grep -q '✓'; then
    echo "$line"
  fi
done)
[ -z "$stale" ]; check $? "no TODO section is named after a shipped version"
[ -n "$stale" ] && echo "$stale" | sed 's/^/    /'

newest=$(git tag -l --sort=-v:refname | grep '^v[0-9]' | head -1)
grep -qF "## $newest " CHANGELOG.md; check $? "CHANGELOG has an entry for $newest"

if [ "$WITH_AGENT" -eq 1 ]; then
  step "a fresh Claude, given only CLAUDE.md"
  cd "$ROOT/compost" || exit 1
  if ! command -v claude >/dev/null; then
    echo "  SKIP  claude not on PATH"
  else
    # Deterministic assertions only. The prose varies run to run; what must not
    # vary is that CLAUDE.md still carries these facts at all.
    ans=$(claude -p "Do not use any tools. From what is already in your context,
answer in three short lines: (1) the exact command that fetches the test
corpus, (2) the command that runs the suites, (3) what the last line of that
runner tells you." 2>/dev/null)
    echo "$ans" | sed 's/^/  | /'
    echo "$ans" | grep -q "fetch-corpus.sh";  check $? "CLAUDE.md still names the fetch command"
    echo "$ans" | grep -q "tests/run.sh";     check $? "CLAUDE.md still names the runner"
    echo "$ans" | grep -qiE "corpus|absent|present"; check $? "CLAUDE.md still explains the tier line"
  fi
fi

printf '\n%d passed, %d failed\n' "$ok" "$bad"
exit $((bad > 0))

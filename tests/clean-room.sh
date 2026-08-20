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
#   ./tests/clean-room.sh [env-name] [repo-url]
set -u
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
compost import README.md >/dev/null; check $? "import markdown"
cp "$ROOT/compost/tests/fixtures/sessions/session-smoke.jsonl" s.jsonl
compost import s.jsonl >/dev/null; check $? "import transcript"
compost ls >/dev/null;    check $? "ls"
compost check >/dev/null; check $? "check"
compost render >/dev/null; check $? "render"
G=$(python3 -c "
import json
for l in open('.compost/graph/README-md.jsonl'):
    d = json.loads(l)
    if d.get('type') == 'Header':
        print(d['guid']); break")
compost lookup "$G" >/dev/null; check $? "lookup resolves a full guid"
if compost lookup "${G:0:8}" >/dev/null 2>&1; then false; else true; fi
check $? "lookup refuses a prefix"
compost serve >/dev/null 2>&1 & SP=$!
sleep 2
curl -sf -o /dev/null http://127.0.0.1:7373/; check $? "serve answers"
curl -s -D- -o /dev/null http://127.0.0.1:7373/ \
  | grep -qi 'cache-control: no-store'; check $? "responses are not cacheable"
kill $SP 2>/dev/null; wait $SP 2>/dev/null

printf '\n%d passed, %d failed\n' "$ok" "$bad"
exit $((bad > 0))

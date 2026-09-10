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
# and not automated.
#
# **It has nothing to do with tags.** A clone checks out the default branch, so
# this always tests pushed HEAD — run it whenever you want the answer, on work
# that will never be a release or on work about to become one. Tagging is a
# separate decision and no tag, release-candidate or otherwise, is needed to
# rehearse it. The one thing to remember is that it tests what is **pushed**;
# pass the repo's own path as `repo-url` to gate commits still sitting locally.
# See DEVELOPMENT.md.
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
# Say plainly what is being tested. A clone checks out the default branch, not
# a tag, so this gate always runs against HEAD — it is a release *rehearsal*
# any day of the week, and needs no tag to be useful. Printing the distance
# from the newest tag keeps "am I testing a release?" from being a guess.
_tag=$(git tag -l --sort=-v:refname | grep '^v[0-9]' | head -1)
if [ -n "$_tag" ]; then
  _ahead=$(git rev-list --count "$_tag..HEAD" 2>/dev/null || echo "?")
  if [ "$_ahead" = "0" ]; then
    echo "  testing $_tag itself — this is a release"
  else
    echo "  testing unreleased work: $_ahead commit(s) after $_tag"
  fi
fi

step "environment.yml -> conda env"
conda env remove -n "$ENVNAME" -y >/dev/null 2>&1
conda env create -q -f environment.yml -n "$ENVNAME" >/dev/null 2>&1; check $? "env created"
conda activate "$ENVNAME"; check $? "env activated"
echo "  $(python -V 2>&1) | $(pandoc --version | head -1)"

# ABORT here rather than continue, and verify we are where we think we are.
#
# Everything below installs into and writes to *the active environment*. If
# the two steps above failed, the active environment is still whichever one
# the operator was using when they ran this — and `pip install -e .` then
# repoints THEIR editable install at $ROOT, a temp directory this script
# deletes on exit. The result is `compost` on their PATH raising
# `ModuleNotFoundError: No module named 'src'` from a path that no longer
# exists, with nothing connecting it to a gate run that reported success.
#
# That is not hypothetical: it happened on 2026-09-09, to the env this repo
# is developed in, and went unnoticed until `compost --version` was run by
# hand hours later. `check` reports a failure and returns 0, which is right
# for a gate that wants to report every problem rather than stop at the
# first — but it means a failed *precondition* silently becomes a wrong
# action. Preconditions are the exception: they abort.
#
# The env name is checked and not just the exit status, because `conda
# activate` can report success while leaving a different env active, and the
# cost of being wrong here is damage outside the sandbox.
ACTIVE="$(basename "${CONDA_PREFIX:-none}")"
if [ "$ACTIVE" != "$ENVNAME" ]; then
  echo "  FAIL  refusing to continue: active env is '$ACTIVE', expected '$ENVNAME'"
  echo "        everything below installs into the active env, and this would"
  echo "        have repointed '$ACTIVE''s editable install at a temp directory"
  echo "        that is deleted when this script exits."
  bad=$((bad+1))
  printf '\n%d passed, %d failed\n' "$ok" "$bad"
  exit 1
fi

step "pip install -e ."
pip install -q -e . >/dev/null 2>&1; check $? "installed"
command -v compost >/dev/null; check $? "compost on PATH"
# The gate is worthless if it tested the operator's checkout instead of the
# clone, and `pip install -e .` is silently a no-op-shaped success either
# way. Assert the interpreter resolves `src` from $ROOT.
#
# Both sides are resolved to their physical paths before comparing. On macOS
# `mktemp -d` hands back /var/folders/... while /var is a symlink to
# /private/var, and Python reports the resolved form — so a plain prefix test
# on $ROOT fails while `src` is in fact inside the clone. The first version of
# this check did exactly that and reported FAIL on a perfectly good run:
# a check describing something other than what it names, added in the commit
# that fixed another instance of the same thing.
ROOT_REAL="$(cd "$ROOT" && pwd -P)"
SRC="$(python -c 'import src,os;print(os.path.realpath(os.path.dirname(os.path.dirname(src.__file__))))' 2>/dev/null)"
case "$SRC" in "$ROOT_REAL"/*|"$ROOT_REAL") true ;; *) false ;; esac
check $? "src resolves inside the clone, not the operator's checkout"

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
# `--mutability` is required at creation as of v0.2.15, and the value is
# chosen per artifact rather than uniformly: a README is a TA, a transcript
# only ever grows, and a pandoc AST dump is a snapshot. Naming them honestly
# here keeps this flow a demonstration of the model rather than three copies
# of whichever value was shortest to type.
compost digest --as=notes --mutability=mutable README.md >/dev/null
check $? "digest --as=notes"
cp "$ROOT/compost/tests/fixtures/sessions/session-smoke.jsonl" s.jsonl
compost digest --as=claude-code-transcript --mutability=append-only s.jsonl >/dev/null
check $? "digest --as=claude-code-transcript"
pandoc -f commonmark_x-smart-attributes-fancy_lists -t json README.md > ast.json
compost digest --as=pandoc-ast --mutability=immutable ast.json >/dev/null
check $? "digest --as=pandoc-ast"
# The route is never inferred, so a bare file is a usage error and not a guess.
if compost digest --mutability=immutable README.md >/dev/null 2>&1; then false; else true; fi
check $? "digest without --as is refused"
# ...and neither is the contract. Both are required, and a caller that gives
# one without the other gets an error rather than a default. This gate found
# that out the hard way: v0.2.15 made `--mutability` required, these three
# calls did not have it, all three were refused, and the base they build was
# left empty — which surfaced as `render`, `lookup` and `serve` failing on a
# missing directory, four steps downstream of the actual cause.
if compost digest --as=notes README.md >/dev/null 2>&1; then false; else true; fi
check $? "digest without --mutability is refused"
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

# The mirror of the TODO rule above. A CHANGELOG heading naming a version is a
# claim that the version exists; with no tag behind it, it is a planning bucket
# wearing a release number -- the thing this repo keeps relearning. Work that
# has landed but not shipped belongs under "## Unreleased".
phantom=$(grep -oE '^## +v[0-9][0-9A-Za-z.-]*' CHANGELOG.md | awk '{print $2}' | while IFS= read -r v; do
  git rev-parse -q --verify "refs/tags/$v" >/dev/null || echo "$v"
done)
[ -z "$phantom" ]; check $? "no CHANGELOG heading names a version without a tag"
[ -n "$phantom" ] && echo "$phantom" | sed 's/^/    /'


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

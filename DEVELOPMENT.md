# DEVELOPMENT

## v0.2 layout

```
extras/         installed, but not the tool — see "What belongs in extras/"
  compost_new.py     `compost-new`: mint a scratch file, open $EDITOR,
                digest it on close
  compost_name.py    `compost-name`: give a root a display name — a new
                graph/<uuid>.jsonl each run, never an edit of one
src/            the implementation
  cli.py        the compost command: a dispatcher and nothing else
  records.py    pandoc AST <-> records, the whole-graph checks, citations
  routes.py     the named ways material enters a base; nothing else reads
                a file extension to decide anything
  session.py    Claude Code JSONL -> records
  store.py      the .compost/ base: init, digest, ls, check, lookup
  layers.py     compost layer: derives records from the base itself
                (citations today). One of the tool's two writers — anything
                emitting valid JSONL under graph/ is an equal writer
  views.py      the three views, and the per-node-type view dispatch
  draw.py       compost draw: a Graphviz picture of the base under
                graphviz/, a peer of views/ rather than part of it — always
                DOT, SVG only when the layout engine is on PATH
  serve.py      a static server over the HTML view; renders nothing
tools/          committed scripts that are not the tool, and never installed
  bleach.py     lorem-ise a markdown file, keep the formatting
  bleach_session.py   the same for a transcript
  roundtrip.py  the pandoc-only fixed-point harness
  dj_prepare.py      repair a v0.1 .dj so pandoc keeps its list-item handles
  v01_dictionary.py  the legacy handle -> guid dictionary, as alias records
  record-schema-1.json   the record grammar, machine-read — the ground
                truth tests/test_grammar.py holds the base against
  schema_tables.py   record-schema-1.json -> markdown tables
  build_whitepaper.py    regenerates docs/compost.md's grammar appendix
                from schema_tables.py, between two markers, idempotently
  loop.py       one round of the conversation loop: note in, response out,
                already cited — docs/roadmap.md, "the conversation loop"
  graph_sql.py  the read-only SQL view over graph/*.jsonl, via duckdb —
                nothing materialised, no file ever written
  queries/      *.sql files graph_sql.py runs; docs/queries.md is the prose
tests/          one suite per property; ./tests/run.sh runs them all
  fixtures/     the smoke set, ~80 KB: the documents suites name directly
    grammar/    one instance of every constructor, so docs/record-grammar.md
                is verified rather than believed
  corpus/       fetched, gitignored — see fetch-corpus.sh
  corpus.txt    the pinned commits
  fetch-corpus.sh
  clean-room.sh whether somebody else could start: clone, env, install, run
  tier.py       which material is on disk, and what that means for a guarantee
docs/           man page, decisions, record format, the original drafts
vendor/         pandoc-types, cloned to read the AST grammar; no test uses it
```

**Every module in `src/` is reachable from `cli.py`, and that is the entry
rule.** `pyproject.toml` says `packages = ["src"]`, so anything put there is
installed into the environment of everyone who runs `pip install -e .` —
which is the wrong home for a fixture bleacher or a one-off migration script.
Those live in `tools/`, which is importable from a checkout and installed
nowhere. Until v0.2.5 the bleachers and the round-trip harness sat in `src/`
and shipped with the package for no reason at all.

**What belongs in `extras/`.** v0.2.5's rule above is a binary — `src/` is
installed and reachable from `cli.py`, `tools/` is never installed — and a
user-facing convenience wrapper is neither: it is installed, because someone
running `pip install -e .` should get the command without a second step, but
it is not the tool, because `docs/man-compost.md` asserts `compost`'s
subcommand count in a sentence and `tests/test_manpage.py` enforces it.
`extras/` is that third bucket. Every module there is exposed through its
own `[project.scripts]` entry — `compost-new`, never `compost new` — so a
distinct command reads as adjacent to the tool rather than part of it, and
adding one never moves the count. The test for whether something belongs
here, taken from `docs/roadmap.md`'s introduction of `compost-new`: **nothing
is lost if it does not exist.** It only orchestrates things `src/` already
does — a route, a mint, a check — plus something outside the tool entirely,
like spawning an editor. A module that is the only place some piece of logic
lives does not belong here; that is `src/`, reachable from `cli.py` either
directly or as a subcommand.

`compost-name` (v0.2.10) is the second resident, for the same reason:
resolving an identifier through `derived_from`, minting a `display_name` node
and its `names` edge with `records.Builder`, and calling `check` are all
things `src/` already does. It is not a subcommand for the same reason
`compost layer alias` was rejected in `CLAUDE.md` — a display name is a
record, written the way any hand-written graph file is, and a wrapper script
around that is exactly the third bucket's shape.

## Closing a version: tag the candidate first

`tests/clean-room.sh` asserts that a version named in `CHANGELOG.md` has a tag
behind it — a heading with no tag is a planning bucket wearing a release
number. But the gate is the last thing you run *before* tagging, so the check
fails on every release by construction and every reader trips on it.

**The fix is a release candidate tag, and it changes nothing else.** Three
states, one hedge convention:

| CHANGELOG heading | tag | means |
|---|---|---|
| `## Unreleased` | — | landed on `main`, no version chosen yet |
| `## v0.2.7-rc — the graph view` | `v0.2.7-rc` | version named, gate runnable, not released |
| `## v0.2.7 — 2026-08-27 — the graph view` | `v0.2.7` | released |

The `-rc` suffix replaces the word "unreleased" once a version has a number,
so there is one convention rather than two.

**There is exactly one `-rc` tag and it has no number.** A second candidate
moves it: `git tag -f v0.2.7-rc`. It is a pointer at *what is being tested*,
not a record of history — the release is the last candidate, so keeping old
ones stores nothing.

The order:

1. name it: rename the heading to `## vX.Y.Z-rc — …` **and** `git tag vX.Y.Z-rc`.
   Both together — tagging while the heading still says `## Unreleased` makes
   the gate pick the rc as newest, find no matching heading, and fail.
2. `./tests/run.sh`, then `./tests/clean-room.sh --with-agent`. Both now pass.
3. fix what they find; `git tag -f vX.Y.Z-rc`; repeat 2.
4. bump `src/__init__.py` and the man page's `Version` line; **bring
   `docs/compost.md` up to date and set its version line**; rename the heading
   to `## vX.Y.Z — DATE — …`; commit as `chore:`.

   The whitepaper step is not optional and was missing until v0.2.13, which is
   how a release that changed what a hash *means* nearly shipped with a paper
   describing the old one. Only its generated appendix is guarded by a test;
   the prose is not, so nothing else will catch it. The same step is where a
   design document earns its deletion: `docs/design-*.md` is deleted when its
   version ships, so anything in it worth keeping has to reach the whitepaper
   *first* or it leaves with the file.
5. `git tag -a vX.Y.Z`, **delete the rc in the same breath**, push branch and
   tags. Then freeze the whitepaper — `git show vX.Y.Z:docs/compost.md >
   docs/whitepaper/compost-vX.Y.Z.md` — which has to happen *after* the tag,
   because by the next commit the working copy has already moved on. Forgetting the delete leaves the rc sorting above the release — git
   orders `v0.2.7-rc` *above* `v0.2.7` by default — so the gate looks for the
   rc's heading, which no longer exists, and fails. That is the failure telling
   you to finish the cleanup, and it is why the delete is part of step 5 rather
   than a step of its own.

**Known hole, unenforced:** abandon a version and its `-rc` tag stays behind
with nothing to notice, because the gate only inspects the newest tag. A
leftover rc is a true statement — testing began here and never finished — so
this is a signal rather than a defect. Enforcing "at most one `-rc` tag exists"
is one line if that stops being good enough.

The test material is in two tiers. The **smoke set** under `tests/fixtures/`
is committed, ~80 KB, and holds the documents the suites name directly — the
one markdown file that reaches every sabotage, a hand-built AST no reader can
produce, three notes and one trimmed transcript. Every suite runs on a bare
clone.

The **corpus** is fetched at pinned commits recorded in `tests/corpus.txt`:

```
./tests/fetch-corpus.sh
```

That takes the round-trip from 6 documents to 526 and re-enables four
guarantees that need volume — they report themselves `skip` when it is absent,
and `run.sh` ends with `corpus present` or `corpus ABSENT` either way.

Curated material lives in its own repository, `compost-corpus`, because test
data grows and this repo's history has twice had material removed
retroactively. Bulk material is fetched from upstream rather than republished.

`vendor/pandoc-types` is a different thing and no test reads it — verified by
running every suite with the directory moved away, which changed nothing, not
even the document count. It is the Haskell definition of the AST, and
`Definition.hs` is the grammar `docs/decisions.md` argues from. Clone it when
the record format is in question, and delete it when it is not:

```
git clone --depth 1 https://github.com/jgm/pandoc-types.git vendor/pandoc-types
```

Both commands are in `.gitignore` too.

## Requirements

Python 3.12, pandoc 3.10+. Nothing from PyPI. Node is not needed.

```bash
conda env create -f environment.yml   # or `conda env update -f environment.yml`
conda activate compost
pip install -e .                      # puts `compost` on PATH
```

Check what you are in before believing a result: the base conda env has pandoc
3.8, below the floor, and the suites pass there anyway, so nothing warns you.
`python3 -m src.cli` runs the CLI from a checkout regardless of PATH.

If `compost` cannot find pandoc, check that your shell profile is loaded — a
non-interactive script does not source `.zshrc`, which is how a Node-based
toolchain used to fail here.

## Conventions


- **A version is a batch, not a commit.** Let several things accumulate before
  closing one, patch levels included. Three patch versions were once cut in a
  single day, which is how a version number stops meaning anything: it should mark a
  change in what the tool can do, not a change in the working tree. Finish a
  piece of work, commit it, and stop — the tag comes when the version has a
  theme somebody could describe. `TODO.md`'s *Known gaps* lists what is still
  missing — deliberately not named after a version, because a bucket wearing a
  version number reads as a promise the moment that version ships.
- **`./tests/clean-room.sh --with-agent` is a release rehearsal, not a release
  step, and needs no tag.** A clone checks out the default branch, so it always
  tests pushed `HEAD` — run it any day, on work that will never be a version or
  on work about to become one. It prints how far `HEAD` is from the newest tag
  so "am I testing a release?" is never a guess. **Do not cut a
  release-candidate tag to make it run**: an `_rc` tag sorts newest, and the
  gate then demands a `CHANGELOG.md` entry for a version that does not exist,
  so it fails for a bookkeeping reason having nothing to do with the code.

  It tests what is **pushed**. To gate commits still sitting locally, pass the
  repository's own path as `repo-url`.

  Run it before you tag, because that is when the answer matters most. It is
  the only thing that tests the contributor experience rather than the code: a clone of
  what is actually pushed, a conda env built from `environment.yml`,
  `pip install -e .`, both test tiers, and every subcommand. It takes minutes
  because it builds an environment, so it is not wired into `run.sh` and not
  automated — tagging is the one moment the answer matters.

  `--with-agent` adds the check the rest of the script structurally cannot make.
  Every command in it is the *correct* sequence, hardcoded, so it passes whether
  or not `CLAUDE.md` mentions any of it — a quickstart that forgets a step still
  goes green. So it asks a fresh Claude, in the clone, with only `CLAUDE.md` in
  context, to name the fetch command, the runner, and what the runner's last
  line means. Only `CLAUDE.md` is auto-loaded, measured: one file, nothing under
  `docs/`, `tests/` or `src/`. It costs an API call, which is why it is opt-in
  everywhere except here.

  It also checks that the docs describe only what shipped. A `TODO.md` heading
  beginning with a version name is a section claiming to be that release, so if
  the tag exists the heading must be marked done — and the newest tag must have
  a `CHANGELOG.md` entry. Both come from tagging v0.2.1 while `TODO.md` still
  had a `v0.2.1` bucket full of open items, which read as a list of what the
  release contained.
- **Work on `main`; tag each version.** No feature branches. One developer, no
  CI, no review gate — a branch buys isolation from nothing and
  costs a stale trunk. This was learned the direct way: a `conversations`
  branch left `main` seventeen commits behind, still describing `notes/`,
  `wiki/` and UUID block ids, so anyone reading the default branch — or any
  agent following the instructions in it — got confidently wrong instructions. That is the
  documentation drift this repo has been rescued from twice, in a new costume.
  Branch only for a change that is a genuine one-way door, and merge it fast.
- Commit per logical step; separate infrastructure/config changes from code.
- Update `CHANGELOG.md` when behaviour changes.
- **Fix documentation drift in the same session as the decision**, not the next
  one. This repo has been rescued from contradictory docs twice; both times the
  cause was a decision recorded in code but not in the design doc.

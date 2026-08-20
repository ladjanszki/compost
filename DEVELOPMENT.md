# DEVELOPMENT

## v0.2 layout

```
src/            the implementation
  cli.py        the compost command: a dispatcher and nothing else
  records.py    pandoc AST <-> records, the whole-graph checks, citations
  session.py    Claude Code JSONL -> records
  store.py      the .compost/ base: init, import, ls, check, lookup
  views.py      the three views, and the per-node-type view dispatch
  serve.py      a static server over the HTML view; renders nothing
  bleach.py     lorem-ise a markdown file, keep the formatting
  bleach_session.py   the same for a transcript
  roundtrip.py  the pandoc-only fixed-point harness
tests/          one suite per property; ./tests/run.sh runs them all
  fixtures/     the smoke set, ~80 KB: the documents suites name directly
  corpus/       fetched, gitignored — see fetch-corpus.sh
  corpus.txt    the pinned commits
  fetch-corpus.sh
  tier.py       which material is on disk, and what that means for a guarantee
  corpus/       cloned documentation sites, gitignored
docs/           man page, decisions, record format, the original drafts
vendor/         pandoc-types, cloned to read the AST grammar; no test uses it
```

The test material is in two tiers. The **smoke set** under `tests/fixtures/`
is committed, ~80 KB, and holds the documents the suites name directly — the
one markdown file that reaches every sabotage, a hand-built AST no reader can
produce, three notes and one trimmed transcript. Every suite runs on a bare
clone.

The **corpus** is fetched at pinned commits recorded in `tests/corpus.txt`:

```
./tests/fetch-corpus.sh
```

That takes the round-trip from 5 documents to 525 and re-enables four
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
  theme somebody could describe. `v0.2.1` is the next one open, and `TODO.md`
  lists what it is waiting for.
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

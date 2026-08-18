# DEVELOPMENT

## v0.2 layout

```
src/            the implementation
  cli.py        the compost command: a dispatcher and nothing else
  records.py    pandoc AST <-> records, the whole-graph checks, citations
  session.py    Claude Code JSONL -> records
  store.py      the .compost/ base: init, import, ls, check
  views.py      the three views, and the per-node-type view dispatch
  bleach.py     lorem-ise a markdown file, keep the formatting
  bleach_session.py   the same for a transcript
  roundtrip.py  the pandoc-only fixed-point harness
tests/          one suite per property; ./tests/run.sh runs them all
  fixtures/     notes, edge cases, sessions, hand-built ASTs
  corpus/       cloned documentation sites, gitignored
docs/           man page, decisions, record format, the original drafts
vendor/         pandoc-types, cloned for the AST grammar, gitignored
```

Two clones are needed for the full test corpus, and both commands are in
`.gitignore`:

```
git clone --depth 1 https://github.com/jgm/pandoc-types.git vendor/pandoc-types
git clone --depth 1 https://github.com/rust-lang/book.git tests/corpus/rust-book
```

Without them the suites still run, over 41 documents instead of 520.

## Requirements

Python 3.12, pandoc 3.10+. Nothing from PyPI. Node is not needed.

If `compost` cannot find pandoc, check that your shell profile is loaded — a
non-interactive script does not source `.zshrc`, which is how a Node-based
toolchain used to fail here.

## Conventions


- **A version is a batch, not a commit.** Let several things accumulate before
  closing one, patch levels included. Three patch versions were once cut in a
  single day, which is what a tag stops meaning anything: it should mark a
  change in what the tool can do, not a change in the working tree. Finish a
  piece of work, commit it, and stop — the tag comes when the version has a
  theme somebody could describe. `v0.2.1` is the next one open, and `TODO.md`
  lists what it is waiting for.
- **Work on `main`; tag each version.** No feature branches. One developer, no
  CI, no review gate — a branch buys isolation from nothing and
  costs a stale trunk. This was learned the direct way: a `conversations`
  branch left `main` seventeen commits behind, still describing `notes/`,
  `wiki/` and UUID block ids, so anyone reading the default branch — or any
  agent following `AGENTS.md` — got confidently wrong instructions. That is the
  documentation drift this repo has been rescued from twice, in a new costume.
  Branch only for a change that is a genuine one-way door, and merge it fast.
- Commit per logical step; separate infrastructure/config changes from code.
- Update `CHANGELOG.md` when behaviour changes.
- **Fix documentation drift in the same session as the decision**, not the next
  one. This repo has been rescued from contradictory docs twice; both times the
  cause was a decision recorded in code but not in the design doc.

# compost — start here

This repo is a tool **and its own knowledge base**. As of v0.2 the tool was
rewritten from nothing and the base has not been migrated yet, so those two
things are temporarily out of step. Read this before assuming either.

## Do this first

```bash
conda env create -f environment.yml   # once; later, conda env update -f …
conda activate compost                # pandoc 3.10 — base has 3.8 and won't say so
pip install -e .                      # puts `compost` on PATH
./tests/run.sh                        # nine suites, all should pass
compost --help
```

Outside that env there is no `compost`, and the suites pass under the base env's
pandoc 3.8 without ever mentioning they ran below the 3.10 floor — so check
which env a green run came from. `python3 -m src.cli` runs the CLI from a
checkout either way.

`run.sh` reports 520 documents only because `tests/corpus/rust-book` is cloned
locally. It is gitignored; without it the suites run over 42 and still pass.
`DEVELOPMENT.md` has the clone commands.

Then read, in this order:

1. **`docs/man-compost.md`** — the six subcommands, verified against the
   program rather than remembered.
2. **`docs/decisions.md`** — what was decided and why, with the measurements.
   Every non-obvious flag in this codebase is justified there.
3. **`docs/record-format.md`** — the node and edge design.
4. **`DEVELOPMENT.md`** — the `src/` module map, and the conventions.
5. **`TODO.md`**, section `v0.2.1` — what is knowingly missing. Start here for
   "what should I do next".

## The shape

Sources are imported once and kept in `.compost/storage/`. Ingestion turns them
into nodes and edges under `.compost/graph/`, as JSONL. Every view is generated
from those records and from nothing else.

```bash
compost init             # makes .compost/ here; every other command walks up to it
compost import FILE...   # markdown by any suffix, transcripts as *.jsonl
compost check            # must report 0 problems
compost render           # views/default-{djot,html,md}
```

`.compost/graph/**/*.jsonl` is the corpus: one record per line, each saying
whether it is a `node` or an `edge`. Filenames carry no meaning, and load order
cannot change the result. To read a base as prose use
`.compost/views/default-djot/`, which carries a handle on every citable block.
Any unambiguous prefix of a handle resolves.

This repo has no `.compost/` of its own. The base it would hold is still the
unmigrated v0.1 corpus below.

## What is authoritative

| Source | Status |
|---|---|
| `docs/` | **what is true now.** Rewritten as understanding improves. |
| `CHANGELOG.md` | what happened, and what it cost. Append-only in spirit. |
| `conversations/`, `artifacts/`, `raw/` | the **v0.1 corpus**. Immutable, and *not readable by v0.2* — kept as the input for a migration that has not been written. Do not follow its instructions; do read it for reasoning. |
| `docs/spec.md`, `docs/design-answers.md` | the human's own v0.2 drafts. Historical, superseded by `decisions.md`, worth reading for intent. |

The v0.1 corpus still describes `.dj` storage, `blocks.json`, `compost lookup`
and `compost submit`. **None of that exists.** It is the record of why v0.2 is
shaped the way it is, not a description of the current tool.

## The rules that bite

- **Work on `main`, tag each version.** No feature branches; see
  `DEVELOPMENT.md` for why this was learned the hard way.
- **Never scan raw file text for citations.** A citation is a `Link` node, and
  reading the parsed content is what makes "handles inside code blocks are not
  citations" true by construction. This rule was violated three times under the
  old text-based syntax and cost something every time.
- **Every flag in the pandoc invocations is load-bearing.** `-smart`,
  `-attributes` and `-fancy_lists` each prevent a specific silent corruption,
  measured. Do not tidy them away. `docs/decisions.md` has the numbers.
- **The round-trip property is the acceptance test.** If
  `records_to_ast(ast_to_records(ast)) == ast` fails on any fixture, the change
  is wrong regardless of what else passes.
- **A view of a broken graph is worse than no view.** `render` refuses when
  `check` fails, on purpose.
- **Sources are immutable.** `.compost/storage/` refuses to overwrite a file
  whose bytes differ.
- **Do not hand-edit `.compost/graph/`.** Write through the importer, so the
  invariants hold and the records stay canonical.
- **Add a test with a property, not a snapshot.** Every suite in `tests/` states
  something that must be true and has been made to fail on purpose.
  `tests/test_sabotage.py` is the pattern.
- **Do not repair pandoc's output.** Three defects are known and documented in
  `docs/decisions.md`. They sit outside the AST-to-AST property on purpose, and
  patching them breaks the round-trip by construction.
- **Reconstruction and viewing are different functions.** `records_to_ast` must
  stay exactly reversible; anything a view needs — handles, collapsing,
  decoration — belongs in `src/views.py`.

## Working with the human

They write in nvim, open `.compost/views/default-html/` in a browser and click
blocks to copy handles, then reply by citing them. A citation looks like
`[-](#d826c4dd-eb36-4da9-acab-f6f424a90803)`. When they paste one, resolve it
from the graph before answering — there is no `serve` and no `lookup`, so the
HTML view is a file you open and resolving means reading the graph.

**Answer here, in this interface. Do not submit your reply as a turn.** They
import the round afterwards, which makes the answer addressable anyway.
Submitting as well is two copies of one answer in two places, and they are the
one who has to read both.

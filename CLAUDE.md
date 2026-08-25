# compost — start here

This repo is a tool **and its own knowledge base**. As of v0.2 the tool was
rewritten from nothing and the base has not been migrated yet, so those two
things are temporarily out of step. Read this before assuming either.

## Do this first

```bash
conda env create -f environment.yml   # once; later, conda env update -f …
conda activate compost                # pandoc 3.10 — base has 3.8 and won't say so
pip install -e .                      # puts `compost` on PATH
./tests/run.sh                        # fourteen suites, all should pass
compost --help
```

Outside that env there is no `compost`, and the suites pass under the base env's
pandoc 3.8 without ever mentioning they ran below the 3.10 floor — so check
which env a green run came from. `python3 -m src.cli` runs the CLI from a
checkout either way.

The suites run in two tiers. A bare clone has only the **smoke set** — about
80 KB of fixtures, enough that every suite runs — and the last line of `run.sh`
says `corpus ABSENT`. `./tests/fetch-corpus.sh` fetches the pinned corpus into
`tests/corpus/`, which takes the round-trip from 6 documents to 526 and turns
four skipped guarantees back on. Never trust a green board without reading that
last line.

Then read, in this order:

1. **`docs/man-compost.md`** — the nine subcommands, verified against the
   program rather than remembered.
2. **`docs/decisions.md`** — what was decided and why, with the measurements.
   Every non-obvious flag in this codebase is justified there.
3. **`docs/record-format.md`** — the node and edge design.
4. **`DEVELOPMENT.md`** — the `src/` module map, and the conventions.
5. **`TODO.md`**, section *Known gaps* — what is knowingly missing and has not
   shipped. Start here for "what should I do next".

## The shape

Sources are imported once and kept in `.compost/storage/`. Ingestion turns them
into nodes and edges under `.compost/graph/`, as JSONL. Every view is generated
from those records and from nothing else.

```bash
compost init             # makes .compost/ here; every other command walks up to it
compost digest --as=R FILE...   # R is one of notes, claude-code-transcript,
                                # pandoc-ast. Required; never inferred.
                                # A transcript digest is lossless: every line
                                # and key is kept, filter at query time. It also
                                # pulls in the subagent transcripts it names;
                                # --no-follow reads only the file given.
compost check            # must report 0 problems
compost layer citation   # mints `cites` edges, plus placeholders for
                          # what does not resolve; --by defaults to
                          # uuid-link. Rerunning it accumulates, on
                          # purpose — nothing is deduplicated.
compost render           # views/default-{djot,html,md}
compost lookup HANDLE    # the block a handle names, and what cites it
compost serve            # the HTML view on 127.0.0.1:7373
```

`.compost/graph/**/*.jsonl` holds **the records**: one per line, each saying
whether it is a `node` or an `edge`. Filenames carry no meaning, and load order
cannot change the result. Both graph and storage filenames are minted uuids,
and the two are unrelated: to get from a document to its bytes, follow its
`derived_from` edge to the `blob` node and read `params["stored_as"]`. There is
no rule that turns an original filename into a storage path, and anything that
invents one will be wrong. To read a base as prose use
`.compost/views/default-djot/`, which carries a handle on every citable block.
A handle is the whole guid; a prefix of one resolves to nothing.

This repo has no `.compost/` of its own. The base it would hold is still the
unmigrated v0.1 corpus below.

**Three things get called a corpus here, so this file is strict about it.**
Bare *corpus* always means the **test corpus** under `tests/corpus/`. The
**v0.1 corpus** is the removed personal notes and is never unqualified. And a
base's own content is **the records**, never a corpus.

## What is authoritative

| Source | Status |
|---|---|
| `docs/` | **what is true now.** Rewritten as understanding improves. |
| `CHANGELOG.md` | what happened, and what it cost. Append-only in spirit. |
| the **v0.1 corpus** | **not in this repository.** It was personal notes and was removed from the history, not merely deleted. It is kept privately as the input for a migration that has not been written. |
| `docs/spec.md`, `docs/design-answers.md` | the human's own v0.2 drafts. Historical, superseded by `decisions.md`, worth reading for intent. |

Anything quoting the v0.1 corpus — `docs/migration.md` above all — describes
files you will not find here. Its measurements were taken while those files were
present and still stand; the paths are historical. If you need them to do the
migration, ask, because they are deliberately not on this disk any more.

It described `.dj` storage, `blocks.json` and `compost submit`, none of which
exist. Treat any instruction recovered from it as the record of why v0.2 is
shaped the way it is, never as a description of the current tool.

## The rules that bite

- **Work on `main`, tag each version.** No feature branches; see
  `DEVELOPMENT.md` for why this was learned the hard way.
- **Digest everything the file holds; filter at query time, never at import.**
  Deciding a field is noise while reading it is a decision made once, silently,
  and unrecoverably — the bytes are still in `storage/`, but every base built
  in the meantime is missing them and nobody knows. Filtering later is free and
  reversible; filtering at import is neither. `--as=claude-code-transcript`
  holds this by property — `records_to_session(session_to_records(lines)) ==
  lines`, exact — after an audit found it dropping 46% of a real transcript's
  lines and seventeen log-line keys. Every line node carries its own original
  JSON in `params["log"]`, and a line type nobody has a reading for becomes a
  `logline` rather than nothing. If a new importer is tempted to skip
  something, store it and let a view or a query ignore it. Volume is not the
  objection: this is not the main way the base is read.
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
- **Sources are immutable, and storage is a blob store.** Every file lands
  under a freshly minted `GUID.EXT`, so `.compost/storage/` never overwrites
  anything — it refuses a name already in use, which can only mean a uuid
  repeated itself. The same bytes may legitimately be stored twice; `digest`
  reports that and does not resolve it.
- **Nothing about ingestion is inferred from a file extension.** The route is
  named with `--as` or the command refuses. This was dispatch on the suffix
  until v0.2.2, where the fallback was not "markdown" but "anything at all".
  `src/routes.py` is the only place that knows how to read anything.
- **Do not hand-edit `.compost/graph/`.** Write through `compost digest`, so the
  invariants hold and the records stay canonical. **Two narrow exceptions**,
  reasoned in `docs/decisions.md`: a *generated* file of valid JSONL may be
  written under `graph/` — the alias dictionary is one, and a script producing
  records with ordinary Python is not different in kind from `digest` doing it —
  and a *whole* file that one `compost layer` run wrote may be deleted, which is
  the only inverse the design offers for accumulation it never removes. `check`
  is the enforcement, not the identity of the writer. Editing a line inside an
  existing file is still banned, and there is no `compost layer alias`.
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
before answering: `compost lookup <guid>` prints the block it names, whole guid
only, and also what cites it — but only after `compost layer citation` has
been rebuilt on the current base; `lookup` does not rebuild it for you and
under-reports on a stale one. They read the HTML view through `compost serve`,
which does not render: when they ask to see a change, run `compost render` and
tell them to refresh.

**Answer here, in this interface. Do not submit your reply as a turn.** They
import the round afterwards, which makes the answer addressable anyway.
Submitting as well is two copies of one answer in two places, and they are the
one who has to read both.

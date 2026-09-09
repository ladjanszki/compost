# compost — start here

This repo is a tool **and its own knowledge base**. As of v0.2 the tool was
rewritten from nothing and the base has not been migrated yet, so those two
things are temporarily out of step. Read this before assuming either.

## Do this first

```bash
conda env create -f environment.yml   # once; later, conda env update -f …
conda activate compost                # pandoc 3.11 — base has 3.8 and won't say so
pip install -e .                      # puts `compost` on PATH
./tests/run.sh                        # twenty-three suites, all should pass
compost --help
compost ls                            # what is in the base here, if there is one
```

Outside that env there is no `compost`, and the suites pass under the base env's
pandoc 3.8 without ever mentioning they ran below the pinned 3.11 — so check
which env a green run came from. `python3 -m src.cli` runs the CLI from a
checkout either way.

The suites run in two tiers. A bare clone has only the **smoke set** — about
80 KB of fixtures, enough that every suite runs — and the last line of `run.sh`
says `corpus ABSENT`. `./tests/fetch-corpus.sh` fetches the pinned corpus into
`tests/corpus/`, which takes the round-trip from 6 documents to 526 and turns
four skipped guarantees back on. Never trust a green board without reading that
last line.

Then read, in this order:

1. **`docs/man-compost.md`** — the ten subcommands, verified against the
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
compost digest --as=R --mutability=M FILE...
                                # R is one of notes, claude-code-transcript,
                                # pandoc-ast. Required; never inferred.
                                # M is immutable | append-only | mutable,
                                # required at creation and never changed.
                                # --updates=GUID appends to an existing
                                # append-only root instead of minting a
                                # second one; it is refused on immutable
                                # roots, and on mutable ones until v0.2.16.
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

`.compost/graph/*.jsonl` holds **the records**: one per line, each saying
whether it is a `node` or an `edge`. Filenames carry no meaning, load order
cannot change the result, and `graph/` is flat by rule — no subdirectory, ever
(v0.2.8; `Store.write` refuses one). Both graph and storage filenames are minted uuids,
and the two are unrelated: to get from a document to its bytes, follow its
`derived_from` edge to the `blob` node and read `params["stored_as"]`. There is
no rule that turns an original filename into a storage path, and anything that
invents one will be wrong. To read a base as prose use
`.compost/views/default-djot/`, which carries a handle on every citable block.
A handle is the whole guid; a prefix of one resolves to nothing.

**Whether this repo has a `.compost/` depends on the machine, so check rather
than assume.** It is gitignored — as `.compost` with no trailing slash, on
purpose, because on the human's machine it is a *symlink* into a separate
local-only repository and git stores a symlink as a blob, which a trailing
slash would not match. The `.gitignore` comment has the detail.

- **On a fresh clone there is no base.** `compost lookup` says so plainly, and
  the only material in the repo is `tests/corpus/`.
- **On the human's machine there is one**, holding their **personal** knowledge
  base — the working notes and conversations this project exists to keep. That
  is why it is not shared: this repository has had personal material purged
  from its history once already, and better never in than removed twice.

Two things follow, and both have been got wrong. **When the human pastes a
citation, run `compost lookup <guid>` before answering.** This file is not
evidence that there is nothing to resolve; an earlier version of this
paragraph asserted the base was absent, and an agent believed it over a
two-second check and guessed at a block it could have read. And **whatever a
present base holds is private**: read it to answer the question in front of
you, never copy it into a tracked file, never commit anything under
`.compost/`.

The **v0.1 corpus** is a different thing again — still unmigrated, still not on
this disk, and described below.

**Three things get called a corpus here, so this file is strict about it.**
Bare *corpus* always means the **test corpus** under `tests/corpus/`. The
**v0.1 corpus** is the removed personal notes and is never unqualified. And a
base's own content is **the records**, never a corpus.

## What is authoritative

**`docs/` holds four different kinds of thing, and the table says which.** It
used to claim one status for the whole directory while calling `spec.md`
historical four lines later; both could not be true. The superseded v0.2 drafts
that row named are in the notes repository now, with everything else that is
merely old.

| Source | Status |
|---|---|
| `docs/compost.md` | **the whitepaper — start here.** Carries its version in the status line; the *path* never moves, because the build and two suites hardcode it. What compost is, the fifteen principles, the shape, the grammar's vocabularies, and the decisions with the measurement behind each. |
| `docs/record-grammar.md`, `docs/record-format.md`, `docs/queries.md`, `docs/decisions.md` | **what is true now.** Rewritten as understanding improves. Prose and reasons — as of v0.2.12 `record-grammar.md` is **no longer the machine-read source**; that is the schema below. |
| `tools/record-schema-1.json` | **the record grammar, machine-read.** What a record may be. `tests/test_grammar.py` holds it against a real digest in both directions and validates every record with it. Graph-level invariants are not here — they are `check()`'s thirteen. |
| `docs/man-compost.md` | **what is true now**, and held against the program by `tests/test_manpage.py`. |
| `docs/roadmap.md`, `docs/design-*.md` | **what is being decided now.** A design document that has served its purpose moves to the notes repository rather than being deleted — it is a revision of something, and once TA ships it becomes a document in the base like any other. |
| `docs/migration.md` | the v0.1 corpus migration. **Part shipped, part never built** — the handle dictionary and `kg-8hex` exist; the routes are still a proposal. Describes files not on this disk. |
| `CHANGELOG.md` | what happened, and what it cost. Append-only in spirit. |
| the **v0.1 corpus** | **not in this repository.** It was personal notes and was removed from the history, not merely deleted. It is kept privately as the input for a migration that has not been written. |

Anything quoting the v0.1 corpus — `docs/migration.md` above all — describes
files you will not find here. Its measurements were taken while those files were
present and still stand; the paths are historical. If you need them to do the
migration, ask, because they are deliberately not on this disk any more.

It described `.dj` storage, `blocks.json` and `compost submit`, none of which
exist. Treat any instruction recovered from it as the record of why v0.2 is
shaped the way it is, never as a description of the current tool.

## The rules that bite

- **Work on `main`, tag each version.** No feature branches; see
  `DEVELOPMENT.md` for why this was learned the hard way. **Tag the
  candidate before running the gate** — `vX.Y.Z-rc`, one tag, no number,
  force-moved for each new candidate and deleted when the release is
  tagged. `clean-room.sh` demands a tag for the version the CHANGELOG
  names, and it runs before you tag; the rc is what breaks that circle.
  The full order is in `DEVELOPMENT.md`, "Closing a version".
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
- **Sources are immutable, and storage is a blob store.** Every digestor
  input lands under a freshly minted `GUID.EXT`, so `.compost/storage/`
  never overwrites anything — it refuses a name already in use, which can
  only mean a uuid repeated itself. The same bytes may legitimately be
  stored twice; `digest` reports that and does not resolve it. As of
  v0.2.14 that is not only the files a human imports: a digestor that meets
  content it does not own (a transcript turn's markdown prose) delegates to
  the digestor that does, and the delegated input is stored the same way,
  under `GUID.json` — no filename of its own, addressed instead by a JSON
  Pointer into the parent it came from. See `docs/roadmap.md`, "the
  recursion made explicit".
- **Nothing about ingestion is inferred from a file extension.** The route is
  named with `--as` or the command refuses. This was dispatch on the suffix
  until v0.2.2, where the fallback was not "markdown" but "anything at all".
  `src/routes.py` is the only place that knows how to read anything.
- **Anything may write records; they must be valid JSONL under `graph/`.**
  `digest` and `layer` are two writers, not the only two. A script, an agent or
  a migration tool that emits well-formed records is doing the same thing they
  do — `Store.load()` does not care who wrote a file, and **`check` is what
  enforces every invariant, not the identity of the writer.** A generated file
  that passes `check` is indistinguishable from one `digest` wrote.

  **This is a trust model, and right now the trust is unearned.** `check`
  verifies structure — parent counts, dangling endpoints, cycles — but it does
  **not** validate that a node's `type` is a known one, so a typo'd `"alais"`
  passes. A *grammar validation layer* is planned for when this has to run
  somewhere the writers are not trusted; until then the guarantee is "the
  agents writing here are trusted and `check` catches the structural mistakes",
  which is weaker than it looks and should be said out loud rather than assumed.

  **Two things that are still wrong.** Editing a line inside an existing file —
  records are immutable, and a whole-file rewrite is the only honest form of
  change. And inventing a CLI surface for it: there is no `compost layer alias`
  and there will not be one. Deleting a *whole* file that one `layer` run wrote
  is fine, and is the only inverse the design offers for accumulation it never
  removes.
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

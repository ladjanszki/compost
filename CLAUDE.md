# compost — start here

This repo is a tool **and its own knowledge base**. As of v0.2 the tool was
rewritten from nothing and the base has not been migrated yet, so those two
things are temporarily out of step. Read this before assuming either.

## Do this first

```bash
./tests/run.sh          # eight suites, all should pass
compost --help
```

Then read, in this order:

1. **`docs/man-compost.md`** — the five working subcommands, verified against
   the program rather than remembered.
2. **`docs/decisions.md`** — what was decided and why, with the measurements.
   Every non-obvious flag in this codebase is justified there.
3. **`docs/record-format.md`** — the node and edge design.
4. **`TODO.md`**, section `v0.2.1` — what is knowingly missing. Start here for
   "what should I do next".

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
- **Sources are immutable.** `storage/` refuses to overwrite a file whose bytes
  differ.

## Working with the human

They write in nvim, click blocks in the served HTML to copy handles, and reply
by citing them. A citation looks like `[-](#d826c4dd-eb36-4da9-acab-f6f424a90803)`.
When they paste one, resolve it from the graph before answering.

**Answer here, in this interface. Do not submit your reply as a turn.** They
import the round afterwards, which makes the answer addressable anyway.
Submitting as well is two copies of one answer in two places, and they are the
one who has to read both.

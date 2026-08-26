# compost — conversations and text to an addressable graph

A local-first knowledge base for people who run many projects at once and need
to get back into one cheaply after weeks away.

You write in your editor and submit. Every paragraph, list item, todo, tool call
and answer becomes a node with a permanent identifier, so you and an agent can
point at the same sentence and argue about it. Nothing is summarised away: the
conversation that produced a decision stays readable next to the decision.

```
compost init
compost digest --as=notes notes.md
compost digest --as=claude-code-transcript ~/.claude/projects/<slug>/*.jsonl
compost check
compost layer citation         # mint `cites` edges from the links already there
compost render
compost lookup d826c4dd-eb36-4da9-acab-f6f424a90803   # the block, and what cites it
compost serve                  # read it at http://127.0.0.1:7373
```

## What v0.2 is

v0.2 replaced everything. The tool no longer stores documents as text files
with identifiers written into them; it stores **nodes and edges** as JSONL, and
generates every view from those records and from nothing else.

```
--as=notes           ─► pandoc AST ─┐
--as=pandoc-ast      ─────────────► ├─► records ──► compost layer ──► records ──► views/default-djot  (agents)
--as=claude-code-transcript ──────► ┘               (derives, e.g.                views/default-html  (people)
                                                      citations)                  views/default-md    (README, …)
```

How a source is read is **named, never inferred from its extension**. The
suffix is a decoration that follows the bytes into storage; nothing routes on
it. `compost digest --as` lists the routes.

`compost layer` is the base's **second** writer: unlike `digest`, it reads
records already in the base and derives more from them — `compost layer
citation` mints a `cites` edge for every `[-](#guid)` link that resolves, and
an `alias`/`unresolved_citation` placeholder for every one that does not, so
the absence becomes a record instead of scrolling off a terminal. It is a
step of its own, not folded into `digest` or `render`: a citation can point at
a guid from an *earlier* import, so resolving it needs the whole loaded base,
not the batch a single `digest` validates in isolation.

The middle is the waist. Everything downstream reads two record types and never
an AST, which is what keeps the graph from drifting away from what is displayed:
a missing edge is a visibly broken page the same day.

## What it holds

| | |
|---|---|
| **nodes** | pandoc's own constructor names — `Para`, `Header`, `CodeBlock`, `Table` — plus `ListItem` and two others where pandoc's grammar is anonymous, plus `session`, `turn`, `toolcall`, `tooloutput`, `thinking`, `file`, `document`, `blob`, `alias`, `unresolved_citation` |
| **edges** | `contains` and `next` per layer, `touches`, `replies_to`, `cites`, `names`, `responds_to` |
| **identity** | a UUIDv4 per node, and a SHA256 `content_hash` where a node has content of its own; every edge also carries `content_hash`, `created_at` and `tool_version` |
| **citations** | `[-](#<guid>)` — a link, so a handle quoted inside a code block cannot become an edge. `compost layer citation` turns each into a `cites` edge, or an `alias`/`unresolved_citation` placeholder when the target is not in the base yet |

## Guarantees, and how they are kept

The design is only worth what its tests hold. Each suite states a property and
each has been made to fail on purpose:

```
$ ./tests/run.sh
test_records             526/526 identity round-trip   |   19853 nodes, 35788 edges
test_sabotage            6/6 sabotages caught
test_store               10/10 storage guarantees hold
test_digest              17/17 ingestion guarantees hold
test_views               6/6 view guarantees hold
test_citations           8/8 citation guarantees hold
test_bleach_session      7/7 session-fixture guarantees hold
test_session             11/11 session-import guarantees hold
test_session_views       13/13 session-view guarantees hold
test_lookup              12/12 lookup guarantees hold
test_serve               9/9 serve guarantees hold
test_manpage             6/6 man-page guarantees hold
test_grammar             7/7 grammar guarantees hold  |  35 node types, 12 edge pairs, 380 nodes
test_layer               16/16 layer guarantees hold
test_response            13/13 response guarantees hold
test_loop                7/7 loop guarantees hold
test_dj_prepare          8/8 dj_prepare guarantees hold
test_v01_dictionary      9/9 dictionary guarantees hold
corpus                   present, 520 documents
```

The first line is the whole format in one assertion:
`records_to_ast(ast_to_records(ast)) == ast`, exact equality, over 526
documents once the corpus is fetched — a documentation site, a curated corpus,
and one hand-built AST reaching the constructors no markdown reader can
produce. A bare clone runs the same property over a six-document smoke set,
and says so.

## Requirements

Python 3.12 and **pandoc 3.10 or newer**, which does every read and every
write. Nothing from PyPI. Node is no longer needed: djot goes through pandoc
like everything else.

Markdown is read as `commonmark_x` with three extensions **off**, each for a
measured reason — `attributes` would eat citations, `smart` would merge `—`,
`---` and `--` before anything is stored, and `fancy_lists` silently disables
task lists. `docs/decisions.md` has the numbers.

## Documentation

| file | what it is |
|---|---|
| `docs/man-compost.md` | the command, verified against the program rather than remembered |
| `docs/decisions.md` | what was decided and why, with the measurements behind it |
| `docs/record-format.md` | the node and edge design, and the AST translation |
| `DEVELOPMENT.md` | how to work on it |
| `TODO.md` | what is next, and what is knowingly missing |
| `CHANGELOG.md` | what happened |

The v0.1 corpus — the conversations, artifacts and raw session logs this was
built from — is **not in this repository**. It was personal notes, and it was
removed from the history rather than deleted in a commit. It is kept privately
as the input for a migration that has not been written yet, and it is not
readable by v0.2 in any case.

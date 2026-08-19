# compost — conversations and text to an addressable graph

A local-first knowledge base for people who run many projects at once and need
to get back into one cheaply after weeks away.

You write in your editor and submit. Every paragraph, list item, todo, tool call
and answer becomes a node with a permanent identifier, so you and an agent can
point at the same sentence and argue about it. Nothing is summarised away: the
conversation that produced a decision stays readable next to the decision.

```
compost init
compost import notes.md ~/.claude/projects/<slug>/*.jsonl
compost check
compost render
compost lookup d826c4dd        # the block a handle names, and what cites it
```

## What v0.2 is

v0.2 replaced everything. The tool no longer stores documents as text files
with identifiers written into them; it stores **nodes and edges** as JSONL, and
generates every view from those records and from nothing else.

```
sources ──► pandoc AST ──► records ──► views/default-djot   (agents)
            session JSONL ─┘           views/default-html   (people)
                                       views/default-md     (README, TODO, …)
```

The middle is the waist. Everything downstream reads two record types and never
an AST, which is what keeps the graph from drifting away from what is displayed:
a missing edge is a visibly broken page the same day.

## What it holds

| | |
|---|---|
| **nodes** | pandoc's own constructor names — `Para`, `Header`, `CodeBlock`, `Table` — plus `ListItem` and two others where pandoc's grammar is anonymous, plus `session`, `turn`, `toolcall`, `tooloutput`, `thinking`, `file`, `document` |
| **edges** | `contains` and `next` per layer, `touches`, `replies_to`, `cites` |
| **identity** | a UUIDv4 per node, and a SHA256 `content_hash` where a node has content of its own |
| **citations** | `[-](#<guid>)` — a link, so a handle quoted inside a code block cannot become an edge |

## Guarantees, and how they are kept

The design is only worth what its tests hold. Each suite states a property and
each has been made to fail on purpose:

```
$ ./tests/run.sh
test_records             520/520 identity round-trip   |   19567 nodes, 35308 edges
test_sabotage            6/6 sabotages caught
test_store               10/10 storage guarantees hold
test_views               5/5 view guarantees hold
test_citations           7/7 citation guarantees hold
test_bleach_session      7/7 session-fixture guarantees hold
test_session             9/9 session-import guarantees hold
test_session_views       10/10 session-view guarantees hold
test_lookup              10/10 lookup guarantees hold
test_manpage             6/6 man-page guarantees hold
```

The first line is the whole format in one assertion:
`records_to_ast(ast_to_records(ast)) == ast`, exact equality, over 520
documents — 42 fixtures, a 478-document documentation site, and one hand-built
AST reaching the constructors no markdown reader can produce.

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

`conversations/`, `artifacts/` and `raw/` are the v0.1 corpus, kept as the input
for a migration that has not been written yet. They are not readable by v0.2.

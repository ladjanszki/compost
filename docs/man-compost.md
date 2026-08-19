# compost(1) — v0.2

## NAME

compost — turn text and transcripts into an addressable graph, and generate
views from it

## SYNOPSIS

```
compost init [DIR]
compost import FILE...
compost ls
compost check
compost lookup HANDLE
compost render
compost serve [-p PORT]
compost version
```

## STATUS

Version 0.2.0. The eight subcommands below are the whole program.

`compost` is on PATH inside the `compost` conda env, which `DEVELOPMENT.md`
describes; from a checkout `python3 -m src.cli` is equivalent.

The v0.1 subcommands `new`, `submit`, `last` and `artifact` no longer exist.
`lookup` and `serve` are back, the two the daily loop actually missed.

## DESCRIPTION

compost reads sources once, turns them into nodes and edges, and generates
every view from those records and from nothing else. Sources are kept forever;
views are disposable and can be deleted at the cost of a rebuild.

Markdown is read as `commonmark_x` with `attributes`, `smart` and
`fancy_lists` disabled. Session transcripts are read as Claude Code JSONL.
Prose in a transcript goes through the same path a markdown file takes, so a
paragraph of an answer is a node like any other; tool output is stored whole,
because it is terminal text and parsing it as markdown invents structure it
never had.

Every citable block carries a **UUIDv4 handle**. A citation is a link whose
target is a handle:

```
[-](#d826c4dd-eb36-4da9-acab-f6f424a90803)
```

The link text carries nothing a machine reads. A handle is the whole guid: a
prefix of one does not match the citation syntax and is an ordinary link.

## SUBCOMMANDS

### init [DIR]

Create `.compost/` in DIR, or in the current directory if DIR is omitted.
Makes `graph/`, `storage/` and `views/`. Safe to run on an existing base.

`.compost/` is also the marker: every other command finds the base by walking
up from the current directory until it appears. There is no environment
variable and no config file, so a base cannot be half-configured.

### import FILE...

Ingest one or more sources. The reader is chosen by extension:

- `*.jsonl` — a Claude Code session transcript
- anything else — markdown

There is **no separate subcommand for transcripts**; `import` dispatches on the
suffix. For each file it copies the source into `storage/`, refusing to
overwrite a stored source whose bytes differ, and writes records to
`graph/STEM-EXT.jsonl`. The suffix is part of that name because `thing.md` and
`thing.jsonl` would otherwise write the same file.

Prints nodes, edges and the root handle per file, then a total. With no files,
prints usage and exits 2. If a source is already in `storage/` with different
bytes, says so and exits 1 without writing anything.

Re-importing a file mints fresh guids and writes the graph file again. Two
imports of one document therefore produce two sets of nodes with matching
`content_hash` values, which sit beside each other; recognising them as
multiples of one thing is a later layer.

### ls

List every loaded graph file, then counts: files, documents and sessions,
nodes, edges.
The file list is printed rather than summarised, because the failure mode of
"everything in `graph/` is the graph" is surprise about what was in there.

### check

Load the graph and verify it. Prints each loaded file, then any problems, then
counts. Exits non-zero if anything failed.

What it enforces:

- no edge points at a node that does not exist
- every node has exactly one incoming `contains`, except roots (`document`,
  `session`) which have none, and entities (`file`) which are referenced rather
  than contained
- the containment graph is acyclic
- each parent's `next` chain has exactly one head and reaches every child
  exactly once, without leaving the parent
- no guid carries two different records
- no two nodes share a handle
- `content_hash` is present exactly when a node has content of its own

### lookup HANDLE

Print the node a handle names: the guid, the node type, the source file it came
from, and the node's own text. Exits 0 on a hit and 1 on a miss.

**The handle is the whole guid.** A prefix is not a shorter handle, and there is
no resolver that would make it one. Shortening handles is an optimisation
nobody has yet felt the need for, and an abbreviation that silently stops
resolving as a base grows is a worse failure than a long citation.

It does **not** report what cites the node. That is the citation layer's
question and the citation layer does not exist yet; answering it here would
have meant deriving `cites` edges on every query, and a layer built by accident
is harder to replace than one that was never built.

Unlike `render`, this does **not** require `check` to pass. A view asserts the
whole graph is sound; a lookup answers one question from what is on disk, and
refusing because some unrelated file has a dangling edge would make a broken
base harder to debug rather than safer.

### render

Generate all three views into `.compost/views/`. If the graph fails `check`,
prints `refusing to render: …` and exits 1 without writing anything — a view of
a broken graph looks fine and is wrong, which is worse than no view.

| view | for | tool output |
|---|---|---|
| `default-djot/*.dj` | agents | shown in full — djot has no collapse |
| `default-html/*.html` | people | collapsed into `<details>` with a line count |
| `default-md/*.md` | regenerating README, TODO and the like | shown in full, **no handles injected** |

The markdown view carries only the handles its source already had, so its
output is clean enough to commit.

In the HTML view every citable block is an anchor; clicking a handle copies
`[-](#guid)` to the clipboard. `default-html/index.html` lists the documents.

### serve [-p PORT]

Serve `.compost/views/default-html/` on `http://127.0.0.1:7373`. Runs in the
foreground until interrupted; `-p` or `--port` chooses another port.

**It does not render.** `render` is the only thing that writes views and it
already refuses on a graph that fails `check`, so every file being served was
produced from a graph that was sound. The guarantee lives where the files are
made, and serving them needs no opinion of its own. Run `compost render` in
another terminal and refresh the page.

The socket is bound to **loopback only**. A knowledge base is not something to
put on the local network by accident, and `0.0.0.0` is exactly that accident.

Responses carry `Cache-Control: no-store`, and revalidation headers from the
client are ignored rather than answered. `Last-Modified` is accurate only to
the second, so a `render` landing in the same second as your last page load
would otherwise be answered `304 Not Modified` and you would refresh onto
yesterday's page. These are small local files; there is nothing to gain from
caching them.

With no views yet, says so and exits 1 rather than serving an empty directory.
A port already in use is reported the same way.

### version

Print the version. Also `--version` and `-V`. With no arguments at all, or with
`--help`, `-h` or `help`, compost prints its usage and exits 2 or 0 respectively.

## FILES

```
.compost/
  graph/      *.jsonl records, committed. Filenames carry no meaning: the
              loader concatenates every match, and load order cannot change
              the result. Only *.jsonl is read, so an editor backup is not
              part of the graph. Writes go through a temp file and an atomic
              rename, so a partial write never holds the extension.
  storage/    sources exactly as ingested, immutable
  views/      generated, disposable
```

## NODE TYPES

From pandoc, named exactly as pandoc names them: `Para`, `Plain`, `Header`,
`CodeBlock`, `RawBlock`, `BlockQuote`, `BulletList`, `OrderedList`,
`DefinitionList`, `Table`, `Figure`, `Div`, `LineBlock`, `HorizontalRule`, plus
`Row`, `Cell`, `Caption`, `TableHead`, `TableBody`, `TableFoot`.

Invented where pandoc's grammar is anonymous: `ListItem`, `DefinitionTerm`,
`DefinitionItem`.

From transcripts: `session`, `turn`, `toolcall`, `tooloutput`, `thinking`,
`file`. Also `document` for an imported text file.

## EDGE LAYERS

| layer | edges |
|---|---|
| `pandoc-ast` | `contains`, `next` — structure and order within parsed prose |
| `session` | `contains`, `next`, `touches` — transcript structure; `next` is log order |
| `claude-code` | `replies_to` — the `parentUuid` chain |
| `citation` | `cites` — derived from links in the text |

## EXIT STATUS

`0` success · `1` the graph has problems, no base was found, or a source would
be overwritten · `2` usage, or an unknown subcommand

Verified: `check` outside a base exits 1; no arguments exits 2; an unknown
subcommand exits 2; `init` is idempotent; a changed source exits 1; `render`
on a graph with a dangling edge exits 1.

## EXAMPLES

```
compost init ~/notes
cd ~/notes
compost import draft.md ~/.claude/projects/-Users-me-notes/*.jsonl
compost check
compost render
compost serve
```

## NOT YET IMPLEMENTED

No `submit`, `new` or `artifact`. No view for `file` nodes,
which are uncontained and so appear in no document tree. No migration of a
v0.1 base. Empty `thinking` nodes are stored but not rendered.

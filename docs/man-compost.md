# compost(1) — v0.2

## NAME

compost — turn text and transcripts into an addressable graph, and generate
views from it

## SYNOPSIS

```
compost init [DIR]
compost digest --as=ROUTE FILE...
compost ls
compost check
compost lookup HANDLE
compost render
compost serve [-p PORT]
compost version
```

## STATUS

Version 0.2.2. The eight subcommands below are the whole program.

`compost` is on PATH inside the `compost` conda env, which `DEVELOPMENT.md`
describes; from a checkout `python3 -m src.cli` is equivalent.

The v0.1 subcommands `new`, `submit`, `last` and `artifact` no longer exist.
`lookup` and `serve` are back, the two the daily loop actually missed.

## DESCRIPTION

compost reads sources once, turns them into nodes and edges, and generates
every view from those records and from nothing else. Sources are kept forever;
views are disposable and can be deleted at the cost of a rebuild.

How a source is read is **named on the command line and never inferred**. A
file called `notes.jsonl` digested `--as=notes` is markdown, because that is
what was asked for; the extension survives into `storage/` as a decoration for
whoever pulls the bytes back out, and nothing reads it.

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

### digest --as=ROUTE FILE...

Ingest one or more files, all read by the same named route.

| route | reads |
|---|---|
| `notes` | prose, as `commonmark_x` with the three extensions off |
| `claude-code-transcript` | a Claude Code session log, the whole `*.jsonl` |
| `pandoc-ast` | a pandoc JSON document somebody else already produced |

**`claude-code-transcript` is lossless.** Every line of the file becomes a node
carrying its own original JSON in `params["log"]`, and the guarantee is a
property rather than a promise:

```
records_to_session(session_to_records(lines)) == lines
```

A line type the importer has no reading for becomes a `logline`; an
unrecognised message block becomes a `contentblock` and is shown rather than
hidden. Nothing is filtered at read time, because a filter applied while
reading is applied once and silently. What to ignore is a question for a view
or a query, asked later.

`--as` is **required**. Omitting it, or naming a route that does not exist,
prints the table above and exits 2 rather than guessing. This replaces
dispatch on the file extension, which was wrong twice over: the fallback was
not "markdown" but "anything at all", so a PNG became a pandoc error rather
than a compost one; and `.jsonl` is a container, not a format, so the suffix
stops naming a reader the moment a second kind of JSONL exists.

`pandoc-ast` is the narrowest route, not the broadest — there is no reading
step in it to be wrong, because `ast_to_records` takes exactly that shape.
Whatever pandoc invocation produced the file stays outside the tool, where the
person who wrote it can inspect and tune it.

**Nothing is written until every file has been read and parsed.** A batch that
died halfway could not simply be re-run: storage names are minted, so the
files it had already ingested would come in a second time under fresh guids.
Validating first is what makes it safe to pass a glob.

**Directories are refused**, pointing at the shell rather than growing a
recursion flag — `compost digest --as=notes notes/*.md`, or `find … -exec`,
and the question of how deep to walk stays where the caller already has an
answer for it.

For each file it mints a guid, copies the bytes to
`storage/GUID.EXT`, writes records to `graph/OTHER-GUID.jsonl`, and adds a
`blob` node joined to the document root by a `derived_from` edge. The two
guids are unrelated on purpose: if either name were derivable from the other,
something would eventually derive it, which is suffix routing wearing a
different hat.

The `blob` node is how a document reaches its bytes, and the only way:

```json
{"record": "node", "guid": "8bfcf838-…", "type": "blob",
 "params": {"original_name": "s.jsonl", "stored_as": "8bfcf838-….jsonl",
            "bytes_sha256": "6b9b084b…", "imported_at": "2026-08-21T16:59:44Z",
            "route": "claude-code-transcript"}}
```

Reconstructing a storage path from the original name is guessing and will
guess wrong. The root node also records the `route` it came by, because every
block below it looks the same whichever way it was read.

Prints nodes, edges, the root handle and the blob handle per file, then a
total. With no files, prints usage and exits 2. A missing file or a directory
exits 1 having written nothing.

Re-digesting a file mints fresh guids and stores the bytes again, so the same
content can sit in storage more than once. That is **reported and not
resolved** — `note: these bytes are already in N blobs` — because deciding two
copies are one thing is a later layer's call. Two imports of one document
likewise produce two sets of nodes with matching `content_hash` values; the
identity question is still open.

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
  `session`) which have none, and entities (`file`, `blob`) which are pointed
  at rather than contained
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
`file`, `logline`, `contentblock`. Also `document` for an ingested text file,
and `blob` for the bytes one was derived from.

`logline` is a line the importer keeps but has no reading for — *kept* and
*understood* are different claims, and only the first is the importer's to
make. `contentblock` is the same for a message block. Both carry the original
JSON verbatim.

`file` and `blob` are different things and are deliberately not merged. A
`file` is a **path a session touched** — it may not exist, and no bytes are
held. A `blob` is **bytes that are in `storage/`**. Every vocabulary that has
faced this splits it the same way (PROV-O, NFO, FRBR, DCAT): a path is a
locator, not a thing. When the same path is both, a `represents` edge joins
them; nothing mints one yet.

## EDGE LAYERS

| layer | edges |
|---|---|
| `pandoc-ast` | `contains`, `next` — structure and order within parsed prose |
| `session` | `contains`, `next`, `touches` — transcript structure; `next` is log order |
| `claude-code` | `replies_to` — the `parentUuid` chain |
| `citation` | `cites` — derived from links in the text |
| `ingestion` | `derived_from` — which bytes a document was read from |

## EXIT STATUS

`0` success · `1` the graph has problems, no base was found, or an input was
missing or unreadable · `2` usage, an unknown subcommand, or a missing or
unknown `--as`

Verified: `check` outside a base exits 1; no arguments exits 2; an unknown
subcommand exits 2; `init` is idempotent; `digest` without `--as` exits 2;
a directory or a missing file exits 1 having written nothing; `render` on a
graph with a dangling edge exits 1.

## EXAMPLES

```
compost init ~/notes
cd ~/notes
compost digest --as=notes draft.md
compost digest --as=claude-code-transcript ~/.claude/projects/-Users-me-notes/*.jsonl
compost check
compost render
compost serve
```

## NOT YET IMPLEMENTED

No `submit`, `new` or `artifact`. No view for `file` or `blob` nodes, which
are uncontained and so appear in no document tree. No migration of a v0.1
base. Empty `thinking` nodes are stored but not rendered.

**Sidechains are not followed.** A `claude-code-transcript` reads exactly the
file it was given. A subagent's turns live in a second file, discoverable at
`<session-id>/subagents/agent-<agentId>.jsonl` with a `.meta.json` sidecar
beside it. Everything needed to join them now reaches the graph — the sidecar's
`toolUseId` matches a stored `toolcall`, verified on real data — but the join
itself is deliberately a later, explicit step. See `TODO.md`.

**`logline` and `contentblock` have no view.** Loglines are harness machinery
and are stored, addressable and not rendered. Envelope turns — a `user` line
whose only content was a tool result, already folded into the call that
produced it — are likewise kept and not shown.

`check` does not verify `storage/`. It reads records, so a blob whose bytes
were altered on disk is not detected, even though `bytes_sha256` is exactly
what would detect it.

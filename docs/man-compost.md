# compost(1) — v0.2

## NAME

compost — turn text and transcripts into an addressable graph, and generate
views from it

## SYNOPSIS

```
compost init [DIR]
compost digest --as=ROUTE (--mutability=VALUE | --updates=GUID) FILE...
compost ls
compost check
compost layer NAME [--by SCHEME]
compost lookup HANDLE
compost render
compost draw [ROOT] [--engine ENGINE]
compost serve [-p PORT]
compost version
```

## STATUS

Version 0.2.17. The ten subcommands below are the whole program.

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
| `claude-code-response` | a `{responds_to, follows?, envelope}` wrapper around `claude --print --output-format json` |

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

**A transcript brings its subagents with it.** A Claude Code log that launched
a subagent records that agent's id in its own lines, and the agent's turns are
in a file named after it — so digesting the parent digests those too,
recursively, and joins each one to the `Agent` call that launched it. Every
discovery is printed. `--no-follow` digests exactly the file named and nothing
else.

This is the only place `digest` reads a file it was not handed, and it is
allowed because it is **not a guess**: the file says the other file exists.
Following a reference and globbing a directory are different acts — globbing
would be an assumption about layout, while this reads only what the source
named. A referenced file that is absent is reported and skipped, since a
transcript copied away from its `subagents/` directory is an ordinary thing to
digest.

`--as` is **required**. Omitting it, or naming a route that does not exist,
prints the table above and exits 2 rather than guessing. This replaces
dispatch on the file extension, which was wrong twice over: the fallback was
not "markdown" but "anything at all", so a PNG became a pandoc error rather
than a compost one; and `.jsonl` is a container, not a format, so the suffix
stops naming a reader the moment a second kind of JSONL exists.

**`--mutability=VALUE` is required at creation** — `immutable`, `append-only`
or `mutable` — for the same reason `--as` is: a statement of intent the bytes
do not contain is never guessed. It is set once and never changes; giving it
together with `--updates` is refused, because `--updates` names a root whose
mutability was already decided the day it was minted.

**`--updates=GUID` re-ingests a longer or changed version of a file already in
the base**, naming the root explicitly — "which of fifty `README.md` files"
has no safe automatic answer, so the tool never guesses it. `GUID` must
already be a `document` or `session` root; naming anything else, or a root
declared `immutable`, is refused. What happens next depends on the target's
own declared mutability, decided the day it was minted and never
re-litigated by this flag:

- **`append-only`** mints nodes for only the **tail** — the file's own
  unchanged prefix is not re-minted — adds `contains`/`next` edges onto the
  *existing* root, and rewrites that root's `record_subtree_hash` in place (a
  whole-file rewrite of `graph/*.jsonl`, the only honest form of change to an
  otherwise-immutable record; the root's own `record_hash`, what it
  *claims*, never moves). Refused if the file's start no longer matches the
  root's recorded head — see below.
- **`mutable`** mints a **whole new tree**, chained to the old one by exactly
  one `revision_of` edge, root to root (`docs/design-0.3.0.md` §7, §9,
  v0.2.16). Nothing is shared with the previous tree — every block, changed
  or not, gets a fresh guid — and the old tree is not rewritten at all; it
  stays in its own file, exactly as it was, fully reachable. This is
  deliberately the unsophisticated choice: sharing unchanged blocks across
  revisions would give a block two `contains` parents, which breaks the
  invariant that makes `render` a tree walk rather than a graph walk.
  Routing `mutable` through the `append-only` path instead would run and be
  silently wrong — an appended `mutable` root would inherit the
  head-unchanged refusal above, so the one contract that promised "anything
  here may change" would be the one told its start no longer matches.

The file's whole new bytes are stored again as a second blob either way —
storage does not deduplicate across a re-ingest yet (`TODO-storage-revamp.md`)
— so an `append-only` root can carry more than one `derived_from` edge;
`records.blob_of()` still returns one blob, the current one, and
`records.blobs_of()` returns all of them, oldest first.

Both order blobs by `imported_at`, then by guid. **The guid is there for
determinism, not meaning.** `imported_at` records whole seconds, so two
ingests inside one second tie, and without a second key the answer was
decided by whichever `graph/*.jsonl` loaded first — against the standing rule
that file order carries none. On a tie the guid picks arbitrarily: one base
always answers the same way, but the answer is not "the newer bytes". It
cannot be, because nothing in the records says which ingest came last —
`imported_at` is audit metadata, the same class as `created_at`, which this
project has already declined to build a contract on. The real answer is a
`supersedes` edge blob-to-blob, making "current" mean *the blob nothing
supersedes*; that is a schema change and belongs with the storage work
(`TODO-storage-revamp.md`).

**Omitting `--updates` mints a second root, silently** — accumulation is the
standing rule (`docs/decisions.md`), not an error and not (yet) a warning. One
exception is derivable and printed when it fires: a Claude Code transcript's
own filename can name the session it already belongs to (`<sessionId>.jsonl`,
or `agent-<toolUseId>.jsonl` for a subagent), so `digest` prints a note
suggesting the matching `--updates=GUID` when one exists in the base — advice
only, never acted on, since acting on it would be exactly the silent behaviour
change this paragraph just said does not happen.

`check` verifies the contract `--mutability` declares: an `append-only` root
whose recorded head no longer folds the way it used to is a reported problem,
and so is an `immutable` root carrying more than one `derived_from` edge. A
`mutable` root's own contract is checked on `revision_of` instead
(v0.2.16): the edge must be irreflexive, acyclic, root-to-root only, and at
most one revision per predecessor root — never per-block, since a revision
re-mints the whole tree and correspondence between the two is computed by
`records.align()` on demand, not stored as a second graph the size of the
first.

`pandoc-ast` is the narrowest route, not the broadest — there is no reading
step in it to be wrong, because `ast_to_records` takes exactly that shape.

`pandoc-ast` is the narrowest route, not the broadest — there is no reading
step in it to be wrong, because `ast_to_records` takes exactly that shape.
Whatever pandoc invocation produced the file stays outside the tool, where the
person who wrote it can inspect and tune it.

**`claude-code-response` digests one round of the conversation loop** —
`docs/roadmap.md`, "the conversation loop". Its input is not the bare envelope
`claude --print --output-format json` prints, but a one-key wrapper naming
what it answers:

```json
{"responds_to": "<a document or session root's guid>",
 "follows":     "<the previous round's response root>",   // optional
 "envelope":    { ...all 21 keys claude printed, verbatim... }}
```

Every envelope key lands in `params` on the new `document` root, unrenamed —
including `params["uuid"]`, the envelope's *own* identifier, which is not the
same thing as the record's `guid` even though the two sit one key apart.
`result` is kept there whole **and** read through the same markdown dialect as
`notes`, so the answer's paragraphs become citable blocks like any other
document's — without that second step you could read a response but never cite
a sentence of it. The route also mints two edges: `responds_to`, from this
root to the guid named in the wrapper, and `next`, from that guid to this root,
for reading order. Given `follows` it mints a third, `next` from the previous
round's response to this round's note, which is what turns a pile of pairs
into one walkable chain. None is a `contains` edge and no node contains
another — see EDGE LAYERS below — so a note and its response stay two
documents, each with its own page.

**`follows` is what makes a conversation a chain.** The route mints `next`
from a note to its own response, but nothing joins one round to the next —
this wrapper is the only file in the loop carrying structural guids, and the
first implementation did not have it name the round before. Two rounds gave
`note1 → resp1` and `note2 → resp2` with nothing between them, so *walking a
conversation* — the whole reason no container node is needed — silently did
not work. It is optional, because a first round follows nothing, and asserted
rather than derived from `created_at`, which would be guesswork the moment two
rounds interleave.

```
note1 --next--> resp1 --next--> note2 --next--> resp2
```

**A guid the wrapper names must already be resolvable, or the whole file is
refused.** Unlike a citation, which may legitimately point at something not
yet in the base and gets a placeholder from `compost layer citation`,
`responds_to` and `follows` are structural: a value that resolves to nothing is a bug in
whatever wrote the wrapper, not a fact worth recording, and `digest` refuses
the file rather than writing a dangling edge. This extends the same
all-or-nothing promise every route already gets — see below — to check that
every edge a route mints resolves against this batch or the base already on
disk, not only that the route itself could parse its input.

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
likewise produce two sets of nodes with matching `record_hash`/
`record_subtree_hash` values; the identity question is still open.

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
  `session`) which have none, and entities (`file`, `blob`, `alias`,
  `unresolved_citation`) which are pointed at rather than contained
- the containment graph is acyclic
- each parent's `next` chain has exactly one head and reaches every child
  exactly once, without leaving the parent
- a session is launched by at most one tool call
- `contains` and `launched` together are acyclic, since a view renders a
  subagent inside its call and would otherwise loop
- no guid carries two different records
- no two nodes share a handle
- every node carries `record_hash` and `record_subtree_hash` — unconditionally,
  not only a node with content of its own
- `schema_version`, when present on a record, is not greater than what this
  tool writes — the check exists to fire the day a newer tool's records are
  loaded by an older one
- both hashes **recompute**: `record_hash` from `[type, params, content]`,
  `record_subtree_hash` from the fold over `contains`/`next` — the first
  assertion here that verifies content rather than structure. When this fails
  on a node under a root declared `append-only` or `immutable`, the problem
  names that root's `mutability` explicitly — the same signal, attributed to
  the contract it violates, since existing content changing is exactly what
  both contracts forbid
- an `immutable` root carries at most one `derived_from` edge — a proxy for
  "no edges were added after the ingest that created it" rather than that
  literal claim, which would need a clock this project does not keep
  (`created_at` is audit metadata, never semantics); a hand-authored edge
  spliced onto such a root with no second blob to go with it is a real gap
  this does not catch
- `revision_of` is irreflexive, acyclic, root-to-root only (never a block),
  and at most one revision per predecessor root — the same treatment
  `derived_from` gets above, for a TA revision's whole-new-tree chain
  (v0.2.16)

### layer NAME [--by SCHEME]

Derive new records from the base **itself**, rather than from bytes nobody
has seen before — `digest`'s job. Bare `compost layer` lists what can be
built, and by which schemes:

```
compost layer citation [--by uuid-link]   the current syntax  (the default)
compost layer citation --by kg-8hex       v0.1 legacy handles (opt-in)
```

**`--by` names how a citation is recognised, and it defaults to `uuid-link`.**
The default is written down rather than being "the only scheme there is", so
adding the second one did not turn a bare `compost layer citation` into an
error.

Either scheme mints a `cites` edge for every citation that resolves. A target
not in the base cannot become an edge — a dangling endpoint would fail
`check` — so instead it mints one `alias` node (naming the missing value) and
one `unresolved_citation` node it points at, per *distinct* unresolved value
in the run, and a `cites` edge from the citing block to that placeholder.

Prints a line like:

```
  1,204 cites edges  |  3 unresolved -> 3 placeholders
    deadbeef-0000-0000-0000-000000000000
    …
```

#### --by uuid-link

Reads every `[-](#guid)` link in the base. A citation is a `Link` node, so
reading the parsed content — never the raw text — is what makes "handles
inside code blocks are not citations" true by construction.

#### --by kg-8hex

Reads the v0.1 syntax, `{#a3f2b1c4}`, in the three forms the old corpus
writes: bare, with the expansion marker `{#a3f2b1c4+++}`, and with a version
pin `{#a3f2b1c4@ver}`. All three name the same handle; the suffix is not part
of the name.

**Nothing is rewritten.** The old syntax stays exactly as authored, on disk
and at render time. This adds a way to look it up and nothing else.

The match runs *within* each `Str` of the parsed content, not against whole
tokens, because real prose puts punctuation after a citation — `{#aa813aa9}.`,
`({#b1c2d3e4}),`. Exclusions are structural rather than rules: a `Code` node's
text is a bare string and a code block's lives in `params["text"]`, neither of
which is ever a `Str`, so handles quoted inside code contribute nothing.
`{#xxxxxxxx}`, `{#handle}`, `{#uuid:hash}` and `{#...}` are excluded because
they are not eight hexadecimal characters.

An 8-hex handle is not a guid, so it resolves through an **alias dictionary**
— `alias` nodes with `scheme: kg-8hex` and a `names` edge to the real block —
which arrives from outside the tool. That makes a `kg-8hex` placeholder
genuinely resolvable, unlike a `uuid-link` one: build before the dictionary
lands and every handle gets a placeholder; add it, rebuild, and the same
handles mint real edges. The earlier placeholder is kept, as the record of a
moment when it did not resolve.

A `names` edge pointing at an `unresolved_citation` is never followed, so a
build's own placeholders can never become the next build's answer.

If two aliases name two *different* real blocks for one handle, the handle is
**ambiguous**: it mints nothing and is reported.

```
  4 cites edges  |  1 unresolved -> 1 placeholder
    e5f6a7b8
  1 ambiguous, minted nothing:
    a1b2c3d4 -> 2 distinct targets
```

**This scheme is opt-in and is never the default.** It recognises eight hex
characters in prose, so a conversation that says in words "handles look like
`{#a3f2b1c4}`" mints a real edge when that string is also a real handle.
Nothing structural excludes it, which is why choosing it has to be deliberate.

**Running it twice writes two complete sets of records.** `layer` does not
read what a previous run wrote, so nothing is deduplicated and nothing is
removed — the same governing decision as everywhere else in this tool: it
does not hold your hand. See `docs/roadmap.md`.

Like `lookup` and unlike `render`, this is **not** gated on `check` passing.

### lookup HANDLE

Print the node a handle names: the guid, the node type, the source file it came
from, and the node's own text. Then print what **cites** it — every `cites`
edge whose destination is the node — and, separately, any citer that only
reached a placeholder minted before this block existed, labelled apart.
Exits 0 on a hit and 1 on a miss.

**The handle is the whole guid.** A prefix is not a shorter handle, and there is
no resolver that would make it one. Shortening handles is an optimisation
nobody has yet felt the need for, and an abbreviation that silently stops
resolving as a base grows is a worse failure than a long citation.

**If the argument is not a guid in the graph, it is tried as an alias
value.** Every `alias` node whose `params["value"]` matches is resolved and
printed — never one picked silently, since several aliases legitimately share
a value (two builds of the citation layer mint two aliases for the same
missing handle, naming two different placeholders).

This does not rebuild the citation layer, and is not gated on it having been
rebuilt. On a base where a citing document arrived after the last
`compost layer citation`, this **under-reports rather than lies** — an
accepted risk, recorded in `docs/roadmap.md`.

Unlike `render`, this does **not** require `check` to pass. A view asserts the
whole graph is sound; a lookup answers one question from what is on disk, and
refusing because some unrelated file has a dangling edge would make a broken
base harder to debug rather than safer.

### render

Generate all three views into `.compost/views/`. If the graph fails `check`,
prints `refusing to render: …` and exits 1 without writing anything — a view of
a broken graph looks fine and is wrong, which is worse than no view.

A transcript that was **launched by another** gets no page of its own — it is
rendered inside the `Agent` call that ran it, collapsed in HTML like any other
tool output, because that is what it is. One conversation is one page however
many subagents it spawned. A subagent digested on its own, with no parent in
the base, does get a page: nothing else would show it.

`render` writes exactly this render's output and **removes view files it did
not produce**, so a page that should no longer exist cannot linger in a
browser.

| view | for | tool output |
|---|---|---|
| `default-djot/*.dj` | agents | shown in full — djot has no collapse |
| `default-html/*.html` | people | tool calls, their output, subagent transcripts and slash-command output collapsed into `<details>` |
| `default-md/*.md` | regenerating README, TODO and the like | shown in full, **no handles injected** |

The markdown view carries only the handles its source already had, so its
output is clean enough to commit.

In the HTML view every citable block is an anchor. **Hovering highlights the
smallest block under the cursor**; holding Shift extends the highlight over its
subtree — the descendants of a container, or everything under a heading down to
the next heading of equal or higher level. **Clicking anywhere in a block**
copies `[-](#guid)` and a toast shows what was copied.

Shift changes the highlight and never the clipboard: the copied string is
identical with or without it. v0.1's `{#8hex+++}` was a subtree *citation
syntax*, and v0.2 resolves no such thing.

`default-html/index.html` lists every root, in one section per member of
`records.ROOT_TYPES` — generated at render time, never a hardcoded pair, so a
root type v0.3.0 adds grows the page a section without touching `views.py`.
Today that is `Sessions` and `Documents`, sorted newest first: sessions by
last turn, documents by when they were imported. A row shows a **display
name** when one exists — its own record, read here and written nowhere in
`src/`, see `extras/compost-name` below — and falls back to the source
filename otherwise; naming a root never changes its page's filename. A
session row also carries its first and last turn and its session id; a
document row carries a word count and its import time, the only date a
`document` root can reach, through `derived_from` to its `blob`. Every root
digested more than once gets its own row — nothing is collapsed.

### draw [ROOT] [--engine ENGINE]

Generate a Graphviz picture of the base into `.compost/graphviz/` — the whole
base by default, or the subgraph under `ROOT` (a whole guid) when named. Like
`render`, refuses on a graph that fails `check` and prints
`refusing to draw: …`, exiting 1 without writing anything.

**Always writes `graph.dot`. Writes `graph.svg` too only when the chosen
engine is on PATH.** The DOT is the deliverable that keeps the graphviz
binary optional at all: readable by an agent, pasteable, and renderable later
on any machine that has graphviz, so the command never makes the SVG a
precondition for writing it. With no engine found, says so and still exits 0.

`--engine` picks the layout engine, one of `twopi` (default), `sfdp` or
`dot`. **`dot` is not the default and is not safe for a whole base** — it was
killed at a 180-second ceiling on a single 500-node graph shaped like
compost's `contains` tree plus `next` chain, and again on a single
2,773-node document. `twopi` lays that shape out radially in a fraction of a
second and is the measured fastest engine at scale; `sfdp` is available for a
citation-heavy graph that has stopped being tree-shaped, and `dot` for a
small scoped subgraph where hierarchy is worth the wait. See
`docs/roadmap.md`, "v0.2.7 — a graph view", for the measurements.

v1 draws everything: every node, every edge, no collapsing policy. A whole
base is thousands of nodes, so the first picture is unreadable *as a
picture* and useful *as evidence* — the DOT is a full listing regardless of
whether anyone can read the SVG as an image.

Every node carries `id="<guid>"`, which survives into the SVG as `<g
id="…">` — graphviz escapes a guid's hyphens on the way out (`&#45;`), so
anything checking for one must parse the SVG rather than search its raw
text. Every edge carries `class="<layer>"`, its record layer rather than its
type, so a citation-heavy overlay can be pulled out of an otherwise
structural picture later without re-deriving it. Neither is `subgraph
cluster_`: measured, `twopi` ignores clusters entirely.

A whole-base picture adds one node graphviz never sees as a record: a
DOT-local `__root__`, joined to every root (`document` or `session`) so a
radial engine has one centre for the whole forest. It never reaches `check`
and is never written to `graph/`.

Past roughly 5,000 nodes, prints a warning that the SVG is getting large —
one real base measured 16.9 MB at 12,632 nodes — and **still writes it**;
output size, not layout time, is the ceiling, and there is no node count at
which withholding the SVG is more useful than saying so.

`draw` owns `.compost/graphviz/` the way `render` owns `views/`: what is on
disk after a run is exactly that run's output, so switching from one root to
another, or to the whole base, cannot leave a stale picture behind.

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
              rename, so a partial write never holds the extension. Flat by
              rule as of v0.2.8: a subdirectory is never read, and `digest`
              and `layer` refuse to write into one.
  storage/    sources exactly as ingested, immutable
  views/      generated, disposable
  graphviz/   generated, disposable — `compost draw`'s graph.dot/graph.svg.
              A peer of graph/, storage/ and views/, not inside views/: a
              future HTML view will *embed* this SVG, so it is an input to
              `render`, not one of its outputs.
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

`document` is also what `--as=claude-code-response` mints, reusing the type
rather than inventing one: a root needs zero `contains` parents to pass
`check`, and only `document` and `session` qualify. Its `params` hold every
key the `claude --print --output-format json` envelope carried, verbatim,
beside the usual `meta`/`pandoc_api_version`/`source`/`route` — see
`docs/record-grammar.md` §3.3.

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

`alias` and `unresolved_citation` are minted by `compost layer citation` rather
than by `digest` — and by anything else that writes valid records, such as the
migration's dictionary script. An `alias` names a value
(`params["value"]`, `params["scheme"]`) that leads to another node by a
`names` edge; today that node is always an `unresolved_citation`, a
placeholder for a citation target not yet in the base. Both carry
`created_at` and `tool_version` as top-level fields, the same as an edge —
and both carry `record_hash`/`record_subtree_hash` like every other node,
since v0.2.13 made the two unconditional (`layers.py:_entity()` folds them
in, the same as `digest`'s own mints).

## EDGE LAYERS

| layer | edges |
|---|---|
| `pandoc-ast` | `contains`, `next` — structure and order within parsed prose |
| `session` | `contains`, `next`, `touches` — transcript structure; `next` is log order |
| `claude-code` | `replies_to` — the `parentUuid` chain |
| `citation` | `cites` — derived from links in the text; `names` — an `alias` to what it names |
| `ingestion` | `derived_from` — which bytes a document was read from |
| `agent` | `launched` — the tool call a subagent transcript ran under |
| `conversation` | `responds_to` — response root → the root it answers; `next` — that root → the response, reading order |

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
compost layer citation
compost render
compost serve
```

## NOT YET IMPLEMENTED

No `submit`, `new` or `artifact`. No view for `file`, `blob`, `alias` or
`unresolved_citation` nodes, which are uncontained and so appear in no
document tree. No migration of a v0.1 base. Empty `thinking` nodes are
stored but not rendered.

`layer` keeps no record of what it has built. Nothing tells you a base's
citation layer is stale, and nothing rebuilds it for you — `lookup` and any
future view under-report on a base where a citing document arrived after the
last `compost layer citation`. There is no `drop`, no deduplication of what a
rerun produces, and no way to shrink a base other than deleting a whole graph
file. All deliberate: see `docs/roadmap.md`, "the tool does not hold your
hand".

**Views carry their full meaning to djot, HTML and markdown only.** Handles,
authorship and tool names ride on `Div` attributes and format-specific raw
blocks, which `latex`, `plain`, `man`, `typst`, `rst`, `docx` and `odt` drop —
so a transcript exported to any of those, **PDF included**, is unattributed
prose. This is a deliberate limit, not an oversight: the readers that matter
(agents on djot, people on HTML, GitHub on markdown) are all on the surviving
side. `docs/decisions.md` has the measurements and the staged plan for lifting
it.

**`logline` and `contentblock` have no view.** Loglines are harness machinery
and are stored, addressable and not rendered. Envelope turns — a `user` line
whose only content was a tool result, already folded into the call that
produced it — are likewise kept and not shown.

`check` does not verify `storage/`. It reads records, so a blob whose bytes
were altered on disk is not detected, even though `bytes_sha256` is exactly
what would detect it.

## SEE ALSO

Two things sit beside `compost` rather than inside it, and neither is a
subcommand — the count in STATUS does not include them.

**`compost-new`** — a separate console command, installed by the same `pip
install -e .`. Mints a scratch filename, opens `$EDITOR`, digests the file
as `notes` on close. `extras/compost_new.py`; `DEVELOPMENT.md`, "What
belongs in extras/".

**`compost-name <root-guid | storage-name> "The display name"`** — same
standing, same file it is documented beside. Resolves the identifier to a
root (a guid directly, or a storage name through the `blob` it names and its
`derived_from` edge), refuses a non-root, an unknown identifier or an empty
name, and writes one new `graph/<uuid>.jsonl` holding a `display_name` node
and the `names` edge that points it at the root — never editing a file
already written, so renaming is running it again. Runs `check` on the result
and reports it. `extras/compost_name.py`.

**A read-only SQL view over `graph/*.jsonl`**, via duckdb — nothing
materialised, no subcommand, no `compost query`. `tools/graph_sql.py`
connects it; `tools/queries/*.sql` holds starting queries and a SQL twin of
most of `check`'s assertions; `docs/queries.md` says what each one answers.
Development material, not installed.

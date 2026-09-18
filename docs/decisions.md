# v0.2 text importer — decisions and known issues

Working document for the pandoc-only importer. Decisions here are settled
unless revisited explicitly; known issues are accepted and *not* being fixed
in this step. Everything is measured against pandoc 3.10.1 / pandoc-types
1.23.1.2 on the 19 notes in `raw/` plus the five root markdown documents.

## The dialect

`.md` input is read as **commonmark_x**, with three extensions disabled.

```
read:   pandoc -f commonmark_x-smart-attributes-fancy_lists -t json
write:  pandoc -f json -t commonmark_x-smart --wrap=preserve
```

*This reverses an earlier decision to use `gfm`, and the reversal is the
reason to keep a corpus around.* On the 25 documents of this repo both score
identically — 1625 addressable blocks, fixed point everywhere — so gfm won on
having the safe defaults. Measured against 112 more documents from a real
documentation site, they separate sharply:

| read / write | fixed point |
|---|---|
| `commonmark_x` tuned | **140 / 152** |
| `markdown` + list extension | 119 / 152 |
| `gfm` | 71 / 152 |

The gfm *writer* loses data that the commonmark_x writer keeps — most of all
code fence info strings containing a comma, which is how every mdBook, Jekyll
and Docusaurus corpus annotates its examples:

```
source        ```rust,ignore        classes: ["rust,ignore"]
gfm writes    ```                   classes: []            <- lost
cmx writes    ``` rust,ignore       classes: ["rust,ignore"]
```

The three disabled extensions each prevent a silent corruption, and none of
them is optional:

- `-attributes` — otherwise `{#fce6a885}` parses as an attribute and a
  *citation* becomes an anchor *definition*: an empty `Span` carrying that id,
  colliding with the real block that owns it.
- `-smart` — otherwise the reader collapses `—`, `---` and `--` into two
  typographic characters before anything is stored. Reader-side, so
  unrecoverable.
- `-fancy_lists` — otherwise it silently suppresses `task_lists` and every
  `- [x]` stays literal text. `--list-extensions` reports `+task_lists` the
  whole time; there is no warning.

The two invariants that outrank the flag list, and that any replacement reader
must satisfy: **`{#...}` stays literal text** and **`---` stays three
hyphens**. Enabling either extension later is a canonization-time change
disguised as a flag. Extensions may be added *additively* because those change
text that was previously inert.

Verified surviving a full read/write/read cycle: handles plain and expanded,
all four dash forms, checked and unchecked task items, all five callout types,
and comma-bearing fence info strings.

## Citations

> **Superseded in two places, kept for the reasoning.** The syntax is
> **`[-](#<guid>)`**, a markdown link — not `{@a1b2c3d4}`, which was an
> intermediate step that was never shipped. And the migration **does not rewrite
> the old corpus**; see `docs/roadmap.md` v0.2.5 and *Reading a v0.1 `.dj`*
> below. The argument about `{#x}` meaning the wrong thing is what led to both,
> and stands.

A reference was to be written **`{@a1b2c3d4}`**, not `{#a1b2c3d4}`.

`{#x}` means "this element *has* id x" in every markup language that knows the
notation, and both pandoc and djot act on it. Using it to mean "points at x"
was backwards, and any reader with `attributes` enabled silently agreed with
the language rather than with us. The two notations now say what they mean:
`{#x}` assigns, `{@x}` refers. Verified unescaped through a full read/write
cycle, plain and expanded.

**`{@x}` was superseded by `[-](#guid)` for a stronger reason than either.** It
fixed the *meaning* but not the *mechanism*: it was still text, so extraction was
a regex over flattened content, and a handle quoted inside a code block became a
real edge. A link is a `Link` node, and a code block holds text with no inlines —
so "handles inside code are not citations" became true by construction rather than
by vigilance.

**Citation edges are derived, not asserted.** The draft classed them as
asserted alongside `derived_from`, but the stated reason `derived_from` must be
asserted is that no parser can recover it — and a citation is the exact
opposite, sitting in the text where a regex finds it every time.

That is what dissolves the duplication worry. Two copies of a fact can diverge
only if both are authoritative. The text is the source of truth and the edge is
a projection of it, so a stale edge is a rebuild to run rather than a conflict
to resolve — exactly like `contains`. The original text is never rewritten to
remove the reference, and the graph still gets real edges.

**The existing corpus was to be normalised during migration.** *(Rejected — see
below.)* A line that is exactly `{#xxxxxxxx}` is an assignment and stays one;
every other occurrence is a citation and becomes `{@xxxxxxxx}` in the records the
migration produces.

**That normalisation is rejected.** The old syntax stays exactly as written, in
the records and in every view, and an opt-in `alias` layer makes the old handles
resolvable instead. Three reasons: it would delete the only record that the old
handles ever existed; the rewrite pass is textual, which is the operation this
project forbids, applied to the one corpus that quotes its own syntax constantly;
and the corpus is full of conversations *about* eight-character handles, which
would end up referencing a format appearing nowhere in the base they live in.

## Identifiers and citations, as settled

A handle is the **full UUIDv4** — in records, in views, and in citations. A
prefix of one is not a handle: it does not match the citation syntax, and there
is no resolver that would make it one.

It costs something measurable. On the bleached notes, handle text is **21.7%**
of the djot view at full length against 7.7% at eight characters, and on small
structurally dense documents it reaches 60–75% of the file. That is real, and
it is accepted.

*This entry previously said* the cost was accepted because deferring committed
to nothing — a resolver already took any unambiguous length, so when the prefix
arrived old citations would stay long, new ones would be written short, and no
pass over stored text would be needed, exactly as full and abbreviated SHAs
coexist in a git log.

That resolver was written and then removed, and the reasoning with it. Three
things were wrong with it. It resolved prefixes in the graph while the HTML
view emitted the href verbatim, so a shortened citation resolved for a tool and
was a **dead anchor for a person clicking it**. Uniqueness was computed over
whatever happened to be loaded, so a prefix unambiguous today collides as the
base grows — and `check` never looked at citations, so nothing would have said
so. And it was an optimisation built ahead of any measured pain: nobody had
complained about handle length; the 21.7% was a number in a document, not a
person's complaint. The git analogy held for the storage and broke for the
reader, which is the half that matters here.

Short handles remain a legitimate future change. They need a design that says
what a view does with an abbreviated href and what `check` does when one stops
resolving — not a resolver left lying around in the hope that the rest follows.

Collision is the trigger to watch, since the first eight hex characters of a
UUIDv4 are 32 random bits: 0.5% at today's ~6,700 blocks, 17% at 40,000, 68% at
100,000. `records.check` already rejects a base where two nodes share a handle,
so the failure is loud.

**A citation is a link:** `[-](#<guid>)`.

The link text carries nothing a machine reads and a hex string mid-sentence
helps nobody, so it is a single dash. `[...]` was rejected because the djot
writer escapes it to `[\...]`; `-` survives both writers clean.

The form was chosen structurally, not aesthetically. `{@x}` fixed the *meaning*
of the old `{#x}` but not the mechanism: it was still text, so extraction was a
regex over flattened content, and a handle quoted inside a code block became a
real edge — measured, not hypothetical, in a corpus that quotes its own syntax
constantly. A `Link` is a node; a code block holds text with no inlines, so it
contains no links and *cannot* contribute a citation. The rule that has been
broken three times becomes a property of the format rather than a thing to
remember. Links also render clickable in HTML for free, against blocks that
already carry the matching `id`.

## Two orderings, both stored

| layer | edges | meaning |
|---|---|---|
| `pandoc-ast` | `contains`, `next` | structure and order within parsed prose |
| `session` | `contains`, `next`, `touches` | transcript structure; `next` is **log order**, which regenerates the file |
| `claude-code` | `replies_to` | the `parentUuid` chain — the conversational truth |
| `citation` | `cites` | derived from links in the text |

Log order and reply order are the same until a session has a sidechain, and
this corpus has **zero** sidechain lines, so neither is exercised by real data.
Storing only one of them would mean guessing the other forever. The `session`
layer holds what any transcript format has; `claude-code` holds what is
specific to this one, so another agent's log can reuse the first without
inheriting the second.

## Decisions taken

- **Inlines are not nodes.** A block node stores its pandoc inline array
  verbatim as nested JSON in `content`. Plain text is derived at render, never
  stored as the authoritative form. Storing only flattened text would make the
  graph unable to rebuild the AST, and would hash `**foo**` and `foo` alike.
  Whether a link or an image becomes its own node stays open until a query
  needs it.
- **Identifiers: a guid on nodes *and* edges.** Nodes carry `guid` (UUIDv4,
  identity) and, since v0.2.13, `record_hash`/`record_subtree_hash` (SHA256,
  a dedup key — not identity; `content_hash` before the rename, and
  conditional on the node having content before v0.2.13 generalised it —
  `design-total-mapping.md`). Edges carry a `guid` too in this version.
  A pure content-hash identity for edges
  is attractive and may come later as an optional `identity_hash`, but only
  once the hash input is pinned down; until then a guid cannot lose
  information to an unforeseen edge case.
  - Whatever hashes exist, the hash *input* must be specified exactly — field
    order, key sorting, UTF-8, separators, no whitespace. An undefined
    serialisation means a different JSON encoder silently duplicates every
    record.
  - A guid may live in an edge, never in stored text. Handles inside immutable
    prose cannot be rewritten; edge endpoints can be remapped freely. This is
    what keeps the later switch to short ids a migration rather than a rewrite.
- **Directory layout as drafted**: everything hidden and mixed under
  `.compost/` — `storage/`, `graph/`, `views/`. Accepted for simplicity in
  this version. The known cost is that committed ground truth and disposable
  generated output sit side by side, and that `rg`/`find`/GitHub skip dotdirs
  by default. Revisit later via configurable external paths in a settings file
  under `.compost/`.
- **pandoc-types is the AST grammar ground truth**, cloned to
  `vendor/pandoc-types/` and gitignored. `Definition.hs` *is* sufficient
  to derive the JSON without reading much Haskell: the data declarations give
  the shape, and one line at `Definition.hs:391` gives the encoding rule —
  `sumEncoding = TaggedObject { tagFieldName = "t", contentsFieldName = "c" }`.
  That is the whole `{"t": …, "c": …}` convention.

## Serving is not rendering

`serve` hands over `.compost/views/default-html/` and does nothing else. v0.1
rendered first; v0.2 does not, and the split is deliberate.

`render` is the only thing that writes views, and it refuses on a graph that
fails `check`. So the invariant *a view of a broken graph is worse than no view*
is already enforced where views are produced, and re-enforcing it at delivery
buys nothing while costing the ability to look at a base through the browser
while debugging it. It also agrees with `lookup`: queries and views answer from
what is on disk, and only `render` asserts the graph is sound.

**Loopback only.** The listener binds `127.0.0.1`, not `0.0.0.0`. A personal
knowledge base reachable from the local network is a mistake nobody makes on
purpose, and there is no flag to make it.

**Nothing is cached, and revalidation is refused.** Responses carry
`Cache-Control: no-store`, and `If-Modified-Since` / `If-None-Match` are dropped
before the handler can answer them. `Last-Modified` has one-second granularity,
so a `render` landing in the same second as the previous page load is answered
`304 Not Modified` and the browser shows the old page. Measured directly: same
mtime, different bytes, `304` and an empty body. These are small local files
regenerated by a command you just ran; caching them has nothing to win and a
stale refresh has a confused half-hour to lose.

**Port 7373.** v0.1 used 8000, which is `irdmi` in `/etc/services` and the
default for `python -m http.server` and for Django. On this machine 5000 and
7000 are already held by macOS AirPlay Receiver, and 49152–65535 is the
ephemeral range the OS allocates outbound ports from, so a fixed port there
collides eventually. 7373 is unassigned, outside that range, and the default of
nothing common. `-p` overrides it.

## Known issues — accepted, not fixed now

- **Callout titles are doubled.** Pandoc synthesises title text that is not in
  the source:

  ```
  source:   > [!IMPORTANT]
            > This all leads to the conclusion that...
  AST:      Div .important > [ Div .title > Para "Important", Para "This all…" ]
  ```

  `Important` was never typed. A naive "every AST block is a node" ingestion
  would mint a node with content the author never wrote, hash it, and make it
  citable — breaking the invariant that a document's rendered text equals its
  source text. The intended fix, when we get to it: treat `Div .title` inside
  an alert as derived presentation, with the alert type as a property of the
  container node and the title regenerated at render. This is a compost-side
  modelling choice, not a pandoc workaround.
- **Byte-identical round-trip is not achieved, and is not the goal.** 4 of 19
  notes come back byte-identical; all 19 come back **AST-identical**. The
  differences are surface only: list indent width, blank-line runs collapsing,
  fenced code blocks rewritten as indented ones, `1.` becoming `1. `, `---`
  redrawn as a long rule.
- **Whitespace is normalised.** Consecutive spaces collapse to one and
  trailing whitespace is dropped, because the AST holds a single `Space` node
  regardless. Content hashes are therefore over normalised text, not over the
  author's bytes.
- **Invented callout types degrade to a quote.** Only `NOTE`, `TIP`,
  `IMPORTANT`, `WARNING`, `CAUTION` map to a `Div`. `> [!HEUREKA]` becomes a
  plain `BlockQuote`; the text survives and the AST is still a fixed point,
  but it writes back with escaped brackets as `\[!HEUREKA\]`.
- **Pandoc's writer injects `<!-- -->` separators.** Two adjacent lists that
  would otherwise merge — a task list beside an ordinary list, a list followed
  by a code block inside a quote — are separated by an HTML comment. It
  re-reads as a `RawBlock` that nobody wrote. Same class as the callout title:
  synthesised content the source never contained. Writer-independent.
- **A code block inside a *tight* list item is destroyed.** The writer emits it
  as an indented block with no preceding blank line, and an indented code block
  requires one, so it re-reads as lazy paragraph continuation and the
  `CodeBlock` node is gone. A *loose* list — blank lines between items —
  survives intact. Writer-independent.
- **Inline code adjacent to raw inline HTML is mangled.** `<span>` … `` `a` ``
  … `</span>` comes back with the code merged into the raw inline as
  `` a``</span> ``. Accounts for 5 of the 9 remaining failures on the test
  corpus.
- **Document metadata lives outside `blocks` and is dropped by default.** A
  YAML frontmatter block is parsed into the AST's `meta` field, not into
  `blocks`, and every writer omits it unless `--standalone` is passed:

  ```
  pandoc -f gfm -t json note.md | pandoc -f json -t gfm       -> frontmatter gone
  pandoc -f gfm -t json note.md | pandoc -f json -t gfm -s    -> frontmatter kept
  ```

  This is not a gfm quirk — `markdown`, `commonmark_x`, `djot` and `html` all
  behave the same way. No note in `raw/` has frontmatter today, so it is a
  latent trap rather than a live bug, but the record schema currently models
  only blocks and has nowhere to put `meta`. The importer must read it
  explicitly or a whole class of content vanishes without an error.
- **No PDF reader in pandoc.** `pdf` is an output format only, so PDF input
  needs a separate extractor. Deferred.
- **djot.js and the `npx` spawn are gone**, removed in v0.2 as this entry
  planned. Pandoc reads and writes djot natively, so there is no second
  toolchain and no subprocess spawn per canonization.

## Ingestion: named routes, minted storage names

*Decided and built 2026-08-21, shipped in v0.2.2. Supersedes dispatch on
the file extension.*

### The route is named, never inferred

`import` chose its reader from the suffix: `*.jsonl` was a Claude Code
transcript and **everything else** went to pandoc. Two faults, and the second
is the one that forced the change.

The `else` was not "markdown", it was *anything at all* — a PNG reached
pandoc's markdown reader and came back as a pandoc error rather than a compost
one. And `.jsonl` is a container, not a format. The moment a second kind of
JSONL exists the suffix stops naming a reader, and that moment is close: the
`claude --print` path will produce single text turns, which are a different
material from a session log with its tool calls.

So there are three named routes and `--as` is required:

| route | reads |
|---|---|
| `notes` | prose, as `commonmark_x` with the three extensions off |
| `claude-code-transcript` | a Claude Code session log, the whole `*.jsonl` |
| `pandoc-ast` | a pandoc JSON document somebody else already produced |

Naming, and why not the obvious alternatives:

- **`notes`, not `simple-markdown` or `custom-markdown`.** "Custom" promises
  configurability and this route has no knobs at all — one dialect, three
  extensions off, no options. If the reader ever does become configurable, the
  name would already be taken by the thing that is not.
- **`claude-code-transcript`, not `…-session` or `…-conversation`.** It names
  the *unit of material*, because `claude-code` already carries the
  technology. Its sibling will be `claude-code-turn` — one reply from
  `claude --print` — and transcript-versus-turn is exactly the distinction
  that needs to survive. "Conversation" is reserved for something else.
- **`pandoc-ast` is the narrowest route, not the broadest.** It reads nothing:
  `ast_to_records` already takes that shape. The unreliability people expect
  here lives in the pandoc invocation, and this route puts that invocation
  *outside* the tool where it can be inspected and tuned.

### Storage names are minted uuids, not content hashes

`storage/GUID.EXT`, where `GUID` is the `blob` node's own guid.

Content-addressed storage was the alternative and was rejected. It is better
on two counts — the name is verifiable by re-hashing, and identical bytes
collapse to one copy for free — but it costs the invariant **every object has
a guid**, which is worth more here. Storage is a blob store on purpose; the
metadata layer lives entirely in the graph, and a `storage/` without its graph
is meant to be an unlabelled pile.

The risk that buys is *silent duplication*: with content hashes, ingesting the
same file twice was a no-op. Two things close it, and neither is the naming:

- `bytes_sha256` on the blob node, so duplication is detectable and a stored
  file is still verifiable against what the graph claims.
- `digest` reports a duplicate — `these bytes are already in N blobs` — and
  does **not** resolve it. Deciding two copies are one thing is a later
  layer's call, and the same identity question is already open for re-imports
  producing matching `content_hash` values.

**The extension is kept**, so a file pulled back out of `storage/` is still
usable by hand. It is a decoration and nothing routes on it — which is the
whole point of the paragraph above. One accepted wart: the same bytes ingested
as `.md` and as `.txt` are two files.

### Ingestion is two-phase

Nothing is written until every input in a batch has been read and parsed.

This is a direct consequence of minted names. Under content-addressed storage
a half-finished batch was safe to re-run, because the files that had landed
were idempotent. With minted names they are not: re-running would ingest them
a second time under fresh guids. Validating first is what makes it safe to
pass a glob, which is also why directories are refused rather than walked —
the shell already answers "how deep", and better.

### Storage and graph names must not be derivable from each other

Both are uuids and they are different uuids. If either could be computed from
the other, something would eventually compute it, and a filename that means
something is how suffix routing happened in the first place. The supported
path from a document to its bytes is the `derived_from` edge and
`blob.params["stored_as"]` — `records.blob_of()`, and nothing else.

The cost is that `ls .compost/graph/` is now opaque. That was accepted
knowingly: `ls` is to be superseded by a DuckDB-backed `query`, and reading
filenames in a file browser is not how this base is meant to be inspected.

### `import` became `digest`

The rename is flavour, but the release breaks the CLI regardless — the route
is mandatory now — so doing both at once is one break instead of two. `add`
does not say what it adds to; `break-down` is awkward to type.

**A bare `compost --as=notes FILE`, with no subcommand, was rejected.** It
would have to distinguish `compost --as=notes render` (ingest a file called
`render`) from `compost render`, which is implicit routing on the shape of an
argument — the exact class of thing this whole change removes. Deleting suffix
routing and adding name routing in one release is not progress.

### View filenames are disambiguated

Found while making the above land, and repaired with it. `render` names view
files from `params["source"]`, so two documents with the same original name
overwrote each other's pages — `render` would report writing files that held
the wrong document. Nothing had noticed because the old name-keyed storage
*accidentally* guarded it by refusing a second `notes.md` with different
bytes. Minted names removed that guard.

Colliding stems now take the root's handle as a suffix. A counter was rejected:
it renumbers when an unrelated document arrives, so every URL in the browser
moves, while a handle is the document's own and never does. Names that do not
collide stay clean, which is the common case.

## Output portability: what a view can carry, and where it stops

*Measured and decided 2026-08-21. The decision is to accept the current limit
deliberately, and the staged plan for lifting it is recorded so that accepting
it stays a choice rather than becoming an assumption.*

### The illusion worth naming

"We generate a pandoc AST, so all 68 of pandoc's output formats come free."

That is **true for every node that came from pandoc** — `Para`, `Header`,
`Table`, `CodeBlock` are pandoc's own vocabulary and round-trip to everything.
It is **false for every node compost invented**: `session`, `turn`, `toolcall`,
`tooloutput`, `thinking`, `file`, `logline`, `contentblock`. Those have no
pandoc equivalent, so `views.py` must *choose* a representation, and
portability is a property of that choice — not of using pandoc.

### The three strategies, and which writers survive them

| | strategy | survives to |
|---|---|---|
| 1 | `Div` + attributes | djot, html, commonmark_x, gfm, markdown |
| 2 | visible text (a Header, a bold label, a definition list) | **everything** |
| 3 | `RawBlock(format)` | exactly one writer |

`_render_session` uses **1 and 3**, and nothing at 2. Handles are
`RawBlock("djot", "{#…}")`; author, timestamp and tool name are Div
attributes; the HTML collapse is `RawBlock("html", "<details>")`.

### Measured, on a fixture whose prose contains no guids

One session, one set of records, every writer:

| writer | prose | handle | author | tool name |
|---|---|---|---|---|
| djot | ✓ | ✓ | ✓ | ✓ |
| html | ✓ | ✓ (as `id`) | ✓ | ✓ |
| commonmark_x, gfm, markdown | ✓ | — | ✓ | ✓ |
| latex, plain, man, typst, rst | ✓ | ✗ | ✗ | ✗ |
| docx, odt | ✓ | ✗ | ✗ | ✗ |

The same session is 924 bytes of djot, 749 of LaTeX and **215 of plain**. PDF
goes through LaTeX, so PDF is on the losing side.

**So: a transcript rendered to PDF today is unattributed prose.** You cannot
tell who spoke, which tool ran, or cite any of it. That is the limit, stated
plainly so nobody discovers it by exporting something important.

### Crawl — accept it, today

Deliberate, with reasons, and none of them are "we did not notice":

- **All of pandoc's output formats was never the aim.** The reachable set
  covers every real reader: **agents read djot**, **the human reads HTML**, and
  the **markdown render is committed to GitHub** as `README.md` and friends.
  Every one of those is in the attribute-preserving column.
- **A prose-soup PDF is expectation management, not a missing feature.** It
  looks bad, and it is not a capability anybody is waiting on. The correct
  response is to say so — which is why it is in the man page — rather than to
  build for it.
- **Input breadth is worth more than output breadth.** If there is capacity for
  work of this kind, spending it on getting the *input* formats understood — the
  `pandoc-ast` research programme in `TODO.md` — returns far more than making a
  transcript survive to LaTeX. Reading many kinds of document into one
  addressable graph is what this tool is for; emitting many kinds of document is
  not.

### Walk — a fallback representation, when a format actually needs one

Strategy 2, chosen per node type, used when the target cannot carry attributes:
a turn becomes a small Header or a bolded `human — 10:00`; a tool call becomes
a labelled code block.

This is **legal and not a violation of the waist.** Views are read and never
re-ingested — `render_djot` already says so in its own comment — so a view may
say things the source did not literally say. `records_to_ast` stays exactly
reversible; only `views.py` gains a branch. Build it the day a format is
actually wanted, not before.

### Run — make the out-mapping a real plugin

The asymmetry underneath all of this: **a type is two bodies of work, and only
one of them has a home.**

| | where it lives | modular? |
|---|---|---|
| in: bytes → nodes and edges | `routes.py` dispatch, `session.py` reader | **yes** — one route entry, one module |
| out: nodes → AST | `views.py`: an `if t == …` chain, plus `SESSION_TYPES`, plus `CITABLE` / `SELF_LABELLING` | **no** — three coupled places, both writers hard-coded |

A node type should register `(node, target capabilities) -> blocks` beside its
reader, so adding a type is one module rather than edits in four places. This
is what makes *walk* maintainable rather than a second if-chain, and it is the
thing the next type — whatever `claude --print` produces — will want.

Do not start here. `run` without a concrete second format to serve is
architecture for its own sake.

### A sharper line: information versus affordance

A first pass at this concluded that the subagent fold should avoid `<details>`
because strategy 3 is the least portable. **Measuring it says otherwise, and
the correction is the more useful rule.**

`_details` emits `[RawBlock(html), *blocks, RawBlock(html)]`. In LaTeX and
plain the two wrappers vanish and **everything between them stays** — the same
session is 7984 bytes of HTML and 11005 of LaTeX, tool output included. So
`<details>` is not lossy at all. It degrades to *showing everything*, which is
exactly right, because a collapse widget has no meaning in a PDF.

The real line is not which strategy, it is **what the construct carries**:

- **Information** — a handle, an author, a tool name. If it rides on a
  format-bound construct it is *lost*, and the reader cannot tell. This is the
  whole problem above, and it is strategy 1 and 3 used for facts.
- **Affordance** — a fold, a summary label, anything about interaction. It has
  no meaning outside the format that offers it, and losing it costs nothing.
  Strategy 3 is the *correct* choice here.

So: `<details>` stays for tool output and is right for subagent folding too,
which also keeps one folding mechanism instead of two. What must move to
strategy 2, when *walk* arrives, is only the attribute-borne facts.

---

# v0.2.4 — the layer mechanism

Everything below was settled while designing v0.2.4 and v0.2.5. `docs/roadmap.md`
has the plan; this file has the reasons that were not obvious.

## Guids stay UUIDv4, including for derived records

A draft gave *derived* records — citation edges — a UUIDv5 over the relation they
state, so a rebuild would be byte-identical and `Store.load()`'s dedup would
collapse it for free. **Rejected.**

It is a content hash with a uuid-shaped output. Two records stating the same fact
would become *the same record*, silently, at write time — which is resolving
duplicates at import, the thing this project forbids everywhere else. It also
discarded citation multiplicity without anyone deciding to: two citations of one
target from one block would have collapsed into one edge.

And it falsified two sentences that carry unrelated weight. `record-grammar.md`
§2 says *"GUID is a UUIDv4 in every case. Nothing derives a guid from content, and
nothing derives one guid from another"* — the second clause is also what forbids
deriving a document's guid from its blob's. Weakening the sentence for citations
would have weakened it for storage.

So: every guid is minted. Sameness is *described* by `content_hash` and resolved
later, by a design written from evidence rather than in advance.

## `content_hash` on an edge excludes provenance, not just identity

```
EDGE_HASH_SKIP = {record, guid, schema_version, content_hash,
                  created_at, tool_version}
```

The first version of this said "hash all properties". With `created_at` also a
property, the same citation rebuilt tomorrow would hash differently from the one
written today — and finding the same fact restated is the *only* thing the hash
is for. It would have been defeated for exactly the duplicates being deliberately
accumulated.

So the rule is: **a hash says what the record claims, never when or by what it
was written.** `schema_version` is excluded for the same reason — two records
stating one fact across a format change must still match.

Note the node hash (`record_hash` since v0.2.13; `content_hash` before the
rename) is a *different function* — a positional array
`[type, params, content]`, with no skip list — and the two are not
comparable. They no longer even share a field name.

## `content_hash` is evidence, not a mechanism

Nothing in `src/` reads `content_hash` to decide anything. No load path
collapses two records because their hashes match, no `check` assertion
compares them, and `compost layer` does not consult them before writing. It
is written and never consulted — on purpose, for now.

That is a decision, not an oversight. A dedup design needs to be written from
the *pattern* of how duplicates actually accumulate — which fields tend to
match, which never do, whether a `cites` edge into a placeholder should ever
be treated as "the same fact" as one into a real target once the placeholder
resolves — and none of that pattern exists yet, because nothing has minted
duplicates at scale under this design. Writing the hash now and acting on it
later means the evidence is there the day someone sits down to design that
layer; acting on it now would mean guessing the policy before there is
material to guess from, and re-deciding it once real accumulation shows the
guess was wrong. `docs/roadmap.md`, v0.2.8, is where the accumulated
duplicates are meant to finally become legible — grouped by `content_hash`,
by `created_at`, by `tool_version` — and that grouping is the first use this
field is expected to have.

## `load()` deduplicates byte-identical records — dedup step zero

`Store.load()` drops a record it has already seen, comparing `R.canonical(rec)`
— the whole record, not the guid. Two writers asserting the same fact is
agreement, not conflict. A guid carrying two *different* records is a hard
error and is left for `check`, because picking a winner is how a corpus starts
lying.

**This looks like a convenience and is not.** Removing it does not yield the
"collect everything, collapse later" behaviour the project prefers elsewhere —
it yields a base that fails `check`. Measured on a base holding one duplicated
graph file:

| | |
|---|---|
| with dedup | 3 nodes, 2 edges, **0 problems** |
| without | `Para … has 2 parents, expected 1`; `render` refuses |

A duplicated `contains` edge counts twice against the one-parent invariant, so
an innocent copy of a graph file would take every view down. Getting
collapse-later would mean teaching `check` to count *distinct* parent edges —
the same dedup logic relocated, not removed.

So it stays, named honestly: **the first rule of a dedup design that has not
been written**, rather than an implementation detail. `TODO.md`'s dedup section
records it so that design accounts for it instead of rediscovering it.

**What it costs:** a base can contain a duplicated file and nothing will say
so. It also makes `Store.load()` and raw SQL over `graph/*.jsonl` disagree
about how many records exist — which is why the query layer's mirror is
`SELECT DISTINCT` over the whole row, reproducing this rule rather than
`count(DISTINCT guid)`, which would additionally hide the guid conflicts
`check` exists to catch.

## The tool handles no dependencies, and guarantees no consistency

An architecture review of a larger design found four states a base could enter and
never leave, each escapable only by hand-editing `.compost/graph/`. All four came
from one source: trying to keep the graph automatically consistent, through layer
declarations, staleness detection, dependency-ordered rebuilds and a `drop` that
had to find its own files.

Two constraints replaced the machinery:

1. **Dependencies are not handled.** The operator sequences `digest`, `layer` and
   `render` themselves. Nothing infers what is out of date.
2. **No deduplication, no preservation across rebuilds, no consistency
   guarantee.** Duplicates accumulate, deliberately.

Removing the goal removed all four failure modes with it. What remains is bare and
honest: `compost layer NAME` builds and stops. The costs are listed in the
roadmap's *Risks accepted without mitigation*, which exists so that meeting one is
a known price rather than a discovery.

## Anything may write records; `check` is the gate

**Not a relaxation of a rule — the model.** An earlier `CLAUDE.md` said *"Do not
hand-edit `.compost/graph/`. Write through `compost digest`."* That was always a
description of habit rather than of mechanism, and it was wrong in a way that
mattered: it implied the tool has a privileged position it does not have.

The records `digest` writes are produced by ordinary Python. So are `layer`'s.
So are a migration script's, and so are an agent's. **`Store.load()` does not
care who wrote a file**, and `check` is what enforces every invariant — not the
identity of the writer. A generated file that passes `check` is
indistinguishable from one `digest` wrote, because there is nothing to
distinguish. The requirement is the *format and the location*: valid JSONL,
one record per line, under `graph/`.

`digest` and `layer` are therefore two writers among however many there are,
and calling `layer` "the second writer" counts subcommands, not writers.

**This is a trust model, and the trust is currently unearned.** `check`
verifies structure — parent counts, dangling endpoints, cycles, guid
collisions. It does **not** validate that a node's `type` is a known one, so a
typo'd `"alais"` passes if its parent count is right. Today's guarantee is
therefore "the agents and scripts writing here are trusted, and `check` catches
the structural mistakes", which is weaker than the earlier prohibition sounded
and is the honest statement of where things stand.

**A grammar validation layer is planned** for when this has to run somewhere
the writers are not trusted — validating each record against the grammar in
`docs/record-grammar.md` rather than only against structural invariants. It is
not scheduled inside the current window, and until it exists the trust
assumption should be stated wherever it is being relied on rather than left
implicit.

**Two things remain wrong regardless of who writes.** Editing a line inside an
existing file: records are immutable, and rewriting a whole file is the only
honest form of change. And deleting anything finer than a whole file — deleting
a *whole* file that one `layer` run wrote is fine, and is the only inverse the
design offers for accumulation it never removes.

## Reading a v0.1 `.dj`: djot, and what two wrong answers cost

**Settled by measuring the corpus.** Two earlier versions of this entry were
argued from samples written by hand, and both were wrong. The numbers here come
from the 23 real `.dj` files.

The v0.1 canonization did two things nobody had recorded:

1. **Every block is wrapped in a div carrying its handle as a djot attribute** —
   `{#acd83164}` on the line above a `:::` fence, `wrapper="1"` on the div.
2. **Inline citations are already escaped** — `\{#44670084+++\}`. So they are
   literal text to the djot reader, not attribute syntax.

Which means `pandoc -f djot` recovers both, and the AST does the hardest part:

```
Div  id=376c3ce7  class=turn  author=human  turn=019ff17b-…
  Div  id=acd83164  wrapper=1
    Para: 'Now this definitely needs reworking {#44670084+++}'
```

| | |
|---|---|
| files parsed by `-f djot` | 23 / 23 |
| handles assigned in the text | **6,601** |
| surviving `pandoc -f djot` untreated | 5,834 — 767 dropped from list items |
| distinct ids after `tools/dj_prepare` | 6,601 — **zero collisions** |
| escaped citations surviving as text | 206 |
| bare handles in fenced code / code spans | 948 / 226 |
| **bare handles in prose — the only loss** | **13** (~0.15%) |

**Two consequences worth keeping.** The migration dictionary is a direct read of
the AST, with no text matching of any kind. And the assignment-versus-citation
rule is unnecessary: an assignment is an `id`, a citation is text, and the reader
separates them — so there is no exception to state, test, or get wrong.

**`--as=notes` was tried and rejected.** It loses no handles, but none of the four
lines at the head of a turn — the turn attributes, the `:::` fence, the first
block's handle, the first block's text — has a blank line between them, so
markdown merges all four into one paragraph. That happens at every turn head,
making the dictionary ambiguous ~2,400 times. Djot loses 13 occurrences instead.

**The cost of getting this wrong twice, recorded on purpose.** The first version
claimed the djot reader was correct without checking what it did to citations. The
second claimed it deleted them, measured on an *unescaped* sample that the corpus
does not contain, and switched the whole release to the wrong reader. Both were
written with the word *Verified* attached. The rule that follows: **a claim about
how a reader treats material is only verified against that material.**

## Citation matching is `finditer` within a `Str`, not whole-`Str` equality

Measured at design time over the 18 documents in this repo carrying real v0.1
handles: **135 a whole `Str` exactly, 98 embedded** in a larger token —
`{#aa813aa9}.`, `{#93360c21},`, `{#330f8531}:`. Whole-token matching had
**57.9% recall**.

**Re-measured after implementing it, through `records.legacy_handle_refs`
rather than the pattern alone**, over `tests/fixtures/notes/` plus the fetched
corpus:

| | |
|---|---|
| occurrences the reader finds | **242** |
| occurrences whole-`Str` equality would find | 144 |
| **lost by equality** | **98, or 40%** |

Same finding, larger material — the corpus has grown since the first number was
taken, so the totals differ and the conclusion does not. `tests/test_layer.py`
asserts `found > whole > 0` by **calling the reader**, not by running the regex:
a first draft measured the pattern directly and went on passing with the reader
switched back to equality, which is the exact failure this entry exists to
prevent. It states its tier, so a bare clone's smaller count is never mistaken
for the corpus figure.

A draft specified whole-token equality on the strength of one hand-written example
with spaces on both sides. Real prose puts punctuation after a citation, and in
the corpus itself the first surviving citation is `{#44670084+++}` mid-sentence.
The pattern is self-delimiting, so matching within the `Str` costs nothing and the
structural exclusions — `Code` text is not a `Str`, `params["text"]` is never
walked — are unaffected.

It must also cover all four legacy forms, not just the bare one: `{#8hex}`,
`{#8hex+++}`, `{#8hex@ver}`, and the metasyntactic `{#handle}` / `{#uuid:hash}` /
`{#xxxxxxxx}` / `{#...}`, which must **not** become citations. Shipped in
v0.2.5, and the exclusions cost no code: the three real forms differ only by a
suffix that is not part of the name, and every decoy fails `[0-9a-f]{8}`.

**Exactly eight, never more.** `{#a1b2c3d4e5}` must not match, so the pattern
closes on `}` immediately after the eight characters or after one known suffix.
Nothing in the corpus depends on this; it is cheap to state and expensive to
discover missing.

## The concept-map answer format: a line per fragment, measured against a real model

`docs/roadmap.md`'s v0.3.0 draft chose a line format (`[id] label`) over JSON
on a guess — "a cheap model follows it more reliably" — and said so in
writing, with `prompts/concept-map.md`'s `version` field left there for
exactly the moment this got measured.

**Measured against `openai/gpt-4o-mini`, temperature 0, 22 real batches
across three throwaway bases (never the human's own):** the count-mismatch
and unsent-id checks — guarantee 5's first and third — never fired once. The
model reliably returns exactly one line per fragment sent, in order, with
the id it was given. **The line format survived contact.** The failure that
did happen, on 4 of 22 batches, was always the second check: the model
answering with a real-sounding topic (`Ownership`, `Functions with Return
Values`) or a plausible but unlisted sublabel (`Storage > Ownership`)
instead of the map's own `none of these`, whenever the material had an
obvious topic the map did not name. That is a **map-fit** failure, not a
format failure — no measured evidence favours JSON over the line format, and
switching would not have prevented any of the four real failures observed.

**This is evidence, not proof.** Twenty-two batches against one model is a
starting measurement, not a closed question; a different model, a larger
map, or material more thoroughly unrelated to it could behave differently.
Recorded here so the next person who revisits `prompts/concept-map.md`'s
`version` field inherits a number instead of a guess.

## `--cost-calculation` prices from a static table, never a fetch

The v0.3.0 draft's own prose said the price per token would be "fetched"
when `--model` is given; the guarantee it also wrote down says
`--cost-calculation` makes no network call **with or without** `--model`.
Both cannot be true — a live fetch of OpenRouter's models list is a network
call regardless of how harmless or free it is.

**Sided with the guarantee.** `src/llm.py:PRICE_TABLE` is a small,
hand-maintained dict of USD per million input tokens for a few named
models; a model missing from it prices as "no local price for X" rather
than being guessed at or fetched live. It will go stale — OpenRouter's
prices move and this table will not follow them — and that is the accepted
cost of a flag whose one hard promise is that it never touches the network,
even for a read that would itself have been free.

## The classifying model: measured against ground truth, not chosen by price

**Measured 2026-09-17, after v0.3.0 was built and before it shipped.** The
first default was `openai/gpt-4o-mini`, picked because the release's working
hypothesis said *"semantic categorisation will not need the most expensive
models."* Nothing had tested that. This is the test.

### The instrument: Wikipedia, because it has ground truth

Every earlier attempt to judge this layer failed on the same thing — the
abstention rate is uninterpretable. A high rate means either *the map is
wrong* or *the material is unclassifiable*, and from outside they look
identical. The roadmap says so and leaves it open.

Wikipedia closes it. Fifteen articles on stochastic analysis were fetched,
converted with `pandoc -f mediawiki`, and used **both** as the notes and as
the concept map: the page title is a label, each `##` section a sublabel. So
every fragment has a **known correct answer**, and an abstention is provably a
false negative rather than an ambiguous signal. Three of the fifteen were held
out of the map — their fragments are in the notes but their titles are not
concepts — so the correct answer for all 352 of them is "none of these". That
gives a measured **false-positive** rate, which the human's stated preference
(false negatives over false positives) had never had.

Two arms, on identical fragments:

- **arm A** keeps the headings, so the ancestor path names the answer
- **arm C** deletes every heading line and changes nothing else, so a fragment
  arrives as bare text

### The result

2,207 fragments with ground truth, ~$2.79 of API spend for the whole sweep.

| | arm A batches failed | arm A page | arm C batches failed | arm C page | arm C exact |
|---|---|---|---|---|---|
| `openai/gpt-4o-mini` | 12/13 | 88.7% | 5/10 | **39.3%** | 14.0% |
| `google/gemini-2.5-flash-lite` | 11/13 | 99.1% | 6/10 | 81.2% | 48.5% |
| **`google/gemini-3.8-flash`** | **0/13** | **99.7%** | **0/10** | **99.4%** | **97.9%** |
| `anthropic/claude-opus-5` | 0/13 | 99.6% | 0/10 | 98.7% | 96.1% |

**`gemini-3.8-flash` matches `claude-opus-5` on every measure at a sixth of
the price** — $0.127 against $0.845 for a 1,235-fragment run. It is the
default. Claude's role here was as the **instrument, not the candidate**:
without a ceiling, 99.4% could not be distinguished from "as good as this task
gets", and the whole point of the sweep was to tell those apart.

**The hypothesis is confirmed, with a floor under it.** The cheapest models
are not adequate — two of the four tested are well below the bar — but the
best is not needed either. Re-picking this constant without re-running this
measurement is how the floor gets lost, which is why `src/llm.py` carries the
numbers beside it.

### Three things this overturned, each of which had been argued from one model

**Instruction-following is a capability, and was being read as a design flaw.**
`gpt-4o-mini` had 12 of 13 batches rejected for naming labels absent from the
map. That was diagnosed as a representational bug — the map expresses two
levels and the articles are five deep, so the model named a real `h3` it could
see and the strict check rejected it. The diagnosis was half right: 608 of the
743 rejected answers did name a genuinely existing heading. But a *capable*
model obeys "use only topics from the list" regardless, and rejections went to
**zero**. The `flash-lite` row is the proof: **99.1% page accuracy and still
11 of 13 batches rejected** — it knows the answer and violates the constraint
anyway. Semantic judgement and constraint adherence are separate capabilities
and only the first is about difficulty.

**The ancestor path is not doing the work.** Removing every heading costs
`gpt-4o-mini` **49.4 points** of page accuracy and `gemini-3.8-flash` **0.3**.
The conclusion drawn from the cheap model — that this layer reads the heading
above the prose rather than the prose — is false for a model that can do the
task. This matters directly for real material: the 14.1% of blocks in a notes
base that have no ancestor path are not a lost cause.

**Refusing the whole run on one bad batch is affordable.** With `gpt-4o-mini`
at an 18% per-batch failure rate, a 49-batch run completes with probability
0.01%, and that arithmetic was used to argue the policy was too strict. At
0/13 and 0/10 the policy costs nothing. The policy was never the problem; the
model was.

### Rejected, and why they are recorded rather than built

**Concept ids instead of label strings.** Proposed to make invention
impossible by construction. Rejected: detection was *already* deterministic —
`_parse_response` validates membership exactly — so ids improve nothing there,
while an in-range but wrong id passes validation and mints a bad edge
**silently**. Trading a loud failure for a quiet one is the wrong direction
here.

**Longest-valid-prefix resolution** — resolve `A > B > C` to `A > B` when only
that exists. It works: it lifts `gpt-4o-mini`'s arm-A acceptance from 65.5% to
90.6% with accuracy unchanged, and arm C to 100%. It is not built, because at
the chosen model acceptance is already 100% and it silently coarsens an answer
the model did not give. Recorded here as the measured fallback if a cheaper
model is ever wanted.

**A third, character-based batch limit.** Still not built — see the group-size
bound below, which was the limit that actually turned out to be missing.

## `batch_size` is a bound, and three other repairs the sweep found

The sweep above was run through the shipped code, which is why it found these
rather than the tests finding them: each needed either real material or a real
model to show up at all.

**`_make_batches` never split a path-group, so `batch_size` was a hint.** Its
docstring claimed *"nothing in any measured material reaches that case"*, and
that was false when written. The **test corpus holds one path-group of 1,140
fragments**, and — the sharper case — every fragment with no ancestor path
shares the empty path, so context-free material collapses into a single group
of everything. Arm C's first run sent **948 fragments in one call** and got
1,580 answer lines back for them. A group is now split when it exceeds
`batch_size` on its own. The cost is one repeat of that group's ancestor path
per extra chunk — which is the exact cost the grouping exists to avoid — and
it is obviously the lesser one.

**`llm.ask` returned `message["content"]` unchecked.** The models that pass
the measurement above are reasoning models: they spend output tokens on a
trace before answering. With no `max_tokens`, a 100-fragment answer is
truncated, the response carries `content: null` and
`finish_reason: "length"`, and that `None` was handed to the caller — dying
inside `_parse_response` with an `AttributeError` far from its cause. This
broke the first sweep run. Now: an explicit cap, `reasoning: {"exclude":
true}` since this layer wants a label and not an argument for it, and a named
`LLMError` that reports `finish_reason` and points at `--batch-size`.
Transport failures still retry; a response that *arrived* but is unusable
raises, because retrying buys the same answer again.

**`key_usage` hardcoded a second `openrouter.ai` URL**, so
`COMPOST_LLM_ENDPOINT` moved the chat endpoint but not that one — the override
exists precisely so a test can point every call in the module somewhere
closed. It is derived from `endpoint()` now.

**`_label_index` merged duplicate labels silently.** A flat dict, so a second
label of the same name overwrote the first and blocks were attributed to
whichever won — differently depending on document order. Measured over the
twelve mapped articles, **14 headings repeat**: `Definition`, `History`,
`Examples`, `Properties`. Those are safe as *sublabels*, whose keys are
qualified by their parent; it is two top-level labels, or two sublabels under
one parent, that collide. It refuses now, naming the label. Nothing in the
answer format can say which of two identically named concepts is meant, so
there is no honest merge.

## A map revision invalidates every classification made against it

**Not a defect, and not fixed — a consequence worth writing down before
someone meets it.** Measured 2026-09-17: revise a concept map with
`--updates`, changing only its last section, and of the labels that are
byte-for-byte unchanged, **0 of 5 keep their guid**. A `mutable` re-ingest
mints a fresh tree, so every prior `talks_about` edge points at a heading no
live map reaches.

Decision 10 says a removed label's old edges "stay, pointing at the heading
node they named, which remains true". That is literally true and practically
empty: after *any* edit to the map, that is the state of *every* edge, not
just the removed label's. `check` stays clean and the collection view simply
renders nothing for them, so the accumulation is silent.

The workflow this implies is in `docs/man-compost.md`: **revise the map,
delete the old run's graph file, re-classify.** At the measured cost — a full
pass over a 4,845-block base is about $0.50 — re-classifying is cheap enough
that this is a procedure rather than a problem. Making guids survive a
revision is a real design question about identity, and is not being answered
here; it is the same shape as the semantic clock this project has declined to
build three times.

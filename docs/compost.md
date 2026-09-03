# compost

*A local-first knowledge base where a conversation and a document are the same
kind of thing, and every paragraph has a name.*

**Status: v0.2.11 draft, complete in outline.** Assembled from `CLAUDE.md`,
`decisions.md`, `record-format.md`, `record-grammar.md` and the roadmap. Where
it disagrees with the code, **the code is right and this is a bug** — and that
is the only reading order this document accepts, because every number in it was
measured rather than remembered.

Not yet done: the mechanical half of v0.2.11 — aligning the README's opening
with the abstract, the test that keeps them aligned, the link-resolution test,
and splitting `migration.md` along the seam between what shipped and what was
only ever proposed.

---

## Abstract

compost turns conversations and notes into an addressable graph. Every
paragraph, list item, tool call and answer becomes a node with a permanent
identifier, so a person and an agent can point at the same sentence and disagree
about it. Nothing is summarised away: the conversation that produced a decision
stays readable beside the decision.

It is built for one situation — running several projects at once, and needing to
get back into one cheaply after weeks away. The design follows from that: keep
everything, decide later, and make every claim checkable.

> This is the README's opening, verbatim. `tests/test_manpage.py` asserts the
> two are byte-identical, so neither can drift — the same reasoning that keeps
> `tools/queries/*.sql` referenced from `docs/queries.md` rather than pasted
> into it.

---

## 1. The shape

Three parts, and the middle one is the point.

```
  digestors                    the records                    renderers
  ─────────                    ───────────                    ─────────
  --as=notes              ┐
  --as=pandoc-ast         ├──►  nodes + edges   ──►  views/default-djot   (agents)
  --as=claude-code-…      ┘     JSONL, flat          views/default-html   (people)
                                                     views/default-md     (README, …)
        ▲                            │                        ▲
        │                            ▼                        │
    storage/                  compost layer              graphviz/
   (immutable bytes)      (derives more records)      (drawn, then embedded)
```

**This is a waist.** Everything entering becomes nodes and edges; everything
leaving is generated from nodes and edges and from nothing else. A missing edge
is a visibly broken page the same day, not a silent wrong answer months later.

The waist is what makes the rest of the design possible to state at all. Any
number of digestors, any number of renderers, and neither has to know about the
other.

## 2. Principles

**These are not invariants, and the distinction matters.**

An **invariant** is a property of the graph that a program checks. `check()`
makes **ten** assertions and refuses a view when any fails. You cannot violate
an invariant and ship; you get an error. (Ten assertions, twelve call sites —
the parent-count rule reports three different ways. Counting `problems.append`
gives twelve and is the wrong number; `docs/record-grammar.md` §5 enumerates the
ten, and `tests/test_grammar.py` checks that enumeration against the code.)

A **principle** is a rule about how the system is built, enforced by attention.
You can violate one and everything still passes. Each of the fifteen below was
learned by violating it — several more than once — and each carries the incident
that produced it. Python's own list calls itself *aphorisms* (`import this`);
this is the same kind of thing. Calling them invariants would make them sound
stronger than they are, and the whole reason to write them down is that nothing
enforces them.

**Fifteen principles. Ten invariants. They are different lists, they live in
different documents, and only one of them is enforced by a program.**

### On what enters

**1. Digest everything the file holds; filter at query time, never at import.**
A field dropped while reading is dropped once, silently, and every base built
afterwards is missing it with nothing to show it was ever there. Filtering later
is free and reversible; filtering at import is neither. *Held by property:*
`records_to_session(session_to_records(lines)) == lines`, exact. *The incident:*
an audit found the transcript importer dropping 46% of a real transcript's lines
and seventeen log-line keys.

**2. Nothing about ingestion is inferred from a file extension.** The route is
named with `--as` or the command refuses. *The incident:* this was dispatch on
the suffix until v0.2.2, where the fallback was not "markdown" but *anything at
all*.

**3. Sources are immutable, and storage is a blob store.** Every file lands
under a freshly minted `GUID.EXT`; `storage/` never overwrites. The same bytes
may legitimately arrive twice — `digest` reports that and does not resolve it.

**4. Filter only when disk or compute requires it.** The operator's formulation,
and the general form of principle 1. A **view** may filter freely, because it is
a projection rebuilt on every render and its omissions are undone by editing the
projection. An **importer's** omissions are not. So when something should not be
on the page, the answer is always a view-time suppression that leaves the node
addressable.

### On what is stored

**5. Filenames carry no meaning, and load order cannot change the result.**
Graph files are minted uuids; records are concatenated from every matching file;
shuffling them must produce an identical graph. This is what keeps files freely
regroupable and a SQL glob honest.

**6. `graph/` is flat, by rule.** A subdirectory is meaning. `Store.write`
refuses one. *The incident:* subdirectories were permitted, read, and used by
nothing — until a read-only SQL view over the same directory had to glob it too,
and a file visible to one reader and not the other would have been a silent
disagreement about what the graph is.

**7. Guids are UUIDv4, everywhere, always. Nothing derives a guid from
content.** A content hash with a uuid-shaped output resolves duplicates at write
time by construction, which is the thing forbidden everywhere else. *Measured:*
content-addressed naming would merge 633 empty table cells into one node, and
every identical `Yes.` across every document. Identity is positional; equality
is content-derived; conflating them merges things that are only accidentally
alike.

**8. A handle is the whole guid.** A prefix is not a shorter handle. *The
incident:* a prefix resolver was written and removed — it resolved in the graph
while the HTML view emitted the href verbatim, so a shortened citation resolved
for a tool and was a dead anchor for a person clicking it.

**9. Anything may write records; `check` is the gate.** The records `digest`
writes are ordinary Python, and so are a script's, a migration's, an agent's.
`Store.load()` does not care who wrote a file. *Stated honestly:* this is a
trust model and the trust is currently unearned — `check` verifies structure,
not that a node's `type` is a known one, so a typo'd `"alais"` passes.

**10. Duplicates accumulate, on purpose.** Nothing is deduplicated,
no consistency is guaranteed, and no dependency is managed. *The incident:* an
architecture review of a design that *did* try to stay consistent found four
states a base could enter and never leave. Removing the goal removed all four.

### On what leaves

**11. A view of a broken graph is worse than no view.** `render` refuses when
`check` fails, and says so.

**12. The round-trip property is the acceptance test.** If
`records_to_ast(ast_to_records(ast)) == ast` fails on any fixture, the change is
wrong regardless of what else passes.

**13. Reconstruction and viewing are different functions.** `records_to_ast`
stays exactly reversible; handles, collapsing and decoration belong in the view.

**14. Never scan raw file text for citations.** A citation is a `Link` node, and
reading the parsed content is what makes *"handles inside code blocks are not
citations"* true by construction rather than by rule. *The incident:* violated
three times under the old text-based syntax, and it cost something every time.

**15. Do not repair pandoc's output, and do not tidy its flags.** Three defects
are known and documented; they sit outside the AST-to-AST property on purpose,
and patching them breaks the round-trip by construction. Every flag in the
pandoc invocations — `-smart`, `-attributes`, `-fancy_lists` — prevents a
specific, measured corruption.

### The one about working, not about the system

**Work on `main`, and tag each version.** One developer, no CI, nothing to
isolate from. Branch only for a genuine one-way door. *The incident:* the
standing candidate for a feature branch turned out to be render-time and shipped
on `main` in an afternoon.

## 3. Digestors

A **digestor** — a *route* in the code — is one named way material enters a
base. There are four:

| route | reads | pulls in other files |
|---|---|---|
| `notes` | prose, as commonmark_x | no |
| `pandoc-ast` | a pandoc JSON document, already parsed | no |
| `claude-code-transcript` | a Claude Code session `*.jsonl` | **yes** |
| `claude-code-response` | a `{responds_to, envelope}` wrapper around `claude --print` | no |

**The route is named, never guessed** (principle 2). `compost digest --as=notes
notes.jsonl` reads markdown, because that is what was asked for. A missing or
unknown `--as` is an error that lists the routes rather than a guess at what was
meant.

### Ingestion is two-phase, and that is what makes it safe to re-run

**Nothing is written until every input has been read and parsed.** Storage names
are minted rather than derived, so a batch that dies halfway leaves the files it
already ingested in the base — and re-running it after fixing the bad input
would ingest them a *second* time under fresh guids. Validating first makes a
batch safe to re-run, which is the only reason it is safe to hand this command a
glob.

### A route may say the file it read names other files

This is the one place `digest` reads something it was not handed, and it is
allowed for one reason: **it is not a guess.** A transcript that launched a
subagent records that agent's id in its own log, the agent's turns are in a file
named after that id, and the parent is *incomplete* without it. Every discovery
is printed, because a side effect nobody can see is the kind found by accident
two months later. `--no-follow` turns it off.

That makes ingestion **recursive** — a depth-2 agent finds its parent among the
depth-1 transcripts pulled in by the same invocation. It is depth-first and
synchronous today. If it ever became asynchronous, this is the part that needs a
queue: the recursion is discovered while reading, not known in advance.

### Every edge endpoint a batch mints must resolve

Either within the batch or already committed, or **nothing is written.** A
structural field naming a guid nobody minted is not a fact about the world, it
is a typo in whatever produced the file.

This is deliberately *not* the citation path. A citation whose target is missing
is real information — something was cited that is not here yet — and
`compost layer citation` records it as a placeholder.

### What a digest leaves behind

Bytes are copied into `storage/` under a freshly minted `GUID.EXT`, and a `blob`
node records the original name, the sha256, the import time and the route. The
document is joined to it by a **`derived_from`** edge in the `ingestion` layer —
derived *from* the bytes, not contained *by* them.

**The two names are unrelated on purpose.** To get from a document to its bytes
you follow `derived_from` and read `params["stored_as"]`. There is no rule that
turns an original filename into a storage path, and anything that invents one
will be wrong.

## 4. The records

One record per line of JSONL, each saying whether it is a `node` or an `edge`.
Measured on a working base: **90,434 records — 29 node types and 8 edge types.**

### Structure is two edge types

**`contains`** builds the tree: every node has exactly one parent, except roots
(`document`, `session`) which have none and a short list that is *pointed at*
rather than contained — `blob`, `file`, `alias`, `unresolved_citation`,
`display_name`.

**`next`** orders siblings. Order is a chain, not an index, because an index has
to be renumbered and a chain does not. Three loader checks replace what an index
made impossible: one head, no cycle, full coverage of the children.

Everything else — `cites`, `launched`, `touches`, `replies_to`, `derived_from`,
`names` — is meaning rather than structure.

### Layers are the unit of provenance and of deletion

Every edge carries one. Eight are defined: `pandoc-ast`, `session`,
`claude-code`, `ingestion`, `agent`, `citation`, `conversation`, `display`.

A layer answers *who asserted this, and can I remove it without touching
anything else?* Deleting a whole graph file that one `layer` run wrote is the
only inverse this design offers for accumulation it never removes — and it works
because a layer's edges are separable from the structure they annotate.

### Two hash functions that share a name and are not comparable

| | node | edge |
|---|---|---|
| input | `[type, params, content]` | the record minus a skip list |
| shape | positional **array** | an **object** |
| present | only when the node has content | always |

Both are `sha256(canonical(…))`, where `canonical` is JSON with sorted keys, no
spaces, `ensure_ascii=False`. **A query grouping by `content_hash` across record
kinds is comparing nothing.**

The edge form excludes identity *and provenance* deliberately: a hash must say
what the edge **claims**, never when or by what it was written, or the same fact
rebuilt tomorrow would not match the one written today.

**Neither reaches everything**, and this is the honest statement of the gap: the
transcript node types, `alias` and `unresolved_citation` carry no hash at all,
and an edge pointing at a placeholder hashes differently on every build.
`content_hash` is **evidence for a dedup design**, not a mechanism anything acts
on. Nothing in `src/` reads it to decide anything.

### The closed vocabularies

Four lists are closed in schema 1; everything else is open. Closed means a value
outside the list is a bug, not an extension.

**Routes** — `notes`, `claude-code-transcript`, `pandoc-ast`,
`claude-code-response`. Nothing is inferred from a file extension; the suffix
survives into `storage/` as decoration and nothing reads it.

**Layers** — `pandoc-ast`, `session`, `claude-code`, `ingestion`, `agent`,
`citation`, `conversation`, `display`.

**Authors** on a `turn` — `human`, `assistant`, `envelope`. *These bit once:*
the HTML view shipped CSS selectors naming `claude` and `agent`, ported from
v0.1, which matched nothing on any page ever rendered. A closed list is only
useful if the code is checked against it.

**Schemes** — which resolver produced a citation edge or an alias: `uuid-link`,
and `kg-8hex` for migrated v0.1 handles.

Two more sets are closed in code rather than in prose. **`ROOT_TYPES`** —
`document`, `session` — the nodes with no parent. **`UNCONTAINED`** — `blob`,
`file`, `alias`, `unresolved_citation`, `display_name` — nodes that are *pointed
at* rather than contained. Everything else has exactly one `contains` parent.

### The ten invariants

What `check()` asserts over a whole loaded graph. **A view of a graph failing any
of them is refused, not rendered** (principle 11).

1. No guid carries two different records.
2. Every edge endpoint resolves to a node that is present.
3. Parent count: `UNCONTAINED` zero, roots zero, everything else **exactly one**.
4. A `session` is `launched` by at most one `toolcall`.
5. No cycle through `contains` ∪ `launched` — both are containment as far as
   rendering is concerned, and a cycle across the pair would loop a view.
6. No cycle in `contains` alone.
7. The `next` chain over a node's children is a total order: one head, no cycle,
   no edge leaving the parent, full coverage.
8. No two nodes share a handle. Vacuous while a handle is the whole guid; it
   exists so that shortening handles cannot silently introduce collisions.
9. `content_hash` is present exactly when required — nodes only.
10. `schema_version`, when present, is not greater than the one this tool writes.

### Where the per-type grammar lives, and why it is not in this file

**`docs/record-grammar.md` holds the exhaustive tables** — every node type with
its params, every `(layer, type)` edge pair, the two hash definitions in full.
This document states the *shape*; that one is the *reference*.

The split is not a filing preference. **`tests/test_grammar.py` holds that file
against a base built from the fixtures, in both directions**: the grammar may
not name a type the base never produces, and the base may not produce one the
grammar does not name — and the same for edge pairs and for every node type's
params. An undocumented param is exactly the drift it exists to catch.

That property is worth more than having one file. It also means the reference
cannot be moved or absorbed without moving the test that guards it, and a
grammar nothing checks is how every stale document in this repository started.

### `schema_version`, on every record

Not per file and not per base: filenames carry no meaning and `load()` moves
records between files freely, so a per-record field is the only form that
survives regrouping and lets schema 2 sit beside schema 1 during a migration.
**Absent means 1**, by definition rather than by guess.

The field is also *read* — `check` refuses a record from a newer tool than the
one loading it. Without that it would be a comment in JSON.

## 5. Renderers

Three views, from the records and from nothing else:

| view | for | how it treats bulk |
|---|---|---|
| `views/default-djot/` | agents | shown in full — djot has no collapse |
| `views/default-html/` | people | tool calls, output and subagent transcripts folded |
| `views/default-md/` | regenerating README and the like | full, **no handles injected** |

The markdown view carries only the handles its source already had, so its output
is clean enough to commit.

### `render` refuses a graph that fails `check`

Not a crash — a refusal, printed (principle 11). A page that looks fine and is
wrong is worse than no page.

### What is on disk is exactly this render's output

`render` used to only ever write, which was invisible while every document had a
page forever, and became wrong the moment a transcript could stop having one of
its own — the stale page stays in the browser showing a document the graph no
longer presents that way. So the sweep removes what this run did not produce.
Views are generated and disposable; deleting one costs a rebuild.

### Renderers depend on each other

`compost draw` writes DOT — and SVG when graphviz is installed — into
`.compost/graphviz/`, a **peer** of `graph/`, `storage/` and `views/` rather
than a subdirectory of `views/`.

The direction of the dependency is why: an HTML view will eventually *embed*
those SVGs, which makes graphviz output an **input** to `render`, the way
`storage/` is an input to `graph/`. Putting an input inside the output directory
would be backwards, and actively confusing the moment `render` starts reading
from it. The pipeline is legible from the layout alone.

**The DOT is always written; the SVG only when the binary is there.** That is
what keeps the dependency optional: text an agent can read and anyone can render
later, rather than all-or-nothing.

### A display name changes what is shown, never what a file is called

Page filenames come from the document's source stem, disambiguated by the root's
guid when two collide. A display name — a record, not a field — changes the text
on the index and nothing else. Otherwise every bookmark moves whenever a name is
edited.

## 6. The symmetry, which is the thesis

**An agent and a person read the same text.** Not a summary for one and the
source for the other — the same blocks, the same handles, the same graph.

HTML for people because it is pleasant to read and click; markdown and djot for
agents because they carry less distraction; both openable in a browser, so any
claim about what an agent saw is auditable by looking. Both carry a handle on
every citable block, so either can point at a sentence and the other can resolve
it.

Everything else in this document exists to keep that true.

## 7. Decisions, and the principle behind each

Every non-obvious choice in this codebase is justified here or in
`docs/decisions.md`, which loses nothing in the move. A selection, with what
settled each:

**The tool does not hold your hand.** *(principle 10)* An architecture review of
a larger design — declarations, staleness detection, dependency-ordered
rebuilds — found **four states a base could enter and never leave**, each
escapable only by hand-editing `graph/`. All four came from one source: trying
to keep the graph automatically consistent. Removing the goal removed every one
of them.

**`load()` collapses byte-identical records.** Two writers asserting the same
fact is agreement, not conflict. This looks like a convenience and is not:
measured on a base holding one duplicated graph file, *with* dedup 0 problems,
*without* it `Para … has 2 parents` and `render` refuses. Getting
"collapse later" would mean teaching `check` to count distinct parent edges —
the same logic relocated, not removed.

**A handle is the full UUIDv4.** *(principle 8)* It costs **21.7%** of the djot
view's characters against 7.7% at eight, and on small dense documents reaches
60–75%. Accepted. A prefix resolver was built and removed: it resolved for a
tool while the HTML view emitted the href verbatim, uniqueness degraded as the
base grew, and nobody had complained about length — the 21.7% was a number in a
document, not a person's complaint.

**Storage names are minted uuids, not content hashes.** *(principle 7)* A
content-addressed name resolves duplicates at write time by construction. The
same bytes may legitimately arrive twice, and the second arrival is information.

**`graph/` is flat.** *(principle 6)* Closed ahead of the query layer, because
Python's `rglob` and a SQL glob over the same directory would have disagreed
about what the graph is, for a reason having nothing to do with whatever was
being checked.

**The three pandoc defects are recorded and not repaired.** *(principle 15)*
They live in pandoc's *writer*, downstream of everything the round-trip
property covers. Suppressing them on read would pull them inside the boundary
being tested and break the property by construction.

**Views may filter; importers may not.** *(principle 4)* The harness injects
slash-command boilerplate into transcripts — an instruction addressed to the
model, rendered inside a frame attributed to the human. It is suppressed **at
view time**, recognised structurally rather than by matching prose, and every
suppressed paragraph is still a node that `compost lookup` resolves.

**Alignment is positional, not by hash.** Measured on two re-ingested
transcripts: walking both trees in document order, the older is a clean prefix
of the newer — **5,496 of 5,496** and **221 of 221**, exactly. So *"has this
append-only document changed underneath us?"* is a walk, and needs no global
identity. The same measurement showed 99.98% of an older tree's nodes already
hash-identical after a re-ingest, the single miss being the root, whose
`params["lines"]` counts the file rather than describing the conversation.

**A content hash cannot be an identity.** Within one 6,193-node transcript,
**36% of nodes share a content hash with another** — 633 empty table cells, 229
empty thinking markers, 217 rows. A Merkle fold cuts that to 28.5% by
distinguishing containers, and does **nothing** for leaves, because a leaf's
fold *is* its content hash. Those 229 markers genuinely are the same value; what
makes them different blocks is where they sit. Hence principle 7.

## 8. What this is not

- **Not multi-writer.** Single writer assumed. That assumption licenses most of
  the design and is written down so its removal is a decision rather than a
  discovery.
- **Not a dependency manager.** Nothing infers what must be rebuilt or in what
  order. The operator sequences `digest`, `layer` and `render`.
- **Not consistent.** See principle 10.
- **Not a place to hide personal material.** A base is gitignored and
  machine-local. This repository has had personal material purged from its
  history once, and that is the standard for rewriting history: material that
  should never have been committed, not material that is merely old.

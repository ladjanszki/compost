# compost

*A local-first knowledge base where a conversation and a document are the same
kind of thing, and every paragraph has a name.*

**Version 0.2.14.** Every earlier version of this document is kept, unedited, in
the notes repository — because the paper explaining this project is going to be
digested *by* it: one revision chain over its own history, once v0.2.17 lands
`revision_of`. They are not in `docs/`, and there is no procedure for putting
them there. A checklist telling a person which markdown file to copy where is a
policy standing in for the system this project exists to build, and it would
have to be maintained until the day it became unnecessary.

The version lives in this line and not in the filename: `docs/compost.md` never
moves, because the appendix build and two suites hardcode the path.

**First assembled in v0.2.11** from `CLAUDE.md`,
`decisions.md`, `record-format.md`, `record-grammar.md` and the roadmap. Where
it disagrees with the code, **the code is right and this is a bug** — and that
is the only reading order this document accepts, because every number in it was
measured rather than remembered.

**Section 4's grammar paragraph was rewritten in v0.2.12**: the per-type
grammar's machine-read source moved from `record-grammar.md` prose to
`tools/record-schema-1.json`, validated by `jsonschema`; `record-grammar.md`
keeps the prose and the reasons. Still deferred: splitting `migration.md`. The
superseded v0.2 drafts were waiting on a review that was never going to happen
on a schedule; in v0.2.13 they moved to the notes repository with everything
else that is merely old, to be ingested rather than triaged.

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
makes **thirteen** assertions and refuses a view when any fails. You cannot
violate an invariant and ship; you get an error. (Thirteen assertions,
nineteen call sites — one rule can report several ways, the parent-count rule
alone in three. Counting `problems.append` gives nineteen and is the wrong
number; *The thirteen invariants*, below, is the enumeration this document
keeps current. This paragraph said "ten assertions, twelve call sites" through
v0.2.15, two releases after the count moved — the same drift the invariant
list itself shipped at v0.2.14, and the reason a number here is now written
next to the thing that produces it.)

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
is free and reversible; filtering at import is neither. *The incident:*
an audit found the transcript importer dropping 46% of a real transcript's lines
and seventeen log-line keys.

*Held by two properties, and the second was missing until v0.2.13.* The first is
`records_to_session(session_to_records(lines)) == lines`, exact — the **file** is
reconstructible. The second is **total mapping**: for every object a digestor
reads, every key is accounted for — a param, the node type, or descended into as
children. A key that lands nowhere fails the suite, naming the digestor and the
key.

**The file-level property is not enough on its own, and hid a real loss for four
minor versions.** Every transcript line is kept verbatim in the parent turn's
`params["log"]`, so the round trip stayed green while the *nodes* were
impoverished: `thinking` dropped `signature` on 492 blocks, `toolcall` dropped
`caller` on 902, and a list-shaped tool result was flattened to joined text. The
first had a visible consequence nobody noticed — every empty `thinking` node in
a base hashed identically, **491 into 1**, because the only thing distinguishing
them was the field the mapping threw away. The file was whole and the graph was
not, and only one of those was being tested.

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

### Digestion is delegating, not recursive-by-accident — v0.2.14

**A digestor that meets content it does not own hands it to the digestor that
does, explicitly, and the delegated input is stored as a blob like any other
digestor input.** A transcript's assistant prose is markdown; the transcript
digestor does not parse markdown, it delegates.

*The incident that produced this:* `session.py` did not call the text digestor,
it **reimplemented** it — two `READER` constants holding one string, two
functions turning markdown into blocks, and a reach into a private function to
do what the public one does. `docs/decisions.md` records every flag in those
invocations as load-bearing and measured, so the second copy was a silent
divergence waiting for the first edit to the notes reader.

The rule the release produced has no exceptions:

> Every digestor's input is stored as a blob. Every key of that input is a
> param, the node type, a child, or delegated to a named digestor — whose input
> is itself a blob.

That makes totality (principle 1) **compositional**: each digestor is total on
its own format, delegation composes them, and the pipeline is total by
induction. It is also why the first version of this rule was wrong: it split
mappings into "structural" and "interpretive" and asked importers to declare
which they were, turning a structural problem into a list of exceptions.
Delegation removes the kinds instead of documenting them.

**Cost, measured:** 549 delegated inputs across seven transcripts, 376 KB
against 10.8 MB — **3.5%**, median input 158 bytes.

**The delegated document is a root nobody contains**, reached by a
`delegates_to` edge, because `document` is a `ROOT_TYPES` member and a root with
a parent fails `check`. This is the shape a launched subagent session already
has. The consequence worth knowing: **a walk over `contains` and `next` alone
now reaches 52.5% of a digest** — every `Para`, `Plain` and `Header` lives below
a delegation — so anything traversing a conversation must follow the edge.
Missing that is invisible: it reports a tidy 100% of half a graph.

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

Both are called `record_hash` — v0.2.13 renamed them from `content_hash`,
because that name claimed a semantics neither has. They are computed by
different functions over different shapes and **a query grouping by
`record_hash` across record kinds is comparing nothing.**

| | node | edge |
|---|---|---|
| input | `[type, params, content]` | the record minus a skip list |
| shape | positional **array** | an **object** |
| present | **always, every node** (v0.2.13) | always |

Both are `sha256(canonical(…))`, where `canonical` is JSON with sorted keys, no
spaces, `ensure_ascii=False`. A node also carries `record_subtree_hash`, the
fold over its own hash and its children's, in `next` order.

The edge form excludes identity *and provenance* deliberately: a hash must say
what the edge **claims**, never when or by what it was written, or the same fact
rebuilt tomorrow would not match the one written today.

**`record_hash` answers *is this the same record*, not *is this the same
value*.** The second question is a projection that differs per question and
belongs in a layer, where being wrong is a rebuild rather than a migration.
Nothing in `src/` reads either hash to decide anything yet; they are evidence
for a dedup design, plus the two things `check` now verifies — that they
recompute, and that `derived_from` is acyclic.

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

### The thirteen invariants

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
9. Every node carries `record_hash` and `record_subtree_hash` — unconditionally,
   not only nodes with content of their own (v0.2.13 renamed and generalised the
   old per-node `content_hash`, which was conditional).
10. `schema_version`, when present, is not greater than the one this tool writes.
11. Both hashes **recompute** — `record_hash` from `[type, params, content]`,
    `record_subtree_hash` from the fold over `contains`/`next` — v0.2.13, and
    the first assertion here that verifies content rather than structure
    (`docs/roadmap.md`, "v0.2.13 — the fold").
12. **`derived_from` is irreflexive and acyclic.** v0.2.14, and it is here
    because the edge was aligned with `prov:wasDerivedFrom`: PROV binds
    derivation to being irreflexive and acyclic, so borrowing the name means
    enforcing them. PROV's third constraint — that the source pre-exists the
    target — is **deliberately not enforced**, because `created_at` is audit
    metadata rather than semantics and there is no semantic clock to order by.
    The schema records both halves of that, and a test asserts every borrowed
    name declares what it does and does not honour.
13. **An `immutable` root carries at most one `derived_from` edge.** v0.2.15,
    and the only assertion here that is openly a **proxy**. The contract
    `mutability` declares is "no edges added to this root after the ingest
    that created it" — which needs the very clock 12 just explained does not
    exist. Nodes carry no creation time; `created_at` is audit metadata; load
    order carries no meaning. What survives without a clock is the structural
    trace: every ingest path mints exactly one `derived_from` per root, so a
    second one on an `immutable` root is what such a violation leaves behind.
    A hand-authored `contains` edge spliced on with no second blob is **not**
    caught, and that gap is named here rather than left to be discovered.

### Where the per-type grammar lives, now in three layers

Through v0.2.11 this section argued that `docs/record-grammar.md` was the
*machine-read* reference, held against a fixture-built base by
`tests/test_grammar.py`. That test discovered the grammar by scraping the
document's prose — splitting on a heading string, parsing markdown table
pipes, pulling field names out of backticks — and a rename of that heading
would have made the suite quietly assert less rather than fail.
`TODO-code-review.md` keeps the incident; **v0.2.12** is the fix.

**Three layers now answer three different questions, and no single file is
asked to answer all of them.**

| layer | answers | where |
|---|---|---|
| JSON Schema | what may a *record* be | `tools/record-schema-1.json` |
| `check()` | what must a *graph* be | `src/records.py`, unchanged |
| prose | *why* | this document, and `docs/record-grammar.md` |

A schema validates one document at a time and cannot express any of the ten
invariants above — no cycle in `contains`, the `next` chain a total order,
exactly one parent — so `check()` is not replaced and does not shrink.

**The five coverage guarantees survive, unweakened, reading structured data
instead of scraping a document**: `tests/test_grammar.py` holds the schema
against a base built from the fixtures, in both directions — the schema may
not name a type the base never produces, and the base may not produce one the
schema does not name — and the same for `(layer, type)` edge pairs and for
every node type's params. It also validates every record in that base against
the schema directly, which no amount of table-scraping ever did.

`docs/record-grammar.md` keeps the prose and the reasons; it is no longer what
any program reads. The appendix below is the schema, rendered.

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

**Alignment is positional, not by hash.** Walk both trees in document order and
the older is a clean prefix of the newer. Re-measured in v0.2.13 under
`record_hash`, over six corpus sessions truncated to 70% and re-read: **8,848 of
8,848 — 100.0000%** of the older tree, every session exactly. So *"has this
append-only document changed underneath us?"* is a walk, and needs no global
identity.

**And one derived param defeated it single-handed.** Before v0.2.13 the session
root carried `params["lines"]`, a count of the file. On `session-04` the
identical prefix was **0 of 2,306** with it and **2,306 of 2,306** without —
because the root is position 0, so a root that fails to match makes the prefix
empty and delta ingest re-mints everything. Hence the rule: *a derived param may
be a function of the node itself; it may never be a function of the node's
subtree.* `empty` on `thinking` is `f(text)` and is stable forever; `lines` was
`f(children)` and moved every time the tree grew.

**A record hash cannot be an identity.** Within one 6,193-node transcript, **36%
of nodes shared a hash with another** — 633 empty table cells, 229 empty thinking
markers, 217 rows. A Merkle fold cuts that to 28.5% by distinguishing containers
and does **nothing** for leaves, because a leaf's fold *is* its own hash. Those
229 markers genuinely are the same value; what makes them different blocks is
where they sit. Hence principle 7.

**`record_hash` answers "is this the same record", not "is this the same
value".** *(v0.2.13, renaming and generalising the conditional `content_hash`.)*
The second question is a projection — it differs per question, and it belongs in
a layer, where being wrong is a rebuild rather than a migration.

**The fold earns its place on documents, not on transcripts.** A container's
whole substance is its children, so its own hash says nothing: **all 417
`BulletList`s** in the corpus share one `record_hash`, all 159 `BlockQuote`s, all
1,040 `Cell`s. `record_subtree_hash` cuts those to 144, 60 and 988. This is also
what makes the hash safe in one direction only — given total mapping, subtree
equality implies the source subtrees were identical, so for any coarser notion
of sameness the fold yields **false negatives only**. It can fail to notice a
sameness; it cannot invent one. Before total mapping that was false, and the 491
merged thinking blocks were the proof.

**The mapping is the whitelist.** *(principle 1.)* A per-type list of which
params count as content was specced and abandoned: it costs one discretionary
decision per param per type per digestor, and cstlib, graphviz and a filesystem
digestor would each bring dozens of types. The importer already decides what a
thing is made of, in code that is reviewed and under test. Asking a second time,
in a table, is asking in a worse place — so the hash covers the record, and to
change what counts you change the mapping.

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

## Appendix: the record grammar

Generated from `tools/record-schema-1.json` by `tools/schema_tables.py`, run
through `python3 -m tools.build_whitepaper`. Everything between the two
markers below is regenerated on every build and discarded if hand-edited —
`tests/test_grammar.py` asserts the file already holds exactly what a fresh
render produces, and that running the build again changes nothing.

<!-- BEGIN GENERATED: tools/schema_tables.py -->

**36 node types.** Params split required / optional; "carries content" means the type also holds pandoc inline content, not only `params`.

| type | required params | optional params | carries content |
|---|---|---|---|
| `BlockQuote` | — | — | — |
| `BulletList` | — | — | — |
| `Caption` | — | — | — |
| `Cell` | `align`, `attr`, `colspan`, `rowspan` | — | — |
| `CodeBlock` | `attr`, `text` | — | — |
| `DefinitionItem` | — | — | — |
| `DefinitionList` | — | — | — |
| `DefinitionTerm` | — | — | yes |
| `Div` | `attr` | — | — |
| `Figure` | `attr` | — | — |
| `Header` | `attr`, `level` | — | yes |
| `HorizontalRule` | — | — | — |
| `LineBlock` | — | — | yes |
| `ListItem` | — | `wrap` | — |
| `OrderedList` | `list_attributes` | — | — |
| `Para` | — | — | yes |
| `Plain` | — | — | yes |
| `RawBlock` | `format`, `text` | — | — |
| `Row` | `attr` | — | — |
| `Table` | `attr`, `colspecs` | — | — |
| `TableBody` | `attr`, `intermediate_rows`, `row_head_columns` | — | — |
| `TableFoot` | `attr` | — | — |
| `TableHead` | `attr` | — | — |
| `alias` | `scheme`, `value` | `generated_by`, `pandoc` | — |
| `blob` | `bytes_sha256`, `imported_at`, `original_name`, `route`, `stored_as` | `selector_conforms_to`, `selector_value` | yes |
| `contentblock` | `block`, `block_type` | — | — |
| `display_name` | `value` | — | — |
| `document` | `meta`, `pandoc_api_version`, `route` | `api_error_status`, `duration_api_ms`, `duration_ms`, `fast_mode_disabled_reason`, `fast_mode_state`, `is_error`, `modelUsage`, `mutability`, `num_turns`, `permission_denials`, `result`, `session_id`, `source`, `stop_reason`, `subtype`, `terminal_reason`, `time_to_request_ms`, `total_cost_usd`, `ttft_ms`, `ttft_stream_ms`, `type`, `usage`, `uuid` | — |
| `file` | `path` | — | — |
| `logline` | `line_type`, `log`, `timestamp`, `uuid` | — | — |
| `session` | `route`, `session_id`, `source`, `version` | `agent`, `mutability` | — |
| `thinking` | `empty`, `signature`, `text` | — | — |
| `toolcall` | `input`, `name`, `tool_use_id` | `caller` | — |
| `tooloutput` | `is_error`, `text`, `tool_use_id` | — | — |
| `turn` | `author`, `log`, `timestamp`, `uuid` | — | — |
| `unresolved_citation` | — | — | — |

**14 `(layer, type)` edge pairs.**

| layer | type | aligns with |
|---|---|---|
| `agent` | `launched` | — |
| `citation` | `cites` | — |
| `citation` | `names` | — |
| `claude-code` | `replies_to` | — |
| `conversation` | `next` | — |
| `conversation` | `responds_to` | — |
| `display` | `names` | — |
| `ingestion` | `derived_from` | prov:wasDerivedFrom (W3C PROV-O) — enforced: irreflexive (a node is never derived from itself); acyclic (records.check()'s twelfth assertion, v0.2.14); not enforced: the source pre-existing the target — created_at is audit metadata, not semantics, so there is no semantic clock to order derivation by (docs/design-0.3.0.md §7) |
| `pandoc-ast` | `contains` | — |
| `pandoc-ast` | `next` | — |
| `session` | `contains` | — |
| `session` | `delegates_to` | — |
| `session` | `next` | — |
| `session` | `touches` | — |

**63 distinct params.** Which node types each appears on. The third column is a leftover: it was to be filled in by hand, one row at a time, deciding which params counted as content. `v0.2.13` removed that question rather than answering it — the mapping is the whitelist — so nothing reads this column. It is still rendered because the table is generated and an empty column is cheaper than a special case.

| param | appears on | content? (unused) |
|---|---|---|
| `agent` | `session` |  |
| `align` | `Cell` |  |
| `api_error_status` | `document` |  |
| `attr` | `Cell`, `CodeBlock`, `Div`, `Figure`, `Header`, `Row`, `Table`, `TableBody`, `TableFoot`, `TableHead` |  |
| `author` | `turn` |  |
| `block` | `contentblock` |  |
| `block_type` | `contentblock` |  |
| `bytes_sha256` | `blob` |  |
| `caller` | `toolcall` |  |
| `colspan` | `Cell` |  |
| `colspecs` | `Table` |  |
| `duration_api_ms` | `document` |  |
| `duration_ms` | `document` |  |
| `empty` | `thinking` |  |
| `fast_mode_disabled_reason` | `document` |  |
| `fast_mode_state` | `document` |  |
| `format` | `RawBlock` |  |
| `generated_by` | `alias` |  |
| `imported_at` | `blob` |  |
| `input` | `toolcall` |  |
| `intermediate_rows` | `TableBody` |  |
| `is_error` | `document`, `tooloutput` |  |
| `level` | `Header` |  |
| `line_type` | `logline` |  |
| `list_attributes` | `OrderedList` |  |
| `log` | `logline`, `turn` |  |
| `meta` | `document` |  |
| `modelUsage` | `document` |  |
| `mutability` | `document`, `session` |  |
| `name` | `toolcall` |  |
| `num_turns` | `document` |  |
| `original_name` | `blob` |  |
| `pandoc` | `alias` |  |
| `pandoc_api_version` | `document` |  |
| `path` | `file` |  |
| `permission_denials` | `document` |  |
| `result` | `document` |  |
| `route` | `blob`, `document`, `session` |  |
| `row_head_columns` | `TableBody` |  |
| `rowspan` | `Cell` |  |
| `scheme` | `alias` |  |
| `selector_conforms_to` | `blob` |  |
| `selector_value` | `blob` |  |
| `session_id` | `document`, `session` |  |
| `signature` | `thinking` |  |
| `source` | `document`, `session` |  |
| `stop_reason` | `document` |  |
| `stored_as` | `blob` |  |
| `subtype` | `document` |  |
| `terminal_reason` | `document` |  |
| `text` | `CodeBlock`, `RawBlock`, `thinking`, `tooloutput` |  |
| `time_to_request_ms` | `document` |  |
| `timestamp` | `logline`, `turn` |  |
| `tool_use_id` | `toolcall`, `tooloutput` |  |
| `total_cost_usd` | `document` |  |
| `ttft_ms` | `document` |  |
| `ttft_stream_ms` | `document` |  |
| `type` | `document` |  |
| `usage` | `document` |  |
| `uuid` | `document`, `logline`, `turn` |  |
| `value` | `alias`, `display_name` |  |
| `version` | `session` |  |
| `wrap` | `ListItem` |  |

<!-- END GENERATED -->

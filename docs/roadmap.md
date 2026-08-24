# Roadmap

What is **scheduled**, and into which release. `TODO.md`'s *Known gaps* is the
list of things found and named but deliberately unscheduled; an entry moves
here when it has a version number and a design. Nothing here is a promise about
dates — only about order, and about what each release has to prove before it is
tagged.

`CHANGELOG.md` still says what actually happened. If this file and the changelog
disagree, the changelog is right and this file is stale.

| release | what it is |
|---|---|
| **v0.2.4** | `schema_version`, edge provenance, and the citation layer with its naming machinery |
| **v0.2.5** | the legacy handle scheme — then the v0.1 migration runs, as a procedure |
| **v0.2.6** | the conversation loop |
| **v0.2.7** | a graph view: DOT always, SVG when graphviz is installed |
| **v0.2.8** | a query layer over the records |

---

## The governing decision: the tool does not hold your hand

This was decided after a full architecture review of an earlier, much larger
design. That design tried to keep the graph automatically consistent —
declarations, staleness detection, dependency ordering, wholesale rebuilds — and
the review found four states a base could enter and never leave, each escapable
only by hand-editing `.compost/graph/`.

**Two constraints replaced all of it:**

1. **Dependencies are not handled for you.** Nothing infers what must be rebuilt,
   in what order, or whether it is out of date. The person running the tool is
   responsible for running things in the right order.
2. **Deduplication, information preservation across rebuilds and consistency are
   not guaranteed.** Duplicates accumulate. That is the intended behaviour, not a
   defect: *"collect all we can and filter or collapse later"*, and the pattern of
   how duplicates actually accumulate is the input to a dedup design that has not
   been written.

Removing the goal removed every one of the four failure modes with it. What is
left is deliberately bare, and `docs/decisions.md` records the trade in full.

**A consequence to state plainly:** `content_hash` is *evidence for a future
dedup design*, not a mechanism that anything acts on today. Nothing collapses
records automatically. Two things that hash equal both stay.

---

## v0.2.4 — the citation layer, and the naming machinery it needs

### Why this first

`records.citation_edges()` was written, tested in `tests/test_citations.py`, and
**never called by anything in `src/`**. So today a `[-](#guid)` in a digested
document creates no edge and `compost lookup` cannot say what cites a handle.
Everything downstream — the migration, backlinks, concept maps — waits on edges
that are not being minted.

Wiring it is not a one-line call: `_digest` deliberately validates a batch in
isolation (`src/store.py:261`), and a citation points at a guid from an *earlier*
import. Resolution has to run against the whole loaded base, which is a shape
nothing in the codebase has.

### `schema_version`, starting at 1

Every record carries the version of the grammar it conforms to.

```json
{"record": "node", "schema_version": 1, "guid": "…", "type": "Para", …}
```

**On every record**, not per file and not per base: graph filenames carry no
meaning, `load()` moves records between files freely, and a per-record field is
the only form that survives regrouping and lets schema 2 sit beside schema 1
during a migration.

**The field is also read.** `check` asserts that a `schema_version`, when
present, is not greater than the one this tool writes. It cannot fire on any
existing base — absent means 1 — and it fires the first time a newer tool's
records are loaded by an older one, which is the only reason to carry a version
at all. Without it the field would be a comment in JSON.

**Storage cost, measured on the whole change rather than the flattering half:**

| | |
|---|---|
| `schema_version` alone | +5.1% |
| **the whole v0.2.4 record change** | **+27.1% overall, +78.8% on edges** |

An earlier draft published *4.4%*, which measured `schema_version` alone against
a fixture set that has since grown. Edges nearly double, because three fields are
added to a record whose mean size is 213 B. That is accepted — storage is not
being optimised for — but it is accepted with the real number attached.

**Absent means 1**, by definition rather than by guess: schema 1 *is* what
compost has always written, so no existing base needs rewriting. Optional on
read, required on write. That asymmetry is the entire migration.

Everything through v0.2.5 is additive — new node types, new edge types, new
layers, new optional properties — so **the number stays at 1**. A version that
increments every release carries no information.

### Guids stay UUIDv4 — everywhere, always

An earlier design gave *derived* records a UUIDv5 over the relation they state,
so a rebuild would be byte-identical and `Store.load()`'s dedup would collapse it
for free. **That was rejected.** It is a content hash with a uuid-shaped output,
and it resolves duplicates at write time by construction — the thing this project
forbids everywhere else. It would also have made two documents' identical
sentences share machinery they should not share, and it silently discarded
citation multiplicity.

So `docs/record-grammar.md` §2 stands unchanged: *"GUID is a UUIDv4 in every
case. Nothing derives a guid from content, and nothing derives one guid from
another."* And `docs/decisions.md`'s *"A handle is the full UUIDv4"* stays true.

### `content_hash` on edges

Edges gain a `content_hash`, so that two edges stating the same fact are
*findable* later even though neither is collapsed now.

```
content_hash = sha256(canonical(record minus
    {record, guid, schema_version, content_hash, created_at, tool_version}))
```

So it covers `type`, `layer`, `by`, `source`, `destination` — **what the edge
claims**, never when or by what it was written.

That exclusion list is load-bearing and was found the hard way. An earlier
version said "hash all properties"; with `created_at` also a property, the same
citation built twice would hash *differently*, and the entire purpose of the hash
— finding the same fact restated — would have been defeated for exactly the
duplicates being deliberately accumulated. Provenance is framing, not content.

**The node hash and the edge hash are different functions and are not
comparable.** A node's is `sha256(canonical([type, params, content]))` — a
positional array with no exclusion list. An edge's is an object minus six keys.
They share a field name because they answer the same question about different
record shapes, but a query that groups by `content_hash` *across* record kinds is
comparing nothing. `docs/record-grammar.md` §5 states both definitions side by
side for this reason.

**And it does not reach the records that grow fastest.** A `cites` edge into an
`unresolved_citation` placeholder has a fresh placeholder guid every build, so
two builds' edges for the same unresolved citation differ in `destination` and
therefore hash differently. The same fact restated, unfindable. Unresolved
citations are outside the hash's reach, deliberately and permanently.

### `created_at` and `tool_version`

Top-level properties on **every** edge, ingest-time and built alike. Storage is
not being optimised for. On built edges they are the only record of which run
produced what, which is the raw material for the dedup design; on structural
edges they are redundant with the `blob`'s `imported_at` and kept anyway for
uniformity.

### The two new node types

A citation whose target is not in the base cannot become an edge — a dangling
endpoint fails `check` and would take the whole graph down. Previously that fact
had nowhere to live at all: not in the text, not in the graph, only in terminal
output that scrolls away.

```
citing_block            --cites--> placeholder      layer: citation, by: uuid-link
alias("deadbeef-1111…") --names--> placeholder      layer: citation, by: uuid-link
```

```json
{"type":"alias","created_at":"…","tool_version":"0.2.4",
 "params":{"value":"deadbeef-1111-…","scheme":"uuid-link"}}

{"type":"unresolved_citation","created_at":"…","tool_version":"0.2.4"}
```

**Provenance on these two node types is top-level, never inside `params`.** It
would be harmless in `params` for these two, which carry no `content_hash` — and
it would be wrong the first time a hashed type needs provenance, since node
hashing is `canonical([type, params, content])`. Decided once, here, while it is
free.

**These are the only two node types that carry it.** Every edge does,
ingest-time and built alike; every other node does not. That asymmetry is real
and is not settled — see `TODO.md`, *Provenance is on every edge and on only two
node types*. It is deferred to after v0.2.8 on purpose, because widening it
changes every record written from then on and invalidates the storage figures
above, and neither is worth doing mid-plan.

- **`UNCONTAINED` gains both** (`src/records.py:34`). They are entities: pointed
  at, inside nothing, like `file` and `blob`.
- **Neither carries a `content_hash`.** `check`'s ninth assertion requires it to
  be *absent* unless the node has `content` or is in `TEXT_IN_PARAMS`. Adding one
  would fail the board. Group aliases by `params["value"]` instead.
- **One alias and one placeholder per distinct unresolved value per build.** Two
  citations of the same missing handle in one run produce two `cites` edges into
  one placeholder.

**Why the value lives on the alias rather than on the placeholder.** Because
`lookup` resolves a guid, else an alias, and nothing else. Putting a
lookup-worthy string into a node's params would force `lookup` to know what an
`unresolved_citation` is — a type-specific exception in the one mechanism that
should have none. An alias is *any name that leads to a node*, and a placeholder
is a perfectly ordinary thing to name.

**What a placeholder is mostly for, today.** Forensics: which guids the model
hallucinated when writing an answer, which documentation examples parsed as
citations, what was pasted in from another base. Resolution is possible but
uncommon — see below.

### `compost layer`

```
compost layer                        list what can be built
compost layer NAME [--by SCHEME]     build it
```

No verb, because there is only one action — the criterion set when the shape was
chosen: a verb is earned only when the noun does more than one thing. There is no
`drop`, no `list` of what has been built, and no `layer` node declaring anything.
Bare `compost layer` prints the registry, which is static help rather than
bookkeeping.

`compost layer citation` defaults to `--by uuid-link`.

**`layer` is the second writer to `graph/`, and it does not read what it wrote
last time.** Running it twice produces two full sets of citation edges. Neither
is removed. That is the design.

### `layer` reports what it could not resolve

`citation_edges()` returns `(edges, unresolved)` and the second value has never
had a consumer. Since nothing is bookkept, **the build is the only moment the
information exists** — and now it is written into the graph as placeholders as
well as printed:

```
1,204 cites edges  |  3 unresolved -> 3 placeholders
  deadbeef-0000-0000-0000-000000000000
  7f0e91a2-…
```

### `lookup`

- Resolves an **alias** as well as a guid, and says which alias resolved it.
- Returns **all** matches when several aliases share a value, and says how many.
  Choosing one silently is the failure this project keeps finding.
- Reports **incoming citations**. `CLAUDE.md` currently says it "does not say what
  cites it — there is no citation layer yet"; that sentence has to stop being
  true in the release that makes the layer exist.
- **Reports citations that reached a placeholder naming this guid**, labelled
  distinctly. Without this, `lookup <guid>` says *nothing cites this* for a block
  that **is** cited — because the citing edge points at an `unresolved_citation`
  minted before the target existed, and nothing is ever retracted. The reverse
  path is two hops: `alias` nodes whose `value` equals the guid → `names` → the
  `cites` edges into those placeholders.

  This is not the staleness case in the accepted risks below. Staleness is a
  citation nobody built yet; this is one that *was* built, correctly, and is one
  hop away from where a reader will look for it.

### `Graph._rel` keeps the discriminator

`src/records.py:284` indexes edges by **type alone** and `linked()` returns bare
destination guids, so a view calling `linked(g, "cites")` cannot tell a legacy
citation from an exact one — even though `by` is right there on the record. That
is unintentional discarding of information, not a design choice, and it is fixed
here rather than after four layers depend on it.

### No new `check` assertions

Every assertion the earlier design proposed — layer declarations, staleness,
undeclared layers — went with the bookkeeping. `records.check()` gains nothing
except the two `UNCONTAINED` entries, which are a set membership change rather
than an assertion.

### Tests

`tests/test_layer.py`, added to `tests/run.sh`. Properties, sabotage-verified.

1. Building twice produces **two** sets of citation edges, both present — the
   accumulation is the behaviour, and a test asserting it is what stops someone
   "fixing" it later.
2. Those two sets have **equal `content_hash` pairwise** and different guids.
3. `content_hash` ignores `created_at` and `tool_version` — build twice with
   different timestamps, hashes match. *This is the property that caught a real
   contradiction in design; it must exist.*
4. An unresolved citation mints exactly one `alias` and one `unresolved_citation`
   per distinct value, and the `cites` edge points at the placeholder.
5. The graph `check`s clean after a build with unresolved citations — nothing
   dangles.
6. `lookup` by alias value returns the placeholder and names the scheme.
7. `Graph.linked` preserves `by`.

`tests/test_citations.py` gains the case its unit tests cannot reach: a citation
**across documents**, through `digest` then `compost layer citation` — which is
exactly what `_digest`'s batch isolation could never resolve.

---

## v0.2.5 — the legacy handle scheme, and the migration

**No new record types.** The legacy scheme reuses `alias`, `names` and
`unresolved_citation` from v0.2.4 with `by: kg-8hex`. v0.2.4 builds the naming
machinery; this is its second customer.

### The decision this encodes

The v0.1 corpus cites with `{#xxxxxxxx}`. `TODO.md`'s migration plan proposed
rewriting every occurrence to `[-](#<new-guid>)`. **That plan is rejected**, for
three reasons:

1. **It deletes its own evidence.** That plan's own step 1 says the `.dj` files
   are the only record that the old handles ever existed; its step 3 rewrites
   them, leaving the dictionary as the single record of the mapping.
2. **It is the operation CLAUDE.md forbids** — a textual pass deciding which
   `{#x}` occurrences are citations, applied destructively to the one corpus that
   quotes its own syntax constantly.
3. **Lineage.** Conversations in that corpus are *about* eight-character handles
   and *about* the change to link syntax. Rewrite them and those discussions
   reference a format that appears nowhere in the base they live in.

**Nothing is rewritten — not on disk, not at render time.** The old syntax stays
exactly as written; what is added is a way to look it up.

### The ingest route: `pandoc -f djot` → `--as=pandoc-ast`

**Measured against the real corpus**, not a constructed sample. Two earlier drafts
of this section were written from samples that did not match the material, and
both were wrong; the numbers below come from the 23 `.dj` files themselves.

The shape the v0.1 canonization produced:

```
{#376c3ce7 .turn author="human" turn="019ff17b-…"}
:::
{#acd83164}
Now this definitely needs reworking \{#44670084+++\}
```

Two things matter and neither was guessed correctly before:

1. **Every block is wrapped in a div carrying its handle as a djot attribute.**
2. **Inline citations are already escaped** — `\{#…\}`. The canonization did this
   itself, so they are literal text to the djot reader, not attribute syntax.

Through `pandoc -f djot`, the same bytes give:

```
Div  id=376c3ce7  class=turn  author=human  turn=019ff17b-…
  Div  id=acd83164  wrapper=1
    Para: 'Now this definitely needs reworking {#44670084+++}'
```

Turn structure and authorship intact; the old handle is the block's `id`; the
citation survives as text, unescaped.

**Across all 23 files:**

| | |
|---|---|
| files parsed by `-f djot` | **23 / 23** |
| blocks carrying their 8-hex handle as an AST `id` | **6,741** |
| distinct ids — the collision check, done | **6,741, zero duplicates** |
| escaped citations surviving as text | 206 |
| bare handles inside fenced code / code spans | 948 / 226 |
| **bare handles in prose — the only loss** | **13** |

**13 occurrences out of ~8,400, about 0.15%**, and several of those sit inside
quoted tool output rather than authored prose. Accepted, with the number
attached. The one-off script can recover them from the `.dj` text if they turn out
to matter.

**Why not `--as=notes`.** A draft switched to the markdown reader on the theory
that it loses nothing. It loses no handles, but it merges the turn attribute line,
the `:::` fence, the first block's handle and the first block's text into a single
paragraph — because none of those four lines has a blank line between them. That
happens at the head of **every** turn, making the dictionary ambiguous for the
first block of each. Djot loses 13 occurrences; markdown mangles ~2,400 turn
heads.

**The dictionary is a direct read of the AST** — 6,741 `(id, block)` pairs, no
text matching, no positional alignment, no folding rule, nothing fuzzy.

### `--by kg-8hex`

**Match `\{#[0-9a-f]{8}\}` *within* each `Str`, never as whole-`Str` equality.**
Measured over the 18 documents in this repo that carry real v0.1 handles:

```
135 handles are a whole Str exactly     98 are embedded in a larger Str
whole-token recall: 57.9%
missed: '{#aa813aa9}.'  '{#93360c21},'  '{#330f8531}:'  '({#b1c2d3e4}),'
```

An earlier draft specified whole-token equality and would have dropped 42% of
occurrences silently. The surviving citations sit mid-sentence — *"…needs
reworking {#44670084+++}"* — and real prose puts punctuation after them. The
pattern is self-delimiting, so `re.finditer` over a `Str` handles adjacent
punctuation with nothing to assemble.

Every exclusion is **structural**:

| case | excluded because |
|---|---|
| inline code | a `Code` node's text is a bare string at `c[1]`, not a `Str` |
| code block | its text is in `params["text"]`; the walker never reads `TEXT_IN_PARAMS` |
| `{#xxxxxxxx}` | `x` is not in `[0-9a-f]` |

**There is no assignment rule, and there does not need to be one.** Earlier drafts
carried one — *"a block whose whole text is one handle is an assignment"* — to
stop ~6,700 block labels becoming self-citations. Reading the corpus as djot
retires it entirely: **an assignment is an AST `id`, a citation is text.** The
reader separates them, so any handle appearing in a `Str` is a citation, with no
exception to state, test or get wrong. This is the single biggest simplification
the measurement bought.

The `{@x}` era failed because it regexed `plain_text()`, which *does* fold
`params["text"]` in (`records.py:598-599`). Walking `content` for `Str` nodes
instead of flattening is the whole fix, and it mirrors `_links()` exactly.

### The syntax has four forms, not one

Counted in the real v0.1-derived material already in this repo:

| form | count |
|---|---|
| `{#8hex}` | 240 |
| `{#8hex+++}` — the expansion marker | 13 |
| `{#8hex@ver}` — the version pin | 2 |
| metasyntactic: `{#handle}`, `{#uuid:hash}`, `{#xxxxxxxx}`, `{#...}` | 5 |

The last row must **not** become citations.
`tests/corpus/compost-corpus/curated/edge-cases/handles.md` is a curated fixture
enumerating every one of these, including handles inside code spans and fences.
**So this parser is testable today**, against real bleached v0.1 prose, without
the private corpus — the migration is blocked on that material, the parser is not.

The `+++` form is not rare in what actually survives ingest: the first citation
in the first file measured is `{#44670084+++}`. The pattern must cover all four
forms, not just the bare one.

### The resolver must ignore its own placeholders

After one build with no dictionary present, every legacy handle already has an
`alias` node naming an `unresolved_citation`. A second build looking up aliases
by value would find those alongside the real target.

> **Follow only `names` edges whose destination is not an `unresolved_citation`.
> If more than one real target remains, mint nothing and report the ambiguity.**

Without this rule, each pre-dictionary build adds another candidate and growth is
quadratic in build count rather than linear. Sabotage-verify it.

### This is where a placeholder can actually resolve

Unlike `uuid-link`, a `kg-8hex` placeholder is resolvable — because alias nodes
for legacy handles arrive from **outside**, not from digesting.

1. `compost layer citation --by kg-8hex` before the alias file is in place →
   placeholders for every `{#a3f2b1c4}`.
2. The alias file is added.
3. Rebuild → the builder finds the alias and mints a real `cites` edge to the
   real block.

The old placeholder and its edge remain, as a record of a moment when it did not
resolve. Nothing is retracted.

### Hand-written graph files are allowed — a rule change

`CLAUDE.md` says *"Do not hand-edit `.compost/graph/`. Write through `compost
digest`."* **That rule is relaxed here, deliberately**, and the reasoning belongs
in `docs/decisions.md` rather than being quietly broken:

The records `digest` writes are produced by ordinary Python. A migration script
that produces valid JSONL is not different in kind. `Store.load()` does not care
who wrote a file, and **`check` is the actual enforcement of every invariant** —
not the identity of the writer. A generated file that passes `check` is
indistinguishable from one `digest` wrote.

So the alias dictionary is produced by a purpose-built script into its own
directory and copied under `graph/`. There is no `compost layer alias`
subcommand, and there will not be one.

**The relaxation covers deletion too, and has to.** `layer` writes exactly one
file per run and nothing removes it, so a base's records only ever grow — and the
only remedy the design offers is deleting a graph file, which the unrelaxed rule
forbids. The safe form is narrow and worth stating: **delete a whole file that one
`layer` run wrote; never edit a line inside one.** Whole-file deletion is a clean
inverse of a whole-file write. Anything finer is hand-editing and stays banned.

**What is lost, and why it does not matter here:** the dictionary's bytes never
enter `storage/`, so the base does not hold that source. But **the alias records
*are* the dictionary in full** — nothing is recoverable from the file that is not
already in the graph. To keep the trail, every record the script writes carries
`created_at`, `tool_version` and the generating script's name.

**What this raises:** `check` becomes the only gate, and it does not validate
that a node's `type` is a known one. A typo'd `"alais"` node passes if it has the
right parent count. This is knowingly not fixed — a central contract mechanism is
planned well after this window and will cover it.

### The migration — a procedure, not a release

**The material is private but measured.** The v0.1 corpus was removed from this
repository's history, not merely deleted, and is kept privately — 23 `.dj` files
holding 6,741 handles. Everything in this section is measured against those files;
nothing here is a guess about their shape any more.

No version number, because it changes no code.

**There is no `--as=djot` route and there will not be one.** Pandoc reads djot,
and `--as=pandoc-ast` takes what it produces:

```bash
pandoc -f djot -t json old.dj > old.json
compost digest --as=pandoc-ast old.json
```

Steps:

1. `pandoc -f djot -t json`, then `compost digest --as=pandoc-ast`.
2. A one-off external script builds the dictionary from the **digested graph** —
   every block whose `attr` id is 8 hex characters maps that handle to the block's
   guid — and emits `alias` nodes and `names` edges as JSONL. Copy the file under
   `graph/`. It never becomes part of the CLI.
3. `compost layer citation --by kg-8hex`.
4. Commit the dictionary script and its output as ordinary files.

**The collision check is already done.** 6,741 ids, 6,741 distinct — zero
duplicates across the whole corpus. That was listed as a thing to confirm before
minting anything; it is confirmed.

**Provenance.** Every migrated document records `route: "pandoc-ast"`, so the base
will not say these came from djot. Put the exact pandoc invocation, and the
generating script's name, into the `alias` records the script writes.

**Back up the corpus before running any of this.** It is the only copy of 6,741
handles' worth of history, and the migration is the first thing that will read it
in anger.

**Acceptance:** every handle resolvable before the migration resolves after; the
count of prose-quoted example handles recorded rather than silently absorbed; and
the recall of the citation match measured, not assumed — the first draft of this
section assumed it and was 42% wrong.

### The residual risk, which cannot be engineered away

A conversation that says in **prose** — not code — "handles look like
{#a3f2b1c4}", where that hex string is also a real handle, becomes a real edge.
Nothing structural excludes it. It is why the legacy scheme stays opt-in and
never the default. Count the cases once when the dictionary is built: a handful
is a footnote, forty is a finding.

### HTML backlinks

Deferred here from v0.2.4. v0.1 had *Referenced by* and v0.2 lost it.
**Open design question:** per block, or once per document. Per block is what the
citation means; per document is what fits the page. The view must distinguish an
exact citation from a recovered one — which is why `Graph.linked` keeping `by` is
a v0.2.4 item.

**Backlinks dedup in the view**, by `(source, destination, by)`. Two builds of the
citation layer put every citer in the base twice, and a page listing the same
citer twice is noise rather than information. Deduping in a view breaks no rule —
views are derived, disposable and never re-ingested — and it touches no records,
so the accumulation the dedup design needs to study stays intact underneath.

---

## v0.2.6 — the conversation loop

### What this is not

**It is not an alternative to the transcript importer.** That route exists, is
lossless, follows subagents, and stays exactly as it is. This is a *different*
source arriving by a *different* route for a *different* purpose: the
round-by-round exchange read in a browser instead of a TUI. They describe the
same conversation and will one day be joined by a `duplicates` layer. **That join
is not built here.**

### Why the envelope is a legitimate source

An earlier draft of this reasoning called digesting `claude --print
--output-format json` "filtering at import". **That was wrong**, and the
distinction is worth recording. Filtering would be keeping only `result`.
Digesting the *whole* envelope — `result`, `session_id`, `total_cost_usd`,
`modelUsage`, `permission_denials`, `terminal_reason` — keeps everything the file
says. The rule is about not discarding what a source holds, never about a source
having to be the largest available.

### Two consequences that make this shape right

- **Storage is linear.** Each round is one small envelope and one small note.
  Forty rounds is eighty small files. The cumulative-file problem was entirely an
  artefact of re-digesting a growing transcript.
- **Handles never move.** A note digested in round 3 is never digested again, so
  the handle cited stays the handle on the page in round 20.

**So re-import identity leaves the critical path.** It remains a real gap for the
transcript route (`TODO.md`) and blocks nothing.

### What has to be built

1. **A route for the envelope.** Keeps every envelope key in params on the root,
   **and** runs `result` through the markdown reader so the answer is made of
   addressable blocks. Without the second half you cannot cite claude's
   paragraphs, which is the whole point. **Promote `session_id` to a top-level
   param** — it is the join to the transcript and it is free at import.
2. **Conversation edges arrive by a digest route.** The wrapper knows every guid
   involved; it writes a small file naming them, and `compost digest` ingests it.
   This reuses `digest`'s immutability and blob-store guarantees instead of
   inventing parallel ones, and "a fact arrived from outside" is what `digest`
   means. It is a route whose input names guids from *other* documents — a shape
   no route has today.
3. **The conversation edge cannot be `contains`.** `check` requires a root to have
   zero parents (`src/records.py:472`). It needs its own edge type, and
   `render_all` must consult it to decide those roots get no page of their own.
   Precedent is exact: `launched` already does this for subagent transcripts.
4. **Append-only comes free.** Nothing is ever rewritten; each round is a new
   immutable document. v0.1 needed explicit append verification; this shape makes
   it a property.
5. **The wrapper**, outside the CLI. `nvim` on a nameless file, digest, layer,
   render, pipe, digest the response, layer, render.

### The loop, end to end

```
f=/tmp/round-$(date +%s).md          # a fresh name every round — see below
nvim "$f"
compost digest --as=notes "$f"       # read the view path back from this output
compost layer citation
compost render
cat .compost/views/default-djot/<stem>.dj | claude --print --output-format json > r.json
compost digest --as=claude-code-response r.json
compost layer citation
compost render
```

**The filename must be unique per round, and the wrapper must read the view path
from `digest` rather than guessing it.** Reusing one name breaks at round two:
`view_names()` (`src/views.py:372-375`) breaks a stem collision by appending the
root's handle **to both documents**, so `xxx.dj` stops existing and each round's
view is named `xxx-<36-char guid>.dj`. A loop that `cat`s a guessed stem reads a
file that is no longer there — and the failure is a missing file, not a wrong
answer, so at least it is loud.

---

## v0.2.7 — a graph view

### The property that earns a new dependency

`environment.yml` says *no pip dependencies and no system dependencies beyond
pandoc*. Graphviz is worth relaxing that for, and the reason is specific:

**DOT is a deliverable on its own, so the binary stays optional.** The command
always writes the DOT — text, from records. If `dot` is on PATH it also writes the
SVG. If not, the DOT is still there, readable by an agent and renderable later on
any machine that has graphviz.

So the line narrows rather than breaking: **no *required* system dependency
beyond pandoc.** That is exactly what D3 cannot do — a vendored blob is all or
nothing with no text form. And it is why mermaid's advantage evaporates: also
text, but its renderer needs the node ecosystem or a 3 MB browser blob.

Other reasons: one generator serves the agent path and the human path; agents
write DOT at least as fluently as mermaid; `dot` for hierarchical layout and
`sfdp` for the thousands-of-nodes case, one flag apart; and it is thirty years
old and finished.

### It is its own subcommand, not part of `render`

```
compost graph [ROOT]        whole base, or one root's subgraph
```

**Not a fourth view.** v0.2.6 puts `compost render` in the inner loop — twice per
conversational round — and v1 of this draws every node in the base, which for a
single transcript is thousands. Folding an unbounded graphviz layout into the
command the daily loop runs most is a cost nobody asked for on every turn.

It also keeps two hard-coded lists out of trouble: `render_all`'s stale-file
sweep names three view directories explicitly (`src/views.py:420`) and so does
`main()`'s summary loop (`:461`), so a fourth directory would accumulate orphans
and go uncounted until both are edited.

`ROOT` optional resolves the contradiction an earlier draft carried, which
described both a per-document `default-dot/NAME.dot` and "a walk over every node
in the base" three lines apart. Whole base by default; one root when named.

### v1 draws everything

No collapsing policy, no filters. A walk over `g.nodes` and every edge, one DOT
line each, `subgraph cluster_` per root for legibility.

This makes the release **smaller**, not larger — the whole design difficulty was
the collapsing policy, and "draw everything" has none. It is also the honest
first move: the question is *what does compost actually store*, and a filtered
picture cannot answer it.

Expectation set now: a session transcript is thousands of nodes, so the first
picture of a real base will be unreadable **as a picture** and useful **as
evidence**.

This is also where `unresolved_citation` nodes first become visible — they are
`UNCONTAINED`, so no prose view shows them.

### DOT is a text surface, not just an input

A `compost tree` subcommand was proposed and dropped: the DOT file already is the
text inspection tool — agent-readable, pasteable, greppable, and able to
represent arbitrary graph structure rather than only trees.

Consequence to write down before someone optimises it away: **DOT output must
stay readable to a person.** Indentation, `subgraph cluster_` grouping, honest
labels. Minified for the layout engine, it serves half its purpose.

### Measured — graphviz 14.1.2, against a real base

**The guid reaches the picture. Click-to-copy works.** An explicit `id=` on a DOT
node becomes the SVG's `<g id="…">`, and on a real 1,910-node base all **5,051
guids survived, none missing**. Edges carry ids by the same mechanism. The SVG is
self-contained — no scripts, no external images, no fetched fonts — so it is safe
under `compost serve`, which is loopback-only and offline.

**But the guid is not in the SVG bytes, and a naive test will say the feature is
broken.** Graphviz escapes every hyphen, because it also emits `<!-- name -->`
comments where `--` is illegal:

```
emitted : id="d826c4dd&#45;eb36&#45;4da9&#45;acab&#45;000000000007"
grep    : 0 hits for the plain guid
parsed  : d826c4dd-eb36-4da9-acab-000000000007   ← exact, all 500 of 500
```

So **assert through an XML parser, never with a substring match.** The earlier
claim that "a guid with hyphens goes in verbatim" is right going *in* and wrong
coming *out*. `href` is the one attribute not escaped.

Two smaller findings: `<title>` holds the DOT node *name*, not its id — so name
the node the guid as well if the native hover tooltip should show it. And
`tooltip=` changes the emitted element structure, wrapping the shape in an `<a>`
inside an extra `<g id="a_…">`, which introduces near-duplicate ids. Avoid it.

### Measured — and `dot` cannot be the engine

This is the finding that changes the release. On graphs shaped like compost's —
a `contains` tree plus a `next` chain — `dot` collapses far below the sizes this
plan assumed:

All six engines on one 500-node graph shaped like a `contains` tree plus a `next`
chain, 180 s ceiling:

| engine | what it does | time |
|---|---|---|
| **`twopi`** | **radial tree, root at centre** | **0.13 s** |
| `sfdp` | multilevel force-directed | 0.18 s |
| `neato` | spring model | 0.40 s |
| `fdp` | force-directed | 6.21 s |
| `circo` | circular | **killed at 180 s** |
| `dot` | layered hierarchy | **killed at 180 s** |

And at scale, on the same shape:

| nodes | edges | `twopi` | `sfdp` |
|---|---|---|---|
| 5,000 | 9,997 | 0.29 s / 4.7 MB | 0.98 s / 4.6 MB |
| 20,000 | 39,997 | **0.65 s** / 19 MB | 4.46 s / 18.8 MB |

**`dot` stops being usable between 250 and 500 nodes** — below a single document.
`docs/decisions.md` alone digests to 434 nodes. An earlier draft said `dot` and
`sfdp` were "one flag apart", to be chosen per scale; that underestimated by an
order of magnitude.

> **`compost graph` defaults to `twopi`**, not `sfdp`. It is the fastest measured
> — 7× `sfdp` at 20,000 nodes — *and* it is the only fast engine whose model
> matches the data: compost's structure is a forest of `contains` trees, and
> `twopi` lays out a rooted tree radially. `sfdp` was the first answer only
> because it is the usual reply to "too big for `dot`"; it produces a
> force-directed blob of something that is not a blob.
>
> `sfdp` stays available for when cross-document `cites` edges dominate and the
> graph stops being tree-shaped. `dot` stays available for a small scoped
> subgraph, where hierarchy is worth the wait.

**Caveat on the measurement:** the test graphs are pure tree-plus-chain. A base
with a dense citation layer is no longer a tree, and `twopi`'s advantage is
untested there. Re-measure when there is a real base with many `cites` edges —
today's has five.

**And output size, not layout time, is the real ceiling.** One corpus base
renders to **58 MB of SVG**, handed to a browser over loopback. That arrives
*before* any of the collapsing-policy questions this release deferred — so "v1
draws everything" survives for a document and does not survive for a base, and
the first filter will be forced by file size rather than by legibility.

### Costs, accepted knowingly

- **231 MB and 51 packages**, measured, not the 50–100 MB estimated. That is
  against pandoc's single binary, and it is the strongest argument for keeping
  the DOT output useful on its own so the binary stays optional.
- **A second tool whose version silently changes output.** `CLAUDE.md` already
  documents this trap for pandoc. Graphviz gets the same treatment on day one:
  pinned in `environment.yml`, producing version recorded on the view.
- **`./tests/clean-room.sh --with-agent` becomes mandatory before the tag**, since
  `environment.yml` changes and the contributor path is what that gate tests.

---

## v0.2.8 — a query layer

Last, and it earns the position: by now there are citations, aliases,
placeholders and conversation edges — an actual graph to query.

**DuckDB, reading `.compost/graph/**/*.jsonl` in place.** Nothing is
materialised, so nothing can go stale and there is no cache to invalidate.

**It is a view in the same sense `views/` is — derived, disposable, rebuilt from
the records — but it produces a different artifact and the two must not blur.**
`layer` writes derived *records* into the graph. DuckDB writes nothing at all.
Nobody should later "improve" this into a materialised store.

**Why SQL before Cypher.** Not because Cypher is bad at graphs. An embedded graph
database requires a **declared schema** before you have learned what a node is,
and `params` is an open object with 35 distinct keys precisely because compost has
not decided. `read_json` needs no schema and no load step; in-memory mode does not
change that, because in-memory is not the same as no-load. The list of path
questions SQL made painful *is* the requirement document for a graph database.

**The test is the point:** every health assertion expressed twice, in Python and
in SQL, required to agree on every fixture base. Sabotage-verifiable in both
directions.

**The dedup divergence is real, and it was constructed rather than argued.**
Measured on duckdb 1.5.5, by copying one graph file to a second filename inside a
base so a record literally appears twice:

```
base      Store.load() = 5051   SQL count(*) = 5051   agree
dupbase   Store.load() = 5051   SQL count(*) = 5082   DISAGREE  (+31 = the copied file)
```

`Store.load()` deduplicates byte-identical records (`src/store.py:159`); SQL over
the raw files does not. **And `compost check` calls the duplicated base perfectly
healthy** — *1910 nodes, 3141 edges, 0 problems* — so "scope the agreement test to
bases with no cross-file duplicates" has no mechanism to enforce its own
precondition. Either read a `load()`-produced snapshot on the SQL side, or state
the limit and accept that nothing detects when it is violated.

> **Reject `count(DISTINCT guid)` as the bridge, in writing, before someone
> reaches for it.** It reconciles the duplicate case and *hides a guid conflict* —
> two different records under one guid, which is the first thing `check` exists to
> catch. Measured: on a base with such a conflict, `check` reports 2 problems
> while `DISTINCT guid` reports agreement.

**The read shape: the predicted failure does not happen, but not for a reason
worth relying on.** `read_json` with no schema works, and nothing is dropped —
`params` infers as `MAP(VARCHAR, JSON)` and all 39 keys are reachable. Node and
edge lines unify with no `union_by_name`. 88k records materialise in **0.25 s**.
So `columns={… 'params': 'JSON'}` is **not** required, and planning as though it
were would be over-fitting.

But the safe MAP is chosen only because `params` is heterogeneous *enough*:
inference flips to `STRUCT` below roughly 30 keys, and compost sits near that
boundary — reading the same records one file at a time infers `STRUCT`. **When it
is a STRUCT, keys past the sample vanish silently**, columns included. The lever
is `map_inference_threshold=0`, which forces the lossless MAP with one argument
and no column list to maintain.

Three things the earlier draft did not anticipate, all of which change how the
queries get written:

- **`content`, not `params`, is the unstable inferred type** — `JSON[]` on one
  base, `STRUCT(c JSON, t VARCHAR)[]` on another. The design attention went to
  the wrong field.
- **`->>` raises inside a `WHERE` that also filters on `record`.** The most
  natural query against this schema fails with a cast error in both read modes.
  Use `json_extract_string(params, '$.x')` in predicates.
- **`guid`, `source` and `destination` infer as `UUID`, `created_at` as
  `TIMESTAMP`** — so the two sides of the twin assertion compare different types
  unless one is cast.

**This is also where the accumulated duplicates finally become legible** — group
by `content_hash`, by `created_at`, by `tool_version`, and the pattern that a
dedup design needs becomes visible instead of theoretical.

**Explicitly not in scope:** revamping `check` (the gate must stay
dependency-light, since `render` refuses when it fails), a `query` subcommand
(decide after `docs/queries.md` shows which queries are worth shipping), and the
`check` → `health` rename, which belongs with the severity change that makes the
new name mean something.

Skip cleanly when `duckdb` is absent, using the existing `tests/tier.py` pattern,
so a bare environment still shows a full board.

---

## Risks accepted without mitigation

Every item here was found, considered, and **deliberately not fixed**. Each is a
consequence of the two governing constraints. They are listed so that hitting one
is a known cost rather than a discovery.

**Nothing tells you a layer is out of date.** Digest a document that cites an
older block, skip `compost layer citation`, and the edge does not exist. `check`
is clean, `render` renders, and the page shows no backlink. The correct sequence
is the operator's responsibility. *Mitigation deliberately declined: an earlier
design detected this and it produced four unescapable states.*

**`lookup` will under-report on an unbuilt layer.** It is not gated by `check`,
by design, so on a base where the citation layer has not been rebuilt it prints
"nothing cites this" when something does. No warning is printed. Same reason.

**Builder drift is undetectable.** Staleness of any kind is not tracked. Change
the citation parser in a later release and every existing base keeps edges built
by the old logic, with nothing anywhere saying so. `tool_version` is on every
edge, so this becomes *queryable* at v0.2.8 — but nothing detects it, and no
release will re-run builders for you.

**Rebuilds multiply.** Two runs of `compost layer citation` produce two complete
sets of citation edges, two sets of placeholders, and two sets of aliases naming
them. Nothing removes any of it, and there is no `drop`. The only way to reduce a
base is to delete a whole graph file that one `layer` run wrote — which the
relaxed rule now permits explicitly, because otherwise the sole remedy for the
tool's intended accumulation would be an operation the project forbids.

**One alias value can name several nodes** — two builds, two aliases, two
placeholders. `lookup` returns all matches. Two kinds exist and only one is
dangerous: *benign* is one value naming N `unresolved_citation` nodes, N stand-ins
for one missing thing; *dangerous* is one value naming two different real blocks,
which would mean the dictionary is wrong. They are distinguishable by the target's
node type.

**A bare 8-hex `lookup` is ambiguous in a migrated base.** `decisions.md` records
why the prefix resolver was removed: a short string that resolves for a tool is a
dead anchor for a person, and uniqueness degrades as the base grows. v0.2.5 makes
`compost lookup a3f2b1c4` succeed again through aliases, and in a migrated base
such a string could be both a legacy alias value and a prefix of a real guid.
`lookup` names the scheme that answered, which makes the ambiguity visible rather
than resolving it.

**A `uuid-link` placeholder resolves only when records arrive from outside the
tool.** Every digest mints fresh UUIDv4s, so digesting more material never
resolves one. But guids do arrive from outside: v0.2.5 blesses copying externally
produced JSONL into `graph/`, `graph/` is committed so a checkout or restore moves
guids in and out, and whole-file deletion is the sanctioned way to shrink a base.
An earlier draft of this list claimed such a placeholder *can never* resolve,
which the same roadmap falsifies three sections later. Placeholders are mostly
forensic — hallucinated guids, pastes, typos, documentation examples — and
occasionally pending.

**A citation to a not-yet-present block is recorded one hop away from where a
reader looks for it.** The `cites` edge points at the placeholder and is never
retracted, so a rebuild after the target arrives adds a second, direct edge beside
the first. `lookup` compensates by following the reverse path; any other consumer
— a view, a query, the graph picture — sees both and must decide what to do about
it. Nothing collapses them.

**`content_hash` does not reach unresolved citations.** A placeholder gets a fresh
guid every build, so two builds' `cites` edges into placeholders for the same
missing handle differ in `destination` and hash differently. For the records that
multiply fastest, the hash finds nothing.

**Documentation examples inflate the placeholder count.** A `[-](#…)` written in
running prose to demonstrate the syntax is a citation by every structural rule and
becomes a placeholder. Only backticks and code blocks are excluded. The first
build's number will look alarming and should not.

**`check` does not validate node types.** A typo'd type passes if its parent count
is right. This matters more now that hand-written graph files are permitted. Not
fixed: a central contract mechanism is planned well after this window.

**`Graph._next` is layer-blind.** `src/records.py:282` keys next-edges by source
alone, so a node that is the source of two `next` edges silently loses one. Safe
today because `pandoc-ast` and `session` never overlap, and safe in v0.2.6 because
roots are nobody's sibling — but safe *by accident*. **Revisit when the
conversation layer lands**, which is the third user of a shared edge type.

**`content_hash` proves nothing about node duplicates.** It exists on edges and on
nodes that carry `content`; the transcript node types have none, and neither do
`alias` or `unresolved_citation`. Grouping those needs a param comparison, not a
hash.

**No concurrency control anywhere.** Two `compost layer` runs at once produce two
sets of records. `Store.write` is atomic per file, so nothing is corrupted, but
nothing is coordinated either.

---

## Open questions carried forward

- **Backlink placement in the HTML view** — per block or per document (v0.2.5).
- **The route name for the envelope.** `claude-code-response` is a placeholder.
- **The conversation edge type name.** `includes` was proposed; not settled.
- **How `represents` and `duplicates` relate to `alias`** — three ways of saying
  two records are about one thing.

**Nothing in this document is now waiting on a measurement.** That is deliberate:
three separate claims here had already been wrong because they were argued from
constructed samples rather than measured against real material — the djot reader's
treatment of handles, the citation match's recall, and the storage cost. Each was
labelled *Verified* or *Measured*, and the label is what stopped anyone looking
again. Every remaining number was taken from a real base or a real corpus.

*Closed by measuring the v0.1 corpus:* the `.dj` files' shape, the ingest route,
the handle-collision check (6,741 distinct, zero duplicates), and the assignment
rule, which turned out not to be needed at all.

*Closed by spiking graphviz and duckdb:* the SVG `id` question — it survives, and
hyphens are escaped in the bytes; `dot`'s usable ceiling — between 250 and 500
nodes, so `sfdp` is the default and not an option; the `read_json` shape — no
schema needed, `MAP` not `STRUCT`, and `columns=` unnecessary; and the SQL-versus
-`load()` dedup divergence, constructed and confirmed at 5,051 against 5,082.

## Beyond this window

- **A dedup design**, written from the accumulation patterns v0.2.8 makes visible.
  Aliases are one mechanism it can use: collapse two nodes by giving the survivor
  the loser's name, so no citing text ever has to change.
- **A `duplicates` layer** between transcript turn text and conversation round
  records. Hash equality will not find these — the same prose sits bare in one and
  wrapped in notification envelopes in the other.
- **Filters for the graph view**, argued from a real hairball rather than in
  advance.
- **Promises and placeholders for async multi-agent work.** The
  `unresolved_citation` node is the first instance of "something will be here";
  the general form needs a real async use case to design against.

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
| **v0.2.5** | `tools/`, the legacy handle scheme — then the v0.1 migration runs, as a procedure |
| **v0.2.6** | the conversation loop |
| **v0.2.7** | a graph view: DOT always, SVG when graphviz is installed |
| **v0.2.8** | a query layer over the records |
| **v0.2.9** | the view a person can actually read — the v0.1 affordances, restored |

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

**`layer` is the tool's second writer to `graph/`, and it does not read what it wrote
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
| handles assigned in the text, outside code fences | **6,601** |
| of those, surviving `pandoc -f djot` untreated | 5,834 — **767 dropped**, see the dry run |
| distinct ids after `tools/dj_prepare` — the collision check, done | **6,601, zero duplicates** |
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

**The dictionary is a direct read of the AST** — 6,601 `(id, block)` pairs, no
text matching, no positional alignment, no folding rule, nothing fuzzy.

### `--by kg-8hex` — shipped in v0.2.5

**Built, and re-measured through the reader rather than the pattern.** Over
`tests/fixtures/notes/` plus the fetched corpus, `records.legacy_handle_refs`
finds **242 occurrences where whole-`Str` equality finds 144** — 98 of them,
40%, lost in silence. The design-time figures below were taken over a smaller
set and reached the same conclusion; both are kept, since the point of the
entry is that the first draft got it wrong by not measuring at all.

`tests/test_layer.py` grew from 8 properties to 16. Two of the new ones passed
their first sabotage and had to be rewritten: one measured the regex instead of
calling the reader, the other ran on a base carrying no legacy handles.


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

### The dictionary is written by a script, which needs no special permission

**Anything may write records** — valid JSONL, one per line, under `graph/`.
`digest` and `layer` are two writers, not the only two, and `Store.load()` does
not care who wrote a file. `check` is the enforcement, not the identity of the
writer. See `docs/decisions.md`, "Anything may write records; `check` is the
gate", which also states the trust assumption this rests on and names the
grammar validation layer that will eventually replace it.

An earlier version of this section framed that as *relaxing* a rule in
`CLAUDE.md`. It was not a relaxation; the rule had described a habit as though
it were a mechanism.

So the alias dictionary is produced by a purpose-built script into its own
directory and copied under `graph/`. There is no `compost layer alias`
subcommand, and there will not be one.

**Deletion needs saying explicitly.** `layer` writes exactly one file per run
and nothing removes it, so a base's records only ever grow, and the only remedy
the design offers is deleting a graph file. The safe form is narrow: **delete a
whole file that one `layer` run wrote; never edit a line inside one.**
Whole-file deletion is a clean inverse of a whole-file write. Anything finer
edits an immutable record and stays wrong no matter who does it.

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
holding 6,601 handles. Everything in this section is measured against those files;
nothing here is a guess about their shape any more.

No version number, because it changes no code.

**There is no `--as=djot` route and there will not be one.** Pandoc reads djot,
and `--as=pandoc-ast` takes what it produces:

```bash
pandoc -f djot -t json old.dj > old.json
compost digest --as=pandoc-ast old.json
```

Steps:

1. `python3 -m tools.dj_prepare CORPUS OUTDIR` — without it 767 handles are
   lost silently — then `pandoc -f djot -t json` and `compost digest
   --as=pandoc-ast`. `--verify` asserts every assigned handle survived.
2. `python3 -m tools.v01_dictionary BASE` builds the dictionary from the
   **digested graph** — every block whose `attr` id is 8 hex characters maps
   that handle to the block's guid — and writes `alias` nodes and `names` edges
   straight into `graph/`. `--dry-run` reports the count without writing, which
   is how a dictionary short by 767 is caught before anything is minted. Run it
   from the checkout: `tools/` is importable there and installed nowhere, so
   pass the base as an argument rather than running from inside it. It is not a
   subcommand and will not become one.

   **Only cited handles, by default — 152 rather than 6,601.** The corpus
   assigns 6,601 handles and cites 159 of them, so a full dictionary is 13,202
   records answering about two hundred questions. Measured both ways against
   the real corpus, resolution is *identical* — 206 cites, 7 placeholders — and
   the base is 6,449 nodes and 4 MB smaller.

   Nothing is lost by leaving the rest out, which is why this is the default
   rather than a flag: **the handle is on the block itself**, in
   `params["attr"][0]`, put there by `digest` and never removed. The dictionary
   is an index over data that stays in the base, so `--all` rebuilds it whole
   at any time. What it costs is that the filter is a snapshot of what was
   cited when it ran — import a document later citing a handle nobody had cited
   before and it will not resolve until the dictionary is rebuilt, and nothing
   will tell you. Consistent with everything else here: the tool does not hold
   your hand.
3. `compost check`. This is the gate for a generated graph file, and it is not
   optional — see `docs/decisions.md`, "Hand-written graph files are allowed".
4. `compost layer citation --by kg-8hex`.
5. Commit the dictionary's output; the script is already in `tools/`.

**The collision check is already done.** 6,601 ids, 6,601 distinct — zero
duplicates across the whole corpus. That was listed as a thing to confirm before
minting anything; it is confirmed.

**Provenance.** Every migrated document records `route: "pandoc-ast"`, so the base
will not say these came from djot. Put the exact pandoc invocation, and the
generating script's name, into the `alias` records the script writes.

**Back up the corpus before running any of this.** It is the only copy of 6,601
handles' worth of history, and the migration is the first thing that will read it
in anger.

**Acceptance:** every handle resolvable before the migration resolves after; the
count of prose-quoted example handles recorded rather than silently absorbed; and
the recall of the citation match measured, not assumed — the first draft of this
section assumed it and was 42% wrong.

### The dry run — done before v0.2.5 was tagged

The whole procedure was executed against the real corpus, read-only, into a
scratch base outside the repository. Not the migration: no base was kept. This
is the acceptance test this section asks for, run **before** tagging, because
two earlier drafts of the parser were argued from constructed samples and both
were wrong.

Run twice: once as specified, which is how the reader defect below was found,
and again with `tools/dj_prepare` in front of pandoc. The second column is the
procedure that will actually run.

| step | as specified | with `dj_prepare` |
|---|---|---|
| `pandoc -f djot -t json`, 23 files | **23 parsed, 0 failed** | 23, 0 failed |
| `compost digest --as=pandoc-ast` | 10,973 nodes, **0 problems** | 12,466 nodes, **0 problems** |
| 8-hex ids reaching the AST | 5,834 — **767 short** | **6,601**, zero collisions |
| the dictionary | 5,834 aliases | **6,601 aliases** |
| `compost layer citation --by kg-8hex` | 206 cites, 0 ambiguous | 206 cites, 0 ambiguous |
| — resolving to a real block | 110 — **53%** | **197 — 96%** |
| — into a placeholder | 96, across 74 handles | **9, across 7 handles** |
| `compost check` afterwards | **0 problems** | 19,081 nodes, **0 problems** |
| built three times | identical every run | identical every run |

The record count matching the AST count in both runs is what proves `digest`
loses nothing: the 767 were already gone before compost saw them.

**206 matches this section's predicted count exactly.** So does 159 distinct
cited handles, the figure `docs/migration.md` has carried since v0.1.

**The block count did not, and the first correction was also wrong.** The
recorded figure was 6,741; the dry run emitted 5,834 and this section briefly
said the corpus "holds 5,834". It does not. 5,834 is what *pandoc emits*. The
corpus assigns **6,601** handles outside code fences, and the gap was a defect,
not a counting error — see below. A number relabelled without asking why it
moved is the same failure as a number never measured.

### The reader drops a list item's handle — 767 of them

`pandoc -f djot` **silently drops a block attribute at the start of a list item
when a blank line separates it from the item's content.** The v0.1 canonizer
wrote every handled list item that way:

```
- {#1221ba74}

  Volume. One session in that directory is 2.8 MB, because …
```

The text survives; only the identity is lost, so nothing looks wrong anywhere.
Every one of the 767 lost handles has this single cause — no second pattern
exists in the corpus — and 74 of the 159 distinct cited handles were among them.

`tools/dj_prepare.py` deletes that one blank line on a **copy**. The handle then
becomes a `Div` wrapping the item's content, which is what every other handled
block already is, so the result is more uniform rather than less.
`tests/test_dj_prepare.py` asserts the defect against the live pandoc, so the
day a release fixes it the suite says the repair can be retired.

**This repairs pandoc's input, never its output.** `CLAUDE.md` forbids the
latter because patching an emitted AST breaks the round-trip by construction.
This runs before pandoc reads anything and the round-trip is untouched.

| | before | after |
|---|---|---|
| handles surviving | 5,834 | **6,601** |
| citations resolving | 110 / 206 — 53% | **197 / 206 — 96%** |

**96% is the ceiling, and the remaining 9 are genuinely unresolvable.** Six
handles are cited up to 17 times each and assigned nowhere in the 23 files; one
appears only inside quoted JSON in a code fence. They are what
`unresolved_citation` is for — and the honest count of it is 9, not 96.

### `commonmark_x` was measured, and rejected

It reads `{#id}` too, so it would need no repair at all — worth testing rather
than assuming, since the reader question had already been answered wrongly twice.

| reader | ids | citations resolving | turn divs | `:::` left as text |
|---|---|---|---|---|
| djot | 5,834 | 110/206 — 53% | 1,461 | 2 |
| **djot + `dj_prepare`** | **6,601** | **197/206 — 96%** | **1,461** | **2** |
| commonmark_x | 6,166 | 207/207 | 1,291 | **4,251** |

**Its 100% is inflated.** It mints ids for handles that are assigned nowhere in
the corpus — as empty inline `Span`s — so those citations resolve to nothing
real. All seven of the provably-undefined handles get one. And it leaves 4,251
`:::` fences as literal text while losing 170 turn divs, which is the structural
objection this document raised against the markdown reader, confirmed by a
different mechanism than the one predicted. A 96% that is true beats a 100% that
is partly fabricated.

**The resolver rule holds at scale.** Three consecutive builds each produced
206 cites and 110 resolutions, with 74 placeholders added per run and never
consulted by the next. Accumulation is linear in build count, as designed.

**Whole-`Str` equality would have found 127 of the 206** — 38.3% lost, matching
the 40% measured on the test material.

### The residual risk, which cannot be engineered away

A conversation that says in **prose** — not code — "handles look like
{#a3f2b1c4}", where that hex string is also a real handle, becomes a real edge.
Nothing structural excludes it. It is why the legacy scheme stays opt-in and
never the default. Count the cases once when the dictionary is built: a handful
is a footnote, forty is a finding.

### HTML backlinks — moved out, to after v0.2.8

Deferred into this release from v0.2.4, and deferred out of it again: **nothing
depends on them.** They are a view feature in a release otherwise about naming,
and `Graph.linked` already keeps `by`, so every fact a backlink needs is being
recorded whether or not anything draws it yet. The entry now lives under
*Beyond this window* with its open question intact.

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

### The envelope, measured

Written from a remembered shape until 2026-08-26, when one was finally
captured: `echo … | claude --print --output-format json`. **21 top-level keys,
not the six this section named.** All six named are real — nothing here was
wrong — but the design was working against a third of the surface.

```
is_error  duration_api_ms  num_turns  stop_reason  session_id  total_cost_usd
usage  modelUsage  permission_denials  terminal_reason  fast_mode_state
fast_mode_disabled_reason  subtype  api_error_status  result  ttft_ms
ttft_stream_ms  time_to_request_ms  type  duration_ms  uuid
```

Verified against `params` directly: **nested dicts survive** (`usage`,
`modelUsage`), **JSON `null` survives** (`api_error_status`), and all 21 keys
round-trip. So "keep every envelope key" needs no new machinery.

**Two things to decide before writing the route:**

- **The envelope has its own `uuid`**, unrelated to the node's guid. Putting
  every key in `params` verbatim means `params["uuid"]` is the *envelope's*
  identifier while `guid` is the record's — one word, two meanings, in the
  same record. Rename on the way in and the route stops being a faithful copy;
  leave it and something will eventually read the wrong one.
- `result` here was the bare string `pong`. In a real round it is markdown, and
  it is the half that has to go through the reader.

### What has to be built

**Simplified 2026-08-26.** Two of the five items below were solved by choosing
a different shape rather than by building anything, and the reasoning is kept
because both looked necessary until the constraint was read precisely.

1. **A route for the envelope, `--as=claude-code-response`.** Keeps every one of
   the 21 envelope keys in `params` on the root — verified to survive, nested
   dicts and `null` included — **and** runs `result` through the markdown reader
   so the answer is made of addressable blocks. Without the second half you
   cannot cite claude's paragraphs, which is the whole point. **Promote
   `session_id` to a top-level param**: it is the join to the transcript and it
   is free at import.

   Its input is not the bare envelope but a one-key wrapper the loop writes:

   ```json
   {"responds_to": "<the note's root guid>",
    "follows":     "<the previous round's response root>",   // optional
    "envelope":    { ...all 21 keys, verbatim... }}
   ```

   **This is what removes the old item 2.** The wrapper already knows the note's
   guid when it calls claude, so the edge is minted during the response's own
   digest — one file, one route, one `digest`. The earlier design had the loop
   write a *third* file naming both guids, plus a route to read it, purely
   because `digest` only makes records from a file's contents and there is no
   `compost link A B`. Putting the guid in the file that was being written
   anyway makes that whole mechanism unnecessary.

   Cost, stated: `storage/` holds the wrapper rather than the bare
   `claude --print` output. The envelope is nested verbatim, so nothing the
   source said is lost.

   **Decide `params["uuid"]`.** The envelope carries its own `uuid`, unrelated
   to the record's guid. Copied verbatim, one word means two things in one
   record.

2. **Two edge types, and neither can be `contains`.** `responds_to` from the
   response root to the note root; `next` for reading order.

   **`check` counts parents from `contains` edges only** (`records.py:493-496`).
   Every other edge type is invisible to it, so joining two roots with `next`
   and `responds_to` needs no new machinery and no exception anywhere.
   Verified: two `document` roots joined by both, `check` clean, `render`
   unaffected, both keep their own page.

   **This removes the old item 3.** That item said the conversation edge needed
   its own type *and* that `render_all` must consult it so grouped roots get no
   page of their own — both true only if the conversation is a **container**. A
   container fails outright: `ROOT_TYPES = {"document", "session"}` and a root
   must have zero `contains` parents, so a `turn` holding the note and the
   response is rejected. Chaining sidesteps it completely.

   ```
   note D₁ ──next──▶ response R₁ ──next──▶ note D₂ ──next──▶ response R₂
           ◀──responds_to──┘                       ◀──responds_to──┘
   ```

   **No conversation node in this release.** "This conversation" is *walk the
   chain*, startable from any block a citation lands on, which is what actually
   gets done. A conversation node earns its place when something needs a title
   or metadata, and it will need the suppressed-page handling then.

3. **`digest` must refuse a structural guid that is not in the base.** The
   wrapper's `responds_to` is not a citation: if that guid is absent it is a
   bug, not a fact about the world, and minting an `unresolved_citation` for it
   would record a typo as knowledge.

   Today nothing catches it. `_digest` validates that a route can *read* the
   file and then writes; the edge dangles, and `check` then fails for the
   **whole base**. A one-character slip takes down everything.

   The fix is small and general: after a route returns records, verify every
   edge endpoint is either in this batch or already in the base, and refuse the
   file otherwise. That extends `_digest`'s existing promise — *"nothing is
   written until every input has been read and parsed"* — by one step, and it
   protects every future route that names guids from outside its own file.

   The distinction to hold on to: **a citation may legitimately dangle and gets
   a placeholder; a structural field may not and gets a refusal.**

4. **Append-only comes free.** Nothing is ever rewritten; each round is a new
   immutable document. v0.1 needed explicit append verification; this shape
   makes it a property.

5. **The wrapper, in `tools/`.** Not a subcommand. `nvim` on a fresh name,
   digest, layer, render, pipe, wrap the envelope, digest, layer, render.

### The loop, end to end

```
f=/tmp/round-$(date +%s).md          # a fresh name every round — see below
nvim "$f"
compost digest --as=notes "$f"       # read the view path AND the root guid back
compost layer citation
compost render
cat .compost/views/default-djot/<stem>.dj | claude --print --output-format json \
  | jq --arg g "<root guid>" '{responds_to: $g, envelope: .}' > round.json
compost digest --as=claude-code-response round.json
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

**The wrapper needs the note's root guid too**, not just the view path. `digest`
already prints it (`root <8 hex>` in its per-file line) but that is a *display*
prefix, not the guid — the loop needs the whole thing, so either `digest` gains a
machine-readable output or the wrapper reads it back out of the written file.
Decide which; the second needs no new surface.

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

### `compost draw`, writing to `.compost/graphviz/`

```
compost draw [ROOT]        whole base, or one root's subgraph
```

**The subcommand is `draw`, not `graph`.** An earlier draft called it
`compost graph`, which collides with `.compost/graph/` — the directory holding
the *records*. Two different things under one word in a project that is strict
about exactly that elsewhere.

**Output goes to `.compost/graphviz/`, a peer of `graph/`, `storage/` and
`views/` — not a subdirectory of `views/`.** The reason is the direction of the
dependency: **an HTML view will eventually embed these SVGs**, so graphviz
output is an *input* to `render`, the way `storage/` is an input to `graph/`.
Putting an input inside the output directory would be backwards, and it becomes
actively confusing the moment `render` starts reading from it. The pipeline is
legible from the layout alone: `draw` writes `graphviz/`, `render` writes
`views/` and may read `graphviz/`.

**Not folded into `render`.** v0.2.6 puts `compost render` in the inner loop —
twice per conversational round — and v1 of this draws every node in the base.
An unbounded graphviz layout on every turn is a cost nobody asked for. More
chart kinds are expected, and they should not all become `render`'s problem.

**`draw` owns its directory, and that includes the stale sweep.** `render_all`'s
sweep names three view directories explicitly (`src/views.py:420`) and so does
`main()`'s summary loop (`:461`); those lists are correctly scoped to what
`render` produces and stay as they are. `draw` does the same job for
`graphviz/`: what is on disk after a run is exactly that run's output, so a
deleted document does not leave its diagram behind.

**`draw` refuses when `check` fails**, exactly as `render` does. A picture of a
broken graph is worse than no picture, and the reasoning is unchanged from
`docs/decisions.md` — a view that renders a graph `check` rejects is asserting
something the base does not support.

**`.compost/graphviz/` is ignored whole**, the same as `views/`: `draw`
regenerates it from the records, each run rewrites it wholesale, and one base
is 12–17 MB of SVG. Generated output, not knowledge.

`ROOT` optional resolves the contradiction an earlier draft carried, which
described both a per-document `default-dot/NAME.dot` and "a walk over every node
in the base" three lines apart. Whole base by default; one root when named.

### v1 draws everything

No collapsing policy, no filters. A walk over `g.nodes` and every edge, one DOT
line each.

**Not `subgraph cluster_` per root.** An earlier draft said that "for
legibility"; measured, **`twopi` ignores clusters entirely** — 0 cluster
elements in its SVG against 4 from `dot` on the same file. Clusters are a
`dot`/`fdp` feature, and `twopi` is the default engine, so they would be
invisible work. Group with colour or a `class` attribute instead.

**Three things v1 must get right so the two-phase layout stays possible.**
The planned improvement is: lay out the structural graph with `twopi`, take
its coordinates, and draw the citation layer over them with `neato -n`, which
renders from given positions without re-laying-out. Verified to work —
`twopi -Tdot` emits `pos` on every node and `neato -n` preserved all of them
exactly while drawing an added edge. It suits the data: this base is 17,350
structural edges to 365 citation ones.

- **Every DOT edge carries its record `layer` as a `class` attribute.** Phase
  one needs the structural graph *without* `cites`, and a flat DOT mixing all
  layers has to be filtered by hand. `class` is also emitted into the SVG, so
  the HTML view can style or toggle the citation layer in CSS — which is the
  reason `graphviz/` output sits outside `views/` in the first place.
- **The synthetic root is a DOT-local name, never a record.** It exists only
  in the generated file, like a handle in a prose view, so nothing about it
  reaches `check`. Give it a fixed sentinel — `__root__` — rather than a
  minted guid, so phase two can find it again in phase one's output.

**No layout optimisation, in v1 or in the two-phase version.** An earlier draft
of this section proposed optimising `twopi`'s angular ordering to minimise
total citation-edge length. Dropped deliberately: it is a beauty metric on a
picture nobody has looked at yet.

**Measured — and the two-phase split pays for itself in time, not only in
legibility.** The same 12,632-node base, with and without the citation layer:

| | `twopi` | `sfdp` | SVG |
|---|---|---|---|
| structural only — 17,350 edges | **0.73 s** | 3.81 s | 11.7 MB |
| plus `cites`/`names` — 17,715 edges | 4.52 s | 10.46 s | 16.9 MB |

**365 citation edges — 2% of the total — cost `twopi` 84% of its runtime**,
because they are exactly the edges a radial placement cannot satisfy. Laying
out the forest alone and overlaying the citations with `neato -n` therefore
runs ~6× faster than drawing everything at once, and the earlier 7×
`twopi`-over-`sfdp` figure from synthetic trees is closer to right for phase
one (**5.2×**) than the 2.3× measured on the combined graph.

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

> **`compost draw` defaults to `twopi`**, not `sfdp`. It is the fastest measured
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

### The size threshold: warn, never refuse

Measured on a real 12,632-node base: `twopi` 4.52 s and 16.9 MB of SVG for the
whole thing, `sfdp` 10.46 s. Neither reaches a time ceiling. **Output size is
the ceiling**, at roughly 1.4 KB per node.

> **Warn past ~5,000 nodes; do not refuse.** 17 MB is large but genuinely
> usable, and refusing would break "v1 draws everything" for a base that draws
> in four and a half seconds. The DOT is always written regardless — it is the
> deliverable that keeps the graphviz binary optional — so a refusal would only
> ever withhold the SVG, and there is no size at which that is more useful than
> a warning.

`dot` and `neato` are small-subgraph tools and must not be offered for a whole
base: `dot` was killed at 180 s on a **single 2,773-node document**, and `neato`
took 30 s on that document and was killed on the base.

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

### First, before any of it: `graph/` becomes flat by rule

**Subdirectories under `graph/` were permitted, read, and used by
nothing.** `Store.files()` globbed with `rglob`, `Store.write()` called
`dest.parent.mkdir(parents=True)`, and four documents wrote
`graph/**/*.jsonl`. Demonstrated: a graph file moved to
`graph/nested/deeper/` still loaded and `check` still passed.

**Forbid it.** The graph is a flat soup of record files, and that flatness is
what lets a read-only replica be screwed on beside it — duckdb here, something
else later — without every reader having to agree about directory semantics.
A directory *is* meaning, and `docs/decisions.md` already says filenames carry
none; a subdirectory quietly contradicts that.

It also lands directly on this release: if the query layer globs one way and
`Store.files()` the other, a file in a subdirectory is visible to Python and
invisible to SQL, and the twin-assertion test fails for a reason that has
nothing to do with the assertion. Same class of divergence as the dedup one,
through a different door — and cheaper to close than to explain.

**Do this first, as its own commit, before the duckdb work.** Every site:

| where | change |
|---|---|
| `src/store.py:161` | `self.graph.rglob("*.jsonl")` → `glob` |
| `src/store.py:106` | `write()` must **reject** a relpath containing a path separator, beside its existing `.jsonl` check — refuse rather than create |
| `CLAUDE.md:64` | `graph/**/*.jsonl` → `graph/*.jsonl` |
| `docs/record-grammar.md:83` | same |
| `docs/decisions.md` | same |
| `docs/roadmap.md` | same, including the line below |

`src/store.py:137` is the **storage** write and is not affected; leave it.

**The property, sabotage-verified:** `Store.write("nested/x.jsonl", …)` raises,
and a `.jsonl` file placed under `graph/sub/` is not loaded. Restoring `rglob`
must fail the second half — that is the whole point of the change.

**DuckDB, reading `.compost/graph/*.jsonl` in place.** Nothing is
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

**Answered 2026-08-27: `SELECT DISTINCT` over the whole row.** `Store.load()`
deduplicates on `R.canonical(rec)` — the *whole record*, not the guid — so the
SQL mirror is distinctness over every column, which reproduces it exactly,
leaves a guid conflict as two rows, and materialises nothing.

An earlier note here said this had a wrinkle, that `canonical()` sorts keys
while raw lines might not. **It does not:** `R.to_jsonl` also writes with
`sort_keys=True` (`records.py:454`), and every write goes through it
(`store.py:110`). Identical records are byte-identical lines on disk, always.
The only gap left is a file written by something that bypasses `to_jsonl`, so
a writer must sort its keys — worth stating now that anything may write
records.

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

### The queries live in `tools/queries/*.sql`, not in the document

`docs/queries.md` says what each query answers and why; the SQL itself sits in
`tools/queries/*.sql` as **executable files**. Embedding them in the document
would be literate programming done by hand, and the copy that runs would drift
from the copy that is read.

The divergence risk that separation creates is accepted, with two cheap guards:
**the twin-assertion test reads those same `.sql` files**, so a query under
test cannot rot silently; and a check that every `.sql` file is *mentioned* in
`queries.md`, so a query cannot exist undocumented. Neither pins the prose to
the SQL, which is the point.

`tools/` because it is not installed — these are development material, not the
tool.

### `extras/` — installed, but not the tool

A third category the project does not have yet, and it needs its own name
because v0.2.5's rule was written as a binary: `src/` is installed and
reachable from `cli.py`, `tools/` is never installed. A **user-facing
convenience wrapper is installed but is not the tool**, and neither bucket
allows it.

`extras/`, exposed through `[project.scripts]` as separate console commands —
`compost-new`, not `compost new`. A distinct command reads as adjacent to the
tool rather than part of it, and the subcommand count stays where it is.

**`compost-new` is its first inhabitant, and the directory must not land
empty.** It mints a filename, opens `$EDITOR`, and digests the file on close —
orchestration of things the tool already does, plus an editor. Nothing is lost
if it does not exist, which is the test for belonging here.

`DEVELOPMENT.md` gets the rule stating what belongs in `extras/`, or it becomes
the drawer everything ambiguous is put in.

### Closing the version — reversed, 2026-08-27

This section said the release should stay open, on the grounds that a query
layer with no subcommand does not clear the bar `TODO.md` sets for a tag: *a
version marks a change in what the tool can do*.

**Reversed once `extras/` was decided.** That judgment was made when the
release was going to be duckdb and `docs/queries.md` alone. What shipped is
larger and does change what the tool can do:

- `graph/` is **flat by rule** — an invariant change, enforced in `write()`
- **`compost-new`** is a new user-facing command, installed via
  `[project.scripts]`
- `extras/` names a category the project did not have: **installed, but not the
  tool**
- the query layer, with the twin-assertion test that expresses `check`'s
  assertions twice and requires them to agree

The original reasoning stands as written — it was right about the release it
was describing. It stopped applying when the release grew.

**Explicitly not in scope:** revamping `check` (the gate must stay
dependency-light, since `render` refuses when it fails), a `query` subcommand
(decide after `docs/queries.md` shows which queries are worth shipping), and the
`check` → `health` rename, which belongs with the severity change that makes the
new name mean something.

Skip cleanly when `duckdb` is absent, using the existing `tests/tier.py` pattern,
so a bare environment still shows a full board.

---

## v0.2.9 — the view a person can actually read

### Why this is a release and not a tidy-up

`TODO.md` sets the bar: *a version marks a change in what the tool can do*.
Today the HTML view **cannot tell you who is speaking**. A transcript renders
as an undifferentiated column with two shades of grey rule down the left, and
the author is in the DOM the whole time. That is a missing capability, not a
matter of taste, and it is the one the human hits every session.

v0.2.8 made the records answer questions. This makes the page answer them.

### The v0.1 view is recoverable — recovered, not reconstructed

```
24d5c18  feat: v0.1 — the mechanical loop, end to end          added it
e9f189c  feat!: v0.2 — the rewrite moves in, v0.1 is deleted   deleted it
```

`git show e9f189c^:src/render/to_html.py` is 407 lines and holds every
behaviour this release restores. `git show e9f189c^:src/render/index.py` is the
old index page and is **not** in scope here — it is v0.2.10.

This matters procedurally: the affordances below were read out of that file,
not rebuilt from a description of them. Where this section quotes a selector or
a constant, it is the v0.1 value.

### The four regressions, each with its cause in the current file

**1. The whole guid is printed over the page.** `src/views.py:309` —
`.block::before { content: attr(id); left: -5.6rem }`. That gutter was sized
when `HANDLE_LEN` was 8. It is 36. A 36-character monospace string needs about
16 rem, so it spills across the text it is meant to annotate. The page did not
get uglier by taste; the handle got 4.5× longer and the gutter did not.

**2. Clicking the block does nothing.** The click handler (`src/views.py:336`)
computes `onHandle` from the cursor position and returns early unless the
window is narrower than 992 px. So block-body clicking already exists and is
switched off for exactly the window size the human works in. v0.1 had no
geometry test at all: `e.target.closest('[data-hash]')`, anywhere.

**3. The copy confirmation is invisible.** `.copied::before` replaces the
gutter text — the one place on screen nobody is looking immediately after
clicking. v0.1 had a toast: fixed, bottom centre, dark pill, showing *the
reference it had just copied*, for 1.8 s.

**4. The author label was deleted.** v0.1:

```css
.turn[author]::before { content: attr(author); display: block; font-size: 11px;
      text-transform: uppercase; letter-spacing: .07em; color: #9aa7bb; }
.turn[author="human"]  { border-left-color: #2b5fd9; }
.turn[author^="claude"], .turn[author^="agent"] { border-left-color: #d99b2b; }
```

v0.2 kept the container and the `author` attribute and shipped only
`.turn[author="human"] { border-left-color: var(--mark) }`
(`src/views.py:321`).

**Corrected during implementation — the regression was total, not partial.**
This paragraph originally said human turns got a blue rule and assistant turns
the default grey. They did not: **pandoc's HTML writer `data-`-prefixes a
Div's non-standard attributes**, so `author="human"` in the AST reaches the
page as `data-author="human"` and the `[author="human"]` selector matched
nothing on any page ever rendered. Every turn got the same grey rule.

The claim was wrong because it was read out of `to_html.py` and `views.py`
side by side without re-rendering either — and v0.1 wrote its HTML through
`djot.js`, which does not prefix, so the selector was correct in the file it
was copied from and dead in the file it was copied to. Verified directly:
`pandoc -f json -t html` on a Div carrying `author="human"` emits
`data-author="human"`.

**Two traps, one shape.** The attribute was right and the value was wrong
too: v0.1's authors were `claude` and `agent`, and this release's closed
vocabulary is `human`, `assistant`, `envelope` (`docs/record-grammar.md` §6).
Porting `^="claude"` / `^="agent"` verbatim produced two more selectors
matching nothing, which is how assistant turns kept the default grey through
a first implementation that passed every guarantee this section had written.
**Guarantee 14 exists because of that**: no `[data-author…]` selector may name
a value outside the closed vocabulary.

So *"port the v0.1 CSS verbatim"* is the wrong instruction wherever the value
or the attribute crosses a renderer boundary. The fix is still four lines of
CSS over data already in the page — but not the same four lines.

### The highlight must be JavaScript, not `:hover`

Stated so that nobody simplifies it away later. **Blocks nest.** A `Para`
inside a `ListItem` inside a `BlockQuote` is three nested `.block` divs, and
CSS `:hover` matches all three at once — you would light up the whole
quotation to point at one sentence. v0.1 used `mousemove` plus
`el.closest('[data-hash]')`, which resolves to the *smallest containing block*,
and that is the entire reason it felt precise rather than approximate.

### Shift highlights the subtree; shift does **not** change what is copied

In v0.1, Shift did two things, and only one of them still means anything:

```js
const sub = e.shiftKey && el.hasAttribute('data-subtree') ? '+++' : '';
const ref = '{#' + el.id + sub + '}';
```

`{#8hex+++}` was the **v0.1 citation syntax** for "this block and everything
under it". v0.2 has no subtree citation: `[-](#guid)` names exactly one block,
and the `+++` form survives only inside the `kg-8hex` resolver so that migrated
v0.1 citations still resolve.

So: **restore the highlight, do not restore the copy.** The clipboard gets
`[-](#guid)` whether or not Shift is down. Shift-copy would mint a citation in
a syntax nothing in this tool resolves — a dead anchor generated by the tool
itself, which is worse than the length problem it was invented to solve.

**And the subtree highlight is the same colour as the block highlight** —
`.hl` and `.hl-sub` share one background, against v0.1, which painted the
subtree amber (`#fff3d6`) and the block blue (`#f2f6ff`).

The second colour was not decoration. It warned that **the clipboard was about
to differ**: amber meant "shift-click here and you get `+++`, not the bare
handle". That distinction is gone with the syntax it signalled, and a colour
that no longer marks a difference in behaviour is worse than no colour — it
invites the reader to look for a meaning the page cannot deliver. One
highlight, one meaning: *this is what you are pointing at*.

### The heading subtree, without touching a pandoc invocation

v0.1 got heading subtrees from pandoc's `<section>` wrappers, and paid for it:
the id landed on the section rather than the heading, so its JS had a whole
block moving ids back onto the `h1..h6` and re-tagging the section as
`data-subtree-for`.

`render_html` calls pandoc without `--section-divs`, so v0.2 headings are bare
and that wrapper does not exist. **Adding the flag is rejected.** Every flag in
the pandoc invocations here is load-bearing and measured, this one would be
added for a view affordance rather than a correctness property, and it
reintroduces exactly the id-placement problem v0.1 had to work around.

Compute it in JS instead, which is self-contained and changes no records and no
invocation:

- **List item, blockquote, any nesting container:** the subtree is
  `el.querySelectorAll('.block')` — the descendants it already contains.
- **Header:** walk forward over following siblings of the header's `.block`,
  stopping at the first one containing an `h1…h6` whose level is less than or
  equal to the hovered header's. Everything passed over is the section.

### Slash commands — measured on the human's base, not estimated

An earlier estimate in conversation said "five paragraphs, roughly thirty".
Measured, it is three paragraphs and twenty-one. The real shape is **three
consecutive `turn` nodes, one `Para` each, always in this order**:

```
turn[author=human]  Para  <local-command-caveat>Caveat: The messages below …</local-command-caveat>
turn[author=human]  Para  <command-name>/exit</command-name>
                          <command-message>exit</command-message>
                          <command-args></command-args>
turn[author=human]  Para  <local-command-stdout>See ya!</local-command-stdout>
```

| | |
|---|---|
| slash commands in the base | **7** (`/exit` ×5, `/model` ×2) |
| sessions containing one | 4 |
| turns spent on them | **21** |
| `Para` nodes leading with one of the three tags | 7 each, 21 total |
| turns with more than one child | **0** |
| the three turns non-adjacent | **0 occurrences** |

The regularity is the licence to act. Every instance is three adjacent turns of
one paragraph each; there is no case where a slash command is mixed into a turn
carrying real prose.

What a reader sees today is three human turns in a row saying *"Caveat: … DO
NOT respond to these messages"*, then *"/exit exit"*, then *"See ya!"* — with
the harness's instruction to the model rendered as though the human had typed
it, because the turn really does carry `author="human"`.

### Recognised structurally, never by matching prose

The test is: **the node's first inline is a `RawInline` whose format is `html`
and whose text is one of the three opening tags.** Not a substring search over
rendered text, not a regex over the source bytes.

This is the same standing as *"never scan raw file text for citations"* — the
property that makes "handles inside code blocks are not citations" true by
construction rather than by rule. A paragraph that merely *mentions*
`<command-name>` mid-sentence does not match, and does not need an exception
written for it.

### Suppressed at view time, never at import

Nothing about this touches ingestion. `--as=claude-code-transcript` is lossless
by property — `records_to_session(session_to_records(lines)) == lines`, exact —
and it stays that way. Every one of these paragraphs remains a node, keeps its
guid, keeps its `params["log"]`, and `compost lookup` keeps resolving it. The
human found `aecc64f0-…` that way and that is how it should stay findable.

The rule this follows, as the human states it: **filter only when disk or
compute requires it; never lose information that costs nothing to keep.**
Rendering is neither — it is a projection, rebuilt on every `compost render`,
and a projection that omits something is reversible by editing the projection.
An importer that omits something is not.

The precedent is already in this file: `logline` returns `None`
(`src/views.py:100`) and a `thinking` node with no text returns `None`. *Being
in the graph and being on the page are different things, and the importer no
longer gets to decide the second one by refusing the first.*

### What renders instead

**The caveat: nothing at all.** It is an instruction addressed to the model,
and rendering it inside an `author="human"` frame puts words in the human's
mouth. There is no compact form worth keeping — its entire content is a
directive about how to read the next message.

**The command: one line, still citable.** Name, then message and args when they
are non-empty and differ from the name:

```
/exit
/model  model
```

It keeps its handle, so it stays clickable and citable — the human may well
want to cite *"here is where I switched models"*, and removing citability is
the kind of silent decision this project dislikes.

**The stdout: folded in HTML, plain in djot.** Exactly the `tooloutput` pattern
at `src/views.py:125` — `_details()` in `html` mode, the bare block in `djot`.
Skipped entirely when empty.

**A turn whose children all render to nothing renders to nothing.** This
generalises the rule already at `src/views.py:164`, which drops an envelope turn
carrying only tool results. Without it, suppressing the caveat leaves seven
empty framed boxes on the page, which is a worse outcome than the paragraph
was.

### Scoped to sessions, by construction

`_session_children` is reached only when the root is a `session` (`_ast`,
`src/views.py:220`). A `document` root — a note, a README, this roadmap — never
passes through it. So a markdown file that opens a paragraph with a literal
`<command-name>` is untouched, and no scoping condition has to be written for
that: it falls out of where the code sits.

**Accepted risk, stated:** inside a *transcript*, a human who genuinely begins
a paragraph with one of those three literal tags loses that paragraph from both
rendered views. It stays in the records, in `graph/`, in `lookup` and in the
SQL view. Judged acceptable — the three tags are harness-reserved, and the
alternative is a heuristic about intent.

### ANSI escapes in the stdout

Measured: `'Set model to \x1b[1mOpus 5\x1b[22m and saved as your default'`. The
terminal's SGR sequences survive ingestion, as they must, and render in HTML as
literal `[1m` / `[22m` noise.

Strip them **in the view only**, with one regex over the text being rendered.
The records are not modified, `lookup` still prints what the log held, and the
stripping is a display decision that can be revisited without a migration.

### Also in this release: `digest` prints whole guids

`src/store.py:442` prints `root fff68312, blob 24030d93` — an 8-character
prefix that `lookup` refuses, because a prefix is not a handle. The tool
currently prints an identifier you cannot paste back into the tool. Print the
whole guids.

This is a one-line change and it closes the same loop as the docstring
correction that opened this release: `docs/roadmap.md` already flags it above
(*"the loop needs the whole thing"*) as a problem for the conversation-loop
wrapper, which gets it for free.

### Deliberately not in scope

- **`a[href^="#"]::after { content: attr(href) }`** (`src/views.py:328`), which
  prints the full guid after every citation link in prose. Nobody has
  complained about it, and what a citation should *look like* in running text
  is a separate question that deserves its own answer rather than being
  decided in passing here.
- **`<usage>` (16 occurrences), `<task-notification>` (8), `<result>` (8).**
  All mid-paragraph rather than leading, none in a fixed envelope, and no
  reading exists for them. Inventing one is a guess, and a guess that suppresses
  content is the expensive direction.
- **The index page** — sections by kind, per-row metadata, display names,
  filtering. That is a coherent piece of work and it is **v0.2.10**.
- **The three pandoc defects.** Unchanged and still not repaired.

---

### What has to be built

Everything is in `src/views.py` except item 7. `src/records.py` is not touched,
so the round-trip property is untouched by construction.

**1. `_lead_tag(node)` — a new module-level helper.** Returns the text of the
node's first inline when that inline is `{"t": "RawInline", "c": ["html", …]}`,
else `None`. Three lines. Used only by the two call sites below.

**2. `SLASH_TAGS`, a module-level constant.** The three opening tags, with a
comment naming them as harness-reserved and pointing at this section.

```python
SLASH_CAVEAT  = "<local-command-caveat>"
SLASH_COMMAND = "<command-name>"
SLASH_STDOUT  = "<local-command-stdout>"
```

**3. `_render_slash(g, n, mode)` — a new function.** Given a `Para` whose
`_lead_tag` is one of the three, return the blocks to emit:

- caveat → `None`
- command → a single `Plain`/`Para` block carrying the command line, wrapped so
  the handle survives (see item 4)
- stdout → `_details("output", [_code(text, ["command-output"], guid)])` in
  `html` mode, the bare `_code` block in `djot`; `None` when the text is empty

Build the command line from `R.plain_text(n)`, which already flattens the
inlines and drops the `RawInline` tags — verified: it yields `'/exit exit '`
and `'/model model '`. Collapse repeated whitespace and drop a trailing
duplicate word when message equals name.

**4. Call it from `_session_children` (`src/views.py:185`).** In the `else`
branch, before the ordinary `R._to_block` path:

```python
if _lead_tag(n) in SLASH_TAGS:
    blocks = _render_slash(g, n, mode)
    if blocks:
        out.extend(g.wrap(n, blocks) if g.wrap else blocks)
    continue
```

`g.wrap` is what puts the handle on, so routing through it is what keeps the
command citable. **Do not** call `R._to_block` for these — that is the
reconstruction path and it must keep returning the node exactly.

**5. Empty turns disappear (`src/views.py:159`).** Compute the children first,
then decide:

```python
if t == "turn":
    kids = _session_children(g, guid, mode)
    if not kids:
        return None
    return [{"t": "Div", "c": [_attr(...), kids]}]
```

This subsumes the existing `author == "envelope"` special case; delete that
line and say in the comment that the general rule replaced it.

**6. `CSS` and `JS` (`src/views.py:290` and `:336`) — the restoration.** Port
the v0.1 values from `git show e9f189c^:src/render/to_html.py`:

- `.block::before` stops printing `attr(id)`. It becomes a fixed hint —
  `content: "⧉ click to copy"`, and `"⧉ click · ⇧ subtree"` when the block has
  a subtree — shown only on the hovered block.
- `.hl, .hl-sub { background: #f2f6ff }` — **one colour for both**, applied by
  JS rather than `:hover`. v0.1's amber `.hl-sub` is deliberately not carried
  over; see *Shift highlights the subtree* above for why. The background must
  be opaque, not a translucent overlay: nested `.block` divs stack, and a
  translucent wash would double-darken the inner ones and reintroduce the
  two-tone effect this decision removes.
- `.turn[author]::before { content: attr(author) }` plus the three border
  colours, verbatim from v0.1.
- `#toast` and `#toast.show`, verbatim from v0.1, plus a `<div id="toast">`
  before the closing `</main>` in `render_html`.
- the tool call's **input** moves inside `_details` in `html` mode, with a
  summary of `params["name"]` plus the first ~72 characters of the first
  argument, in the v0.1 summary style (12 px monospace, dim).
- **Keep the dark-mode branch.** v0.1 was light-only; this base is read on a
  machine that may be in either mode. The **light values are the v0.1 palette
  verbatim** — that is the Wikipedia-like look being asked for — and the dark
  block redefines the same tokens. Do not invent a third palette.

**7. JS behaviour, in order:**

1. `mousemove` → `e.target.closest('.block')` → repaint. Track `current`.
2. `keydown` / `keyup` on `Shift` → repaint with the subtree rule from
   *The heading subtree* above.
3. `click` → `e.target.closest('.block')`, **no geometry test, no width
   gate** → `navigator.clipboard.writeText('[-](#' + el.id + ')')` → show the
   toast with the copied text for 1.8 s.
4. Shift is not read in the click handler at all.

**8. `src/store.py:442`** — print `root {root}, blob {guid}` rather than
`[:8]` slices.

---

### Tests — the guarantees this release states

Extend `tests/test_session_views.py` (slash commands, turns) and
`tests/test_views.py` (page furniture). Every one is a property that has been
made to fail on purpose, per `tests/test_sabotage.py`'s pattern — a snapshot of
the CSS is not a test.

1. **A turn whose only child is a caveat `Para` produces no output at all** —
   neither the paragraph nor an empty turn frame. Sabotage: make
   `_render_slash` return the block and the frame reappears.
2. **The caveat's node is still in the graph** after rendering, and
   `compost lookup` on its guid still prints its text. This is the one that
   stops a later "simplification" moving the filter into the importer.
3. **The command paragraph renders with its guid as the block id**, so it stays
   citable.
4. **The rendered command line contains no `<` character** — the three tag
   pairs are gone from the page.
5. **Stdout with text renders inside a `<details>` in HTML and as a bare code
   block in djot**; empty stdout renders nothing in both.
6. **ANSI SGR sequences do not appear in either rendered view**, and *do*
   appear in the record the view was built from. Both halves, in one test.
7. **A `document` root containing a `Para` that leads with `<command-name>`
   renders it unchanged** — the scoping property, asserted rather than assumed.
8. **The HTML page contains no element whose `::before` content is a guid** —
   the regression that made the page unreadable. Assert on the CSS string.
9. **The click handler contains no window-width comparison** — the geometry
   gate is gone. Crude, and it is the property that actually broke.
10. **Every `turn` div carries an `author` attribute and the CSS defines a
    `[author]::before` rule** — "you can tell who is speaking", stated as
    something a test can fail on.
11. **`digest` prints a 36-character root guid**, and the printed string is
    accepted by `lookup`. The round trip through the terminal, which is what
    was broken.

12. **The copied string is byte-identical with and without Shift**, and
    contains no `+`. Asserted directly on the click handler's source, because
    this is the one behaviour a future reader is most likely to "restore"
    from v0.1 without noticing that the syntax it produced is dead.
13. **`.hl` and `.hl-sub` resolve to the same background value.** The rule
    exists to be read as one highlight, and two colours drifting back in is a
    silent change of meaning.
14. **Every `[data-author…]` selector names a value in the closed vocabulary**
    — `human`, `assistant`, `envelope` — and `human` and `assistant` are both
    named. Added during implementation review, after two ported selectors were
    found matching nothing. A dead selector is silent; that is what makes it a
    property rather than a review note.

`./tests/run.sh` must stay green in both tiers, and the round-trip suite must
be untouched — if `records.py` changed, the change is wrong.

### Costs accepted knowingly

- **A transcript paragraph genuinely beginning with one of the three literal
  tags is dropped from both views.** Records unaffected. Named above.
- **The subtree walk is a heuristic about document structure**, not a fact from
  the graph. The graph knows the real containment; the HTML has flattened it
  for headers. If this proves wrong often, the answer is to carry the structure
  into the page, not to add `--section-divs`.
- **Two views now differ in more than collapsing.** djot and html already
  diverge on `<details>`; they now also diverge on the tool-call input. The
  rule stays what it was: djot shows everything, html folds what is long.
- **The light palette is a 2026-08 aesthetic decision** with no measurement
  behind it, unlike most entries in this file. It is restoring something the
  human liked, and that is the whole justification.

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

- **Backlink placement in the HTML view** — per block or per document. Moved
  out of v0.2.5 to after v0.2.8; the question is unchanged, only unscheduled.
- ~~**The route name for the envelope.**~~ Settled 2026-08-26:
  **`claude-code-response`**, parallel to `claude-code-transcript` — same
  producer, different output mode.
- ~~**The conversation edge type name.**~~ Settled 2026-08-26. `includes` is
  **not** used: it implied a container, and a container of roots fails `check`.
  Two edges instead, **`responds_to`** and **`next`**, neither of which `check`
  counts as parenthood.
- **`params["uuid"]` on the response envelope** — the envelope's own identifier
  sits beside the record's `guid`, one word for two things. Rename on import and
  the route stops being a faithful copy; leave it and something reads the wrong
  one eventually.
- **How `represents` and `duplicates` relate to `alias`** — three ways of saying
  two records are about one thing.

**Nothing in this document is now waiting on a measurement.** That is deliberate:
three separate claims here had already been wrong because they were argued from
constructed samples rather than measured against real material — the djot reader's
treatment of handles, the citation match's recall, and the storage cost. Each was
labelled *Verified* or *Measured*, and the label is what stopped anyone looking
again. Every remaining number was taken from a real base or a real corpus.

*Closed by measuring the v0.1 corpus:* the `.dj` files' shape, the ingest route,
the handle-collision check (6,601 distinct, zero duplicates), and the assignment
rule, which turned out not to be needed at all.

*Closed by spiking graphviz and duckdb:* the SVG `id` question — it survives, and
hyphens are escaped in the bytes; `dot`'s usable ceiling — between 250 and 500
nodes, so `sfdp` is the default and not an option; the `read_json` shape — no
schema needed, `MAP` not `STRUCT`, and `columns=` unnecessary; and the SQL-versus
-`load()` dedup divergence, constructed and confirmed at 5,051 against 5,082.

## Beyond this window

- **HTML backlinks.** v0.1 had *Referenced by* and v0.2 lost it. Scheduled into
  v0.2.5 and moved out again, because nothing depends on them and they are a
  view feature in a naming release. Three things are already settled and can be
  picked straight back up:
  - **Open design question:** per block, or once per document. Per block is what
    the citation means; per document is what fits the page.
  - The view must distinguish an exact citation from a recovered one, which is
    why `Graph.linked` keeps `by` — shipped in v0.2.4 and now carrying a second
    scheme's edges as of v0.2.5.
  - **Dedup in the view**, by `(source, destination, by)`. Two builds of the
    citation layer put every citer in the base twice, and a page listing one
    citer twice is noise. Deduping in a view breaks no rule — views are derived,
    disposable and never re-ingested — and it touches no records, so the
    accumulation the dedup design needs to study stays intact underneath.
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

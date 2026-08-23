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
during a migration. **Measured cost 4.4%** — 20 bytes against a mean record of
455 B, over the 767 records the fixtures produce.

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
The node form has always worked this way: `canonical([type, params, content])`,
excluding identity and framing.

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
{"type":"alias",
 "params":{"value":"deadbeef-1111-…","scheme":"uuid-link",
           "created_at":"…","tool_version":"0.2.4"}}

{"type":"unresolved_citation",
 "params":{"created_at":"…","tool_version":"0.2.4"}}
```

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

**What a placeholder is actually for, today.** Not deferred resolution — see the
accepted risks below. Forensics: which guids the model hallucinated when writing
an answer, which documentation examples parsed as citations, what was pasted in
from another base.

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

### `--by kg-8hex`

Verified against pandoc with the project's reader
(`commonmark_x-smart-attributes-fancy_lists`):

```
see {#a3f2b1c4} and `{#a3f2b1c4}` inline.

  Str  "{#a3f2b1c4}"            one whole token, exact
  Code [attr, "{#a3f2b1c4}"]    text at c[1], NOT a Str
```

Every exclusion is **structural**:

| case | excluded because |
|---|---|
| inline code | a `Code` node's text is a bare string at `c[1]`, not a `Str` |
| code block | its text is in `params["text"]`; the walker never reads `TEXT_IN_PARAMS` |
| `{#xxxxxxxx}` | `x` is not in `[0-9a-f]` |
| **an assignment line** | the block's **entire** text is one matching `Str` |

That last row is its own rule and it matters — without it, all ~5839 v0.1
assignment lines become citations, each block citing itself or its neighbour.

> **A block whose entire text is `{#xxxxxxxx}` is an assignment. A handle
> appearing among other text is a citation.**

The `{@x}` era failed because it regexed `plain_text()`, which *does* fold
`params["text"]` in (`records.py:47`). Walking `content` for `Str` nodes instead
of flattening is the whole fix, and it mirrors `_links()` exactly.

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

**Blocked on material deliberately not on this disk.** The v0.1 corpus was
removed from the history, not merely deleted, and is kept privately.

No version number, because it changes no code.

**There is no `--as=djot` route and there will not be one.** Instead:

```bash
pandoc -f djot -t json old.dj > old.json
compost digest --as=pandoc-ast old.json
```

Verified: `pandoc -f djot` reads a v0.1 turn div correctly — `Div` with class
`turn` and `author="human"` intact. **`--as=notes` does not**: the same file
through `commonmark_x-smart-attributes-fancy_lists` yields three bare `Para`s,
the div and the author attribution silently gone. Measured under pandoc 3.8,
outside the conda env; it is a reader-capability difference, not a version
subtlety.

Steps:

1. Read the old `.dj` through `pandoc -f djot -t json`; digest as `pandoc-ast`.
2. A one-off external script builds the dictionary and emits alias nodes and
   `names` edges as JSONL. Copy it under `graph/`.
   - **Check the cheap path first.** An assignment line digests into an ordinary
     `Para` holding exactly one `Str`, sitting immediately before the block it
     labelled — which now carries its own guid. If that holds, the dictionary is
     readable from the new graph alone via `next`, with no comparison against the
     old file. *Unverified: the corpus is not here.* Confirm before writing
     anything else.
   - **Measure feasibility before writing the script.** `src/roundtrip.py` has
     `READ` and `WRITE` as two module constants; swap them to `djot` and run the
     harness over the `.dj` files. A fixed point means alignment is positional and
     exact. Anything less, and the miss count is the size of the job — the
     precedent is on the record: re-deriving handles from `raw/` recovered
     **103 of 217**, zero wrong, half simply not matching.
3. `compost layer citation --by kg-8hex`.
4. Commit the dictionary script and its output as ordinary files.

**Provenance.** `--as=pandoc-ast` means every migrated document records
`route: "pandoc-ast"`, so the base will not say these came from djot. Put the
exact pandoc invocation into the params of the alias records the script writes.

**Acceptance:** every handle resolvable before the migration resolves after;
the count of prose-quoted example handles recorded rather than silently absorbed.

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
nvim /tmp/xxx.md
compost digest --as=notes /tmp/xxx.md
compost layer citation
compost render
cat .compost/views/default-djot/xxx.dj | claude --print --output-format json > r.json
compost digest --as=claude-code-response r.json
compost layer citation
compost render
```

---

## v0.2.7 — a graph view

### The property that earns a new dependency

`environment.yml` says *no pip dependencies and no system dependencies beyond
pandoc*. Graphviz is worth relaxing that for, and the reason is specific:

**DOT is a deliverable on its own, so the binary stays optional.** `render`
always writes `default-dot/NAME.dot` — text, from records. If `dot` is on PATH it
also writes the SVG. If not, the DOT is still there, readable by an agent and
renderable later on any machine that has graphviz.

So the line narrows rather than breaking: **no *required* system dependency
beyond pandoc.** That is exactly what D3 cannot do — a vendored blob is all or
nothing with no text form. And it is why mermaid's advantage evaporates: also
text, but its renderer needs the node ecosystem or a 3 MB browser blob.

Other reasons: one generator serves the agent path and the human path; agents
write DOT at least as fluently as mermaid; `dot` for hierarchical layout and
`sfdp` for the thousands-of-nodes case, one flag apart; and it is thirty years
old and finished.

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

### Must be verified first

**Does an explicit `id` on a DOT node survive into the SVG's `<g id="…">`?** If
so, the guid reaches the picture and clicking a node can copy `[-](#guid)` with
the handler `views.py` already has. If not, the citation story for diagrams
changes shape. **Unverified — `dot` is not installed on the development machine.
One render answers it, and it must happen before the view is designed around it.**

DOT quotes ids, so a guid with hyphens goes in verbatim — the collision that
would break mermaid ids does not arise.

### Costs, accepted knowingly

- conda-forge graphviz pulls cairo, pango and friends — 50–100 MB with deps.
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
them. Nothing removes any of it, and there is no `drop`. **There is no way to
reduce a base's records** short of deleting graph files by hand.

**One alias value can name several nodes.** Two builds produce two aliases with
the same value naming two different placeholders. `lookup` returns all matches.
Two kinds of this exist and only one is dangerous: *benign* is one value naming N
`unresolved_citation` nodes — N stand-ins for one missing thing; *dangerous* is
one value naming two different real blocks, which would mean the dictionary is
wrong. They are distinguishable by the target's node type.

**A `uuid-link` placeholder can never resolve.** Every digest mints fresh
UUIDv4s, so a guid is base-local and unreproducible. A cited guid that is not in
the base was never in it — a model hallucination, a paste from another base, a
typo, or a documentation example — and digesting more material will never fix it.
Placeholders are forensic evidence, not pending work. *(The `kg-8hex` scheme is
the exception, because its aliases arrive from outside.)*

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
- **Whether the v0.1 assignment paragraph precedes its block** and is its sibling
  (v0.2.5 migration, unverifiable here).
- **Whether a DOT `id` survives into the SVG** (v0.2.7, unverifiable here).
- **Do nodes get `created_at`?** Edges do. If nodes should too, it must be a
  **top-level** key, never in `params` — node hashing is
  `canonical([type, params, content])`, so anything in `params` would move every
  existing `content_hash` in every base.
- **The route name for the envelope.** `claude-code-response` is a placeholder.
- **The conversation edge type name.** `includes` was proposed; not settled.
- **How `represents` and `duplicates` relate to `alias`** — three ways of saying
  two records are about one thing.

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

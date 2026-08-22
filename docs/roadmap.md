# Roadmap

What is **scheduled**, and into which release. `TODO.md`'s *Known gaps* is the
list of things found and named but deliberately unscheduled; an entry moves
here when it has a version number and a design. Nothing here is a promise about
dates — only about order, and about what each release has to prove before it is
tagged.

`CHANGELOG.md` still says what actually happened. If this file and the changelog
disagree, the changelog is right and this file is stale.

---

## v0.2.4 — layers become a thing the tool operates on, and citations are wired

### Why this first

`records.citation_edges()` was written, tested in `tests/test_citations.py`, and
**never called by anything in `src/`**. So today a `[-](#guid)` in a digested
document creates no edge, `compost lookup` cannot say what cites a handle, and
the "citation layer" exists only as a function. Every other piece of planned
work — the migration, backlinks, concept maps — is downstream of edges that are
not being minted.

Wiring it is not a one-line call, and the reason is structural. `_digest`
deliberately validates a batch in isolation (`src/store.py:261`), but a citation
points at a guid from an **earlier** import. Resolution has to run against the
whole loaded base. That is a different shape from anything in the codebase, and
building it properly means deciding how *derived* records live in a base whose
only writer so far has been `digest`.

That decision is worth generalising, because adding and deleting semantic layers
is the medium-term direction, not a one-off for citations.

### The record shapes

Two new node types and one new edge field.

```json
{"record":"node","guid":"…","type":"layer",
 "params":{"name":"citation","by":"uuid-link",
           "generated_at":"2026-…","tool_version":"0.2.4",
           "roots":["<root guid>", …]}}

{"record":"edge","guid":"…","layer":"citation","by":"uuid-link",
 "type":"cites","source":"…","destination":"…"}
```

- **`layer` names the kind of claim. `by` names what produced it.** Two fields,
  never one compound string. A `"citation:kg-8hex"` value would make every
  consumer split a string to recover meaning, which is the filename mistake with
  a colon in it. Two JSON keys are two SQL columns and nothing to parse.
- **`by` rather than `scheme`**, because the general case is not syntax. A future
  semantic layer is `{"layer":"topics","type":"about","by":"…"}` — the same shape
  with no new concept.
- **The CLI flag is the field name.** `--by kg-8hex` stores `by: "kg-8hex"`. What
  you type and what is stored are one vocabulary, so nobody holds a translation
  table.
- **`params["roots"]` is the set the build consumed**, and it is what makes
  staleness exact rather than clock-based. Roots are documents and sessions, not
  blocks: 500 documents is ~18 KB of guids.

`layer` joins `file` and `blob` in `records.UNCONTAINED` (`src/records.py:34`) —
an entity, pointed at, inside nothing.

### `schema_version`, starting at 1

The grammar is written down as of this release — `docs/record-grammar.md` — and
every record starts carrying the version of the grammar it conforms to.

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

Everything else in v0.2.4 and v0.2.5 is additive — new node types, new edge
types, new layers, a new optional `by` — so **the number stays at 1** through
both. A version that increments every release carries no information.

`docs/record-grammar.md` is normative for shape; `docs/record-format.md` keeps
the design argument. When they disagree, the grammar is wrong and gets corrected
against the code.

### Derived records get deterministic guids

`Builder` mints `uuid4()`. Rebuild a layer twice without deleting and you get two
edges per citation with different guids, both structurally valid, so `check` says
nothing. Silent duplication, which is the failure class this project keeps
finding.

So:

- **Derived records** — a `cites` edge — take
  `uuid5(COMPOST_NS, canonical([layer, by, type, source, destination]))`.
  A rebuild produces **byte-identical** records, and `Store.load()`'s existing
  deduplication (`src/store.py:159`) collapses them for free. Its docstring
  already blesses this: *"two writers asserting the same fact is agreement, not
  conflict."*
- **Asserted records** — an alias, a `blob` — keep minted guids. A claim is not a
  function of anything.

This also makes a partly-failed build harmless, and makes the records a pure
function of the graph, which is what *derived* means.

### `compost layer`

A noun with verbs, because three things have to happen and they are not
parameters of one action. The bare form is read-only; a verb appears exactly when
something changes.

```
compost layer                              list declared layers, counts, staleness
compost layer build [NAME] [--by SCHEME]   build or rebuild
compost layer drop  NAME    [--by SCHEME]  remove a layer and its declaration
```

- `layer` with no arguments is a **graph query** over `layer` nodes, not a
  directory scan. The base describes itself.
- `layer build` with no NAME rebuilds every declared `(name, by)` pair — the
  common move after a digest. On a base with nothing declared it does nothing,
  so the first build must name what it wants.
- `layer build citation` defaults to `--by uuid-link`.
- **`drop` removes the `layer` node too.** Otherwise a dropped layer is
  permanently stale and the base can never be clean again.

`layer` is the **second writer** to `graph/`. CLAUDE.md's rule becomes *write
through `digest` or `layer`*, with a contract: **`layer` owns its files
completely, rewrites them wholesale, and never touches a file `digest` wrote.**

Deletion cannot key on filenames — those stay minted uuids and carry no meaning.
`layer` finds its files by **reading records**: a file whose records all carry the
target `(layer, by)` is removed; a file that mixes layers causes a **refusal**,
not a partial rewrite. A refusal rather than an assumption, because files already
do mix layers today — `_digest` writes `pandoc-ast` structure edges and the
`ingestion` `derived_from` edge into one file (`src/store.py:334`).

`build` is `drop` followed by a write, so it is idempotent on disk as well as in
the records.

### New `check` assertions

Staleness needs no new gate. `render` already refuses when `check` fails, so
making staleness a `check` problem gives the refusal to every consumer at once.

1. **`layer` is uncontained** — 0 parents, like `file` and `blob`.
2. **Every record carrying a `layer` value outside the digest-written set must
   have a declaration.** The digest-written set is explicit and small:
   `pandoc-ast`, `session`, `claude-code`, `ingestion`, `agent`
   (`records.py:26`, `session.py:60,62`, `store.py:44,48`). Editing that set is a
   visible decision, which is the point.
3. **Staleness** — for each `layer` node, `roots(base) - params["roots"]` must be
   empty.

Three properties make assertion 3 safe to enforce strictly from day one:

- **A base with no declared layers is never stale.** Every existing base and
  every fixture is unaffected — backward compatible by construction, not by a
  grandfather clause.
- **Roots are only ever added**, since sources are immutable. Staleness is never
  "a file changed"; it is "a root arrived". That is why a set difference is exact.
- **The daily loop is `digest && layer build && render`**, which the wrapper does
  anyway (see v0.2.7, below). Strictness bites only when a step is skipped, which
  is when it should.

When `check` becomes `health` with the error/warning split `TODO.md` wants,
staleness is the obvious first *warning*. Choosing strict now is not a one-way
door.

### The failure this prevents

Digest an answer citing a block from last week; run `render` without rebuilding.
The page renders, the cited block shows no reference to the new answer, nothing
errors, and you conclude nothing cites it. It looks right and is wrong — the same
class as *a view of a broken graph is worse than no view*.

### `lookup` and the views

- **`lookup` reports incoming citations.** CLAUDE.md currently says it "does not
  say what cites it — there is no citation layer yet". That sentence has to stop
  being true in the same release that makes the layer exist.
- **The HTML view grows backlinks** — v0.1 had *Referenced by* and v0.2 lost it;
  it is the human-facing payoff of the whole release. **Open design question,
  to settle during implementation:** whether backlinks render per-block or once
  per document. Per-block is what the citation actually means; per-document is
  what fits the page.

### Tests

`tests/test_layer.py`, new suite in `tests/run.sh`. Properties, sabotage-verified.

1. **Build is idempotent** — build twice; the record set and the file count are
   identical.
2. **Guids are deterministic** — two independent builds over the same graph
   produce the same edge guids.
3. **Drop removes exactly the layer** — its records and its `layer` node, nothing
   else.
4. **Drop refuses on a mixed file** rather than rewriting it.
5. **Staleness** — digest a document, `check` reports stale and `render` refuses;
   rebuild and both are clean.
6. **No declared layers is never stale.**
7. **An undeclared layer value is a `check` problem** (sabotage: hand-write a
   record with `layer: "invented"`).

`tests/test_citations.py` gains the case its unit tests cannot reach: a citation
**across documents**, through `digest` then `layer build`, which is exactly what
`_digest`'s batch isolation could never resolve.

### Documentation

`CLAUDE.md` (the second writer, the `lookup` sentence, the pipeline),
`docs/man-compost.md` (a ninth subcommand and its section), `src/cli.py` USAGE,
`docs/record-format.md` (the two node types and the `by` field),
`docs/record-grammar.md` (the same, plus `schema_version` on every form),
`DEVELOPMENT.md`, `README.md`, `CHANGELOG.md`.

Note that `tests/test_manpage.py` tracks only the **top-level** subcommand name —
`usage_names()` matches `^  ([a-z]+)\b` and `section_names()` takes `.split()[0]`.
So `layer`'s sub-verbs are outside the drift guard exactly as `digest --as=`
already is. Extending that test to cover sub-verbs is the honest follow-on and
belongs in this release.

---

## v0.2.5 — aliases, and a second citation scheme that rewrites nothing

### The decision this encodes

The v0.1 corpus cites with `{#xxxxxxxx}`, eight hex characters. `TODO.md`'s
migration plan proposed rewriting every occurrence to `[-](#<new-guid>)`. **That
plan is rejected here**, for two reasons found while designing this:

1. **It deletes its own evidence.** Step 1 of that plan says the `.dj` files are
   the only record that the old handles ever existed; step 3 rewrites them. The
   committed dictionary would then be the *single* record of the mapping.
   Everywhere else this base keeps two independent records of a fact — bytes in
   `storage/` and parsed records in `graph/`; the raw line in `params["log"]` and
   again as parsed nodes.
2. **It is the operation CLAUDE.md forbids.** The rewrite is a *textual* pass
   deciding which `{#x}` occurrences are citations. "Never scan raw file text for
   citations" has already cost something three times, and the stated reason
   `[-](#guid)` was adopted over `{@x}` is that **this corpus quotes its own
   syntax constantly**. So the one corpus least able to survive a textual pass is
   the corpus the plan applies one to — destructively, once.

There is also a lineage argument, and it is the one that decides it: conversations
in that corpus are *about* eight-character handles and *about* the change to link
syntax. Rewrite them and those discussions reference a format that appears nowhere
in the base they live in.

**So nothing is rewritten — not on disk, and not at render time either.** The old
syntax stays exactly as written. What is added is a way to *look it up*.

### The record shapes

```json
{"record":"node","guid":"…","type":"handle",
 "params":{"scheme":"kg-8hex","value":"a3f2b1c4"}}

{"record":"edge","guid":"…","layer":"alias","by":"kg-8hex",
 "type":"names","source":"<handle guid>","destination":"<block guid>"}
```

- `scheme` on the node describes **the format of the name**; `by` on the edge
  describes **what produced the assertion**. They will usually hold the same
  string and they are not the same claim.
- `handle` joins `layer`, `file` and `blob` in `UNCONTAINED`.
- **Asserted, not derived**, by the test `citation_edges()`'s own docstring gives:
  assert what no parser can recover. The old handle-to-block mapping lives in v0.1
  `.dj` assignment lines and is recoverable from nothing in v0.2. So `handle`
  nodes and `names` edges keep minted guids.

**Aliases are not fields on nodes.** An `aliases: []` array would mean editing a
node after minting, which nothing else in this codebase does; it would be
invisible to `check`; it would carry no provenance; and short handles later would
be the same array with a different meaning mixed in.

**Internally, only guids.** An alias can add a name for a node. It can never
change what a guid means.

### `--by kg-8hex` — a parser with the same class of guarantee

Verified against pandoc 3.10 with the project's reader
(`commonmark_x-smart-attributes-fancy_lists`):

```
see {#a3f2b1c4} and `{#a3f2b1c4}` inline.

  Str  "{#a3f2b1c4}"            one whole token, exact
  Code [attr, "{#a3f2b1c4}"]    text at c[1], NOT a Str
```

Every exclusion is **structural**, not a special case:

| case | excluded because |
|---|---|
| inline code | a `Code` node's text is a bare string at `c[1]`, not a `Str` |
| code block | its text is in `params["text"]`; the walker never reads `TEXT_IN_PARAMS` |
| `{#xxxxxxxx}` | `x` is not in `[0-9a-f]` |

The `{@x}` era failed because it regexed `plain_text()`, which **does** fold
`params["text"]` in (`records.py:47`). Walking `content` for `Str` nodes instead
of flattening is the whole fix, and it mirrors `_links()` exactly. The pattern
`\{#([0-9a-f]{8})\}` is self-delimiting, so `re.finditer` over a `Str` handles
adjacent punctuation with no assembly.

**An assignment line is a `Para` containing exactly one `Str`** whose content is
exactly the handle. So the dictionary is built **from the digested graph** — find
those paragraphs, take the `next` sibling as the target — and `TODO.md`'s textual
pre-pass is retired along with its rewrite.

*Unverified, because the corpus is not on this disk:* that the assignment
paragraph **precedes** its block and is its sibling in the v0.1 djot. Confirm
before minting anything.

### The residual risk, which cannot be engineered away

A conversation that says in **prose** — not code — "handles look like
{#a3f2b1c4}", where that hex string is also a real handle, becomes a real edge.
Nothing structural excludes it. This is the exact ambiguity the link syntax was
adopted to remove.

It is an argument *for* the design rather than against it: it is why the legacy
scheme must stay closed, opt-in and droppable, and never the default. **Count the
cases once when the dictionary is built.** A handful is a footnote; forty is a
finding.

### `lookup`

Data-driven, no flag: not a guid, so look for a `handle` node with that `value`
and follow `names`. If the alias layer is not in the base, it fails exactly as it
does today. **`lookup` says which scheme resolved it**, so an exact hit and a
recovered one are never confused.

### Tests

`tests/test_alias.py`. Properties, sabotage-verified.

1. A `{#hex}` in prose yields an edge; **the same string in inline `Code` yields
   none**; in a `CodeBlock` yields none. Sabotage by removing the structural
   guard and confirming failure.
2. `{#xxxxxxxx}` yields nothing.
3. Two `handle` nodes sharing `(scheme, value)` is a `check` problem.
4. Lookup by alias and lookup by guid return the same node, and the alias form
   names its scheme.
5. Dropping the alias layer leaves the `uuid-link` citations untouched.

---

## v0.2.6 — the migration

**Blocked on material that is deliberately not on this disk.** The v0.1 corpus
was removed from the history, not merely deleted, and is kept privately. This
release cannot start until it is supplied.

With v0.2.4 and v0.2.5 in place, the migration becomes an *application* of them
rather than a mechanism of its own:

1. Digest the v0.1 `.dj` files unchanged, `--as=notes`. Not `raw/` — text matching
   recovers 103 of 217 there, because the old canonization normalised text on the
   way to `.dj`. Zero were wrong; half simply do not match.
2. Build the dictionary **from the digested graph**: paragraphs that are a single
   `Str` matching the assignment form, target taken from the `next` sibling.
   ~5839 assignments expected.
3. **Verify no collisions before minting.** `kg check` tested handle collisions in
   v0.1, so zero is expected — confirm, because two blocks answering to one name
   is unresolvable afterwards.
4. Mint the alias layer: `handle` nodes and `names` edges.
5. `compost layer build citation --by kg-8hex`.
6. Commit the dictionary as a plain artifact anyway. It is now a *second* record
   rather than the only one, which is the whole point.

**Acceptance:** every handle resolvable before the migration resolves after; zero
dangling; the count of prose-quoted example handles recorded rather than silently
absorbed.

---

## v0.2.7 — the conversation loop

### What this is not

**It is not an alternative to the transcript importer.** That route exists, is
lossless, follows subagents, and stays exactly as it is — it is how an agent
session gets into the base. This is a *different* source arriving by a *different*
route for a *different* purpose: the round-by-round exchange the human reads in a
browser instead of in a TUI.

Two sources, two routes, two completenesses. They describe the same conversation
and will one day be joined by a `duplicates` layer between transcript turn text
and these round records. **That join is deliberately not built here.**

### Why the envelope is a legitimate source

An earlier draft of this reasoning called digesting `claude --print
--output-format json` "filtering at import". **That was wrong**, and the
distinction matters enough to record. Filtering would be reading the envelope and
keeping only `result`. Digesting the *whole* envelope — `result`, `session_id`,
`total_cost_usd`, `modelUsage`, `permission_denials`, `terminal_reason` — keeps
everything the file says. The rule is about not discarding what a source holds,
never about a source having to be the largest one available.

### Two consequences that make this shape better than the alternative

Both were problems in the design where the *transcript* was re-digested every
round, and both simply do not arise here.

- **Storage is linear, not quadratic.** Each round is one small envelope and one
  small note. Forty rounds is eighty small files. The cumulative-file problem was
  entirely an artefact of re-digesting a growing transcript.
- **Handles never move.** A note digested in round 3 is never digested again, so
  the handle you cited stays the handle on the page in round 20. This design does
  not *solve* re-import identity — it removes the need for it from the daily loop.

**So re-import identity leaves the critical path.** It stays a real gap for the
transcript route (`TODO.md`, *Smaller, but named*), and it stops blocking anything.

### What has to be built

**1. A route for the envelope.** It does two things at once: keeps every envelope
key in params on the root, **and** runs `result` through the markdown reader so
claude's answer is made of addressable blocks. Without the second half you cannot
cite claude's paragraphs, which is the entire point. The answer's text is
therefore held twice — raw in params, parsed as blocks — the same accepted cost
already documented for transcripts, with the same justification.

**Promote `session_id` to a top-level param on the root**, not merely left buried
inside the stored envelope. It is the join to the transcript, it is free at
import, and the lesson is already on the record: the subagent join turned out to
live in a `.meta.json` sidecar nobody knew existed, and the entry claiming the
link had been lost was wrong *because the join had been stored*. Store the join
before anything uses it.

**2. The conversation is a layer.** Notes and responses are separate roots;
something must assert that root A, then B, then C are one conversation in that
order. No parser can recover "these two files were one exchange", so it is
**asserted** — minted guids, written by `compost layer`, droppable, inspectable.
The wrapper asserts it as it goes. A conversation therefore becomes a first-class
thing you can list, drop and rebuild rather than an implicit consequence of
filenames.

**3. The conversation edge cannot be `contains`.** `check` requires a root to have
**zero** parents (`src/records.py:472`), so a `contains` edge into a `document`
would be reported as *document has a parent*. The relation must be its own edge
type in the conversation layer, and `render_all` must consult it to decide those
roots get no page of their own.

Precedent is exact: `launched` already does this for subagent transcripts. Same
mechanism, second customer — which is also the second piece of evidence that
`Graph.linked()` was the right generalisation. Ordering falls out of `next` chains
between the roots, which `records.py:281` already understands.

**4. Append-only comes free.** v0.1 needed explicit append verification —
*"earlier blocks must survive unchanged, structure included, since the seam
failure changes no text"*. Here nothing is ever rewritten: each round is a new
immutable document. Append-only becomes a property of the shape rather than
something to check, and that is a genuine simplification over v0.1.

**5. The wrapper**, outside the CLI. `nvim` on a nameless file, digest, layer
build, render, pipe, digest the response, layer build, render. `--continue`,
`--resume`, `--fork-session` and `--model` are claude's flags and compost has no
opinion about them. Deleting the temp file loses nothing: `digest` has already
copied the bytes into `storage/`.

### The loop, end to end

```
nvim /tmp/xxx.md                      # nameless, wrapper-managed
compost digest --as=notes /tmp/xxx.md
compost layer build                   # citations + conversation
compost render
cat .compost/views/default-djot/xxx.dj | claude --print --output-format json > r.json
compost digest --as=claude-code-response r.json
compost layer build
compost render                        # refresh the browser
```

The payoff closes the chain: claude cites handles it read in the djot, those land
in `result` as markdown links, the parsed blocks contain real `Link` nodes, and
v0.2.4's citation layer turns them into `cites` edges. If claude quotes the
citation syntax inside a code block while explaining it — which it will — that
contributes nothing, by construction.

---

## Open questions carried forward

- **Backlink placement in the HTML view** — per block or per document (v0.2.4).
- **Whether the assignment paragraph precedes its block** in v0.1 djot (v0.2.5,
  unverifiable here).
- **How `represents` and `duplicates` relate to `handle` nodes** — three ways of
  saying two records are about one thing, and it is worth deciding whether they
  are one idea before minting the third.
- **The route name for the envelope.** `claude-code-response` is a placeholder.
- **What `layer build` asserts about an in-flight conversation** — whether the
  wrapper names the conversation explicitly or the layer infers it from
  `session_id`, which only the response roots carry (v0.2.7).

## Beyond this window — discussed, not yet designed

Named so the order is on the record; each needs its own round before it gets a
version.

- **A `duplicates` layer** between transcript turn text and conversation round
  records. Hash equality will not find these — the same prose sits bare in one and
  wrapped in notification envelopes in the other — so it must be asserted or
  derived by something cleverer. Deferred deliberately.
- **A text tree view** before any diagram. `compost tree <guid>`, indented, no
  dependencies, agent-readable. It may answer the "what does compost think a
  title is" question outright and make mermaid-versus-D3 moot.
- **A query layer.** DuckDB over the JSONL in place, with the health assertions
  expressed twice so two independent readings must agree.

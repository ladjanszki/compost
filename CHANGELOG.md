# CHANGELOG

This file overarches versions. Entries below the `v0` marker describe the
LadybugDB-centric architecture that `v0` closes out.

## v0.2.15-rc — AoTA: an artifact that grows

An append-only artifact keeps **one root, forever**. A later ingest of a longer
file adds `contains`/`next` edges to that existing root and mints nodes only for
the tail — no second root, no `revision_of`, no second copy of the head. A
transcript that gained forty turns is not a new transcript
(`docs/design-0.3.0.md` §1).

**What it was worth, measured before it was built:** re-ingesting the six corpus
sessions re-minted **9,217 of 12,987 nodes for nothing — 71%** — and re-stored
369 of 546 fragment blobs. Delta ingest is not an optimisation.

### `mutability` is declared, required, and never changes

`immutable` | `append-only` | `mutable`, required at creation and an error
without it — the same standing `--as` has, and for the same reason: it is a
statement of intent the bytes do not contain. Set once. `--mutability` on an
`--updates` call is an error, because a record that could relax its own contract
is not a contract.

`--updates=GUID` names the root explicitly. "Which of fifty `README.md` files"
has no safe automatic answer, and `record_subtree_hash` is not robust enough to
give one — 13 of 32 cited blocks in a real base shared a hash with another node.
One default *is* derivable and is printed rather than acted on: a transcript is
`<sessionId>.jsonl`, and with the `agent-<toolUseId>` rule beside it the pair
covers **18 of 18** archived transcript filenames.

**Omitting `--updates` still mints a second root, silently.** Principle 10.

### The fold is refreshed, and that is the interesting part

Appending changes the root's fold while the root's own record is, correctly,
untouched — so `check()`'s eleventh assertion fails on every append. The fix is
to rewrite the root's record as a whole-file rewrite, the only honest form of
change to an immutable record. It is cheap because exactly one field on exactly
one node moves: `record_subtree_hash` is *derived*, so refreshing it updates a
cache rather than changing what any record claims, and the root's `record_hash`
— what it asserts — never moves. §1's "the root node itself is untouched" is
amended to "the root's assertions are untouched; its fold is refreshed".

*Rejected: moving the fold to a rebuildable layer.* Cleaner, and it makes the
only content-verifying assertion conditional.

### Two things the spec asked for that could not be built as written

**`check` cannot assert "no edges added to an `immutable` root after the ingest
that created it".** That needs a clock this project decided it does not have:
nodes carry no creation time, `created_at` is audit metadata rather than
semantics, and load order carries no meaning by construction. Shipped instead as
a named **proxy** — an `immutable` root carries at most one `derived_from` edge,
which is the structural trace every such violation made through this tool leaves
behind. A hand-authored `contains` edge spliced on with no second blob is not
caught, and the gap is documented rather than treated as covered. This is
`check()`'s **thirteenth** assertion.

**The roadmap's `n2 < n1 * 1.8` node-count bound is wrong on real material** — a
correct, verified append of `session-02` grows nodes by **1.92×**. It was a proxy
for "the head was not re-minted"; the suite asserts the property directly
instead, that every one of the old nodes is byte-identical in the merged graph.

### `--updates` against a `mutable` root is refused until v0.2.17

The flag's *contract* is settled here — one flag, read by the target's
mutability — so v0.2.17 does not re-litigate it. The `mutable` *behaviour* waits
for `revision_of`. Routing it through the append path meanwhile runs and passes
`check`, and would be silently wrong: an appended `mutable` root inherits the
head-unchanged refusal, so the one contract promising "anything here may change"
would be the one told its start no longer matches.

### `blob_of` had to answer "which bytes", and does so by proxy

A re-ingest stores the whole file again and the root gains a second
`derived_from` (**+10.8 MB per corpus re-ingest**, ~7.7 MB of it bytes already on
disk — accepted and measured, `TODO-storage-revamp.md`). So `blobs_of()` returns
all blobs oldest-first and `blob_of()` returns the current one.

Both order by `imported_at`, **then by guid**. `_now()` records whole seconds, so
two ingests inside one second tied, and the winner fell out of record order —
reversing the records was enough to flip the answer, against the standing
guarantee that load order carries no meaning. The guid buys determinism, not
recency: on a tie it is arbitrary, and says so. The real answer is a `supersedes`
edge blob-to-blob, which is a schema change and is left to the storage work.
`docs/design-blob-currency.md` is the open question written up.

### The cost, and the defect found in the release's own tests

**A test naming a guarantee it does not exercise is this project's most repeated
defect, and this release shipped one before it was caught.** Guarantee 6 — "an
`append-only` root whose head changed is a reported problem" — is answered by two
different mechanisms. `_digest_update` aligns the re-read file and *refuses*,
writing nothing; that is the contract. Inside `check`, a head edited in place
surfaces as a hash that does not recompute, relabelled with the contract's name —
the same signal better attributed, not a second check, since `check` holds no
history and cannot tell a replaced head from ordinary corruption.

Both were built. Only the second was tested. Deleting the ingest refusal outright
left `test_aota` **15/15** and `verify-0.2.15.sh` **11/0** while a tampered file
appended silently and grew the base **499 → 958 nodes**. Found by hand-sabotaging
the implementation after the report said it was fine, which is now the standing
reason that step exists.

The alignment walk follows `contains`, `next` **and `delegates_to`**, and is pure.
Re-measured on the older tree: `session-04` **2,379 of 2,481** nodes reached,
prefix 2,379 of 2,379; the delegation-blind walk reaches **1,323 of 2,481** and
also reports 100% — the same headline over a denominator 1,056 nodes smaller.
What neither walk reaches is `blob` and `file` nodes, `UNCONTAINED` by rule: 102
of 2,481, of which 73 are blobs.

**23 suites green, `test_aota` 18/18, corpus present at 520 documents.** Both
round-trips unchanged: 526/526 and `records_to_session(session_to_records(lines))
== lines`, plus a new one — an *appended* session reconstructs the grown file's
exact original lines.

## v0.2.14 — 2026-09-08 — the recursion made explicit

`src/session.py` did not call the text digestor. It **reimplemented** it: two
`READER` constants holding one string, two functions turning markdown into
blocks, and a reach into `R._block`, a private function, to do what
`ast_to_records` does publicly. `docs/decisions.md` records every flag in those
invocations as load-bearing and measured, so the second copy was a silent
divergence waiting for the first edit to the notes reader.

**A digestor that meets content it does not own delegates to the digestor that
does, and the delegated input is stored as a blob like any other digestor
input.** One rule, no exceptions:

> Every digestor's input is stored as a blob. Every key of that input is a
> param, the node type, a child, or delegated to a named digestor — whose input
> is itself a blob.

That makes totality compositional: each digestor is total on its own format,
delegation composes them, and the pipeline is total by induction. 549 delegated
inputs across seven transcripts, 376 KB against 10.8 MB — 3.5%, median 158 bytes.

### The delegated document is a root nobody contains

The obvious shape — hang the produced `document` under the turn — fails `check`
by construction, because `document` is in `ROOT_TYPES` and a root with a parent
is a reported problem. The turn reaches it through a new `delegates_to` edge
instead, which is the shape a launched subagent session already has: a root
nobody contains, reached from a `toolcall` by `launched`. No node type added, no
invariant changed.

### Borrowed names, and what they cost

`derived_from` is aligned with **`prov:wasDerivedFrom`** (W3C PROV-O), and a
fragment's location uses a **W3C Web Annotation** selector — `RFC 6901` JSON
Pointer, because the parent is a JSON line. A fragment has no filename, so
`original_name` is null and the selector says where inside the parent it came
from. One convention is ours and is written down: a `.jsonl` blob is addressed
as the JSON array of its lines.

Borrowing a name costs something, and the cost is paid rather than assumed.
PROV binds derivation to being irreflexive and acyclic, so those became
**`check()`'s twelfth assertion**. PROV's third constraint — the source
pre-existing the target — is **explicitly declined**, because `created_at` is
audit metadata and there is no semantic clock. The schema records both halves
beside the claim, and a test asserts that every `aligns_with` names what is
enforced *and* what is not, so no name can be borrowed without saying what it
honours.

### The measurement that nearly went missing

The alignment property — v0.2.13's guarantee 5, and v0.2.15's foundation — was
reported as *"100.00%, unchanged"*. It was 100.00% of **half the graph**.
Delegation moves prose out of `contains`, so a walk over `contains`/`next` alone
reaches **52.5%** of a digest: 1,695 of 3,569 nodes unreachable on `session-04`,
among them 348 `Para`, 352 `Plain` and 72 `Header` — precisely the blocks anyone
cites. Measured that way `session-04` goes from 2,306/2,306 before the release
to 1,323/1,323 after, and "still 100%" is true and useless.

Following `delegates_to`, the property is intact: **9,217 of 9,217 across six
sessions, 100.0000%**. The guarantee now asserts two things — the prefix, and
that the walk still covers at least three quarters of the digest — because a
perfect prefix over a shrinking tree is exactly how this gets lost quietly.

A second check had weakened the same way: `test_mapping_totality`'s sabotage
selected its probe fixture on *"has any blocks"*, picked one with no
`tool_use.caller`, and skipped itself — the board went from 2/2 to 1/1 while the
proof that the totality check is non-vacuous stopped running.

### Restored: the release checklist

v0.2.13 deleted three markdown rituals as *policies standing in for a system*.
That was right about where documents go and wrong about the checklist itself,
and this release paid for it immediately: it shipped a twelfth invariant while
two documents said eleven, and an edge type `record-format.md` had never heard
of. `DEVELOPMENT.md`'s *"Closing a version"* has both steps back, with the
destinations changed rather than the steps removed — a retired design document
**moves to the notes repository**, it is not deleted, and the whitepaper freeze
goes there too.

## v0.2.13 — 2026-09-07 — the fold

Every node now carries `record_hash` and `record_subtree_hash`. The release was
specced as something else entirely — a human marking up 59 params, one column,
*is this content?* — and that input turned out to be the wrong thing to ask for.

**A per-type whitelist does not have a fixed cost.** It costs one discretionary
decision per param per type per digestor, and cstlib, graphviz and a filesystem
digestor would each bring dozens of types. The digestor already decides what a
thing is made of, in code that is reviewed and under test. Asking a second time,
in a table, is asking in a worse place. So: **the mapping is the whitelist**, the
hash covers the record, and to change what counts you change the code.

That rule has one hole, and closing it is most of this release. "Hash the
record" and "hash the source" only agree if the mapping drops nothing — and it
dropped three things: `signature` on 492 `thinking` blocks, `caller` on 902
`toolcall`s, and the structure inside a list-shaped `tool_result`. The first had
a visible consequence nobody noticed for four minor versions: every empty
`thinking` node in a base hashed identically, **491 into 1**, because the only
thing distinguishing them was the field the mapping threw away.

**The file-level round trip could never have caught it.** Every line is kept
verbatim in the parent turn's `params["log"]`, so
`records_to_session(session_to_records(lines)) == lines` stayed green while the
nodes were impoverished. The file was whole and the graph was not, and only one
of those was tested. `tests/test_mapping_totality.py` tests the other: every key
of every object a digestor reads must be a param, the node type, or descended
into as children.

### Two measurements that decided the shape

**The fold earns its place on documents, not transcripts.** A container's whole
substance is its children, so its own hash says nothing: all **417
`BulletList`s** in the corpus share one `record_hash`, all 159 `BlockQuote`s, all
1,040 `Cell`s. `record_subtree_hash` cuts those to 144, 60 and 988. It was nearly
cut from this release on the grounds that it had no job; that was measured on
transcripts and did not generalise.

**One derived param defeated alignment single-handed.** `params["lines"]` on the
session root is a count of the file. Truncate `session-04` to 70% and re-read:
the identical prefix is **0 of 2,306** with it and **2,306 of 2,306** without,
because the root is position 0 and a root that fails to match empties the prefix.
Hence the rule — *a derived param may be a function of the node itself, never of
its subtree* — and `lines` is deleted. Re-measured across six sessions under the
new hash: **8,848 of 8,848, 100.0000%**, which is v0.2.15's foundation, taken a
release early rather than assumed.

### What it costs

**Every base written before this release fails `check`, one problem per node**,
and `render` refuses when `check` fails. Re-digesting is not an escape: guids are
minted fresh and every citation would break. `tools/migrate_0_2_13.py` is a
whole-file rewrite — the only honest form of change to immutable records — that
stamps both hashes, renames an edge's `content_hash` to `record_hash`, drops the
old per-node `content_hash` and drops `lines`. It requires the base path
explicitly and refuses to walk up the tree looking for one. It does **not**
retro-fit the mapping fixes, so a migrated base is *valid*, not identical to a
re-digest, and that distinction stays visible.

`check()` makes **eleven** assertions now. The eleventh is the first that
verifies content rather than structure: both hashes recompute from the record and
its children.

### `lookup` no longer drops what an alias names

`lookup` indexed `names` edges into a dict keyed by the alias, so an alias with
two of them reported one target and said nothing about the other. Nothing the
tool writes makes that shape — the citation layer mints exactly one `names` edge
per alias — but that is its convention and not an invariant: `check()` does not
count `names` edges, and an alias with two of them loads with **0 problems**,
verified against a real base. *Anything may write records*; a reader that assumes
more than `check` enforces is the reader that is wrong. Found while designing a
layer that wants one alias to name a whole equivalence class
(`docs/design-naming.md`), and fixed apart from it.

### The whitepaper is now a versioned artifact

`docs/compost.md` carries its version in the status line, and every past version
is frozen unedited under `docs/whitepaper/`. The path of the live document never
moves — `tools/build_whitepaper.py` and two suites hardcode it, and a generator
pointed at a frozen copy would rewrite the history it was keeping.

`DEVELOPMENT.md`'s *"Closing a version"* gains the step that was missing: bring
the whitepaper up to date before tagging. Only its generated appendix is guarded
by a test, so nothing else would have caught a release that changed what a hash
means shipping a paper describing the old one. That step is also where a design
document earns its deletion — anything in `docs/design-*.md` worth keeping has to
reach the whitepaper first or it leaves with the file.

## v0.2.12 — 2026-09-03 — the grammar, untangled

A **markdown document** was the source of truth for what a valid record is, and
the suite that checked it **scraped prose with regexes** — splitting on the
literal string `## 3. Node types`, parsing table pipes, pulling field names out
of backticks. Rename that heading and nothing failed: the suite found fewer
types and quietly asserted less.

The records are JSON. There is a standard way to define and validate a JSON
document's shape. `TODO-code-review.md` keeps the incident as the worked example
of a class, and this release removes it.

### Three layers, each doing what it can

| layer | answers | where |
|---|---|---|
| **JSON Schema** | what may a *record* be | `tools/record-schema-1.json` |
| **`check()`** | what must a *graph* be | `src/records.py`, unchanged |
| **prose** | *why* | `docs/compost.md` |

**`check()` is not replaced and does not shrink.** Its ten assertions are
cross-record — no cycle in `contains`, the `next` chain is a total order,
exactly one parent — and no per-document validator can express any of them.

**The five coverage guarantees survive with their meaning intact**, changing
only their source: `json.load` instead of `text.split(...)`. They are the
valuable half, and no schema expresses them either — *every documented type is
exercised by a fixture* is a claim about a corpus. The regex scrapers are
**deleted**, and a guarantee asserts they are gone.

**Every record in the fixture base is now validated against the schema.**

### Two schema bugs, both found by the machinery working

**Top-level provenance.** `alias` and `unresolved_citation` carry `created_at`
and `tool_version` as top-level keys rather than in `params` — `layers.py`
writes them and `record-grammar.md` documents it as deliberate. The schema had
`additionalProperties: false` and never listed them, so **every alias the tool
produces failed validation.** Found by the implementing agent, which reported it
and named which side was wrong instead of quietly patching either.

**A writer no fixture reaches.** 152 `alias` nodes in a real base carry
`generated_by` and `pandoc` from `tools/v01_dictionary.py`. A schema seeded from
the fixtures never saw them. Adding the params made *documented ⇒ exercised*
fail — which is that check working — so the honest fix was **a fixture**, not
deleting the params.

The lesson is worth the words: **a schema seeded from fixtures describes only
what the fixtures reach.**

### The appendix, and what v0.2.13 reads

`docs/compost.md` gains the grammar as **generated tables**, rebuilt by
`tools/build_whitepaper.py`, asserted current and asserted idempotent. Raw JSON
Schema was rejected on size — 714 lines against the paper's 497.

The last table is **59 params with a blank `content?` column**, grouped by param
rather than by type so a param appearing on four types is decided once. It is
the input that specs v0.2.13's fold.

### What it cost

`tests/test_grammar.py` hardcoded `total = 7` while **8** checks ran — the same
class as `test_manpage`'s `total = 6` last release. **Twice in two releases**, so
it is a confirmed pattern rather than an accident. Both now compute their
denominator.

`CLAUDE.md`'s table stops calling `record-grammar.md` machine-read and names the
schema; the paths test widened to cover `tools/` as well as `docs/`.

`jsonschema` is the third dependency after graphviz and duckdb, and unlike
graphviz it is **required** — a validator that might not be there validates
nothing. Floored rather than pinned, stated as a choice: nothing here measures
version-sensitive behaviour the way those two pins were measured.

## v0.2.11 — 2026-09-03 — the whitepaper

`docs/compost.md`. What compost is, in one document read start to finish: the
abstract, the shape, the principles, the digestors, the records, the renderers,
the symmetry that is the thesis, and the decisions with the measurement behind
each.

### The principles are counted, and they are not invariants

Asked three times across the project's life and never answered: *how many are
there, where do I consult them, and is "invariant" the right word?*

**Fifteen principles. Ten invariants. Different lists, different documents, and
only one of them is enforced by a program.** An invariant is a property `check()`
asserts — you cannot ship past it. A principle is enforced by attention; you can
violate one with every test green, and each of the fifteen was learned by
violating it. Python calls its own list *aphorisms*. Conflating the two makes
the weaker kind sound stronger, which is backwards.

Each principle carries the incident that produced it: the audit that found the
transcript importer dropping 46% of a real file, the suffix routing whose
fallback was not "markdown" but *anything at all*, the prefix resolver that
resolved for a tool and was a dead anchor for a person clicking it.

### The README's opening is the abstract, verbatim

Asserted by a test, so the whitepaper's claim about itself is a fact rather than
an intention — the same reasoning that keeps `tools/queries/*.sql` referenced
from `docs/queries.md` rather than pasted into it.

### `CLAUDE.md` stops claiming one status for all of `docs/`

It said *"what is true now"* and called `spec.md` historical four lines later.
Six rows now, one per kind — the whitepaper, what is true now, what is being
decided now, the part-shipped migration, the superseded drafts, and the material
that is not in this repository at all.

The superseded drafts are named as **superseded and not yet reviewed** rather
than *"worth reading for intent"*. They stay in place until read; leaving them
is not free, and the table now says what they are.

A second test asserts every `docs/` path the table names exists. The
contradiction that opened this release would have been caught by it, and so
would `design-answers.md` being named for two days after it left the repository.

### What it cost

`tests/test_manpage.py` hardcoded `total = 6`, so adding a guarantee did not
move the denominator and removing one would not either — **a test that can
weaken without failing.** The count is derived from the checks that ran now, and
the suite reports 8/8.

The first sabotage of the new abstract test was itself wrong: the phrase chosen
wrapped across a line, so nothing was replaced and the test passed for the wrong
reason. A sabotage that quietly does nothing proves nothing.

### Deferred, deliberately

Splitting `migration.md`, and deciding what becomes of `spec.md`,
`spec-review.md` and `design-answers.md`. And `record-grammar.md`'s headings are
**not** renamed here: `tests/test_grammar.py` discovers the grammar by splitting
on the literal strings `## 3. Node types` and `## 4. Edge types`, so renaming
either would silently make it assert less. That coupling — a markdown document
as the source of truth for a JSON format, scraped by regex — is recorded in
`TODO-code-review.md` as the worked example of a class, and v0.2.12 removes it.

## v0.2.10 — 2026-09-01 — the index page, and a name you chose

v0.2.9 made a document readable. This makes the front page one you can find
something on. It was a flat list of filename stems — **nine of twenty-nine rows
named by a raw uuid**, no dates, no grouping, no counts.

### The sections are generated, never hardcoded

One `<h2>` and one table per member of `records.ROOT_TYPES`, so today
`Documents` and `Sessions` — **the code's words, chosen deliberately as an
irritant.**

Three sections were asked for: transcripts, notes, conversations. The graph can
tell apart two, and measured against a real base the three-way split left **23
of 29 rows homeless** with one section empty — `responds_to` does not exist
there, and 23 documents arrived by `pandoc-ast`. A page reading `Documents: 23`
in a word nobody thinks in is a standing reminder the vocabulary is unfinished.
The real fix is v0.3.0's declared artifact kinds, at which point the sections
become the kinds.

**Hardcoding the pair would have defeated the reason for choosing it.** If the
code gains a third root type and the page still shows two, the page has stopped
reflecting the internals — the exact failure the labels exist to make visible.
So a guarantee monkeypatches `ROOT_TYPES` to add a type and asserts the page
grows a section.

**`render_all`'s own root filter had the same bug**, outside the letter of the
plan and inside its point: it hardcoded `("document", "session")`, so a third
type would have got a section on the index and no page behind it. A section list
and a page list disagreeing is worse than either being wrong alone.

### A display name is a record, not something read out of the file

A heading-derived title would have named **17 of 24** documents for free, and
was rejected: a name that changes when the prose changes is a reminder
pretending to be an identifier, and a view reaching into a document to invent
one is implicitness this project refuses elsewhere.

So a display name is its own `display_name` node, joined to the root by a
`names` edge in a new `display` layer — not a field on the root, because records
are immutable and the root is not ours to edit. It is **not** a reuse of
`alias`: an alias answers *what does this string resolve to*, a display name
answers *what should be shown for this node*, and overloading would put display
names into `lookup`'s resolver.

`display_name` joins `records.UNCONTAINED`. **That is the one line of
`src/records.py` this release touches** — a constant, not the reconstruction
path, and the round-trip stays at **526/526**.

Several names may point at one root; nothing collapses them in the records. The
view takes the newest by `created_at`, ties broken by guid, so the page is
deterministic. Collapsing in a view breaks no rule.

### `compost-name`, in `extras/`

```
compost-name <root-guid | storage-name> "The display name"
```

Installed, but not the tool — the same standing as `compost-new`, so the
subcommand count `docs/man-compost.md` asserts does not move. **Not the CLI
surface `CLAUDE.md` forbids:** that rules out `compost layer alias`, a
*subcommand of the tool* editing records; a separate script writing a
well-formed file into `graph/` is the blessed path.

A storage name resolves through the `blob`'s `stored_as` and its `derived_from`
edge — **never** by parsing a filename into a guid. It refuses a non-root, an
unknown identifier and an empty name, and **runs `check` on what it wrote**,
because a writer outside the tool is exactly the case `check` exists for.

**Each run writes a new file and never edits one.** Renaming is running it
again; older names stay as the record of what the thing was called, which is
what makes newest-wins the natural read rather than an arbitrary one.

### What a row carries, and what it cost

Sessions show first and last turn, session id and source. Documents show words
and **`imported`, with the word on the page** — a `document` root carries no
timestamp at all, so the only date reachable is the `blob`'s `imported_at`,
which is when it was fed in rather than when it was written. One column called
*date* covering both would have been a quiet lie.

**The dates shipped raw and were caught in review:**
`2003-08-05T16:30:57.370Z` in a table cell. The spec asked for date columns and
never said what a date looks like. `_when` now trims to minutes **for display
only** — the record keeps every digit, and a string that is not ISO-shaped
passes through rather than being guessed at.

### Also

Duplicate roots each keep their own row; collapsing them needs revision chains,
and these duplicates are the evidence v0.3.0 is being designed from. Filtering
was cut and the thing actually wanted recorded instead — **full-text search**,
in `TODO.md` under *Known gaps*. The `prefers-color-scheme: dark` branch is
deleted and every colour token kept, so the page is the light, Wikipedia-like
one v0.2.9 restored the palette for.

### Guarantees

Sixteen, in `tests/test_views.py` and `tests/test_extras.py`, each made to fail
on purpose first. One is deliberately **not** encoded: *"the diff on
`records.py` is one line"* passes trivially on a clean checkout and can never
hold again once committed, so it is a review check rather than a suite
guarantee, and `test_records` covers the half that is durable.

## v0.2.9 — 2026-09-01 — the view a person can actually read

The first release aimed at the page rather than the records. `TODO.md`'s bar is
*a version marks a change in what the tool can do*, and what the tool could not
do was **tell you who was speaking**.

### The v0.1 affordances, recovered rather than reinvented

`src/render/to_html.py` was deleted whole in `e9f189c` when the rewrite moved
in. It is 407 lines at `e9f189c^` and every affordance restored here was read
out of it: the `mousemove` + `closest()` highlight, the shift subtree, the
geometry-free click, and the toast that shows what it just copied.

Highlighting stays JavaScript rather than becoming CSS `:hover`, because blocks
nest — a `Para` in a `ListItem` in a `BlockQuote` is three nested `.block` divs
and `:hover` matches all three, lighting a whole quotation to point at one
sentence. `closest()` resolves the smallest containing block, which is why v0.1
felt precise.

**Shift restores the highlight and not the copy.** `{#8hex+++}` was v0.1's
subtree *citation syntax*; v0.2 resolves no such thing, so shift-copy would have
the tool minting dead anchors. The clipboard gets `[-](#guid)` either way. For
the same reason the subtree highlight now shares one colour with the block
highlight: v0.1's second colour was a warning that the clipboard was about to
differ, and it no longer does.

Clicking anywhere in a block copies. The previous handler computed the cursor
position and returned early on any window wider than 992 px, so block-body
clicking existed and was switched off for exactly the window size in daily use.

### What the gutter was actually doing

`.block::before { content: attr(id); left: -5.6rem }` was written when
`HANDLE_LEN` was 8. It is 36. A 36-character monospace string needs about 16 rem
and had been spilling across the text it annotated. It now shows a fixed hint.

### Slash commands render as slash commands

Measured on a real base: **7 commands, 4 sessions, 21 turns, 21 paragraphs**,
always three adjacent turns of one `Para` each — caveat, command, stdout — and
never one with more than one child. That regularity is what licensed acting on
it.

Recognition is **structural**: the first inline being a `RawInline` of format
`html` whose text is one of three harness-reserved opening tags. Never a
substring search over prose — the same standing as *never scan raw file text for
citations*.

The caveat renders as **nothing**. It is an instruction addressed to the model,
and an `author="human"` frame around it puts words in the human's mouth. The
command renders as one line and keeps its handle, so it stays citable. The
stdout folds in HTML and is bare in djot, with ANSI SGR sequences — real, from a
live transcript — stripped in the view only.

**All of it is view-time.** Every suppressed paragraph is still a node, still
carries its guid and its `params["log"]`, and still resolves through `compost
lookup`. The transcript route stays lossless by property. A turn whose children
all render to nothing now renders to nothing, which generalises the envelope
rule and is what stops seven suppressed caveats leaving seven empty frames.

### What it cost: two dead selectors, both silent

**pandoc's HTML writer `data-`-prefixes a Div's non-standard attributes.** So
`author="human"` in the AST reaches the page as `data-author="human"`, and the
shipped `.turn[author="human"]` rule matched nothing on any page v0.2 ever
rendered. The roadmap said human turns got a blue rule and assistant turns grey;
they all got grey. v0.1 wrote its HTML through `djot.js`, which does not prefix
— so the selector was correct in the file it was copied from and dead in the
file it was copied to.

Then the same shape again from the other direction: v0.1's authors were `claude`
and `agent`, and this vocabulary is `human`, `assistant`, `envelope`
(`docs/record-grammar.md` §6). Ported verbatim, two more selectors matched
nothing, and assistant turns kept the default grey through an implementation
that passed every guarantee the design had written.

**So "port the v0.1 CSS verbatim" is the wrong instruction wherever a value or
an attribute crosses a renderer boundary.** Guarantee 14 exists because of it:
no `[data-author…]` selector may name a value outside the closed vocabulary. A
dead selector is silent, which is what makes it a property rather than a review
note.

### Also

`digest` prints whole guids. It had been printing an 8-character prefix that
`lookup` refuses — an identifier the tool would not accept back from you.

`src/views.py`'s module docstring claimed handles were the first 8 hex
characters, false since the guid became the handle, and `CLAUDE.md` asserted
this repo has no `.compost/`, which is true on a clone and false where the base
is symlinked in. Both corrected; an agent had already believed the second one
over a two-second check.

### Guarantees

Fourteen, across `tests/test_session_views.py` and `tests/test_views.py`, each
made to fail before it was made to pass. `shown()` became the general recursive
rule rather than an envelope special case, and `html_collapses` now balances
outputs + calls + subagents + stdouts. `src/records.py` is untouched, so the
round-trip property is safe by construction: **526/526 identity**.

## v0.2.8 — 2026-08-27 — a query layer, and a flat graph

Landed on `main`, no version chosen yet — `DEVELOPMENT.md`, "Closing a
version". v0.2.8's content, a query layer with no subcommand plus a
convenience wrapper, does not clear the bar `TODO.md` sets for a tag: a
version marks a change in what the tool can do.

### `graph/` becomes flat by rule

Subdirectories under `graph/` were permitted, read, and used by nothing —
`Store.files()` globbed with `rglob` and `Store.write()` created parent
directories on demand, so a graph file moved to `graph/nested/deeper/` still
loaded and `check` still passed. Closed ahead of everything else below it:
a read-only SQL view over the same directory has to glob it too, and a file
visible to one reader and not the other would be a silent disagreement about
what the graph is, for a reason having nothing to do with whatever is being
checked. `files()` now globs rather than walks; `write()` refuses a relpath
naming a subdirectory rather than creating one.

### A read-only SQL view over `graph/*.jsonl`, via duckdb

No subcommand, and this document is not asking for one. `tools/graph_sql.py`
connects duckdb to `.compost/graph/*.jsonl` in place — `read_json` over the
whole glob, `map_inference_threshold=0` — and nothing is ever materialised:
no `.duckdb` file is written, and closing the connection leaves nothing
behind. `layer` writes derived records into the graph; this writes nothing
at all.

`tools/queries/*.sql` holds executable queries, referenced from
`docs/queries.md` rather than embedded in it, so the copy that runs cannot
drift from the copy that is read. Four starting queries — node count, edge
count, unresolved-citation count, how many nodes have an alias connected —
and six SQL twins of `check()`'s branches: duplicate guids, dangling edges,
the three parent-count invariants, a session launched by more than one tool
call, `content_hash` presence, and `schema_version`. `tests/test_query.py` is
the twin-assertion test this release is for: each twin is required to name
the exact guid(s) `check()` names on a sabotaged fixture, not merely agree on
a count. Three of `check()`'s branches are not mirrored, and
`docs/queries.md` says why — the handle-collision check cannot fire under the
current guid format, and the containment-cycle and next-chain-ordering
checks are graph-path problems a faithful mirror would need a recursive CTE
to answer correctly, which was not attempted rather than shipped untested.

The dedup bridge is `SELECT DISTINCT` over the whole row, mirroring
`Store.load()`. `count(DISTINCT guid)` was measured and rejected: a base
holding a byte-identical duplicate file and a base holding a genuine guid
conflict report the identical `count(DISTINCT guid)` — it cannot tell them
apart, where the row-level bridge can.

`duckdb=1.5.5` is now pinned in `environment.yml`, conda-forge — the version
every measurement above was taken against, same reasoning as graphviz's exact
pin. Optional at test time: absence skips cleanly and says so, the same
pattern `test_draw.py` already uses for graphviz.

### `extras/` — installed, but not the tool — and `compost-new`

A third bucket beside `src/` (installed, reachable from `cli.py`) and
`tools/` (never installed): a user-facing convenience wrapper that should be
on `PATH` after `pip install -e .` without being a `compost` subcommand, so
`docs/man-compost.md`'s subcommand count does not move. `compost-new`, its
first inhabitant and never `compost new`, mints a scratch filename the way
`graph/` and `storage/` names already are, opens `$EDITOR`, and digests the
file as `notes` on close. `DEVELOPMENT.md` gets the rule for what belongs
here: nothing is lost if it does not exist.

### Suites

Twenty-one. `test_query` and `test_extras` are new; `test_store` gains two
properties for the flatness rule.

## v0.2.7 — 2026-08-26 — a graph view

Landed on `main`, not shipped. It gets a version number when one
is tagged, and not before — a heading naming a version with no tag
behind it is a planning bucket wearing a release number, which
`tests/clean-room.sh` refuses.

### `compost draw`, and graphviz becomes the second system dependency

A tenth subcommand: `compost draw [ROOT]` writes a Graphviz picture of the
base — every node, every edge, no collapsing policy — to `.compost/graphviz/`,
a peer of `graph/`, `storage/` and `views/` rather than a subdirectory of the
last one. The direction of the dependency runs the other way: a future HTML
view will *embed* this SVG, so graphviz output is an input to `render`, not
one of its products.

**DOT is always written; SVG only when the layout engine is on PATH.** That is
the property that earns the new dependency at all — the DOT is a complete,
readable deliverable on its own, so the graphviz binary stays optional rather
than required, and nothing makes the SVG a precondition for writing the DOT.

Defaults to `twopi`, not `dot` or `sfdp`. Measured against a real base:
`dot` — the everyone-reaches-for-it default — was killed at a 180-second
ceiling on a single 500-node graph shaped like compost's `contains` tree plus
`next` chain, and again on a single 2,773-node document. `twopi` lays that
same shape out radially, correctly matching what it is, and was 7x faster
than `sfdp` at 20,000 nodes. `sfdp` and `dot` stay selectable with `--engine`
for a citation-heavy graph or a small scoped subgraph respectively.

A whole-base picture gets a synthetic `__root__` node, joined to every
`document`/`session` root so the radial layout has one centre for the whole
forest. It is DOT-local — never a record, never written to `graph/`, never
reaching `check` — the same relationship a view's handle has to the graph it
decorates.

Every edge carries `class="<layer>"`, its record layer rather than its type,
so a citation overlay can be isolated from the structural graph later without
re-deriving it from a flat file. Every node carries `id="<guid>"`, which
survives into the SVG as `<g id="…">` — graphviz escapes a guid's hyphens on
the way out (`&#45;`), so a test that greps the raw SVG for a plain guid gets
a false negative; asserting this needed an XML parser, not a substring match.
No `subgraph cluster_`: measured, `twopi` ignores clusters entirely.

Past roughly 5,000 nodes the SVG gets large — one real base measured 16.9 MB
at 12,632 nodes — so past that threshold `draw` **warns and still writes it**.
Output size, not layout time, is the ceiling, and there is no node count at
which withholding the SVG outright beats saying so.

**Graphviz 14.1.2 is now pinned in `environment.yml`**, conda-forge, 231 MB
and 51 packages — measured, not the 50–100 MB estimated going in. A second
tool whose version silently changes its output is a trap this project already
knows from pandoc; graphviz gets the same treatment from day one rather than
after an audit finds it.

Nineteen suites. `test_draw.py` sabotage-verifies the load-bearing properties
directly: a `draw` that only writes the DOT once the SVG has succeeded (the
bug the whole design forbids), a `class` carrying an edge's type instead of
its layer, a node missing its `id=`, a `subgraph cluster_` sneaking back in,
`check` disabled, and a stale-sweep that leaves a planted file behind — each
one caught, each one restored.

## v0.2.6 — 2026-08-26 — the conversation loop

### `tools/v01_dictionary.py`, and this repo gets a base

The migration's two remaining pieces, promoted from one-off scripts to tools
with suites. `v01_dictionary.py` reads a digested base and writes the legacy
handle to guid mapping as `alias` nodes and `names` edges — a direct read of
the records, no text matching. `--dry-run` reports the count without writing,
which is what catches a dictionary short by 767 before anything is minted.

**Only handles something cites, by default — 152 rather than 6,601.** The
corpus assigns 6,601 and cites 159, so a full dictionary is 13,202 records
answering about two hundred questions. Measured both ways against the real
corpus, resolution is identical — 206 cites, 7 placeholders either way — and
the base is 6,449 nodes and 4 MB smaller. A suite property asserts that
equivalence, because if the filter ever drops something load-bearing that is
where it must surface.

Nothing is lost, which is why it is the default and not a flag: the handle is
on the block, in `params["attr"][0]`, and the dictionary is an index over data
that stays in the base. `--all` rebuilds it whole. The cost is that the filter
is a snapshot of what was cited when it ran — a document imported later, citing
a handle nobody had cited before, will not resolve until it is rebuilt, and
nothing detects that.

A handle appearing on two blocks is **reported, never picked**. The v0.1 corpus
has none — 6,601 ids, 6,601 distinct — and the check exists so a corpus that
does say so rather than silently choosing.

Running it twice is redundant but not harmful: two aliases for one handle name
the same block, and destinations are collected into a set, so nothing becomes
ambiguous. Asserted, because the opposite would make a re-run corrupt a base.

**This repository now has a `.compost/` of its own**, which it has never had.
It is a symlink into a local-only git repository, so the base gets full version
history while never entering this one — the notes and conversations in it are
the human's working knowledge, and this repo has already had personal material
purged from its history once.

`.gitignore` matches `.compost` with **no trailing slash**. Git stores a symlink
as a blob rather than a directory, so `.compost/` would not match it and the
link itself would have been tracked.

### `compost digest --as=claude-code-response` — the conversation loop

A second source describing the same conversation the transcript importer
already reads, arriving a different way: instead of `claude`'s own session
log, a `claude --print --output-format json` envelope, wrapped with the guid
of the note it answers. `docs/roadmap.md`, "the conversation loop", has the
design; this is what shipped from it.

The input is a one-key wrapper the loop writes, because the wrapper already
knows the note's root guid at the moment it calls claude:

```json
{"responds_to": "<the note's root guid>",
 "follows":     "<the previous round's response root>",   // optional
 "envelope":    {...21 keys, verbatim...}}
```

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

**Every one of the envelope's 21 keys lands in `params`, unrenamed** —
`is_error`, `total_cost_usd`, `permission_denials`, `usage`, all of it —
CLAUDE.md's digest-everything rule applied to a source that happens to be JSON
rather than markdown. `params["uuid"]` is deliberately left as the envelope's
own identifier rather than renamed, even though it sits one key away from the
record's own `guid` and looks like a bug: renaming it on the way in would stop
the route being a faithful copy of what claude printed.

**`result` goes through the same markdown reader `notes` uses**, so a
response's paragraphs become citable blocks like any other document's —
without that step you could read an answer but never cite a sentence of it,
which would have defeated the reason this route exists.

Two new edges join a response to what it answers, in a new `conversation`
layer: `responds_to`, from the response root back to the note; `next`, from
the note to the response, for reading order. **Neither is `contains`, and there
is no container node.** `check` counts parents from `contains` alone
(`src/records.py:493-496`), so a note and its response stay two independent
roots — each keeps its own page — and joining them needed no new machinery. A
container was considered and rejected: `ROOT_TYPES` roots must carry zero
`contains` parents, so a node holding both would fail the very rule that makes
a root a root.

**`_digest` now refuses a structural guid that is not in the base.** Extending
its existing two-phase promise — nothing is written until every input has been
read and parsed — by one more check: every edge endpoint a route mints must
resolve against the batch being written or the base already on disk, or the
whole file is refused before anything is written. This is deliberately
different from a citation, which may legitimately point at something not yet
in the base and gets an `unresolved_citation` placeholder from `compost layer
citation` — a `responds_to` naming a guid nobody minted is not a fact about the
world, it is a bug in whatever wrote the wrapper, and letting it through would
have written a dangling edge straight into the graph. The property is
sabotage-verified: disabling the new guard and re-digesting a wrapper with a
fabricated `responds_to` does write the bad edge, and `compost check` then
catches it — proof the guard was doing real work, not decoration.

**`tools/loop.py`**, not a subcommand and never will be one, turns
`docs/roadmap.md`'s "the loop, end to end" shell pipeline into one function.
It exists because two of that pipeline's steps are traps rather than plumbing:
the round's filename has to be unique every time, because reusing one makes
`view_names()` (`src/views.py:372-375`) silently rename the *previous* round's
view out from under an open browser tab; and `digest`'s printed `root <8 hex>`
is a display prefix, not a citable guid, so the wrapper reads the whole thing
back out of the graph file `digest` just wrote rather than growing the CLI a
new surface for one caller.

Both traps are reproduced directly in `tests/test_loop.py`, not just quoted
from the roadmap: one case digests two documents under one shared stem and
shows `view_names()` renaming both, and another swaps in a `root_of` that
answers the wrong guid and shows the next digest refuses rather than
mis-wiring the conversation.

`tests/test_response.py` (13 properties) and `tests/test_loop.py` (9)
join the suite, eighteen in total.

## v0.2.5 — 2026-08-25 — tools/, and the legacy handle scheme

### `compost layer citation --by kg-8hex` — the v0.1 handle scheme

The second customer of v0.2.4's naming machinery, and **no new record types**:
`alias`, `names` and `unresolved_citation` are reused with `by: kg-8hex`.

**Nothing is rewritten.** The v0.1 syntax `{#a3f2b1c4}` stays exactly as
authored, on disk and at render time. An earlier plan rewrote every occurrence
to `[-](#<new-guid>)` and was rejected: it deletes its own evidence, it is the
textual pass this project forbids, and conversations in that corpus are *about*
eight-character handles — rewrite them and they discuss a format that appears
nowhere in the base they live in. This adds a way to look the old syntax up,
and nothing else.

Three forms, all naming one handle: bare, the expansion marker `{#a3f2b1c4+++}`,
and the version pin `{#a3f2b1c4@ver}`. The suffix is not part of the name.

**The match runs within each `Str` of the parsed content, never against whole
tokens.** Measured through the reader over the fixtures and the fetched corpus:
242 occurrences found, against 144 for whole-`Str` equality — **98 of them, 40%,
sit mid-sentence with punctuation attached** (`{#aa813aa9}.`, `{#330f8531}:`)
and an earlier draft specifying equality would have dropped every one without
saying so.

**Handles inside code are excluded structurally, not by a rule.** A `Code`
node's text is a bare string and a code block's lives in `params["text"]`;
neither is ever a `Str`, and the walk never opens either. That is the whole fix
for the `{@x}` era, which scanned flattened text and mistook fenced examples for
citations three times. `{#xxxxxxxx}`, `{#handle}`, `{#uuid:hash}` and `{#...}`
fail on `[0-9a-f]{8}` rather than on a clause someone has to maintain.

There is **no assignment rule**, and none is needed: read as djot a v0.1 block
carries its own handle as an AST `id`, which never reaches a `Str`. Only
citations are text.

#### A placeholder that can actually resolve

An 8-hex handle is not a guid, so it resolves through an **alias dictionary**
that arrives from outside the tool. Unlike a `uuid-link` placeholder, a
`kg-8hex` one is therefore resolvable: build before the dictionary lands and
every handle gets a placeholder; add it, rebuild, and the same handles mint real
edges. The earlier placeholder is kept — the record of a moment when it did not
resolve is not retracted.

A `names` edge pointing at an `unresolved_citation` is **never followed**, so a
build's own placeholders can never become the next build's answer. Without that
rule each pre-dictionary build adds a candidate, growth is quadratic in build
count, and every handle is permanently ambiguous.

Two aliases naming two *different* real blocks is **ambiguous**: the handle
mints nothing and the run says so, because a handle that mints no record looks
exactly like one nobody cited.

#### Measured against the real v0.1 corpus before tagging

The scheme was exercised end to end on the 23 private `.dj` files, read-only,
into a scratch base that was then discarded — not the migration, its rehearsal.
All 23 parse as djot; `digest --as=pandoc-ast` produces 10,973 nodes with zero
`check` problems; the AST carries **5,834 handles with zero collisions**, and
the record level agrees, so nothing is lost on the way in.

`compost layer citation --by kg-8hex` then minted **206 cites edges, 110 of
them to real blocks**, with 96 into 74 placeholders and nothing ambiguous.
Built three times, identical each time — the rule that a build never follows
its own placeholders holds at 5,834 aliases, and accumulation stays linear.

Two predictions survived to the digit: 206 surviving citations and 159 distinct
cited handles. The recorded block count of 6,741 did not, and the first attempt
to correct it — to 5,834 — was also wrong: that is what *pandoc emits*, not what
the corpus holds. The corpus assigns **6,601** handles outside code fences, and
the gap between the two numbers was the defect below rather than a counting
error. Corrected to 6,601 in all three documents.

Then a second pass found the first pass had been wrong about *why* 96 of those
citations failed to resolve. They do not point outside the corpus. **`pandoc
-f djot` silently drops a block attribute at the start of a list item when a
blank line separates it from the content** — which is how the v0.1 canonizer
wrote every handled list item:

```
- {#1221ba74}

  Volume. One session in that directory is 2.8 MB, because …
```

The text survives and only the identity is lost, so nothing looks wrong. It
costs **767 of 6,601 handles, 11.6%**, and 74 of the 159 distinct cited handles
were among them.

`tools/dj_prepare.py` deletes that one blank line on a **copy** — sources are
never opened for writing — and the handle becomes a `Div` wrapping the item's
content, which is what every other handled block in the corpus already is. This
repairs pandoc's *input*; `CLAUDE.md` forbids repairing its output, and the
round-trip property is untouched because whatever pandoc emits is still
reproduced exactly.

| | before | after |
|---|---|---|
| handles surviving | 5,834 | **6,601** |
| citations resolving | 110 / 206 — 53% | **197 / 206 — 96%** |

**The remaining 9 are genuinely unresolvable and the ceiling is 96%**: six
handles are cited up to 17 times each and assigned nowhere in the 23 files, and
one appears only inside quoted JSON in a code fence.

`commonmark_x` was measured against this, since it reads `{#id}` too and would
need no repair. It resolves 207/207 — and the number is inflated. It mints ids
for handles that are assigned nowhere, as **empty inline `Span`s**, so those
citations resolve to nothing real. It also leaves **4,251 `:::` fences as
literal text** and loses 170 turn divs. The djot reader's 96%, honestly earned,
beats a 100% that includes false matches and destroys turn structure.

#### `--by` now has a written-down default

`DEFAULT_BY` names `uuid-link` per layer. Until now `citation` had a single
scheme and a bare `compost layer citation` fell through to it; adding a second
would have turned that into `--by is required` and broken every documented
invocation. **`kg-8hex` is opt-in and is never the default** — it recognises
eight hex characters in prose, so a conversation that says in words "handles
look like `{#a3f2b1c4}`" mints a real edge when that string is also a real
handle. Nothing structural excludes that, which is why choosing it is deliberate.

`tests/test_layer.py` goes from 8 properties to 16.

### `tools/` — what is not the tool stops shipping with it

`pyproject.toml` declares `packages = ["src"]`, so every module in `src/` was
installed into the environment of anyone running `pip install -e .`. Three had
no business being there: `bleach.py` and `bleach_session.py` lorem-ise
fixtures, and `roundtrip.py` is the pandoc fixed-point harness. None is
reachable from `cli.py`, which dispatches only to `store`, `views`, `layers`
and `serve` — yet all three shipped.

They now live in `tools/`, importable from a checkout and installed nowhere.
`python3 -m src.roundtrip` becomes `python3 -m tools.roundtrip`; nothing else
a user runs changes.

The rule behind it is written into `DEVELOPMENT.md` rather than left implicit:
**every module in `src/` is reachable from `cli.py`.** The migration's
dictionary script is a one-off that must never become a subcommand, so it
needed a home that is not `src/` before it was written.

## v0.2.4 — 2026-08-24 — the citation layer, and the naming machinery it needs

`records.citation_edges()` was written, tested, and never called by anything
in `src/`. A `[-](#guid)` in a digested document minted no edge, and
`compost lookup` could not say what cited a block. This release wires it in —
`compost layer citation`, a second writer to `graph/` alongside `digest` —
and builds what wiring it required: a version field on every record, edge
provenance and hashing, and two node types for a citation whose target is
not (yet) in the base.

### `compost layer`

```
compost layer                        list what can be built
compost layer NAME [--by SCHEME]     build it
```

`compost layer citation` reads every `[-](#guid)` link in the whole loaded
base and mints a `cites` edge for each one that resolves. Resolving against
the *whole* base, not a single `digest` batch, is the reason this is a
command of its own: a citation routinely points at a guid from an earlier
import, and `_digest` validates a batch in isolation on purpose.

A target not in the base cannot become an edge — a dangling endpoint fails
`check` and would take the whole graph down. Before this the absence had
nowhere to live: not in the text, not in the graph, only in terminal output
that scrolled away. Now it becomes one `alias` node (naming the missing
value) and one `unresolved_citation` node it points at, per *distinct*
unresolved value in the run, plus a `cites` edge from every citing block into
that placeholder — two citations of one missing handle share one placeholder.

**Running the builder twice writes two complete sets of records.** `layer`
never reads what an earlier run wrote, so nothing is deduplicated and nothing
is removed. That is the release's central decision, not an oversight: see
`docs/roadmap.md`, "the tool does not hold your hand", and
`tests/test_layer.py`, which asserts the doubling on purpose so nobody
"fixes" it later.

### `compost lookup` reports citations

- Resolves an **alias** when the argument is not a guid in the graph — every
  alias sharing a value is printed, never one picked silently, naming the
  scheme that resolved it.
- Reports every `cites` edge whose destination is the node.
- Also reports a citer that only reached a **placeholder** naming this guid,
  labelled apart. Without this, a block that genuinely *is* cited would say
  "nothing cites this" the moment its citing edge points at an
  `unresolved_citation` minted before the block existed — which is never
  retracted once the real target arrives.

Not gated on `compost layer citation` having been rebuilt; on a stale base
this under-reports rather than lies, the same accepted risk `lookup` already
carried by not gating on `check`.

### `schema_version`, `by`, `created_at`, `tool_version`, `content_hash` on edges

Every record now carries `schema_version` (currently `1`); absent means `1`
by definition, so no existing base needs rewriting, and the field is what
lets a future schema 2 sit beside schema 1 during a migration that rewrites
only what changed shape.

Every edge — ingest-time and built alike — now also carries `created_at`,
`tool_version` and a `content_hash` of its own:

```
content_hash = sha256(canonical(edge − {record, guid, schema_version,
                                        content_hash, created_at, tool_version}))
```

The exclusion list is deliberate and found the hard way: an earlier version
hashed every property, so the same citation built twice — with a different
`created_at` — hashed differently, defeating the one thing the hash is for.
It makes two edges stating the same fact *findable* later; nothing collapses
them now, and a `cites` edge into a placeholder is outside its reach anyway,
since a placeholder gets a fresh guid every build. `content_hash` is evidence
for a future dedup design, not a mechanism anything acts on today.

**Measured cost**, over the 972 records `tests/fixtures/` produce: `+27.1%`
overall, `+78.8%` on edges, because three fields land on a record whose mean
size is 213 B. Re-verified independently against the full 520-document test
corpus: `+78.8%` on edges again, `+22.1%` overall — lower, because real
documents run node-heavy relative to the fixture set, and only edges gained
the three big fields. Storage is not being optimised for; both numbers are
published rather than the flattering one.

### `Graph.linked` keeps `by`

`Graph` used to index every non-`contains`, non-`next` edge by type and
source alone, discarding everything else the record said — including `by`,
which is exactly what would let a view tell an exact citation from some
future legacy one apart. `linked()` now returns edge records, takes an
optional `by=` filter, and its one caller (`views.py`'s subagent rendering)
was updated to match.

### Everywhere else

- `alias` and `unresolved_citation` join `UNCONTAINED` — pointed at, inside
  nothing, like `file` and `blob`. Neither carries a `content_hash`.
  Provenance (`created_at`, `tool_version`) is top-level on both, decided
  once here: it would be harmless for these two hash-less types but would set
  a precedent that breaks the day a hashed node type needs provenance.
- `records.citation_edges()` now reports each unresolved target as
  `(handle, citing guid)` rather than a bare handle, since a layer builder
  needs to know where an unresolved citation came from.
- `docs/record-grammar.md` documents the new fields and node/edge types, and
  gains a tenth `check()` assertion: `schema_version`, when present, may not
  exceed what this tool writes — the only way that can fire is a newer tool's
  records loaded by an older one.
- `tests/test_layer.py` is new: eight properties over two bases, every one
  sabotage-verified. `tests/test_citations.py` gains the case only the real
  pipeline can exercise — a citation across two separately digested
  documents, resolved by `compost layer citation`. `tests/test_lookup.py` is
  substantially rewritten: its old property asserted that a lookup names
  *only* the node asked for, which is the opposite of this release.

## v0.2.3 — 2026-08-21 — transcripts stop filtering, bring their subagents, and show them

`--as=claude-code-transcript` was discarding **46% of a real transcript** and
nobody could see it. It is now lossless, and the guarantee is a property:

```
records_to_session(session_to_records(lines)) == lines
```

Exact, over 8 fixture sessions and 4204 lines across 13 line types.

### What was being dropped

Audited against one real 796-line log:

- **369 of 796 lines (46.4%)** — only `user` and `assistant` reached the graph.
  `attachment` alone was 184 of them, the second most common line type in the
  file.
- **Seventeen log-line keys.** A turn kept `author`, `timestamp` and `uuid`;
  `isSidechain`, `userType`, `entrypoint`, `cwd`, `sessionId`, `version`,
  `gitBranch`, `session_id`, `requestId`, `effort`, `promptId`,
  `toolUseResult`, `sourceToolAssistantUUID`, `permissionMode`, `origin`,
  `promptSource` and `classifierMetaLines` did not.
- **140 whole `user` lines** via the envelope rule. Their content survived — a
  `tool_result` folds into its toolcall — but the line's identity went with it.
  Recognising an envelope is about what to *call* it, never about whether to
  keep it.

None of it was data loss in the strict sense: `storage/` had the bytes. It was
a base built on a filtered log, with nothing to show what was missing.

### What replaced it

Every line becomes a node carrying its own original JSON in `params["log"]`.
Two things now live in the graph and they are different on purpose: `log` is
the line as it was and never changes; the nodes and edges are what compost
understood of it and may improve.

A line type with no reading becomes a **`logline`** — *kept* and *understood*
are different claims, and an importer only gets to make the first. An
unrecognised message block becomes a **`contentblock`** and is **shown**, since
the point of storing it is to notice it exists; the old `else` was silence.

Accepted cost: a message's text is held twice, raw inside `log` and again as
parsed blocks. Raw is the source, parsed is the derivation — the relationship
`storage/` already has with the graph.

Views are unchanged. Loglines and empty envelope turns are stored, addressable
and deliberately not rendered, the same treatment empty `thinking` nodes
already had.

### A transcript brings its subagents with it

Digesting a Claude Code log now digests the subagent transcripts it names,
recursively, and joins each to the `Agent` call that launched it with a
`launched` edge in a new `agent` layer. `--no-follow` digests exactly the file
named and nothing else.

This is the only place `digest` reads a file it was not handed, and the reason
it is allowed is that **it is not a guess**. The plan had been to glob
`<session-id>/subagents/` — an assumption about layout. Measurement showed
every transcript names its own children in `toolUseResult.agentId`, including
at depth 2 where a subagent names *its* child, so discovery follows references
instead. Following a reference and globbing a directory are different acts, and
only the first has the same contract as digesting the file itself.

The join is an **equality between two things already in the graph**: the
`.meta.json` sidecar's `toolUseId` and a stored `toolcall.params.tool_use_id`.
The sidecar is stored on the sidechain's root regardless, so digesting a
sidechain alone keeps the fact and leaves the edge derivable when the other end
arrives — the same shape as citations being derived from stored links.

`toolUseResult` reaches the graph only because the importer stopped filtering,
so that change was a prerequisite rather than a coincidence.

A referenced file that is absent is reported and skipped, not fatal: a
transcript copied away from its `subagents/` directory is an ordinary thing to
digest.

Verified against a real session with four subagents including one nested two
deep, which is joined to a tool call inside *its parent agent's* transcript
rather than the root's.

### One conversation is one page

A transcript that was launched by another gets no page of its own. It renders
inside the `Agent` call that ran it, collapsed in HTML like any other tool
output — which is what it is, arriving in a different file. Before this, one
conversation with four subagents produced **six index entries**, five of them
unreadable `agent-<hex>` names with nothing saying which conversation they
belonged to.

One rule covers the awkward case too: a subagent digested on its own, with no
parent in the base, has no incoming `launched` edge and so does get a page —
correctly, since nothing else would show it.

**This is the first time a view has consulted an edge to decide what to draw.**
Until now `Graph` built lookups for `contains` and `next` and every other edge
type was invisible to rendering; citations are the reverse of what they look
like, since a citation is a `Link` in the content and the `cites` edge is
derived *from* it. `Graph.linked(guid, type)` is generic, so the next relation
a view wants to draw needs no change there.

`check` gained the two guarantees that rendering depends on: a session is
launched at most once, and `contains` and `launched` are acyclic *together* —
for rendering purposes `launched` is containment, so it needs containment's
guarantees or the renderer loops.

### `render` removes what it did not write

Found by this change rather than reasoned about. `render` only ever wrote, which
was invisible while every document had a page forever, and became wrong the
moment a transcript could stop having one: the stale page stayed on disk and in
the browser, showing a document the graph no longer presents that way. Views are
generated and disposable, so the rule is now that what is on disk is exactly
this render's output.

### A correction to the portability decision

`docs/decisions.md` first concluded that the subagent fold should avoid
`<details>` as the least portable strategy. Measuring it says otherwise:
`_details` wraps its blocks in raw HTML, and in LaTeX the wrappers vanish while
**everything between them stays** — the same session is 7984 bytes of HTML and
11005 of LaTeX. The sharper rule replaced it: what matters is whether a
format-bound construct carries **information** (a handle, an author, a tool
name — lost silently) or **affordance** (a fold, which has no meaning in a PDF
anyway). `<details>` carries affordance, so it is correct, and one folding
mechanism serves both tool output and subagents.

### Tests

`test_session` 9 → 11: the round-trip, and that no line type is filtered.
Sabotage-verified twice, and the second one matters — dropping a single key
from a stored line still returns the right *number* of lines and fails anyway,
because the property compares content.

`test_session_views` 10 → 13: the deliberate non-rendering of envelope turns
stated as its own guarantee rather than left as a silent exclusion, plus
subagent inlining and stale-file removal. Each sabotage-verified, and the
`check` guards verified against a hand-built two-session cycle.

That suite was also reading only the pages it expected rather than the pages
that were rendered, so it would have ignored anything `digest` pulled in on its
own; and its three-session sample was silently displaced by the new five-line
fixture, which is now excluded from the slice and digested separately.

`test_digest` 13 → 17 for the subagent behaviour, on a hand-built parent and
sidechain pair. Written rather than bleached from a real one: the join spans a
`.meta.json` sidecar the bleacher does not process, so its `toolUseId` would
stop matching the parent's remapped `tool_use.id` and the fixture would test
nothing.

Adding that fixture broke `test_records`, which rglobbed `*.json` across the
whole tree and swallowed the sidecar. Its sweep is narrowed to `ast/*.json` —
"a pandoc AST" is a claim about what is in a file, not about its extension,
which is the mistake `digest` itself stopped making this release.

## v0.2.2 — 2026-08-21 — ingestion is asked for by name

`compost import FILE...` is gone. Ingestion is `compost digest --as=ROUTE
FILE...`, the route is required, and **nothing about it is inferred from a file
extension**.

### The route is named

`import` chose its reader from the suffix. Two faults, and the second forced
the change: the fallback was not "markdown" but *anything at all*, so a PNG
reached pandoc's markdown reader and came back as a pandoc error rather than a
compost one; and `.jsonl` is a container, not a format, so the suffix stops
naming a reader the moment a second kind of JSONL exists. That moment is
close — `claude --print` will produce single text turns, a different material
from a session log with its tool calls.

| route | reads |
|---|---|
| `notes` | prose, as `commonmark_x` with the three extensions off |
| `claude-code-transcript` | a Claude Code session log, the whole `*.jsonl` |
| `pandoc-ast` | a pandoc JSON document somebody else already produced |

`notes` is not a new reader — it is the dialect `decisions.md` settled in v0.2,
flags unchanged. What changed is that it must now be asked for. `pandoc-ast`
is genuinely new, and it is the *narrowest* route rather than the broadest:
`ast_to_records` already takes that shape, so there is no reading step in it to
be wrong. Whatever pandoc invocation produced the file stays outside the tool,
where the person who wrote it can inspect it.

`src/routes.py` is now the only module that knows how to read anything.
`store.py` no longer invokes pandoc.

### Storage is a blob store

Every ingested file lands under a freshly minted `storage/GUID.EXT`, and a
`blob` node records `original_name`, `stored_as`, `bytes_sha256`,
`imported_at` and `route`. A `derived_from` edge in a new `ingestion` layer
joins the document root to it, and the root records the route it came by.

Content-addressed names were the alternative and were rejected: they are
verifiable and idempotent, but they cost the invariant that *every object has
a guid*, which is worth more here. The duplication that buys is closed by
reporting rather than by naming — `these bytes are already in N blobs` — since
deciding two copies are one thing is a later layer's call. The extension
survives so a file pulled back out of `storage/` is still usable by hand; it is
a decoration and nothing routes on it.

**The original name is no longer where the file lives.** `records.blob_of()`
follows the edge, and anything reconstructing a storage path from
`params["source"]` is guessing.

Storage and graph filenames are different uuids on purpose. If either were
derivable from the other, something would eventually derive it — which is
suffix routing wearing a different hat.

### A batch is all or nothing

Nothing is written until every input has been read and parsed. This falls out
of minted names: under content-addressed storage a half-finished batch was safe
to re-run, and now it is not — the files that had landed would come in again
under fresh guids. Validating first is what makes it safe to pass a glob.

Directories are refused rather than walked, pointing at the shell. `find` is
better at recursion than a flag would be, and the caller already has an opinion
about how deep to go.

### Two things this found

**View filenames collided silently.** `render` names view files from the
source name, so two documents called `notes.md` overwrote each other's pages
and `render` reported writing files that held the wrong document. Nothing had
noticed because the old name-keyed storage *accidentally* guarded it by
refusing a second file with the same name and different bytes; minted names
removed that guard. Colliding stems now take the root's handle. A counter was
rejected — it renumbers when an unrelated document arrives, moving every URL
in the browser, while a handle is the document's own.

**`file` and `blob` are different nodes.** A `file` is a path a session
touched — may not exist, no bytes held. A `blob` is bytes in `storage/`. Every
vocabulary that has faced this splits it the same way, and the shared answer is
that a path is a locator rather than a thing: PROV-O, NFO, FRBR and DCAT are
recorded in `docs/record-format.md` as the reason, with the distinctions
borrowed and the namespaces deliberately not. A `represents` edge will join
them when one path is both; nothing mints one yet.

### Deferred on purpose

**Sidechains are still not followed.** `--as=claude-code-transcript` reads
exactly the file it is given, so storage and graph stay 1:1. The join between
a parent and its subagent is a second kind of fact and belongs in its own layer,
asserted explicitly, rather than smuggled in as a side effect of reading a
file. `TODO.md` names one thing to check first: where `agentId` actually
appears on the parent side, since that decides whether the link is recoverable
from transcripts already ingested.

**The pandoc research programme is written down, not run.** The route is the
instrument; the experiment — a curated set of documents with the exact
invocation and an expert review of where each AST diverged from what the
document meant — is a `TODO.md` entry with a method and no schedule.

### A filename is only a filename

Found by probing the new command rather than by any suite. A relative path
beginning with a dash reached pandoc as a flag — `-dash.md` parsed as `-d
ash.md`, i.e. `--defaults ash.md` — and surfaced as a pandoc error about a
file nobody had named. Paths are resolved before pandoc sees them, and `--`
now ends the options so such a name can be given at all. Both halves are
sabotage-verified, and the test uses a *relative* path deliberately: an
absolute one already begins with a slash and cannot exercise the bug.

Also confirmed along the way: a source with no extension at all is stored
under a bare guid, which is correct — the extension is decoration and never a
fallback.

### Tests

`tests/test_digest.py`, thirteen ingestion guarantees, each sabotage-verified:
the route is never guessed, the extension decides nothing (checked by making it
lie — markdown named `.jsonl`), a batch is all or nothing, a document reaches
bytes that hash to what the graph claims, duplication is reported, storage and
graph names never coincide.

`test_views` now builds its base through the real ingestion path rather than by
hand, which is what surfaced the filename collision above: a view test that
builds its own records can only check the views against itself.

Twelve suites, up from eleven. View guarantees 5/5 → 6/6. Storage stays at
ten: two cases whose mechanism is gone were replaced, not added to.

## v0.2.1 — 2026-08-20 — the daily loop closes

### The man page cannot drift again

`tests/test_manpage.py` holds `docs/man-compost.md` against the dispatcher, in
both directions and down to the number spelled out in prose. Ground truth is the
program: every name is offered to `cli.main` in a scratch directory and has to be
routed somewhere. v0.1.4 shipped a test with this name, the rewrite dropped it
for a promise in a docstring, and what rotted first was the count — five above a
list of six, copied from there into `CLAUDE.md`. Six sabotages, all caught.

It found one thing on its first run: `-h` and `help` are accepted and were
documented nowhere.

### The acceptance test is visible again

`run.sh` reads each suite's last line, and `test_records` printed its coverage
histogram *after* its verdict — so the table reported node types and hid the
520/520 the whole record format rests on. The verdict prints last now, and
`run.sh` checks that the line it picked starts `N/M `, which makes the
convention enforced rather than remembered. Sabotage-verified with a suite made
to end on a stray line.

### `compost lookup HANDLE`

Print the node a handle names: guid, type, source file, and the node's own
text. This is the half of the daily loop that had no tool — `CLAUDE.md` told an
agent to "resolve it from the graph" and left it to write its own JSONL scan.

**The handle is the whole guid**, and `lookup` does not report what cites the
node. Both of those were built first and then deliberately removed before
release, which is worth recording because the reasons generalise.

*Prefix resolution.* `records.py` had grown a resolver taking any unambiguous
prefix of 8 characters or more, and `decisions.md` had leaned on it to argue
that short handles were a free future win. They are not. The resolver worked in
the graph while the HTML view emitted the href verbatim, so a shortened
citation resolved for a tool and was a **dead anchor for a person clicking
it**. Uniqueness was recomputed per query over whatever was loaded, so a prefix
unambiguous today collides as the base grows — and since `check` never looks at
citations, nothing would have said so. It was an optimisation built ahead of
any measured pain. `HANDLE_RE` now matches a whole uuid, so a prefix is not a
short handle, it is an ordinary link, by construction.

*Backlinks.* `lookup` briefly printed what cited a node, which meant calling
`citation_edges` on every query. That function had never been called by the
program before — only by its own tests — so the `cites` layer `decisions.md`
documents still exists nowhere in a real base. Deriving it at query time would
have been the citation layer arriving by accident, ahead of its design, and a
layer built that way is harder to replace than one that was never built.

What remains is exact, small, and does not gate on `check`: a view asserts the
whole graph is sound, a query answers one question from what is on disk, and
refusing because an unrelated file has a dangling edge makes a broken base
harder to debug rather than safer. Seven guarantees.

### `compost serve [-p PORT]`

The HTML view in a browser, on `http://127.0.0.1:7373`, foreground until
interrupted.

**It does not render**, and that is the difference from v0.1, where `serve`
meant "render, then serve". Keeping them apart is not only simpler, it puts the
guarantee in a better place: `render` is the only thing that writes views and it
already refuses on a graph that fails `check`, so every file being served was
produced from a graph that was sound. Delivery needs no opinion of its own,
`serve` is a directory and a port, and it cannot fail for graph reasons. It also
matches what `lookup` does — queries and views hand you what exists; only
`render` asserts soundness. Run `render` in another terminal, refresh the page.

Two choices worth their own lines. The socket binds **loopback only**: a
knowledge base is not something to put on the local network by accident, and
`0.0.0.0` is exactly that accident. And responses carry `Cache-Control:
no-store` while revalidation headers from the client are dropped rather than
answered — `Last-Modified` is accurate only to the second, so a `render` landing
in the same second as your last page load is otherwise answered `304 Not
Modified` and you refresh onto yesterday's page. That was reproduced, not
guessed, and the suite reproduces it: same mtime, different bytes, must serve
the new bytes.

The default port is 7373 rather than v0.1's 8000, which is `irdmi` in
`/etc/services` and the default for `python -m http.server` and Django both.
7373 is unassigned, outside the ephemeral range macOS allocates from, and not
the default of anything common. `-p` overrides it.

Nine guarantees, five sabotages, including that nothing outside the served
directory is reachable.

### Test material in two tiers

`tests/fixtures/` is an 80 KB **smoke set**: the documents the suites name
directly — the one markdown file that reaches every sabotage, a hand-built AST
no reader can produce, three notes, and one transcript trimmed to the shortest
prefix carrying text, tool_use, tool_result and thinking. Every suite runs on a
bare clone.

Everything else moved to a separate repository and is fetched at the commits
pinned in `tests/corpus.txt` by `./tests/fetch-corpus.sh`, alongside rust-book.
A commit SHA is already a hash over the tree, so the pin is the checksum. That
takes the round-trip from 5 documents to 525.

Four guarantees assert volume — over 1000 prose blocks, over 100 thinking
nodes, over 5000 nodes, over 100 tool calls. They report themselves **skipped**
when the corpus is absent rather than being weakened to fit the smaller set,
and `run.sh` ends with `corpus present` or `corpus ABSENT`, because 5/5 and
525/525 are the same shape.

The split happened now rather than later on purpose: this repository has had
material removed from its history retroactively, which is expensive and leaves
residue on any remote it was pushed to, and test data only grows.

### `tests/clean-room.sh`

What the suites cannot tell you: whether somebody else could start. It clones
what is actually pushed, builds an env from `environment.yml`, installs, runs
both tiers, and exercises every subcommand. `--with-agent` adds the one check
the rest of it structurally cannot make — every command in the script is the
*correct* sequence, hardcoded, so it passes whether or not `CLAUDE.md` mentions
any of it. So it asks a fresh Claude, in the clone, with only `CLAUDE.md` in
context, to name the fetch command, the runner, and what the runner's last line
means. Exactly one file is auto-loaded into a fresh session, measured.

Not wired into `run.sh` and not automated. `DEVELOPMENT.md` ties it to the one
moment the answer matters: before tagging.

### Smaller

- The v0.1 corpus and 85 MB of another project's material were removed from
  this repository's **history**, not merely deleted — they were personal notes.
  A clone is 3.9 MB now, was 56 MB. The bytes are kept privately, and
  `docs/migration.md` says so up front rather than describing files a reader
  will not find.
- `compost import` with no arguments printed `usage: store.py import <file>...`.
  The program name comes from `argv[0]` now, so it is right through the CLI and
  still right when the module is run directly.
- `AGENTS.md` is folded into `CLAUDE.md` and gone. It was written to travel with
  a base and teach an agent to read one without this repository, but `compost
  init` never shipped it and no base exists yet, so its only possible readers
  already had `CLAUDE.md`. The three rules it alone carried moved across:
  property tests over snapshots, do not repair pandoc's output, and
  reconstruction is not viewing.
- The development env is `compost`, built from `environment.yml` with the CLI
  installed by `pip install -e .`. The `knowledge-graph` env it had drifted into
  is deleted. `CLAUDE.md`, `DEVELOPMENT.md` and the man page name it now, along
  with the pandoc floor — the base conda env has 3.8 and the suites pass there
  anyway, so nothing warned you.

## v0.2 — 2026-08-18 — nodes and edges, and none of the old code

**Everything was rewritten.** Not a refactor: no line of the v0.1
implementation survives. `src/` is a different program with a different storage
format, and the v0.1 corpus is no longer readable by it.

### The waist

Storage is **nodes and edges as JSONL**, and every view is generated from those
records and from nothing else. Djot is gone as a storage format; `blocks.json`
is gone; the `.dj` files under `conversations/` and `artifacts/` are no longer
written or read.

One rule does the translation: a node stores the pandoc constructor tag and
every non-block field verbatim, and block-valued fields become children joined
by `contains` edges. So there is no per-constructor special casing and no
mapping table to drift. `records_to_ast(ast_to_records(ast)) == ast` holds
exactly over 520 documents, covering all fourteen `Block` constructors.

### Every read and every write goes through pandoc

djot.js and the `npx` spawn are gone; pandoc reads and writes djot natively.
Markdown is read as `commonmark_x` with `attributes`, `smart` and `fancy_lists`
disabled.

This deleted three repair passes rather than fixing them. The em dash is not
restored, because `-smart` means it was never corrupted. Checkboxes are not
patched, because `-fancy_lists` means they parse the first time. There is no
fence tracking. **The pipeline contains no repair code at all** — every fix is
a flag, chosen once against a measured corpus.

Choosing that corpus reversed a decision mid-flight. `gfm` and `commonmark_x`
score identically on this repo's 25 documents, so gfm won on having safe
defaults; across 152 including a real documentation site it is 71 against 140,
because the gfm writer drops code fence info strings containing a comma —
`rust,ignore` becomes nothing — which is how every mdBook and Docusaurus corpus
annotates its examples. Twenty-five documents could not see it.

### Transcripts

Session JSONL is imported directly. Prose in a turn goes through the same path
a markdown file takes, so a paragraph of an answer is a node like any other;
tool output is stored whole, because parsing 60 real tool outputs as markdown
invented a Header, a BulletList and a Div out of terminal text.

Tool results fold into the call that produced them, matched on `tool_use_id`
rather than order. Attribution has a number now: **161 human turns out of 1060
`user` lines** — the other 899 are the transcript's envelopes around tool
results, which is the bug the old importer shipped.

Both orderings are stored, because they diverge on sidechains and this corpus
has none to test with: `session`/`next` is log order, which regenerates the
file, and `claude-code`/`replies_to` is the reply chain.

### Identity and citations

A handle is a **UUIDv4**. That costs 21.7% of a djot view against 7.7% at eight
characters, and up to 75% on small dense files — accepted, because a resolver
takes any unambiguous length, so shortening later needs no pass over stored
text: long and short citations coexist as full and abbreviated SHAs do in a git
log.

**A citation is a link:** `[-](#<guid>)`. The old `{#x}` meant "this element
*has* id x" in every markup language that knows the notation, so using it for
"points at x" was backwards, and any reader with `attributes` on agreed with the
language rather than with us. `{@x}` fixed the meaning but not the mechanism —
it was still text, so a handle quoted inside a code block became a real edge, in
a corpus that quotes its own syntax constantly. A `Link` is a node and a code
block has no inlines, so the rule that had been broken three times is now a
property of the format.

### Views

Three, all generated from records: `default-djot` for agents, `default-html`
for people, `default-md` clean enough to commit as `README.md`. Handles go on
prose and list items, not on the containers holding them — marking everything
produced a page with more handles than words. Tool output is shown in full in
djot, which has no collapse, and wrapped in `<details>` in HTML.

### Storage

`.compost/` is both the layout and the marker, replacing the `.kg` file, so a
base cannot be half-configured. Writes go through a temp file and an atomic
rename; only `*.jsonl` is loaded; filenames carry no meaning and load order
cannot change the result; the loaded file list is printed rather than hidden.

### Tests, and what they caught

Eight suites, 74 stated guarantees, each made to fail on purpose. Findings worth
recording because they were all silent:

- a fenced code block inside a **tight** list item is destroyed by pandoc's
  writer — emitted with no preceding blank line, so it re-reads as paragraph
  text. A loose list survives. Writer-independent, documented, unfixed.
- pandoc **synthesises** callout titles: `> [!IMPORTANT]` produces a `Div`
  containing the word `Important`, which no author typed.
- pandoc injects `<!-- -->` between adjacent lists, which re-reads as a
  `RawBlock` nobody wrote.
- document metadata lives outside `blocks` and every writer drops it without
  `--standalone`.
- `importing thing.md` and `thing.jsonl` wrote the same graph file and the second
  silently discarded the first, while the summary reported both.
- all 491 `thinking` blocks in the corpus carry **no text**: Claude Code
  persists only a signature. The node type stays, because other agents emit
  text into it.

### Fixtures that outlive their sources

`tests/fixtures/` holds 19 bleached notes, 21 edge cases, 7 bleached session
transcripts and two hand-built ASTs. Bleaching replaces every word with a lorem
word of the same length and leaves every character markdown gives meaning to
exactly where it was; correctness is checkable rather than eyeballed, since the
result must parse to the same tree of block types as the original.

It caught two leaks of its own: 57 absolute paths surviving in *key* position
inside `file-history-snapshot`, and a git branch name on the preserved list. A
vocabulary diff now shows 71,893 distinct words reduced to 4,104, all of them
JSON schema keys, enum values or tool names.

### Gone

`src/` and `tests/` from v0.1, `tools/`, the `.kg` marker, `site/`, the
`compost`/`kg`/`kgb`/`pandig` egg-info directories, the `uuid6` dependency, and
the `new`, `submit`, `serve`, `lookup`, `last` and `artifact` subcommands.
`conversations/`, `artifacts/` and `raw/` remain on disk as the input for a
migration that is not written yet, and are not readable by this version.

## v0.1.6 — 2026-08-17 — pandig reverted, the tool is `compost`

**v0.1.5 never worked.** It renamed `kgb` to `pandig` and is reverted here in
full — one commit, cleanly undone, nothing else changed underneath it. Kept in
history rather than erased: `git log` still shows the attempt and that it
didn't pan out, which is the same reasoning that keeps every conversation in
this base immutable in the first place.

**The tool is `compost` now.** Conversations pile up append-only, get turned
into artifacts, and what's fully superseded settles into `archive/` — the name
finally matches the shape of the system instead of punning at it. `kgb` (and
`kg` before it, and `pandig` for its few days) are gone **without an alias**.
Every prior rename kept the old name working with a deprecation notice; this
one doesn't, on purpose — v0.2 is about to break the storage format and the
importer from nothing, so there is no reason to carry three dead names into it
for the sake of continuity that's about to end anyway.

Renamed only where a wrong command breaks someone, same rule as last time:
`README.md`, `AGENTS.md`, `CLAUDE.md`, `DEVELOPMENT.md`, `man compost`
(`raw/artifacts/man-compost.md`, moved from `man-kgb.md`), `state-of-play`, and
`src/cli.py`. `CHANGELOG.md`, the completed `v0.1.4` section of `TODO.md`, and
`field-notes`' account of the day two handles nearly broke all still say `kg`
or `kgb`, because that is what the tool was called when those things happened.
`.kg` and `$KG_HOME` are untouched — renaming an env var breaks a shell profile
silently, which is a worse kind of break than a stale command name.

Also removed: `archive/` (moved to a personal notes directory outside the
repo) and `sample_data/math/` (demo content superseded by the conversation
corpus as a source of real sample data).

## v0.1.4 — 2026-08-11 — kgb, and a man page that cannot drift

**The tool is called `kgb` now.** Knowledge graph blocks, and a system whose
premise is that it knows exactly who said what and when has earned the joke.
`kg` remains as an alias that prints a notice, so every note, doc and shell
history written before the rename still runs.

Renamed only where a wrong command breaks someone: `README.md`, `AGENTS.md`,
`CLAUDE.md`, `DEVELOPMENT.md`. `CHANGELOG.md` and the completed sections of
`TODO.md` keep saying `kg`, because they record what the tool was called at the
time, and 501 blocks across the conversations say it immutably and always will.
Measured before deciding: only 4 cited artifact blocks mention the name, so the
rename cost four handles rather than eighty.

**New commands**, both absorbed from shell scripts that had accumulated:

- `kgb lookup HANDLE` — resolve a handle to its block, and list everything that
  cites it. Accepts `{#handle+++}` as well as a bare handle. Replaces the
  `tools/kgb.sh` function, which is deleted.
- `kgb last` — print recent turns as `{#handle}` plus text, so a turn can be
  pasted into an agent's interface and the agent can cite exact blocks back. A
  conversation file can be half a megabyte; one turn is not. `-n`, `--author`
  and `--handle` select which.
- `kgb --version`.

**The version has one source, and it is the code.** `__version__` lives in
`src/__init__.py` and `pyproject.toml` reads it with `dynamic`. The usual
arrangement is the reverse, and it failed here in the ordinary way: with an
editable install, packaging metadata only refreshes on reinstall, so `pip show`
reported 0.1.0 through three releases while the code was current. Nothing
visible reported a version at all, which is why nobody noticed.

**The behavioural expectation is corrected everywhere it was stated.** An agent
with its own interface answers there and does not submit its reply as a turn;
the human imports the round, which makes the answer addressable anyway. Two
output channels for one answer is worse than one, and it is the human who has
to read both.

This came from days of use rather than from the design, and it does contradict
"everything is a turn" — knowingly. Nothing is lost, because the import is
where the handles came from in either case. What does not change: an agent
resolves every handle before answering and cites handles in its answer, so the
import produces real citations.

Corrected in `CLAUDE.md` (which an agent loads first, and which had been
carrying a marker saying its own instruction was wrong), `AGENTS.md`,
`README.md`, `man kgb`, and `state-of-play`. `kgb submit --author` remains
correct for an agent with nowhere else to write, and for when a turn is asked
for deliberately.

**A man page, verified against the CLI.** `artifacts/man-kgb.dj`, published from
`raw/artifacts/man-kgb.md` and readable in the index as *man kgb*. One long
searchable document rather than help by level: the concepts, every command,
files, environment and examples.

`tests/test_manpage/` walks `build_parser()` and requires every subcommand and
every long option to appear in the page, and anything whose help says it is
deprecated to be marked as such. Sabotage-verified with a parser carrying an
invented command and flag. A reference document nothing checks drifts the first
time a flag is added, and this project has already paid for that once with
`mvp-design.md`.

The argparse tree moved into `build_parser()` so the test can walk it.

## v0.1.3 — 2026-08-11 — the base keeps its own sources

`kg import` now copies the session log into `raw/<conv>/<session>.jsonl` before
deriving anything from it.

Until now an imported conversation's source lived only in
`~/.claude/projects/`: outside the base, outside git, and owned by another
tool's storage layout. The importer discards a great deal on purpose — every
`type: "system"` line — and none of it was recoverable, because the base had
never held the file it was discarded from.

Found by trying to locate where a conversation had been branched and failing.
The `/branch` event is in the log as two `type: "system"` lines carrying the
parent session id, and `SKIP_TYPES` drops them. Also dropped, per session: 34
`turn_duration` records, 10 `away_summary`, 8 `local_command`. And `sessionId`
sits on every line and was never stored, so the base held no record that one
conversation was a branch of another.

None of that is fixed here, and it is not meant to be — the graph milestone is
where those become nodes and edges. What is fixed is that the evidence now
lives inside the base, so a later version can go back and read it. 10 MB for
seven sessions.

- **A refresh may only grow the copy.** A log is append-only upstream, so if
  new content is not a continuation of the stored copy, the log was rewritten
  underneath us and the import refuses rather than overwriting. The stored copy
  is the only record of what was actually ingested.
- Re-importing an unchanged log is a no-op, so the refresh loop stays cheap.
- `tests/test_preserve/` — storage, growth, idempotence, the rewrite refusal,
  and that the dropped fields are recoverable from the copy.

## v0.1.2 — 2026-08-10 — punctuation, and a bug class closed

Every em dash, en dash, ellipsis and curly quote an author had typed was being
deleted from the stored text. `readme.dj`'s own title read
`kg  conversations to an addressable wiki`. 795 occurrences across the corpus.

**The `.dj` files were correct the whole time.** Djot has smart punctuation in
its specification: `---` in a source file *means* an em dash, and `\-\--` means
three literal hyphens. Pandoc was encoding it exactly right, and the round trip
through djot.js is lossless. An earlier TODO entry blamed pandoc's writer, said
the corruption was on disk, and estimated the repair as canonization-time work
needing fence tracking. All of that was wrong. That entry is kept, because it
is cited, with a superseding block beside it.

The defect was in `inline_reconstruct.py`, which had no branch for djot's
`smart_punctuation` node. Its fallback emitted nothing.

- **An unhandled tag now raises**, in the inline reconstructor and in the block
  walker. This is the actual subject of the release. A missing branch that says
  nothing has now produced three bugs: `task_list` silently dropped, a div
  silently swallowing its children, and this. Each was invisible to the tests
  because the element was absent from *both* sides of every comparison, so
  nothing could see the difference. A branch that raises cannot fail that way.
- `smart_punctuation` is resolved to the character it denotes rather than
  echoed as its source spelling, so that an em dash and three literal hyphens
  stay distinguishable in the stored text. Structural markup is still emitted
  as djot source, as it always has been.
- `url` and `email` autolinks were dropped by the same fallback. One occurrence
  in the corpus.
- `double_quoted` and `single_quoted` handled defensively. Unreachable today
  only because pandoc escapes quotes as `\"`, and an unhandled *container*
  loses its children rather than just its wrapper.
- `tests/test_inlines/` — the branches, the sabotage check, and a pass over
  every file in the corpus so an unhandled tag announces itself.

No handle moved. Both sides of the `kg artifact` hash comparison are parsed by
the same reconstructor, so the change is symmetric: all six republished
documents reported 0 new and 0 gone, and `kg check` stayed at 0 dangling.

Sequenced before the `graph/` work deliberately. That milestone migrates block
text into nodes carrying an immutability invariant, so a hole repaired
afterwards would be a content change on a node that already has an identity.

## v0.1.1 — 2026-08-07 — conversations, and an agent in the loop

The loop now runs with both parties in it. Either can write; neither can alter
what the other wrote.

Developed on `main` with a tag per version. A `conversations` feature branch
was created and fast-forwarded away: with one developer, no remote and no CI
there is nothing to isolate from, and the cost was a trunk whose documentation
described an architecture that no longer existed.

**Changed — the shape of the system**

- **The split is mutability, not authorship.** `notes/` and `wiki/` enforced
  "humans write notes, agents write the wiki" with the filesystem. That boundary
  is gone: `conversations/` is append-only and `artifacts/` is rewritten in
  place, and either party writes either kind. What protected anything was never
  the directory but immutability, and that is kept — no block already written
  ever changes, whoever wrote it. Revises invariant 3 and §3 of `mvp-design.md`,
  which called a conversation a view rather than a storage type.
- **A conversation is one append-only file**, not a directory of turns. Turns
  get concatenated for reading anyway, and one file is one djot parse: at the
  measured ~1 s per `npx` spawn, a 70-turn imported session costs about a second
  this way against roughly two minutes as separate files.
- **Turns are fenced divs carrying their author** —
  `{#handle .turn author="claude"}`. One native djot construct provides the
  container, the authorship, and the nesting that folded tool traffic needs. No
  frontmatter, no sidecar, nothing outside the reference implementation.
- **Block ids are 8 hex characters, not UUIDv7.** A UUID cost 39 bytes per block
  on disk and 56 per reference — measured at 26.8% of the corpus, and unreadable
  inline. Handles cost 10.2%. Nothing needed a per-block timestamp; note ids stay
  UUIDv7 so dates and ordering still work. Rejected the shorter registry-backed
  handle: a handle-to-block file cannot be rebuilt from the `.dj` files, so
  losing it would break every reference at once.
- **The version pin is now optional.** `{#handle}` for immutable conversation
  blocks, whose handle already pins their content; `{#handle@ver}` for artifacts.
  Both forms are defined now so the syntax never has to change again.
- **The thread is inferred from citations.** You reply by clicking a block, so
  the conversation is implied; `-c` is only needed when a draft cites nothing or
  cites two threads.

**New**

- `kg artifact` — publish a markdown document as an artifact. On update,
  unchanged blocks **keep their handles**, matched by content hash rather than
  position so an insertion does not renumber everything after it. Without this,
  regenerating a document orphans every comment ever written about it, and those
  comments live in immutable turns where they can never be corrected. This is
  the delta algorithm from `architecture/delta_ingestion_and_block_versioning.md`,
  and it turned out to be about thirty lines.
- `kg import` — a closed Claude Code session becomes a conversation. The whole
  log is turned into one markdown document and canonized in a single pass,
  because pandoc carries fenced divs and their attributes through to djot.
  Nothing is filtered: tool traffic and thinking are wrapped in `.tool-call`
  divs that the renderer folds away, so the transcript is complete and every
  block of it addressable. Subagent branches become `claude:sidechain` turns.
- `site/blocks.json` — every block with its handle, hash, type, source,
  structure, citations and author. An agent can read a `.dj` with grep but
  cannot *cite* one, because the hash is SHA-256 over the parsed block; this
  closes that gap and doubles as whole-corpus context assembly.
- `kg check` — dangling references and handle collisions, as a set difference
  over `blocks.json`. A dangling reference cannot be repaired in place, because
  the turn holding it is immutable, so noticing is the only defence.
- `AGENTS.md` — everything an agent needs to read and write a base, without
  reading this repository.
- Rendering: per-turn author labels straight from the djot attribute via
  `attr()`, no JavaScript; `.tool-call` divs folded into `<details>`; whole
  turns subtree-copyable.

**Fixed — correctness**

- **The importer attributed the harness to the human.** A `user` line in a
  session log is not the same thing as "the person typed this": tool results
  come back as user messages because that is the API protocol, the harness
  injects its own context, and a slash command echoes both its name and its
  output. In one 18-"user"-turn session **only 1 turn was genuinely typed**, so
  a reader saw directory listings above the user's name. Tool results are now
  folded into the call that produced them, matched on `tool_use_id`; harness
  messages are attributed to `system`; injected system-reminders are lifted out
  of real typing and kept, folded, rather than discarded.
- **A conversation's date was decoded from a UUIDv4.** An imported session is
  named after its log, whose id is not a UUIDv7, so reading its first twelve hex
  digits as a millisecond timestamp dated one conversation to the year 4527.
  `_when()` now checks the version nibble, and imported turns carry their real
  timestamp as an attribute.
- **A div swallowed its children.** `inject_ids` recursed into a div and gave
  every child an id; `ast_walker` nested those children inside the div's
  `content` instead of emitting them. Two halves of one pipeline held opposite
  beliefs, so canonization wrote ids into the file for blocks the block list did
  not contain — clickable in HTML, resolving to nothing, absent from every view.
  Neither the verifier nor the roundtrip test could see it, because the blocks
  were missing from both sides of every comparison; `test_roundtrip` even had a
  `_flatten()` helper written to accommodate the nesting. This blocked folds
  entirely, and would have made every block of every imported turn
  unaddressable.

- **A reference inside code is not a citation.** Importing this project's own
  sessions took `kg check` from 6 dangling references to 48 — every one a shell
  command from a throwaway experiment or a documented example. A checker that
  reports those is noise, and noise gets muted, which would cost the only thing
  the check is for. Code blocks and code spans are now excluded, and the count
  went to zero.
- **The repo is its own knowledge base.** `.kg`, `conversations/`, `artifacts/`
  and `raw/` at the root; the docs are published with `kg artifact`. Moving the
  corpus in preserved all 3311 handles exactly, verified by comparing a hash of
  the whole handle set before and after.
- Re-importing a session **preserves handles**. A live session is refreshed
  repeatedly as it grows, and the first implementation overwrote the file
  blindly, renumbering every block on each refresh — which would orphan every
  comment ever made on that conversation. It uses the same content-hash
  matching as an artifact, and refuses when the conversation contains turns the
  log does not know about, because those were submitted by hand and would be
  deleted.
- All four Claude Code sessions for this project are imported: 348, 311, 20 and
  3 turns.
- Index links show the document's own heading, the artifact's filename (so
  "where is the README?" has an answer), the real date, participants, and size.
  A conversation is titled by **what the human opened with** — its first heading
  is usually something the agent wrote, and its first block can be harness
  output, which titled one session "<local-command-caveat>Caveat: The...".

**Docs**

- The documentation surface is halved. `mvp-design.md`, `mvp-interview.md`,
  `my-workflow.md`, `human-log.md` and `architecture/` move to `archive/` —
  1141 of 2195 root doc lines, and the contradictory half. `mvp-design.md` was
  the worst of it: still declaring itself authoritative while describing
  `notes/`, `wiki/`, UUID block ids and "humans write notes, agents write the
  wiki", none of which survive. Its invariants are in `DEVELOPMENT.md` and its
  open questions in `TODO.md`. Code comments still cite its section numbers;
  those are historical now.
- `CLAUDE.md` is the bootstrap a fresh agent loads automatically. It routes to
  `site/blocks.json` and the base rather than to markdown, which is the point:
  the reasoning lives in immutable conversations that cannot drift, while a
  spec can and did.
- `artifacts/state-of-play.dj` is the handoff — what exists, what does not, the
  traps that already cost something, what to do next, and what nobody has
  answered.

**Measured, because it drove decisions**

- Appending a turn directly after a heading section merges it into the
  *previous* paragraph — an already-referenced block's text silently grows and
  the new turn's id attaches to nothing. A list appended after a paragraph is
  absorbed as continuation text and loses its id. A single blank line prevents
  every case found; the turn fence then makes merging structurally impossible.
- `npx @djot/djot` costs ~1 s per spawn, and `kg render` parses each file twice.

**Migration**

`tools/migrate_to_handles.py` remapped the test base: 248 blocks, 27 references
rewritten, zero dangling, including a cross-file subtree reference. Old-to-new
is positional — re-canonizing an immutable draft yields the same block sequence
— so nothing was guessed, and the script refuses to write if the sequences do
not correspond.

## v0.1 — 2026-08-04 — the mechanical loop

The write → submit → canonize → read → reference → submit loop works end to
end, with no LLM anywhere in it. Wiki generation is still unbuilt.

**New**

- `kg` on PATH via `pip install -e .`, working from any directory. The base is
  found via `--root`, `$KG_HOME`, or a `.kg` marker in any parent.
- `kg init` creates a base anywhere, which defers the tool/data split to a
  runtime choice rather than an architectural commitment.
- `kg new` opens `$EDITOR` and submits on exit — never on save, so saving
  mid-thought stays free.
- Static site with click-to-copy. Click a block for `{#uuid:hash}`,
  shift-click for `{#uuid:hash+++}`. Holding Shift while hovering highlights
  the subtree, so what will be copied is visible before committing.
- Backlinks: a note referencing a block appears as "Referenced by" on the note
  containing it. Computed at render time, so it works retroactively.
- Reverse-chronological index, dated from the UUIDv7 timestamp.

**Fixed — correctness**

- `loosen()` moved into canonization. Djot drops a list item's id in HTML
  unless the list is loose, so every list item and todo was unaddressable.
  Since notes are immutable this could not have been repaired later: notes
  canonized before the fix would have been permanently degraded.
- Backlink scanning reads parsed block text rather than the raw file. Pandoc
  escapes references on disk as `\{#uuid:hash\}`, so scanning the file found
  nothing.

**Docs**

- `README.md` restored — the repo had no entry point since the cleanup.
- `DEVELOPMENT.md` added: architecture, the non-obvious pandoc and djot
  behaviours, the sabotage-verification practice, and where the next work is.

## 2026-08-03 — Architecture pivot and repository cleanup

**Tagged `v0-graph-architecture`.** Everything removed in this cleanup remains
reachable there (`git show v0-graph-architecture:<path>`).

The product changed shape after a workflow interview (`my-workflow.md`,
`mvp-interview.md`). The new design is in `mvp-design.md`:

- **`.dj` files in git are the source of truth.** LadybugDB is no longer
  canonical storage. Any graph that returns will be a derived, disposable cache.
- **Notes are immutable and human-written; wiki pages are agent-written.** The
  human never writes the wiki, agents never write notes.
- **Lineage replaces semantic extraction.** Every wiki block cites the note or
  source block it derives from. Recorded at generation time rather than
  extracted afterwards — free, exact, and it doubles as the anti-slop
  mechanism: a block with nothing to cite is invalid.
- **Deleted, not deferred:** Phase 05 (entity/relation extraction), Phase 07
  (LLM-to-Cypher), temporal quadruplets, `Annotation` nodes, the Parquet event
  log (git supersedes it), and HITL diff approval.
- **Retained:** `architecture/delta_ingestion_and_block_versioning.md`. Its
  content-hash and delta mechanisms carry over unchanged; the subject moves
  from human-edited notes to agent-regenerated wiki pages.

Removed 47 files across two commits (superseded docs, then the LadybugDB
ingestion path). ~360 LOC of parsing and rendering carried forward.

**Defects found during the carry-over audit**, both on the MVP critical path
and neither caught by the existing roundtrip test:

1. `ast_walker.py` silently drops `task_list` / `task_list_item`. Djot supports
   them natively (`checkbox: checked|unchecked`); the walker has no branch, so
   todos vanish with no error.
2. Nested list items are emitted *before* their parent, and nesting depth is
   discarded, so `- a` / `- b` (nested) yields `[b, a]` flattened to one level.

*Correction:* an earlier version of this entry claimed nested items were
embedded as raw markup in the parent block. That was wrong. The confusion came
from a probe written without blank lines — **djot requires a blank line before
a nested list**; without one djot itself (not the walker) parses the child as
lazy continuation text of the parent paragraph. That is spec behaviour and a
*canonization* concern, since hand-written notes rarely include those blank
lines. The walker defect is the ordering and depth loss described above.

`test_roundtrip.py` detects none of it: a dropped element is absent from both
sides of the comparison, and reordering survives re-parsing unchanged. The
Phase 03 claim of "no data loss, 31 block types" holds only for the properties
the test actually compares.

---

## Phase 02 & 03 — 2026-05-16

Implemented Phase 02: Rewrote ingestion to bypass Pandoc and use native `djot.js`. Dropped JSONL intermediate representation to write blocks directly into Parquet files, which are immediately loaded into LadybugDB during `ingest_page()`. Extended Block schema with `language` field and added `LINKS_TO` relationships for explicit cross-links. Re-wrote `inline_reconstruct.py` and `ast_walker.py` against the native AST.

Implemented Phase 03: Built Djot rendering via `blocks_to_djot.py` that formats structured Block dictionaries back into raw Djot text. Added a roundtrip validation harness (`test_roundtrip.py`) validating `Djot -> Blocks -> Djot` without data loss (whitespace-normalized, structural fidelity). Passed verification for 31 block types. Achieved ~4.6x token reduction compared to raw JSON block representation.

## 2026-05-10 — Kuzu to LadybugDB Migration
Replaced Kuzu with LadybugDB (community fork) as the embedded graph database, following
Apple's acquisition and archiving of the Kuzu repository. Renamed `kuzu_schema.py` →
`ladybug_schema.py`, `kuzu_loader.py` → `ladybug_loader.py`. Updated all design docs,
implementation plans, and workspace paths. Python package changed from `kuzu` to
`real-ladybug==0.15.3`. Import alias: `import real_ladybug as lb`.
LadybugDB now supports `OPTIONAL MATCH` — constraint removed from Phase 07 design and
implementation plans. Added defensive parsing guidance for `SHOW_TABLES()` output change.
No data migration was needed (no existing database on disk).

## Phase 01 — 2026-05-08

JSONL → LadybugDB graph index. Implemented `src/index/` module: `ladybug_schema.py`, `jsonl_to_parquet.py`, `ladybug_loader.py`, `build_index.py`. Loads blocks and pages from JSONL into LadybugDB via Parquet COPY FROM. Full rebuild on each run. Verified: 47 Block nodes, 7 Page nodes, 47 HAS_BLOCK edges from the test corpus.

Dependencies added: `ladybug`, `pyarrow`.

## Phase 00 — 2026-05-08

Djot → JSONL ingestion pipeline. Implemented `src/ingest/` module: pandoc-based parser, AST walker, inline reconstructor, block schema builder, JSONL writer. Ingests a Djot file into `blocks.jsonl` + `pages.jsonl`. Handles heading, paragraph, list_item (ordered + unordered). Verified: 9 blocks from test file, 47 blocks from full test corpus (7 files).

Dependencies: `python 3.12`, `uuid6`, `pandoc` (system).

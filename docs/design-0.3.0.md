# Design — change, text artifacts, and the ledger (towards v0.3.0)

**Status: working document, jointly edited.** This is not `docs/roadmap.md` and
not `docs/decisions.md`. The roadmap holds work that has a version number and a
settled design; `decisions.md` holds what was decided and why. **This file holds
the argument while it is still an argument.**

The rule for using it: a section is either **SETTLED** — with the reason
attached, ready to be lifted into `roadmap.md` as a version — or **OPEN**, with
the options named and what each one blocks. Nothing sits here unmarked. When a
thing settles, it moves, and this file shrinks.

**As of 2026-09-03 nothing here is open.** Every section is settled or parked
with a reason, and §12 packages the result into versions. What remains is
writing the roadmap entries and building them.

v0.3.0 is reached when change, the text artifacts, and the first semantic layer
exist. The patch versions between here and there are packaging, not milestones.

---

## 0. Vocabulary, fixed

Three words were doing several jobs each. Fixed here so the rest of the document
can be short.

| term | meaning |
|---|---|
| **ImTA** | immutable text artifact. One root, ingested once, never appended and never revised. A note. |
| **AoTA** | append-only text artifact. One root, forever. Later ingests may add to the **tail** only; the head must be unchanged. A transcript, a CHANGELOG. |
| **TA** | mutable text artifact. Blocks may change, be added, removed, reordered, or all be removed. A README, the topic list. |
| **GeTA** | **dropped.** A generated artifact is a view; a view that is ingested back is a TA. It never needed a name of its own. |
| **the records** | a base's own content. Never "a corpus". |

**The dimension is called `mutability`, not `kind`.** *Kind* is too generic for
a project that will grow more artifact classes; this one axis says exactly one
thing — **what may be modified in the subgraph under this root**. ImTA: nothing.
AoTA: the tail only. TA: anything.

**Mutability and route are orthogonal.** `--as=notes` says *how the bytes are
read*; mutability says *what may happen to it afterwards*. A markdown file can
be an ImTA (a dated note) or a TA (the README). The same route reads both.

---

## 1. SETTLED — an AoTA does not get a revision chain

**Corrected during review; the earlier proposal had this wrong.**

An append-only artifact keeps **one root, forever**. A later ingest of a longer
file adds `contains` and `next` edges to that existing root and mints nodes only
for the tail. There is no second root, no `revision_of` edge, and no second copy
of the head.

This follows from what the words mean. A revision says *this document was
replaced by that one*. An append says *this document got longer*. A transcript
that gained forty turns is not a new transcript.

**So `revision_of` is a TA mechanism only.** That answers the question the
current design cannot: *"do you plan to have the whole chain again plus the new
additions?"* — no.

**Records stay immutable.** Appending adds edges; it never edits one. The root
node itself is untouched, which is why nothing about immutability has to bend
to allow this.

---

## 2. SETTLED — `mutability` is declared at ingest and verified by `check`

Not inferred, and not merely computed after the fact.

- **Declared**, because it is a statement of intent that the bytes do not
  contain. The same reasoning as `--as`: *"the route is never guessed"*.
- **Verified**, because a declaration nothing checks is a comment. `check`
  asserts the contract:
  - **ImTA** — no edges added to this root after the ingest that created it.
  - **AoTA** — the head is unchanged: the first *N* children of the root fold
    identically to the previous ingest's *N*.
  - **TA** — nothing to assert; anything is permitted.

A violated contract is a reported problem, not an impossible state. That is the
same standing every other invariant has here.

---

## 3. SETTLED — hashes identify equality, never identity

This is the answer to *"I don't know what to hash"*, and it is settled by
measurement rather than by argument. See §6.

**Two findings, and they point opposite ways:**

1. Re-ingesting a grown transcript produces **5,496 of 6,193 nodes that are
   hash-identical** to nodes already in the base, under the node hash formula
   already shipped in v0.2.4 — `sha256(canonical([type, params, content]))`.
   Matching across ingests already works.
2. Within a **single** tree, **36% of nodes collide with each other** — 633
   empty `Cell`s, 229 empty `thinking` markers, 217 `Row`s. Containers have no
   content of their own, so identical containers hash identically.

Both are correct and neither is a defect. They say the same thing: **a content
hash is a statement about a value, not a name for a thing.**

**Therefore guids stay UUIDv4.** The offer to drop them is declined, with the
number attached: content-addressed naming would merge 633 empty cells into one
node, and would merge every identical `Yes.` paragraph across every document in
the base. A citation names *this block in this document*, and content-addressing
destroys exactly that. `docs/roadmap.md` rejected UUIDv5 for derived records on
the same grounds in v0.2.4; the rejection still holds, and now has a measurement.

**The model is git's.** Content-addressed values, path-addressed identity. Two
empty cells share a value and remain different cells because they sit at
different positions. Hashes go in a **field**, never in the **name**.

---

## 4. SETTLED — what a Merkle fold is, and what it buys

Asked directly, answered directly.

A Merkle fold hashes a tree bottom-up: a leaf hashes its own content, and a
container hashes `[type, params, [child hashes…]]`. Every node ends up with a
hash that summarises everything beneath it.

**It is thoroughly established** — git's tree objects, IPFS, ZFS, Cassandra's
anti-entropy repair, and every blockchain use exactly this. It is not an
invention for this project.

**What it buys here, concretely:**

- *"Did this document change?"* becomes one comparison instead of walking
  thousands of nodes.
- *"Which part changed?"* becomes a descent: compare the root, then only descend
  into children whose folds differ. Unchanged subtrees are skipped whole.
- The **AoTA head check** in §2 becomes cheap and exact.
- It closes the container gap in §3 finding 2: an empty `Cell` still hashes like
  any other empty cell, but the `Row` above it folds differently as soon as any
  sibling differs.

**On the objection that a leaf change re-hashes everything up to the root** —
correct, and that is the design, not a cost. It is O(depth), not O(n), and it is
what makes the root hash meaningful: the root changes *because* something under
it did. Git pays this on every commit.

**Still to specify exactly** — see §8. The fold takes a per-type whitelist and
never includes `guid`, `created_at` or `tool_version`, or two identical
documents never fold equal. It is one function, specified once, or a different
JSON encoder silently makes every document unique.

---

## 5. SETTLED — what "order doesn't matter" actually has to give up

The claim under review: *"we are adding hiding and superseding, so the invariant
that order doesn't matter has to go."*

**Half right, and the half matters.** Two different invariants are being
conflated:

| invariant | fate |
|---|---|
| *Filenames carry no meaning; shuffling the file order produces an identical graph* (`store.py`) | **keep.** It costs nothing to keep and paying for it buys flat uuid-named files, the duckdb glob, free regrouping, and sane git merges. |
| *The graph **is** the set of records* (never written down, assumed everywhere) | **this is the one that goes.** |

Order can live **in the data** — a sequence or commit field on each record —
rather than in the file layout. `Store.load()` still returns a set; the fold
sorts by that field. Replay to a point in time becomes a *filter over records*,
not a property of how bytes are read.

**And retraction alone does not require order at all.** If records are immutable
and no id is ever re-asserted with different content, then "the current graph" is
`records − retracted`, which is set subtraction and order-free.

**Order becomes load-bearing at exactly one moment: upsert.** The same id
asserted twice with different payloads needs last-write-wins, and LWW needs a
sequence. Which means:

> **The ledger question and the mutation question are the same question.**
> Whether `seq` is semantics or audit metadata is decided entirely by §7 —
> and §7 settled on new-node, so `seq` is audit metadata.

---

## 6. The measurements this design rests on

Taken 2026-08-31 against the real base. Reproducible; the method is in the
session that produced them.

**Re-ingest waste — why delta ingestion is not an optimisation but a
requirement:**

| session | older tree | newer tree | hash-identical | genuinely new | re-minted for nothing |
|---|---|---|---|---|---|
| `2e9cd256` | 5,497 nodes | 6,193 nodes | 5,496 | 697 | **88.7%** |
| `cdb16054` | 222 nodes | 728 nodes | 221 | 507 | 30.4% |

The larger transcript re-minted 5,496 nodes to record 697 new ones. Exactly
**one** node failed to match that arguably should have: the `session` root
itself, because `params["lines"]` moved 2129 → 2248. That single fact is the
whole of §8, and §8 dissolves it: `lines` is not on the whitelist.

This is the project's own stated criterion firing: *filter only when disk or
compute requires it.* Here compute does require something — and the answer is
not to filter, it is to stop minting nodes that already exist.

**Within-tree collisions — why the hash cannot be the name:**

| | `2e9cd256` | `cdb16054` |
|---|---|---|
| nodes | 6,193 | 1,455 |
| nodes sharing a hash with another node | 2,228 (**36.0%**) | 323 (22.2%) |
| worst offenders | 633 empty `Cell`, 229 empty `thinking`, 217 `Row` | 79 `thinking`, 54 `Cell` |

Independently corroborated by `delta-ingestion-and-block-versioning-v2.md`,
measured 2026-08-27 from the other direction: of 6,601 blocks carrying a v0.1
handle, only 1,054 carried a `content_hash` at all — *"and the `Div` is exactly
the node that carries the handle you would cite."*

---

## 6b. SETTLED — alignment is positional, and that is the whole AoTA mechanism

**Measured 2026-09-03, and it collapses most of §8.**

Walk both trees in document order — parent, then children in `next` order — and
compare content hashes pairwise:

| session | old tree | new tree | identical prefix |
|---|---|---|---|
| `2e9cd256` | 5,496 nodes | 6,192 | **5,496 — 100.00%** |
| `cdb16054` | 221 nodes | 1,454 | **221 — 100.00%** |

**The old tree is a clean prefix of the new one. Exactly, not approximately.**

So the AoTA head check is: *walk both in document order, compare content hashes,
the old must be a prefix.* Delta ingest is: *mint nodes from index N onward.*
Neither needs a Merkle fold, a global identity, or a way to tell two identical
blocks apart.

**And this answers "why not 100% on a re-ingest?"** It is 100%, of the overlap.
The earlier 88.7% was the fraction of the *newer, larger* tree — misleading. Of
the **older** tree, `5,496 of 5,497` matched: **99.98%**, and the single miss is
the session root, because `params["lines"]` moved 2129 → 2248. One field, one
node, and it is the whole of §8's live question.

**The steps stay separable.** Alignment is a pure function of two trees —
`(old, new) → prefix length` — that writes nothing. Deciding what is new, and
writing it, are separate calls. Nothing here forecloses doing them at different
times, or asynchronously.

---

## 6c. SETTLED — what a hash can and cannot do, revised in v0.2.13

**This section was wrong as originally written, and the error was the table.**
The three-question table below named `content_hash` as answering "is this the
same *value*" — but v0.2.13 shipped a `record_hash` that answers a different,
narrower question, and the value question was not built at all. Both changes
are deliberate, and both are argued in full in `docs/design-total-mapping.md`;
this section states the outcome and keeps the measurements, which still stand.

| | answers |
|---|---|
| **`record_hash`** | is this the same *record* — mechanically, `H([type, params, content])`, unconditional on every node |
| **`record_subtree_hash`** (the fold) | is this the same *subtree* — reads `contains`/`next` only |
| **`guid`** | is this the same *thing* |
| **a class `alias`** | is this the same *X* — **and it names which X** (`docs/design-naming.md`) |

**The fourth row is the one that carries its own question.** The first three are
answers: a hash tells you two things match and nothing about what was compared,
because the projection that produced it lives outside the record. A class alias
stores the projection's *name* beside the hash, which is what makes a wrong merge
diagnosable and, for the first time, checkable. `docs/design-naming.md` is that
design; it changes nothing about the three rows above it.

**"Is this the same value" is not answered here, and is not scheduled here.**
`record_hash` looks like a value hash and is not one: two genuinely identical
empty `thinking` blocks now hash *differently* the moment `signature` is
stored on both, correctly, because they are the same value at different
moments carrying different provenance. That question is a query-time
projection, belongs in a layer, and is catalogued in `TODO-equality-layers.md`
— nothing in v0.2.13 schedules it.

Measured on the 6,193-node session:

| | nodes sharing their hash with another |
|---|---|
| content hash (pre-fold, v0.2.12 measurement) | 2,228 — **36.0%** |
| Merkle fold (pre-fold, v0.2.12 measurement) | 1,762 — **28.5%** |

**The fold helps for containers and not at all for leaves.** `Cell` collisions
drop 633 → 438 and `Row` 217 → 110, because their children differ. But the 229
empty `thinking` nodes have **one** distinct content hash and **one** distinct
fold — a leaf has no children, so its fold *is* its content hash. `Plain` (428)
and `logline` (405) are likewise unmoved. (v0.2.13 changed the *count* here —
`thinking` now also stores `signature`, so the 229 empty markers are no longer
identical to one another — but not the shape of the argument: a leaf's fold is
still exactly its own hash.)

**This is not a defect and no hash will fix it.** Two blocks with the same
`record_hash` are not necessarily "the same value" either — see above — but
even under the older, narrower reading the point held: what makes two blocks
different is sometimes only where they sit, which is what the guid is for, and
why content-addressed naming was rejected. Identity is positional, equality is
content-derived, and conflating them merges things that are only accidentally
alike.

**Hash choice, settled:** `guid` stays **UUIDv4**; `record_hash` and
`record_subtree_hash` are both **SHA-256**. UUIDv5 is a truncated MD5/SHA-1
namespace hash — weaker, shorter, and designed for naming rather than
comparison. Using one family for identity and another for equality also makes
it visible at a glance which is which, which is worth more than uniformity.

**The whitelist/blacklist question below (§8) is superseded, not answered.**
§8 asked which named list of params the fold and the hash should include, per
node type. v0.2.13 did not pick a list — it removed the question: total
mapping (`docs/design-total-mapping.md`) makes the *mapping* the whitelist, so
there is no second list to keep in sync with it. §8 is deleted rather than
amended; that document is where the reasoning now lives.

---

## 7. SETTLED — a new node per change, and no upsert anywhere

**Option A**, chosen. A changed paragraph is a new node with a new guid; the old
node stays, untouched and still true. Retraction is a tombstone, `seq` is audit
metadata rather than semantics, merging two bases is union, and `check` runs on
records exactly as it does today.

Mutation records — the same id re-asserted, last-write-wins — are **not adopted
now and are not foreclosed**. They can be layered on top of this log later; the
reverse is not true. Revisit only if the new-node form produces a measured pain
point rather than an anticipated one.

**So: no `UPSERT`, for TAs or anything else.** Asked directly, and the answer
falls out of Option A: nothing is ever re-asserted under an existing id, so
nothing needs last-write-wins, so nothing needs a sequence to be correct.

### Which records carry `revision_of` — roots only

Asked directly: *do the nodes get connected by revision edges, or only the
roots?*

**Only the roots.** A TA revision mints a whole new tree and chains its root to
the previous root with one `revision_of` edge. Individual blocks get **no**
revision edges.

Two reasons, and the second is the one that decides it:

- **Correspondence is computed, not stored.** §6b showed alignment is a
  positional walk over content hashes. "Which block in v2 is this block from
  v1?" is answerable on demand, from records that already exist. An edge per
  block would be storing an answer a walk already gives — and storing it once,
  at write time, is exactly the shape this project avoids.
- **A per-block revision edge would multiply.** The measured trees are 5,497 and
  6,193 nodes. One edge per block per revision is a second graph the size of the
  first, minted on every save, for a fact recomputable in one pass.

`revision_of` is therefore a small, sparse layer: one edge per revision of one
document. `cites` edges keep pointing at the old block, which stays exactly
true — someone cited that text and they did.

---

## 8. DELETED — see `docs/design-total-mapping.md`

This section proposed a per-type whitelist of params the fold and the hash
would include, hand-written and kept in the grammar. v0.2.13 shipped without
one: `docs/design-total-mapping.md` replaces the whole question with a
mechanical rule — the mapping is the whitelist, so there is nothing left to
write down and keep in sync with the code. Deleted rather than amended,
per `docs/roadmap.md`, "v0.2.13 — the fold", build step 7 — the reasoning this
section held now lives there instead, and this is a pointer rather than a
summary so it cannot drift from it.

One rejection from the original text is worth keeping here, since
`design-total-mapping.md` does not repeat it: **hashing the raw pandoc AST
node was considered and rejected.** It makes pandoc's grammar, not ours,
decide when two blocks are the same, and a pandoc upgrade would silently
re-identify the whole base.

---

## 9. SETTLED for now — a TA revision is a full tree, and the debate is booked

**Option A**, deliberately the unsophisticated one: each revision re-mints the
whole tree. Unchanged blocks get new guids and are recognised by content hash
and position rather than by being shared.

**Why this is acceptable today**, when the same waste was unacceptable for
AoTA: the duplication was already cut where it actually hurts. A transcript
re-ingested daily grows by ~700 nodes and re-minted 5,496 for nothing — that is
the 88.7% §6 measured, and §6b removes it. A README saved twice does not have
that shape or that frequency.

**Why the other options are not chosen yet.** Sharing unchanged blocks across
revisions gives them two `contains` parents and breaks `check`'s invariant 3.
Relaxing that invariant is expensive — it is what makes `render` a tree walk
rather than a graph walk. Splitting structure from content, git's tree/blob
model, is almost certainly where this ends up, but it changes what a *document
is*, and that deserves its own conversation rather than being decided as a
corollary here.

**Booked as its own discussion**, with the context above, so the conversation
starts from the measurements rather than from scratch.

---

## 10. PARKED — the file's life outside the base

Tracked-versus-internal is a real second dimension, orthogonal to `mutability`,
and the interesting cell is the daily one: compost does not *hold* a transcript,
it **tracks an external file that grows**. That is a different relationship from
ownership and may deserve to be recorded on the root.

**Explicitly out of scope for v0.3.0**, by decision rather than by drift. It
does not block anything below.

---

## 11. Parked, with the reason

- **Multi-writer CRDT semantics.** *"Maybe never."* Accepted. The consequence
  worth writing down: **single writer is assumed**, and that assumption licenses
  most of §7's Option A. If it ever changes, §7 reopens.
- **A service/API boundary** (FastAPI, container, Postgres). Real, and out of
  scope for 0.3.0. The relevant conclusion from that conversation: the boundary
  is the *service*, not the container, and enforcement at the domain layer is
  stronger than grants at the storage layer. Nothing here forecloses it.
- **Per-property mutation records.** Only wins when different sources own
  different fields of one node. Not this project's problem yet.

---

## 12. Packaging

Each version is provable alone, and nothing waits on a decision still open.

| version | content |
|---|---|
| **v0.2.10** | the index page — **shipped 2026-09-01** |
| **v0.2.11** | **the whitepaper** — `docs/` revamped into one structured document: the invariants, the shape, the grammar |
| **v0.2.12** | **the grammar, untangled** — a JSON Schema replaces the markdown-scraping test. The fold was *specced* here and did **not** ship here; see below |
| **v0.2.13** | **the fold** — `record_hash` on every node unconditionally, `record_subtree_hash`, total mapping as a tested property. Not the per-type whitelists: `docs/design-total-mapping.md` removed the question rather than answering it |
| **v0.2.14** | **the recursion made explicit** — one markdown digestor, delegated inputs stored as blobs |
| **v0.2.15** | **AoTA** — `mutability` declared and checked, positional alignment, delta ingest |
| **v0.2.16** | the ledger — retraction, provenance, replay as a filter |
| **v0.2.17** | **TA** — `revision_of` on roots, full-tree revisions |
| **v0.3.0** | the first semantic layer, over all of it |

**v0.2.12 absorbed the grammar untangling**, and the two belong together: its
deliverable was *per-type whitelists with a reason for each entry*, and if the
grammar is a schema then the whitelists are schema annotations rather than a
second document to keep in step.

**`jsonschema` becomes the third dependency**, after graphviz and duckdb, and
gets the same treatment they did — a stated justification. The argument is not
convenience: **valid records are the floor every graph-level check stands on.**
`check()` can only ask whether a graph hangs together if the records in it are
well-formed, and today nothing verifies that — `CLAUDE.md` says so plainly,
*"this is a trust model and the trust is currently unearned."* A schema without
a validator would leave that gap open while looking closed.

What a schema **cannot** do stays where it is: the ten invariants are
cross-record — no cycle in `contains`, the `next` chain is a total order,
exactly one parent — and no per-document validator can express any of them.
Three layers, each doing what it can: **schema** for what a record may be,
**`check()`** for what a graph must be, **prose** for why.

**The whitepaper still goes first**, because v0.2.12 changes what the grammar
*is*, and the paper has to describe a shape that has settled.

**v0.2.13 no longer waits on v0.2.12.** §6b showed AoTA alignment is a
positional walk over content hashes, which already exist. The fold makes the
check cheaper and gives ImTA its seal; it is not a prerequisite. If the fold
slips, AoTA still ships.

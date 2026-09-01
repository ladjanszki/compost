# Design — change, text artifacts, and the ledger (towards v0.3.0)

**Status: working document, jointly edited.** This is not `docs/roadmap.md` and
not `docs/decisions.md`. The roadmap holds work that has a version number and a
settled design; `decisions.md` holds what was decided and why. **This file holds
the argument while it is still an argument.**

The rule for using it: a section is either **SETTLED** — with the reason
attached, ready to be lifted into `roadmap.md` as a version — or **OPEN**, with
the options named and what each one blocks. Nothing sits here unmarked. When a
thing settles, it moves, and this file shrinks.

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

**Kind and route are orthogonal.** `--as=notes` says *how the bytes are read*;
the kind says *what may happen to it afterwards*. A markdown file can be an
ImTA (a dated note) or a TA (the README). The same route reads both.

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

## 2. SETTLED — the kind is declared at ingest and verified by `check`

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

**Still to specify exactly** — see OPEN §8. The fold must skip `guid`,
`created_at` and `tool_version` or two identical documents never fold equal. It
is one function, specified once, or a different JSON encoder silently makes
every document unique.

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
> Whether `seq` is semantics or audit metadata is decided entirely by OPEN §7.

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
whole of OPEN §8.

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

## 7. OPEN — new node per change, or a mutation record?

**The central fork.** Everything else in this document waits on it.

**Option A — a new node per version.** A changed paragraph is a new node with a
new guid. The old node stays, untouched and still true. Retraction is a
tombstone; `seq` is audit metadata only; merging two bases is union; `check`
runs on records as it does today.

**Option B — a mutation record.** `{op: upsert, id: …, payload: …}` — the same
id re-asserted. The graph becomes the **fold** of the log rather than the set of
records. `seq` becomes semantics (last-write-wins). `check` must run on the fold.
Merging needs conflict resolution.

**What is known:**

- `delta-ingestion-and-block-versioning-v2.md` establishes that Option B in its
  old form was rejected for three constraints — LLM-generated Cypher, per-block
  enrichment, no-git — **all of which have since expired**. Its conclusion is
  explicitly void and must be re-decided. So this is genuinely reopened, not
  re-litigated.
- Option A is what compost already is. Option B is a different database.
- Option B's own advocate (the ledger conversation, 2026-08-30) says whole-entity
  upsert is *"almost certainly right"* over per-property, and that per-property
  only wins when different sources own different fields of one node — which is
  not this project's situation.

**Recommendation: Option A**, with the ledger envelope carried as records-about-
records. It keeps §5's first invariant, keeps `check` where it is, and makes the
ledger purely additive — so it does not have to come first and cannot paint us
into a corner. Option B can be adopted later *on top of* Option A's log; the
reverse is not true.

**Blocks:** the ledger design, the retraction mechanism, and whether `seq`
exists at all.

---

## 8. OPEN — what goes into the fold

Specifically: which `params` participate.

The measurement in §6 makes this concrete. The `session` root failed to match
across ingests **only** because `params["lines"]` changed. If `lines` is in the
fold, every AoTA root changes identity on every append — which defeats §1. If it
is out, the fold must name what else is out.

Known cases needing a ruling:

- `lines` on a session root — **volatile by design**, changes on every append.
- `source` on any root — the same bytes ingested under a different filename.
  Should that be the same document?
- `log` on a `turn` — the whole original JSON line. It is what makes turns
  stable *and* unique across re-ingest, so it almost certainly stays in.
- `imported_at` on a `blob` — wall-clock, changes every time.

**Recommendation:** a fold over `[type, fold_params, content, [child folds…]]`
where `fold_params` excludes a **named, closed list** of volatile keys, written
in `docs/record-grammar.md` beside the two existing hash functions. Not a
heuristic, not "keys that look like metadata" — a list, with each entry's reason.

**Blocks:** delta ingestion, the AoTA head check, the ImTA seal.

---

## 9. OPEN — how a TA revision shares its unchanged blocks

The question as asked: *"what happens if I only change one block? Does
everything else get a new version, or do we point at the changed one?"*

The obstacle is structural, not philosophical. If revision 2 reuses revision 1's
unchanged block nodes, those blocks are now contained by two roots — and
`check`'s invariant 3 says every non-root node has **exactly one** `contains`
parent. Reuse breaks it.

**Option A — each revision is a full tree.** Simple, current, and pays the 88.7%
again on every TA edit.

**Option B — relax the one-parent invariant.** Cheap to say, expensive to mean:
that invariant is what makes `render` a tree walk rather than a graph walk, and
it is checked in four places.

**Option C — split structure from content.** A revision is an ordered list of
*references* to content nodes; content nodes are shared, structure is per
revision. This is git's tree/blob split, and it is Option A of the old delta-
ingestion doc, which was rejected for the LLM-Cypher constraint that no longer
exists.

**No recommendation yet.** C is almost certainly where this ends up, but it
changes what a document *is*, and that deserves its own argument rather than
being decided as a corollary here.

**Blocks:** TA support, and therefore the topic list, and therefore the first
semantic layer.

---

## 10. OPEN — the file's life outside the base

Raised as *"thinking about the files' afterlife"*, and it is sharper than it
looks: it is a second, orthogonal dimension to the kind.

| | tracked on disk | internal only |
|---|---|---|
| **ImTA** | a note you keep | a note ingested and deleted |
| **AoTA** | **a transcript — the file keeps growing and we re-read it** | a log written only through the tool |
| **TA** | a README rendered, edited, re-ingested | a plan that lives only in the base |

The AoTA/tracked cell is the interesting one, and it is the actual daily case:
compost is not *holding* the transcript, it is **tracking an external file that
grows**. That is a different relationship from ownership, and it may deserve to
be recorded on the root rather than left implicit.

**Not blocking**, but it should be settled before the ingest CLI grows a flag,
because the flag will encode whichever answer we pick.

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

## 12. Proposed packaging

Order chosen so each version is provable alone and nothing waits on a fork that
is still open.

| version | content | waits on |
|---|---|---|
| **v0.2.10** | the index page — sections, display names, filtering | nothing |
| **v0.2.11** | the fold: `subtree_hash`, the closed volatile-key list, `compost diff` | §8 |
| **v0.2.12** | AoTA — declared kind, delta ingestion, the head check | §8, §2 |
| **v0.2.13** | the ledger envelope — retraction, provenance, replay as a filter | §7 |
| **v0.2.14** | TA — revisions and block sharing | §9 |
| **v0.3.0** | the first semantic layer, over all of it | — |

**v0.2.11 is the keystone.** The fold is what AoTA, ImTA sealing, TA diffing and
the citation-carrying layer all read. It is also the only one of these that can
be built and proved with no other decision made.

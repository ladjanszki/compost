# TODO — equality layers: which sameness, and for whom

**Not scheduled. Input for v0.3.0 and after.** `record_hash` and
`record_subtree_hash` answer *is this the same record*. They deliberately do not
answer *is this the same thing I mean*. This file is the catalogue of the second
question — where the record hash is too selective, by how much, and what a layer
that fixes it would have to ignore.

Nothing here is a decision. It is the material for designing a layer builder.

---

## 1. The picture, and it is a physics picture

A node is a particle and its params are its **observables**. Two particles are
the same when every observable you chose to measure agrees; distinguishability
is not a property of the particles alone but of the measurement.

That framing is exact enough to be useful, and it carries three things over:

**Species first.** A `Header` and a `Para` are never the same, however their
params compare, the way an electron and a muon are never the same however you
measure them. `type` is in every hash for that reason.

**Intrinsic and extrinsic.** Physics distinguishes what a particle *is* — mass,
charge, spin — from where it happens to be. Our params mix both, and every
design mistake in this project's hashing has been an extrinsic quantity smuggled
into an intrinsic hash:

| smuggled | extrinsic to | cost, measured |
|---|---|---|
| `lines` on `session` | the tree, not the conversation | alignment prefix 0 of 2,306 |
| `attr[0]` on `Header` | position among siblings (`notes-1`, `notes-2`) | 6 of 1,546 headings |
| `signature` on `thinking` | the generation event, not the text | 491 blocks, 1 distinct text |
| `tool_use_id` | the join, not the command | 900 blocks, 897 distinct commands |

**The guid is a label, and labels are classical.** In physics, attaching a name
to each of N identical particles is what Maxwell–Boltzmann statistics does, and
for genuinely identical particles it is *wrong* — it overcounts microstates by
N!. Bose–Einstein and Fermi–Dirac get it right by refusing the labels.

compost is deliberately classical. Every node keeps its label, always. That is
not a claim that the nodes are distinguishable in any deeper sense — it is a
refusal to decide at storage time. **Because the labels are never discarded, any
statistics can be computed later; if we had merged at write time, no statistics
could be recovered.** That is the same argument as *filter at query time, never
at import*, arriving from another direction.

## 2. You were right: only false negatives — and here is why

The guess was *"since we have a guid we can only have false negatives."* True,
but the guid is not the reason. Two other things are.

**Total mapping is what buys it.** If the mapping drops nothing, then two
records being equal implies their source objects were equal. So for any notion
of sameness *coarser* than byte-identity of the source — every notion anyone
actually wants — record equality implies true equality. The hash can fail to
notice a sameness; it can never invent one.

Note what that means historically: before totality, this was **false**. The 491
empty `thinking` nodes had equal records and *unequal* sources, because
`signature` was discarded. That was a real false positive, sitting in the base
for four minor versions.

**The fold is what makes it true for containers.** A `BulletList` has no params:
its whole substance is its children, which live in other nodes. So
`record_hash` alone does *not* determine a container's source object — all 417
`BulletList`s in the corpus share one hash. `record_subtree_hash` does, because
it folds the children in. The precise statement is:

> Given total mapping, **`record_subtree_hash` equality implies the source
> subtrees were identical.** Hence, for any coarser notion of sameness, the fold
> yields false negatives only.

That is the third independent reason the fold ships in v0.2.13, and the
strongest one.

**And every false negative is recoverable**, because the records are immutable
and the labels are kept. A layer that got it wrong is re-run; nothing was lost.
This is the asymmetry the whole design leans on: a merge is irreversible, a
split is not.

## 3. The catalogue

Each case: what is over-selective, the measurement, and who wants it coarsened.

### 3.1 The generation nonce — `thinking.signature`
491 blocks, 491 distinct signatures, **1 distinct text** (all empty). A layer
ignoring `signature` collapses them to one class. Wanted by: *"show me the
distinct reasoning in this base"*. Not wanted by: anything that cites, because
each marker sits at a different point in a different conversation.

### 3.2 The join key — `tool_use_id` on `toolcall` and `tooloutput`
900 calls → **897 distinct commands (3 repeat groups)**. 900 results → **808
distinct outputs (42 repeat groups)**. Ignoring the id and, for the call,
keeping `{name, input}`, answers *"how many times have I run this exact
command"* and *"which commands always produce the same output"*. This is the
most obviously useful layer in the catalogue and the cheapest to build.

### 3.3 The positional identifier — `Header.attr[0]`
Pandoc generates a heading's id from its text and disambiguates repeats
positionally: `notes`, `notes-1`, `notes-2`. **6 of 1,546 headings, in 2 of 518
documents (0.4%).** Note the scope: pandoc numbers *within* one document, so two
`# Braindump` headings in two different files already agree. The layer only
matters for repeats inside one document, and it is a 0.4% effect — catalogued
for completeness rather than urgency.

### 3.4 The storage event — `blob.imported_at`, `blob.stored_as`
Both change on every import, so the same bytes imported twice give two blobs
with different hashes. This is correct — they *are* two storage events — and the
intrinsic quantity is already named and stored: `bytes_sha256`. The "same bytes"
layer needs no design, only a query. Listed so nobody designs it twice.

### 3.5 The turn — everything except the subtree
`record_hash` on a `turn` is unique for all 2,839 in the corpus, via `uuid`,
`timestamp` and `log`. A turn's *value*, though, is essentially its children. The
layer projects `{author}` plus `record_subtree_hash` and ignores the rest.
Worth noting this is the one type where a careful hand-written whitelist gave a
catastrophic answer — `{author}` alone merges all 2,839 into two classes — which
is why it is a layer and not a param rule.

### 3.6 Normalisation — not measured, and it should be
Two `Para` nodes differing only in trailing whitespace, or in a smart quote that
one reader produced and another did not. This is the classic equality layer and
we have **no measurement** for it. Someone should count, over the corpus, how
many `Para` nodes become equal under (a) whitespace stripping, (b) Unicode NFC,
(c) both. Until that number exists this case is folklore.

### 3.7 The non-case — the same value in two documents
Two `# Braindump` headings, two identical `Para`s in different notes: same
`record_hash`, different guid. **This already works and needs no layer.** The
hash says "same value", the guid says "different block", and both are true.
Included to calibrate the others: not every collision is a problem.

## 4. What a layer builder needs

From the cases above, a layer is fully specified by four things:

1. **A scope** — which node types it applies to. Sameness is per-species.
2. **A projection** — the observables it keeps. Everything else is ignored.
   Expressed over the record, not over the source, so it is recomputable.
3. **Whether it folds** — does the projection include the children's classes?
   §3.5 needs this; §3.2 does not.
4. **What it emits** — an `equivalent_to` edge between members of a class, or a
   class node each member points at. The second is O(n), the first O(n²) within
   a class, and §3.1's class has 491 members.

The last one is the only real design question, and it should be settled by
measuring the largest class a plausible layer produces before choosing.

## 5. Open

1. **Is a layer's projection declared in the schema, or passed on the command
   line?** `compost layer citation --by=uuid-link` already has the shape of an
   answer.
2. **Does a layer accumulate like `cites` does?** Re-running `layer citation`
   accumulates on purpose. For equivalence classes that is probably wrong, and
   "delete the file the run wrote" is the only inverse the design offers.
3. **Can a layer be wrong in a way `check` catches?** Today `check` verifies
   structure and would not notice an equivalence class containing two obviously
   different things.
4. **Does the physics parallel earn a place in the whitepaper**, or is it a
   thinking aid that should stay in this file? It is genuinely load-bearing for
   §2, which is a real theorem about the design.

# Design — which bytes are current (the `blob_of` tie-break)

**Status: OPEN.** One measured defect, fixed with a proxy in v0.2.15; the
proper answer is not built and is not scheduled. Written to be read rested.

---

## First, what this is *not* about

It is about **blobs**, not blocks — and the distinction is the whole reason
the problem is small.

A **block is never updated.** §7 of `design-0.3.0.md` settled that: a changed
paragraph is a *new node with a new guid*, the old one stays untouched and
still true, and there is no upsert anywhere in this project. So "two versions
of a block landing in the same second" is not a state this design can reach.
Two nodes minted in the same second are simply two different nodes, each with
its own guid, and nothing has to decide between them.

A **blob is the bytes of one ingest.** When an AoTA root is re-ingested,
storage does not deduplicate: the whole grown file is stored again, and the
root gains a *second* `derived_from` edge to a *second* blob. Now one root
points at two blobs, and something does have to decide which is current —
that is `blob_of`, and it is the only place in the system that has to pick
between two records rather than keep both.

So the question is narrow: **one root, several blobs, which bytes are the
current ones?**

---

## The defect, as measured

`_now()` records whole seconds (`records.py`, `.replace(microsecond=0)`).
`blob_of` ordered blobs by `imported_at` alone. Two ingests inside one second
therefore carried the *same* key, and the winner fell out of whatever order
the records happened to be in.

Reproduced directly: same records, reversed, different answer.

```
forward order -> 1.jsonl      reversed order-> 2.jsonl
```

That breaks a standing guarantee rather than merely being untidy —
`Store.load()` promises filenames carry no meaning and load order cannot
change the result. Here it changed the result.

Reachability is real but narrow: it needs two ingests of one artifact inside
the same second. A human will rarely do that. A test, a script, or a
migration loop does it constantly, which is how it was found.

## What v0.2.15 does about it

Orders by **`(imported_at, guid)`**. The guid is a stable property of the
record, so the answer no longer depends on load order. Verified across 52
shuffled orderings, and the suite fails if the second key is removed.

**On a tie the guid is arbitrary and means nothing.** A uuid4 carries no
recency. What was bought is determinism — one base always answers the same
way — and explicitly *not* correctness. The comment and the man page both say
so, because a note reading "latest by import time" over a tie settled by a
uuid would be the same defect the project keeps finding: a thing describing
something other than what it does.

## Why it can only be a proxy

Because **nothing in the records says which ingest came last.**

`imported_at` is audit metadata. It is the same class of field as
`created_at`, and this project has already decided, twice, what that class is
worth:

- `check()`'s twelfth assertion enforces two of PROV's three
  `wasDerivedFrom` constraints and **declines the ordering one**, on the
  stated grounds that `created_at` is not a semantic clock.
- v0.2.15's own `immutable` contract could not be built as specced — "no
  edges added after the ingest that created it" — for exactly the same
  reason, and shipped as a different proxy instead.

This is the third appearance of one missing thing. Increasing `_now()`'s
resolution would *not* fix it: finer timestamps make ties improbable rather
than impossible, and a race that is merely unlikely is still a race. It would
also change every future `created_at` for a problem that is not really about
time.

**And the project has already made this exact call once, in the other
direction.** `tools/loop.py`'s `round_name()` names each round of the
nvim→compost→claude loop, and its docstring says why it does not use a
timestamp:

> `date +%s` is one-second resolution and this loop can run faster than that;
> `round_name()` mints a uuid instead, which cannot repeat in any way that
> matters.

Same clock, same second, same conclusion — reached in v0.2.6 for filenames and
not carried over to blobs. Worth noticing that the answer there was *not* a
finer clock either: it was to stop deriving identity from time at all.

## The answer I think is right, unbuilt

A **`supersedes` edge, blob to blob.** A re-ingest mints one edge from the new
blob to the one it replaces, and "current" becomes *the blob that nothing
supersedes*.

- Order-independent by construction — it is a claim in the graph, not an
  inference from a field.
- No clock at all.
- It is the shape this project already uses for exactly this question one
  level up: `revision_of`, root to root, one sparse edge per revision.
- It makes a wrong answer *diagnosable*, because the chain is readable.

It was deliberately not built in v0.2.15: a new edge type is a schema change,
and slipping one into a release that was already specced is the same smuggled
precedent the roadmap refuses elsewhere.

## Where this generalises, and why it is worth deciding before v0.2.17

The tie is trivial today. It stops being trivial at **TA revision**, which is
v0.2.17.

A `mutable` root revised twice in quick succession produces two candidate
trees, and "which is current" becomes a question about *content the human
reads*, not about which copy of identical bytes to open. `revision_of` gives
that ordering structurally — root to root — which is the same answer as
`supersedes`, one level up.

So the two can be designed together, and probably should be: if `revision_of`
orders roots by a stated edge, blobs ordering by a stated edge is the same
idea applied consistently rather than a second mechanism.

## The questions to sleep on

1. Is `supersedes` worth a new edge type, or should a blob's currency be read
   off the `revision_of`/append structure that already exists?
2. If storage deduplication lands first (`TODO-storage-revamp.md`), does the
   question dissolve — several roots pointing at *one* blob, nothing to
   order — or just move?
3. Is there any caller that genuinely wants "current bytes" rather than "all
   bytes"? Today `views.py` is the only one, and a never-appended root has
   exactly one blob, so the question is currently hypothetical for every
   existing reader.
4. Should `_now()` keep sub-second resolution anyway, independently — not as
   a fix, but because a whole-second audit stamp is coarse for a tool that
   ingests in loops?

**Nothing depends on answering these before v0.2.15 ships.** The proxy is
deterministic, documented as a proxy, and the gap is named in the man page.

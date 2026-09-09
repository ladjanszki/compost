# TODO — the clock, and the ledger that needs one

**Not scheduled, and deliberately lifted out of the path to v0.3.0.** This is
the former **v0.2.16, "the ledger"** — retraction, provenance, replay — taken
out of the release line on 2026-09-09 and parked here whole. TA moves up into
its number. Nothing in v0.3.0 depends on anything below; §"Why this is safe to
remove" shows the check.

**Why it is worth doing anyway, in the human's words: they want *time*.** Not
retraction, which is what the planning agent kept weighting, and not
provenance, which is nearly built already. **Replay** — being able to ask what
the base looked like at some past moment, and get an answer. That is the
feature. Everything else here is scaffolding around it, and the reason this
file exists rather than a roadmap entry is that the scaffolding turns out to be
one unsolved problem.

---

## The one problem: this project has no semantic clock

Every record carries `created_at`, and the project has decided — repeatedly,
deliberately, and in writing — that it **means nothing**. It is audit metadata:
a note about when a byte was written, never a fact you may order two records
by. `docs/design-0.3.0.md` §7 settles it, and `check()` enforces the
consequence rather than the field.

That decision has now been made **three separate times, each time under
pressure, each time by declining to build the clock**:

**1. PROV's ordering constraint — `derived_from`, v0.2.14.** Borrowing
`prov:wasDerivedFrom` means honouring what PROV binds to it. Two of the three
are enforced by `check()`'s twelfth assertion: derivation is irreflexive and
acyclic. The third — *the source pre-exists the target* — is **explicitly not
enforced**, and the comment in `src/records.py` says why in one line:
`created_at` is audit metadata, not a semantic clock, so there is nothing to
order by. The schema records both halves, and a test asserts every borrowed
name declares what it does and does not honour.

**2. The `immutable` contract — v0.2.15.** `docs/design-0.3.0.md` §2 specified
`check` asserting that an `immutable` root gained **no edges after the ingest
that created it**. It could not be built. Nodes carry no creation time at all;
`created_at` on an edge is the field above; and load order cannot stand in,
because `Store.load()` guarantees file order carries no meaning. It shipped as
`check()`'s thirteenth assertion, an openly named **proxy** — at most one
`derived_from` per `immutable` root — with the gap it does not cover written
down beside it.

**3. Blob currency — v0.2.15.** An appended root has several blobs, and
`blob_of()` has to say which bytes are current. It orders by `imported_at`,
which `_now()` records to **whole seconds**, so two ingests inside one second
tie — and the winner fell out of record order, which the same `Store.load()`
guarantee forbids. Fixed by breaking the tie on guid: stable, and **arbitrary**,
documented as arbitrary. It cannot be better, because nothing in the records
says which ingest came last. `docs/design-blob-currency.md` is that question at
its smallest scale, and argues a `supersedes` edge as the real answer.

**And once before all three, in the other direction.** `tools/loop.py`'s
`round_name()` (v0.2.6) needed to name each round of the nvim→compost→claude
loop. Its docstring: *"`date +%s` is one-second resolution and this loop can run
faster than that; `round_name()` mints a uuid instead, which cannot repeat in
any way that matters."* Same clock, same second, same conclusion — and note the
answer was **not a finer clock**. It was to stop deriving identity from time.

### Replay is the fourth instance, and the first that cannot dodge

The three above were all dodged, correctly, because each had a structural
answer available: enforce the two constraints you can, assert a proxy, break
the tie on a stable label. **Replay has no such dodge.** "What did this base
look like on 2026-08-14" is a question *about time*, and answering it means
promoting something to a semantic clock — which is precisely the decision
deferred three times.

So the honest framing is not "build the ledger". It is:

> **Decide the clock. Replay is what you get once you have.**

Doing it inside a release that is also shipping retraction and provenance would
bury the one decision that matters under two that do not.

---

## The three parts, and what each is actually worth

### Provenance — mostly built, needs queries not records

`tool_version` on every edge since v0.2.8; `created_at` on every edge;
`derived_from` aligned to PROV-O with its honoured and unhonoured constraints
both declared; `blob.bytes_sha256` making duplicate bytes findable by query.

What is missing is a way to *ask*. This is closer to `docs/queries.md` work than
to a new record type, and it is the cheapest part of the three.

### Retraction — measured, and it has almost no customer

Measured 2026-09-09 against `base-v0.2.13-2026-09-08` (42,613 nodes):

| candidate for retraction | found |
|---|---|
| nodes under superseded re-ingest roots | **11,641 — 27.3%** |
| duplicate `layer` output | **0** of 35,902 layer edges |
| `unresolved_citation` placeholders | **7** |

And that 27.3% splits along the axis v0.2.15 introduced. Aligning each
superseded root against its replacement: **9 of 10 pairs are exact prefixes —
11,433 of 11,641 nodes, 98.21% of the older trees.** Every append-only source
aligns exactly. The single divergence is `compost.md`, a document that was
edited, at node 3 of 211.

**So 98.21% of it is AoTA, which v0.2.15 now prevents from ever accruing again,
and 1.79% is TA, which `revision_of` handles.** Neither wants a tombstone.

The one thing retraction would still buy: **a migration for bases built before
v0.2.15**, which carry their 27.3% with no way to say "this root was
superseded" short of deleting the whole file that holds it. That is a migration
release, not a capability — a different shape of work, and it should be
recognised as one before anyone starts.

### Replay — the actual want, blocked on the clock

Order can live **in the data** rather than in the file layout
(`docs/design-0.3.0.md` §5): a sequence or commit field per record, with
`Store.load()` still returning a set and the fold sorting by that field. Replay
to a point in time then becomes a **filter over records**, not a property of how
bytes are read — which is a genuinely good design and survives everything this
project believes about file order.

The catch is §5's own conclusion, reached two paragraphs later:

> **The ledger question and the mutation question are the same question.**
> Whether `seq` is semantics or audit metadata is decided entirely by §7 — and
> §7 settled on new-node, so `seq` is audit metadata.

Which is to say: **the design already contains the field replay needs, and
already ruled it meaningless.** Reversing that is the decision. It is not
obviously wrong to reverse it — §7's reasoning was about *upsert*, and replay is
not upsert — but it is exactly the kind of thing this project insists on
deciding out loud rather than discovering.

---

## Why this is safe to remove from the path to v0.3.0

`docs/design-0.3.0.md`: *"v0.3.0 is reached when change, the text artifacts, and
the first semantic layer exist."* Change is AoTA (shipped) and §7's new-node
rule (settled). Text artifacts are TA. The ledger is not in the sentence, and
§12 states the versions are independent: *"Each version is provable alone, and
nothing waits on a decision still open."*

Checked directly against the semantic layer's own design inputs:

| document | mentions of provenance / replay / retraction |
|---|---|
| `TODO-equality-layers.md` | **none** |
| `docs/design-naming.md` | **one** — §8, "Still open", item 3 |

That one reads: *"What happens when a member is retracted? A class that named it
still does. Probably correct — the class was true when minted — but it should be
decided rather than discovered."* It is a question that only **arises** if
retraction exists, and it already carries its provisional answer. With no
retraction there is nothing to retract, and it dissolves rather than blocking.

---

## What to decide, when this comes back

1. **Is `seq` (or `created_at`, or a commit id) promoted to semantics?** This is
   the whole thing. §7 said no, for upsert reasons that do not obviously apply
   to replay.
2. **If yes, what is the unit?** Per record, per ingest, per "commit"? An ingest
   is the natural boundary — it is already the thing that mints a blob and a
   `derived_from` — and would answer the `immutable` contract and blob currency
   at the same time, which is an argument for it being the right unit.
3. **Does `supersedes` (`docs/design-blob-currency.md`) fall out of the same
   decision?** It probably does: "which bytes came last" and "what did this look
   like then" are the same question at different scales.
4. **Is the pre-v0.2.15 migration wanted at all**, given the human's base was
   replaced on 2026-09-08 and the current one is empty? The 27.3% is in an
   archive nobody has to migrate.
5. **What happens to a class alias whose member is retracted** —
   `design-naming.md` §8.3, if and only if retraction gets built.

**Nothing here blocks TA or the semantic layer.** If replay never gets built,
the project loses a feature the human wants and nothing else.

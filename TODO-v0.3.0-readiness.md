# TODO — how ready v0.3.0 actually is

**SUPERSEDED IN ITS CONCLUSION, 2026-09-11. Read this warning before the rest.**

This file assessed `docs/design-naming.md`'s readiness and concluded *"design:
ready"*. **It assessed the wrong design.** I checked whether the ledger was a
prerequisite and whether the measurements held — and never asked whether the
layer being specced was the one the human wanted. It was not. `design-naming.md`
is an *equivalence* layer; the first semantic layer was always meant to be the
**talks-about layer**, and is now drafted in `docs/roadmap.md`, "v0.3.0 — the
talks-about layer".

**Checking an answer's readiness without checking the question is the error
here**, and it is worth leaving written down: every individual finding below is
still correct, and the conclusion they add up to was still wrong.

**What survives and is still worth reading:** the measurement warning in "The
real gap" — the human's base was replaced on 2026-09-08, the archive pre-dates
delegation, mutability and sections, and every merge rate in `design-naming.md`
§4.2 was taken on a shape that no longer exists. That applies to the
talks-about layer too, and is carried into its draft as open question 4.
---

## The design is in unusually good shape

`docs/design-naming.md` §5 settles the shape, and it settles it by **reusing
what exists**:

| | |
|---|---|
| new node types | **none** — a class is an `alias` |
| new edge types | **none** — membership is `names` |
| schema changes | **none** — `scheme` is already an open vocabulary |
| new writer | **none** — `layers._entity()` already writes this exact shape |
| new resolver | **none** — `lookup` already resolves an alias by `value` and already prints every alias sharing one |

`src/layers.py` already has the `BUILDERS` registry the design says to register
into, with `_citation` and `_kg8hex` as worked examples. **The first semantic
layer is, mechanically, one more entry in that dict.** That is a far smaller
build than the version number suggests.

§5.2 is the decision worth knowing: the term is **named and hashed, not
stored**. The alias holds the question (`scheme`) and the answer (`sha256`);
the value stays on the members, reachable through `names`. That makes every
class alias constant-sized and retires §4.3's cost table. Its consequence —
`scheme` must resolve to something *executable* — is the one open fork.

## What is still open, and none of it blocks a spec

1. **§6 — is a projection code or data?** A recommendation exists and is
   argued: **code first**, registered like `BUILDERS["citation"]`, with the
   scheme name recorded from day one so a declarative form can be attached
   later to names already in the base. That is the reversible order. It needs
   the human to say yes, not more analysis.
2. **§8.1 — how is a class reached from a member?** `names` points alias →
   member, so *which classes is this node in* is a scan. `views.py:_display_name`
   solved the same problem with a cached reverse index; the design notes a third
   occurrence would be the point to generalise. Small, and discoverable during
   the build.
3. **§8.2 — does a class alias want a `by` field** or is `scheme` enough? They
   would always agree, which argues for one.
4. **§8.3 — a retracted member.** **Moot.** Retraction left the release line on
   2026-09-09 (`TODO-the-clock.md`). Nothing to retract.

## The real gap: every merge measurement is on a shape that no longer exists

`design-naming.md` §4.1 is the most important thing in the document and it
argues against its own successors:

> The `toolcall` layer merges **0.7%** of nodes on the corpus and **85.3%** on
> the working base. […] Every merge rate in the catalogue is a lower bound taken
> on the wrong denominator. **A layer must be judged on a base that has been
> lived in.**

Three facts now collide with that:

**1. There is no lived-in base any more.** The human archived theirs on
2026-09-08 and started empty. The roadmap's own gate for v0.3.0 — *"re-measure
the largest equivalence class a plausible layer produces"* — cannot be
satisfied against anything except the archive.

**2. The archive pre-dates three releases.** Measured 2026-09-10 against
`base-v0.2.13-2026-09-08`:

- **no `delegates_to` edges at all** — it pre-dates v0.2.14's delegation
- **0 of 47 roots carry `mutability`** — it pre-dates v0.2.15
- and v0.2.16's sections will change document shape again

**3. It is stratified, not uniform.** `tool_version` stamps span **0.2.5,
0.2.8, 0.2.9, 0.2.10, 0.2.12**, and **42,447 records carry none at all**. It
was grown across seven releases and never fully re-digested, so measuring it
measures a mixture of shapes rather than any one of them.

### Which measurements survive, and which do not

The shape changes are specific, so the damage is specific. Delegation moved
**markdown prose** out of turn subtrees into delegated `document` roots;
sections will give `Header` children and a second attr.

| candidate layer (§4.2) | working-base figure | still valid? |
|---|---|---|
| `toolcall` by `{name,input}` | 85.3% | **probably yes** — not prose, untouched by delegation or sections |
| `tooloutput` by `{text,is_error}` | 86.6% | **probably yes** — same reason |
| `thinking` by text | 100% (one class) | yes, and §4.2 already concludes it is *not a layer* — one class for a whole type means the projection kept nothing |
| `turn` by `{author}` + subtree | 83.9% | **no** — delegation changed what a turn's subtree *is* |
| `Header` dropping `attr[0]` | 57.2% | **no** — v0.2.16 gives `Header` children and `section_attr` |
| `Para`/`Plain` by plain text | 1,921 classes >1 | **uncertain** — the nodes still exist but have moved under delegated roots |

**So the two layers most worth building are the two whose numbers most likely
survive.** That is luck, not design, and it should be confirmed rather than
assumed.

## What would make v0.3.0 spec-ready

In order, and only the first is blocking:

1. **A lived-in base built by the current tool.** This is the human's material
   and their sequencing — *do not offer to re-ingest for them*. Until one
   exists, any merge rate in the spec is either a corpus number (known to be
   two orders of magnitude wrong) or an archive number (a shape three releases
   stale). One re-ingest of their own material after v0.2.16 ships would
   restore every measurement at once.
2. **The human's answer on §6** — code or data. The recommendation is code
   first; it needs a yes.
3. **Re-run §4.2's table** on that base, and report each row as `x of y`.
   Specifically re-check the two rows marked *no* above, and whether
   `Para`/`Plain` merging changed when prose moved under delegated roots.
4. **Decide §8.2** (`by` versus `scheme`) — a one-line answer either way.

## The honest summary

**Design: ready.** No new record types, no schema change, one entry in an
existing registry, and the one fork has a recommendation.

**Measurement: not ready, and it is the project's own standing rule that
blocks it.** *Measure before designing* has never once failed to change the
answer here, and the numbers that would justify choosing a first layer are
currently taken on a base that no longer exists in that shape.

**This is not a reason to delay v0.3.0's design.** It is a reason the spec
cannot claim a merge rate until a current base exists. A spec that says *"build
the `toolcall` layer, it merges 85.3%"* would be repeating the exact mistake
§4.1 exists to warn about — with the denominator wrong in a new way.

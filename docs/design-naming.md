# Naming — Skolem terms, and what a layer mints

**Status: being decided.** Written 2026-09-06, out of a conversation about how
to describe a JSON transformation in a way no single tool owns. If it survives
review it becomes the spec for the first semantic layer and this file is
deleted; anything in it worth keeping reaches `docs/compost.md` first.

It answers four of the seven questions left open in `TODO-equality-layers.md`,
retires one of its six catalogued cases, and replaces it with a cheaper one
nobody had listed. §7 says which.

**How to read a `§` here.** A bare one is **this document**. Anything else
carries a tag, so a reference resolves where you are reading it and never by
scrolling back here. The tags are needed rather than decorative:
TEQ numbers its own sections 3, 4 and 5 on this same subject, so an untagged
`§3.2` would be ambiguous rather than merely terse.

| tag | file | what this document takes from it |
|---|---|---|
| **TEQ** | `TODO-equality-layers.md` | the catalogue of candidate layers, and the open questions answered in §7 |
| **D030** | `docs/design-0.3.0.md` | D030:§3, identity stays UUIDv4; D030:§6c, what each hash answers |
| **DTM** | `docs/design-total-mapping.md` | DTM:§1, *the code is the whitelist*; why the terms are faithful |
| **RG** | `docs/record-grammar.md` | RG:§3.4, what an `alias` is; RG:§6, the `scheme` vocabulary |

Two of TEQ's sections are numbered *lists* rather than subsections, so
**TEQ:§4.4** means item 4 of its §4.

---

## 1. Three names for one object

The project has circled the same thing three times, under three names, and did
not notice they were one thing:

- **`record_hash`** — v0.2.13, *is this the same record*.
- **`record_subtree_hash`** — v0.2.13, *is this the same subtree*.
- **the naming layer** — TEQ:§4, unbuilt, *is this the same thing I mean*, and
  stuck on what it should emit.

The object is a **Skolem function**: a deterministic map from a record's
meaningful content to a name, chosen so that two records denoting the same thing
land on the same name and two records denoting different things do not. It is
what a `MERGE` key is in Cypher, what a term map is in RML, what a shuffle key
is in map-reduce, and what Estuary calls a collection key. In data-exchange
theory a mapping rule is `∀x φ(x) → ∃y ψ(x,y)`, and Skolemizing is how the
existential — the thing on the target side that does not exist in the source —
gets a deterministic name.

**The first two already do it. Both store the *evaluation* of a term rather than
the term.** That is the whole of what follows.

## 2. What the hashes already are

| stored | the term it evaluates | where that term already lives |
|---|---|---|
| `record_hash` | `record(type, params, content)` | **in the record** — the hash's input *is* the record minus its label (`src/records.py:100`) |
| `record_subtree_hash` | `tree(record(…), [child terms…])`, recursive | **in the graph** — it *is* the subtree, reachable by `contains`/`next` |
| an `alias` | `scheme(value)` | in `params`. The only one stored as a term. |

A Merkle fold is a recursive Skolem term compressed bottom-up by a
collision-resistant function. That is not an analogy; it is what both things are.
So **the graph is already a Skolem term store and the hashes are its index** —
and `alias {value, scheme}`, written in v0.2.4 for a completely different reason,
is already the right shape for a term: `scheme` is the function symbol, `value`
its argument, and the `names` edge is the evaluation.

**Total mapping is what makes the terms faithful.** `docs/design-total-mapping.md`
makes the mapping lose nothing, so `record(type, params, content)` is isomorphic
to the source object. That is TEQ:§2's *only false negatives* theorem restated:
digest is injective, so equal terms imply equal sources.

## 3. What a term buys, and what it costs

`digest` is injective. **`layer` is deliberately not** — it drops observables on
purpose, and each of the catalogued cases drops a different set. So a layer is a
*quotient*, and a quotient needs a name that says **which** quotient.

A hash of a projection names the class and not the projection. Two layers' output
is then indistinguishable in the records, and a class that merged two things it
should not have cannot be diagnosed without re-deriving it from code that may
since have changed. **A hash can only be an answer; the question that produced it
lives outside the record.** A term carries its own question:

```json
{"scheme": "toolcall-ignoring-tool-use-id", "value": {"name": …, "input": …}}
```

That is the gain, and it is the reason to prefer a term. The cost is size, and it
is not small — §4.3. What §5 does is take the gain and refuse the cost.

## 4. The measurements

### 4.1 Two bases, and this is the most useful thing in this document

Everything below was measured twice.

- **the corpus base** — `tests/corpus` digested into a throwaway directory: 520
  notes and 7 transcripts, **527 roots, 32,653 nodes, 58,357 edges, `check` 0
  problems**. Reproducible by anyone with the pinned corpus.
- **a working base** — a lived-in one, 18 sessions and 28 documents, **42,072
  nodes, 71,401 edges**. Counts only; nothing of its content appears here.

**They disagree by two orders of magnitude on the number that matters.** The
`toolcall` layer — the one TEQ:§3.2 calls *"the most obviously useful layer in
the catalogue"* — merges **0.7%** of nodes on the corpus and **85.3%** on the
working base.

The catalogue is not wrong; it measured the corpus, and the corpus is a sample of
*documents*, not a sample of a working life. A command vocabulary is small and
fixed, so repetition grows with how much history a base holds and barely appears
in seven transcripts. **Every merge rate in the catalogue is a lower bound taken
on the wrong denominator**, which is the same failure `HANDOFF.md` records about
the 88.7% re-ingest number. A layer must be judged on a base that has been lived
in.

### 4.2 What each candidate layer actually merges

Nodes → classes, how many of those classes hold more than one member, and the
largest class:

| layer | corpus | working base |
|---|---|---|
| TEQ:§3.1 `thinking` by text | 491 → **1** (largest 491) | 1,382 → **1** (largest 1,382) |
| TEQ:§3.2 `toolcall` by `{name,input}` | 900 → 897, 3 classes >1, largest 2 | 2,370 → 1,288, 940 >1, largest 11 |
| TEQ:§3.2 `tooloutput` by `{text,is_error}` | 900 → 808, 42 >1, largest 10 | 2,370 → 1,175, 858 >1, largest 33 |
| TEQ:§3.3 `Header` dropping `attr[0]` | 1,757 → 1,054, 460 >1, largest 42 | 1,085 → 712, 248 >1, largest 9 |
| TEQ:§3.5 `turn` by `{author}` + subtree | 2,839 → **2,839, nothing merges** | 7,330 → 4,147, 2,968 >1, largest 4 |
| **new** — `Para`/`Plain` by plain text | 12,841 → 6,376, 3,292 >1, largest 894 | 9,101 → 5,217, 1,921 >1, largest 512 |
| *control* — `turn` by `{author}` alone | 2,839 → **3**, largest 1,779 | 7,330 → **3**, largest 4,726 |

Share of nodes landing in a class with more than one member:

| | corpus | working base |
|---|---|---|
| `thinking` | 100.0% | 100.0% |
| `toolcall` | 0.7% | **85.3%** |
| `tooloutput` | 14.9% | **86.6%** |
| `Header` | 66.2% | 57.2% |
| `turn` + subtree | 0.0% | **83.9%** |

Three things follow. **TEQ:§3.1 is not a layer, it is a single class** — one
class, every member, on both bases; a layer that produces one class for a whole
node type is telling you the projection kept nothing, not that the base is
uniform.
**TEQ:§3.5 needs a lived-in base to exist at all** — zero merges on the corpus.
And the *control* line is the reason this is a layer and not a param rule: a
hand-written whitelist of `{author}` alone gives three classes and merges
everything, exactly as TEQ:§3.5 warned.

### 4.3 Term size — the cost of storing the term

Canonical bytes of the projection. A hash is 64 whatever happens.

| projection | median | p90 | p99 | max |
|---|---|---|---|---|
| `thinking {text}` | 11 | 11 | 11 | **11** |
| `turn {author, subtree_hash}` | 80 | 80 | 80 | **80** |
| `Header {level, attr[1:], content}` | 157 | 288 | 429 | **680** |
| `toolcall {name, input}` | 508 | 2,653 | 12,967 | **15,722** |
| `tooloutput {text, is_error}` | 392 | 3,550 | 13,931 | **49,631** |

(corpus; the working base is the same shape — `toolcall` max 21,579,
`tooloutput` max **72,597**.)

Storing one term per **distinct** class, against 64 bytes per class:

| | terms stored | as hashes | ratio |
|---|---|---|---|
| `toolcall`, corpus | 1,010.7 KB | 56.1 KB | **18×** |
| `toolcall`, working base | 1,390.2 KB | 80.5 KB | **17×** |
| `tooloutput`, corpus | 1,136.8 KB | 50.5 KB | **23×** |
| `tooloutput`, working base | 2,563.8 KB | 73.4 KB | **35×** |

**The projections split into two kinds, and the split is structural rather than a
byte threshold.** One kind drops the extrinsic keys and keeps a bounded
descriptor — `thinking`, `turn`, `Header`, all ≤ 680 bytes. The other keeps the
payload itself: `toolcall`'s `input` and `tooloutput`'s `text` **are** the node's
substance, so their term is a second copy of the node.

### 4.4 The recursive term is the whole subtree

The fully expanded `tree(record(…), [child terms…])`, against the 64 bytes of
fold that summarise it:

| | largest root | expanded | ratio | whole base |
|---|---|---|---|---|
| corpus | session, 3,042 nodes | 4,700 KB | **75,200×** | 32.1 MB of term vs 33,728 B of fold |
| working base | session, 6,193 nodes | 6,369 KB | **101,901×** | 48.8 MB vs 2,944 B |

This is why Merkle hashing exists, and it settles the general rule: **the term is
the definition, the hash is the index, and for a recursive term the definition is
the graph itself.** Nothing needs to store it, because the graph already is it.

### 4.5 TEQ:§3.6 is retired, and something cheaper replaces it

TEQ:§3.6 calls whitespace-and-Unicode normalisation *the classic equality layer*
and notes it has no measurement. Measured now, as a ladder over `Para` and
`Plain`:

| | corpus | working base |
|---|---|---|
| by `record_hash` (the inline JSON) | 7,469 classes | 5,571 |
| by **plain text** | 6,376 (**−1,093**) | 5,217 (**−354**) |
| + whitespace collapsed | 6,373 (−3) | 5,214 (−3) |
| + Unicode NFC | **±0** | **±0** |

**Whitespace normalisation is worth three nodes in 12,841. NFC is worth exactly
zero, on both bases.** pandoc's AST has already tokenised runs of whitespace and
normalised the text, so the case the catalogue was saving room for was closed
before it was written. TEQ:§3.6 should be deleted, not scheduled.

What the ladder found instead is the step above it: **dropping the inline markup
and keeping the words** collapses 1,093 classes on the corpus and 354 on the
working base — two orders of magnitude more than the case that was catalogued.
The projection is `records.plain_text()`, which already exists, is already used
by `lookup` and the views, and needs no new code at all. It is the cheapest layer
in the catalogue and it was not in it.

**With one hazard that must be written down: `plain_text` erases `Link` nodes,
so a paragraph that cites something and one that does not become equal under
it.** That layer must never be used to reason about what cites what, and *never
scan text for citations* (`CLAUDE.md`) is the same rule arriving from a third
direction.

## 5. The design

### 5.1 A class is an alias, and membership is `names`

```json
{"record": "node", "type": "alias",
 "params": {"scheme": "toolcall-ignoring-tool-use-id",
            "value": "toolcall-ignoring-tool-use-id:<sha256 of the term>"},
 "created_at": "…", "tool_version": "…"}
```

plus one `names` edge to every member. **No new node type, no new edge type, no
schema change** — `scheme` is already an open vocabulary (RG:§6), `names` already
exists, `layers._entity()` already writes exactly this shape for the citation
layer, and `lookup` already resolves an alias by its `value` and already prints
every alias sharing one.

The `value` is `scheme + ":" + sha256` rather than a bare hash so that a class is
addressable by the resolver that exists, with the whole hash and no prefix —
short handles were removed on purpose (`src/records.py:45`) and this does not
bring them back.

### 5.2 The term is named and hashed, and not stored

This is the decision the measurements force, and it is better than the thing
§3 argued for.

§3 wants the term because the term explains itself. §4.3 says the term is 17–35×
a hash for the two layers most worth building. **Both win, because the value does
not have to be stored: every member holds it, and the `names` edges point at
them.** To read what a class means, take any member and apply the projection.
That is the total-mapping trick one level up — do not store what is recoverable,
but make the route to it explicit — and it is what `blob` already does, holding
`stored_as` rather than the bytes.

So the alias stores **the question** (`scheme`) and **the answer**
(`sha256`), and the value stays where it already is. Every class alias is
constant-sized whatever the payload, and §4.3's cost table stops applying.

**The consequence is that `scheme` must be resolvable to an executable
projection**, not merely descriptive — the record's readability now depends on
it. That is §6, and it is the one fork left.

### 5.3 Not pairwise edges

TEQ:§4 left this open: `equivalent_to` edges between members, or a class node.
**Class node**, and the numbers are not close — the largest class alone, in
`names` edges against pairwise ones:

| | class node | pairwise |
|---|---|---|
| TEQ:§3.1 `thinking`, working base | 1,382 | **954,271** |
| TEQ:§3.1 `thinking`, corpus | 491 | 120,295 |
| §4.5 `Para`/`Plain`, corpus | 894 | 399,171 |

A class node is also the only one of the two that has somewhere to put the
`scheme`.

**Mint one alias per class, including singletons.** Then *every node has exactly
one class alias per layer* and a query needs no special case for a node that
merged with nothing. The alternative — only classes with more than one member —
saves 348 aliases out of 1,288 on the working base's `toolcall` layer, and buys a
branch in every reader.

### 5.4 A layer can now be wrong in a way `check` catches

TEQ:§5.3 asked whether it could. **Yes, and cheaply**: `value` must equal
`scheme + ":" + sha256(canonical(projection(m)))` for *every* member `m` the
alias names. That recomputes from records alone, needs no source
file, and is the same shape as `check()`'s eleventh assertion. It catches a class
holding two things that are not equal under the projection it claims — the one
failure mode of a layer that matters, because a wrong merge is the irreversible
direction.

It needs `scheme` to be executable, which is again §6.

### 5.5 What a class alias is not

- **Not a merge.** Ladybug, Neo4j's `MERGE` and Estuary all make the Skolem term
  a primary key and apply the quotient destructively at write time. Here that is
  forbidden: *a merge is irreversible, a split is not*, and *filter at query
  time, never at import*. The quotient is stored **as records**, and its inverse
  is deleting the file the layer wrote — the only inverse the design offers, and
  enough, because nothing was lost.
- **Not a reduction.** compost needs none of Estuary's reduce annotations,
  because it never reduces: the class carries no merged params, every member
  keeps its guid and its own params, and *last-write-wins vs union vs error*
  never arises. This is the one place the worked example should not be copied.
- **Not `display_name`.** Opposite direction — an alias answers *what does this
  name resolve to*, a display name *what should be shown for this node*
  (RG:§3.4).
- **Not for a human to type.** A citation names a block; a class alias is reached
  from a member or by scheme.
- **Not a change to `guid`.** Identity stays UUIDv4 and positional (D030:§3).
  Content-addressed naming would merge 633 empty cells into one node and is
  still declined.

### 5.6 The fourth row for D030:§6c

| | answers |
|---|---|
| `guid` | is this the same *thing* |
| `record_hash` | is this the same *record* |
| `record_subtree_hash` | is this the same *subtree* |
| **a class alias** | is this the same *X* — **and it names which X** |

The first three are answers. Only the fourth carries its own question, and that
is the whole point of the shape.

## 6. The one fork left — is a projection code, or data?

TEQ:§5.1 asked whether a layer's projection is declared in the schema or passed
on the command line. §5.2 and §5.4 above — of *this* document — turn that from a
convenience question into a requirement: `scheme` must resolve to something
executable, or a class cannot be explained or checked.

**As code**, registered like `BUILDERS["citation"]` in `src/layers.py`.
Consistent with DTM:§1 — *the code is the whitelist* — reviewed, under test, and
the first three projections are one-liners. Reproducing an old class
needs the old code, which is why the alias already carries `tool_version`.

**As data**, a declarative projection spec — the JSON-transformation language
this whole thread started from. Diffable, validatable with `jsonschema` exactly
as records are, editable without a parser, and portable to an implementation that
is not Python. This is what the conversation was actually hunting for, and it is
the more ambitious answer.

**Recommendation: code first, and record the scheme name from day one.** A spec
language is a second thing to design, and designing it before three layers exist
is designing against no evidence. But every alias carries its `scheme` from the
first release, so a declarative form can later be attached to names that are
already in the base. That is the reversible order — the same asymmetry the rest
of the design leans on.

## 7. What this settles in `TODO-equality-layers.md`

| | was | now |
|---|---|---|
| TEQ:§3.2 "most useful layer" | 3 repeat groups in 900 | 0.7% on the corpus, **85.3%** on a working base — right conclusion, wrong denominator (§4.1) |
| TEQ:§3.6 normalisation | folklore, unmeasured | **measured and retired**: 3 nodes in 12,841, NFC zero. Replaced by plain-text (§4.5) |
| TEQ:§4.4 what a layer emits | open, edges vs class node | **class alias + `names`** (§5.1, §5.3) |
| TEQ:§5.1 projection: schema or CLI | open | must be *executable*; code first, name recorded (§6) |
| TEQ:§5.2 does a layer accumulate | open | yes, harmlessly — two runs mint two aliases with one value, which `lookup` already prints both of, tested |
| TEQ:§5.3 can `check` catch a wrong layer | open | **yes** — recompute `value` from every member (§5.4) |
| TEQ:§5.4 does the physics parallel belong in the whitepaper | open | untouched — still the human's call |

## 8. Still open

1. **How is a class reached from a member?** `names` points alias → member, and
   `Graph._rel` indexes edges by source, so *which classes is this node in* is a
   scan. `views.py:_display_name` hit the same problem and built a cached reverse
   index; a third occurrence would be the point to make it general.
2. **Does a class alias want a `by` field**, as citation edges have, or is
   `scheme` enough? They would always agree, which is an argument for one.
3. **What happens when a member is retracted** (v0.2.15's ledger)? A class that
   named it still does. Probably correct — the class was true when minted — but
   it should be decided rather than discovered.

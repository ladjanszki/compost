# The record format, and the pandoc AST ↔ compost translation

*Status: built and passing. `tools/records.py` implements it; `tools/test_records.py` and `tools/test_sabotage.py` verify it.*

This is the design for the two record types the graph is made of, and for the
pair of functions that move between them and pandoc's AST. It builds on
`decisions.md`, which fixes the dialect and lists the pandoc defects we work
around; read that first.

## The property this design exists to hold

```
records_to_ast(ast_to_records(ast)) == ast
```

Exact equality on the pandoc AST, for every document in `fixtures/` and
`corpus/`. This is the same test `tools/roundtrip.py` already runs against
pandoc alone, with our format spliced into the middle:

```
       pandoc reader                  our writer
  .md ──────────────► pandoc AST ──────────────► records
                          ▲                         │
                          └──────── our reader ◄────┘
```

Round-tripping through pandoc is now understood — 140/152 documents, with
three named pandoc defects for the rest. Anything the combined pipeline loses
beyond those is ours, which is what makes this test worth having.

## The one rule

Pandoc's `Block` type has fourteen constructors. Every one of them is a tag
plus some fields, and each field is either *blocks* or *not blocks*:

```haskell
Para        [Inline]                    -- no block fields
CodeBlock   Attr Text                   -- no block fields
Header      Int Attr [Inline]           -- no block fields
BlockQuote  [Block]                     -- one block field
Div         Attr [Block]                -- one block field
BulletList  [[Block]]                   -- a list of block lists
Table       Attr Caption [ColSpec] TableHead [TableBody] TableFoot
```

So the translation needs no per-constructor special casing, only one rule:

> **A node stores the constructor tag and every non-block field verbatim.
> Every block-valued field becomes child nodes, linked by `contains` edges.**

Non-block fields go in `params` and are copied as raw pandoc JSON — `Attr`
tuples, `ListAttributes`, `ColSpec`, `Format`, the heading level. We do not
model them, translate them, or normalise them. They are pandoc's, and the day
pandoc-types adds a field the mapping still round-trips.

Inline content goes in `content`, also verbatim, also unmodelled. That is the
decision already taken: inlines are not nodes, so `**foo**` keeps its
structure and hashes differently from `foo`, and plain text is derived at
render.

## Node

```json
{
  "record": "node",
  "guid": "d826c4dd-eb36-4da9-acab-f6f424a90803",
  "type": "Para",
  "params": {},
  "content": [{"t":"Str","c":"An"},{"t":"Space"},{"t":"Emph","c":[...]}],
  "content_hash": "99355172b2735ba755232245ff002d8fe64742851cbb347f2862aff3a4be2fee"
}
```

- `record` — `node` or `edge`. One word, no overlap with `type`.
- `guid` — UUIDv4. Identity. Permanent, never reused, never derived.
- `type` — **pandoc's own constructor name, verbatim**: `Para`, `Header`,
  `CodeBlock`, `BulletList`. No mapping table to maintain, no translation bugs,
  and `pandoc-types/src/Text/Pandoc/Definition.hs` is the schema documentation.
  Compost-native types are lowercase, so the two families never collide.
- `params` — the constructor's non-block fields, raw. Not an open key-value
  bag: for `Para` it is empty, for `Header` it is exactly the level and `Attr`.
  What goes in it is decided by pandoc's grammar, not by us.
- `content` — the inline array, raw. Absent for constructors that have none.
- `content_hash` — a dedup key, *not* identity. See below.

## Edge

```json
{
  "record": "edge",
  "guid": "6b4e5bfa-d8bf-4dc5-9581-70f8d38a2af9",
  "layer": "pandoc-ast",
  "type": "contains",
  "source": "1218c3a0-d84e-4900-92db-ed29a915d7bd",
  "destination": "d826c4dd-eb36-4da9-acab-f6f424a90803"
}
```

`layer` and `type` stay two sibling scalar keys. That *is* the JSON-native
encoding of a two-level taxonomy — the same as two columns in a table — and
nesting it as `{"type":{"structure":"contains"}}` would make variable key
names out of a closed vocabulary, which is hostile to every query and every
validator. Never concatenate them into `structure/contains`.

Edges carry a `guid` in this version, as decided: an `identity_hash` for
free deduplication is attractive but has to wait until the hash input is
pinned down, and a guid cannot lose information to an unforeseen case.

## Ordering: `next` edges, in the `pandoc-ast` layer

Sibling order is a chain of `next` edges, not an index field. An index would
be a denormalisation that this project does not need: deriving a fact from
several nodes and edges is what a graph is for, and the first hack of that
kind sets the precedent for the next twenty.

Stored in one direction only. `prev` is the same fact twice and two copies of
one fact can disagree; the loader reverses it, where it cannot drift.

What an index gave for free and a chain does not, so it becomes a check:

- exactly one head per parent — one child with no incoming `next` from a
  sibling
- the chain reaches every child exactly once: no forks, no skips, no cycles
- no `next` edge ever joins children of different parents

Those three are cheap to verify and catch every corruption an index made
structurally impossible.

## Node types compost has to invent

Pandoc's grammar has anonymous structure — places where the type is `[[Block]]`
with no constructor naming the inner list. Those still need identity, because
a list item is exactly the thing this corpus cites most.

| synthetic type | stands for | why it must exist |
|---|---|---|
| `ListItem` | one `[Block]` inside `BulletList`/`OrderedList` | 920 of them in the corpus. Un-addressable list items would gut the whole point |
| `DefinitionTerm` | the `[Inline]` of a definition pair | pandoc names neither half |
| `DefinitionItem` | one `[Block]` definition body | a term may have several |

### `Plain` versus `Para` is list tightness

These two constructors are not two names for a paragraph. Inside a list item
they are how pandoc records whether the list is tight or loose:

```
- first item          ->  BulletList [[Plain], [Plain]]     tight
- second item

- first item          ->  BulletList [[Para], [Para]]       loose

- second item
```

So they stay distinct, and not merely because keeping them is free — merging
them would erase list tightness, which is a visible difference in every
rendered view.

This is also what decides the shape of `ListItem`. A `ListItem` wrapping a
single `Plain` is two nodes for one citable meaning, and it is the *common*
case, not an edge case:

| list item shape | count | share |
|---|---|---|
| single `Plain` | 818 | 89% |
| single `Para` | 12 | 1% |
| multi-block | 90 | 10% |

**Rule: an item holding exactly one `Plain` or `Para` collapses into the
`ListItem` node**, which takes the inlines as its own `content` and records
which wrapper it was in `params.wrap`. Items holding anything else keep their
children. That removes 830 redundant nodes, keeps the citable thing and the
clicked thing the same node, and stays exactly reversible — the `wrap` field
is what makes it reversible rather than merely convenient, because without it
the collapse would silently loosen every tight list.

Table structure needs no invention — `Row`, `Cell`, `TableHead`, `TableBody`,
`TableFoot` and `Caption` are all real pandoc-types constructors, so they keep
their names like any other type.

## The fourteen constructors, and what the corpus actually contains

Counts from `fixtures/notes` (your bleached notes), `fixtures/edge-cases`, and
the 112-document `rust-book` corpus.

| constructor | notes | edge | book | children | params |
|---|---|---|---|---|---|
| `Para` | 380 | 65 | 3236 | — | — |
| `Plain` | 453 | 42 | 777 | — | — |
| `RawBlock` | 0 | 2 | 1132 | — | format, text |
| `CodeBlock` | 19 | 7 | 956 | — | `Attr`, text |
| `Header` | 121 | 6 | 543 | — | level, `Attr` |
| `BulletList` | 144 | 15 | 79 | `ListItem`* | — |
| `BlockQuote` | 3 | 7 | 50 | blocks | — |
| `OrderedList` | 8 | 4 | 12 | `ListItem`* | `ListAttributes` |
| `Table` | 0 | 2 | 13 | `Caption`, `TableHead`, `TableBody`*, `TableFoot` | `Attr`, `[ColSpec]` |
| `Div` | 0 | 12 | 0 | blocks | `Attr` |
| `HorizontalRule` | 2 | 3 | 0 | — | — |
| `DefinitionList` | 0 | 0 | 0 | `DefinitionTerm`, `DefinitionItem`* | — |
| `Figure` | 0 | 0 | 0 | `Caption`, blocks | `Attr` |
| `LineBlock` | 0 | 0 | 0 | — | — |

Two things worth noticing. **Eight constructors cover your notes completely** —
and `RawBlock`, `Table` and `Div` never appear in them at all, so the hard
cases are all borrowed from the test corpus rather than felt. And the three
constructors nothing exercises are the three worth implementing *last* and
testing with hand-written fixtures, because no real document will catch a bug
in them.

## The document node and `meta`

A markdown file becomes a `document` node — compost-native, lowercase — whose
children are the top-level blocks. It also has to carry the AST's `meta`,
which is a sibling of `blocks` and not reachable from any block. An importer
that reads `doc["blocks"]` and stops loses frontmatter silently; `decisions.md`
records this. Proposal: `params.meta`, verbatim, same rule as everywhere else.

## Defining `content_hash`

The hash input must be specified exactly or a different JSON encoder silently
duplicates every record. Proposal:

```
content_hash = SHA256( canonical_json([type, params, content]) )

canonical_json: sort_keys=True, separators=(',', ':'),
                ensure_ascii=False, encoded UTF-8
```

Children are excluded — they have their own identity, and including them makes
every ancestor's hash change when a leaf is edited.

**A node with no content gets no `content_hash`.** Container nodes —
`BulletList`, `BlockQuote`, `Div`, the table structure — have nothing of their
own to hash, and a field that is the same constant on every container is worse
than an absent one. Its absence is the honest statement that this node's
meaning lives entirely in its children.

The hash answers "is this the same paragraph", not "is this the same subtree".
If subtree comparison is wanted later, add a separate `subtree_hash` as a
Merkle fold; do not redefine this one.

**Duplicate imports are expected to sit side by side.** Importing the same
document twice mints fresh guids and produces identical `content_hash` values,
and both copies stay. Recognising them as multiples of one thing is a later
layer, not a constraint on the importer, and nothing here should try to be
clever about it in advance.

## Settled

1. **`Plain` and `Para` stay distinct** — they encode list tightness, so
   merging them is a loss, not a simplification.
2. **`ListItem` collapses** when it holds a single `Plain` or `Para`, carrying
   `params.wrap` so the collapse is reversible. 89% of items take this path.
   The goal is a knowledge graph, not a second copy of pandoc's tree: nodes are
   cheap, but a node that is never the thing anyone means is not worth minting.
3. **Order is a `next` chain in the `pandoc-ast` layer**, one direction only,
   with three loader checks replacing what an index made impossible.
4. **No `content_hash` on a node with no content.**
5. **The three pandoc defects are recorded and not worked around.** This costs
   nothing here, and the reason is worth stating: they live in pandoc's
   *writer*, downstream of everything this document describes. Our property is
   `records_to_ast(ast_to_records(ast)) == ast`, which is AST-to-AST, so the
   defects sit outside the boundary being tested. Suppressing them on read
   would have pulled them inside it and broken the round-trip by construction.

## Still open

- **Re-import identity.** Nothing here says how a second import recognises that
  a block is the block it saw last time. Deferred deliberately — it is the
  identity question — but it is the first thing that will hurt, because until
  it is answered every re-import is a fresh set of guids.
- **Where citations attach.** A `{#handle}` lives inside an inline array, and
  inlines are not nodes. The citation edge's `source` is therefore the block,
  not the reference itself, which means two citations in one paragraph are
  indistinguishable as edges. Fine for now; worth knowing before the citation
  layer is built.

## How this gets tested

Extend `tools/roundtrip.py` with a second stage, reusing every fixture:

1. `ast_to_records`, then `records_to_ast`, assert equality with the input AST.
2. Assert every node has exactly one incoming `contains`, except document roots.
3. Assert the `contains` graph is acyclic, and that the `next` chain under each
   parent has exactly one head and reaches every child exactly once.
4. Assert no `guid` appears twice with different content.
5. Assert a collapsed `ListItem` re-expands to the wrapper it came from, and
   that a tight list never comes back loose.
6. Assert a re-import of an unchanged file produces identical `content_hash`
   values and *different* `guid`s — the expected behaviour, not a defect, until
   re-import identity is answered.

**Result.** 520/520 documents round-trip to the identity — 40 fixtures, 478
documents from the test corpus, and two hand-built AST fixtures reaching the
constructors the reader cannot produce. 19,567 nodes and 35,308 edges. All
fourteen `Block` constructors are exercised, and all six sabotages are caught.

Item 1 is the whole design in one assertion. If it passes on every fixture and
every document in `corpus/`, the format is faithful to the AST and everything
else is a question of what we choose to build on top.

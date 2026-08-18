# The record format, and the pandoc AST ↔ compost translation

*Status: for discussion. Nothing here is built.*

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
  "layer": "structure",
  "type": "contains",
  "source": "1218c3a0-d84e-4900-92db-ed29a915d7bd",
  "destination": "d826c4dd-eb36-4da9-acab-f6f424a90803",
  "index": 4
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

## Ordering: an index on containment, not a `next` edge

`index` is the child's position in its parent's block list. The earlier draft
put reading order in a separate `order` layer as `next` edges.

**Recommendation: drop the `order` layer.** Two structures encoding one fact
can disagree, and this pair can disagree in ways nothing catches — a `next`
chain that skips a child, or orders two children of different parents. An
index cannot contradict itself. `next` is a one-line derivation in the loader,
where it cannot drift, which is exactly the argument the draft already makes
for storing `next` in one direction only rather than storing `prev` too.

The cost is that inserting a child renumbers its siblings. That is a rewrite of
`contains` edges, which are derived and freely rewritable, so nothing
immutable moves.

## Node types compost has to invent

Pandoc's grammar has anonymous structure — places where the type is `[[Block]]`
with no constructor naming the inner list. Those still need identity, because
a list item is exactly the thing this corpus cites most.

| synthetic type | stands for | why it must exist |
|---|---|---|
| `ListItem` | one `[Block]` inside `BulletList`/`OrderedList` | 920 of them in the corpus. Un-addressable list items would gut the whole point |
| `DefinitionTerm` | the `[Inline]` of a definition pair | pandoc names neither half |
| `DefinitionItem` | one `[Block]` definition body | a term may have several |

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

The consequence to accept deliberately: **container nodes collide en masse.**
Every `BulletList` has empty params and no content, so they all share one hash.
That is fine, because the hash is a dedup key and identity is the `guid` — but
it means the hash answers "is this the same paragraph" and not "is this the
same subtree". If subtree comparison is wanted later, add a separate
`subtree_hash` as a Merkle fold; do not redefine this one.

## Open questions

1. **Do `Plain` and `Para` stay distinct?** They differ only in whether a
   paragraph break is rendered, and `Plain` is 1272 nodes, almost all of them
   list item bodies. Keeping them distinct is free and lossless. Collapsing
   them would break the round-trip. Raised only because the distinction will
   look like noise in a view.
2. **Is a `ListItem` worth a node when it holds exactly one `Plain`?** That is
   the common case — the item and its text would be two nodes with one
   citable meaning, and a human clicking the text probably means the item.
   Options: keep both, or collapse single-`Plain` items into the `ListItem`
   and re-expand on write. The second is lossy-looking but provably reversible.
3. **Where does `index` live** — on the edge, as proposed, or as a field on the
   child node? On the edge is right if a node can ever have two parents; the
   draft's invariants say it cannot.
4. **Does `document` get a `content_hash`?** It has no content of its own.
5. **What happens to the three synthesised-content defects** from
   `decisions.md` — the callout title `Div`, the `<!-- -->` separators, the
   tight-list code block. They are pandoc's, but our writer decides whether to
   reproduce, suppress or repair them. Suppressing on read means the AST
   round-trip fails by construction; repairing on write means our output stops
   matching pandoc's. This needs a decision before the writer is built.

## How this gets tested

Extend `tools/roundtrip.py` with a second stage, reusing every fixture:

1. `ast_to_records`, then `records_to_ast`, assert equality with the input AST.
2. Assert every node has exactly one incoming `contains`, except document roots.
3. Assert the `contains` graph is acyclic and `index` is dense from 0 per parent.
4. Assert no `guid` appears twice with different content.
5. Assert a re-import of an unchanged file produces identical `content_hash`
   values — and *different* `guid`s, since guids are minted, which is the first
   thing that will need a stable-identity answer.

Item 5 is where the design will first hurt: nothing here says how a re-import
recognises that a block is the same block it saw last time. That is deliberate
— it is the identity question, and it stays deferred — but the test should
exist and be expected to fail until it is answered.

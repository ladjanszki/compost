# v0.2 text importer — decisions and known issues

Working document for the pandoc-only importer. Decisions here are settled
unless revisited explicitly; known issues are accepted and *not* being fixed
in this step. Everything is measured against pandoc 3.10.1 / pandoc-types
1.23.1.2 on the 19 notes in `raw/` plus the six root markdown documents.

## The dialect

`.md` input is read as **gfm**, with no extension surgery.

```
read:   pandoc -f gfm -t json
write:  pandoc -f json -t gfm --wrap=preserve
```

Chosen over `markdown`, `commonmark` and `commonmark_x` because its defaults
are the safe ones — `attributes` off, `smart` off, `fancy_lists` off — and
those three are exactly the settings that silently corrupt this corpus.
Measured: 1625 addressable blocks (bare `markdown` finds 1488), AST fixed
point on 25/25 files, zero normalisation rules needed.

Two invariants that outrank the flag list. Any reader satisfying both is a
legitimate choice; gfm satisfies both without configuration.

- `{#...}` must stay **literal text**. With `attributes` on, `commonmark_x`
  parses `{#fce6a885}` as an attribute and turns a *citation* into an anchor
  *definition* — an empty `Span` carrying that id, colliding with the real
  block that owns it. Silent, and retroactive across every stored note.
- `---` must stay **three hyphens**. With `smart` on, the reader collapses
  `—`, `---` and `--` into two typographic characters before anything is
  stored. This is reader-side, so it is unrecoverable.

Enabling either later is a canonization-time change disguised as a flag.
Extensions may be added *additively* (`gfm+fenced_divs+definition_lists`)
because those change text that was previously inert.

## Decisions taken

- **Inlines are not nodes.** A block node stores its pandoc inline array
  verbatim as nested JSON in `content`. Plain text is derived at render, never
  stored as the authoritative form. Storing only flattened text would make the
  graph unable to rebuild the AST, and would hash `**foo**` and `foo` alike.
  Whether a link or an image becomes its own node stays open until a query
  needs it.
- **Identifiers: a guid on nodes *and* edges.** Nodes carry `guid` (UUIDv4,
  identity) and `content_hash` (SHA256, a dedup key — not identity). Edges
  carry a `guid` too in this version. A pure content-hash identity for edges
  is attractive and may come later as an optional `identity_hash`, but only
  once the hash input is pinned down; until then a guid cannot lose
  information to an unforeseen edge case.
  - Whatever hashes exist, the hash *input* must be specified exactly — field
    order, key sorting, UTF-8, separators, no whitespace. An undefined
    serialisation means a different JSON encoder silently duplicates every
    record.
  - A guid may live in an edge, never in stored text. Handles inside immutable
    prose cannot be rewritten; edge endpoints can be remapped freely. This is
    what keeps the later switch to short ids a migration rather than a rewrite.
- **Directory layout as drafted**: everything hidden and mixed under
  `.compost/` — `storage/`, `graph/`, `views/`. Accepted for simplicity in
  this version. The known cost is that committed ground truth and disposable
  generated output sit side by side, and that `rg`/`find`/GitHub skip dotdirs
  by default. Revisit later via configurable external paths in a settings file
  under `.compost/`.
- **pandoc-types is the AST grammar ground truth**, cloned to
  `text-importer/pandoc-types/` and gitignored. `Definition.hs` *is* sufficient
  to derive the JSON without reading much Haskell: the data declarations give
  the shape, and one line at `Definition.hs:391` gives the encoding rule —
  `sumEncoding = TaggedObject { tagFieldName = "t", contentsFieldName = "c" }`.
  That is the whole `{"t": …, "c": …}` convention.

## Known issues — accepted, not fixed now

- **Callout titles are doubled.** Pandoc synthesises title text that is not in
  the source:

  ```
  source:   > [!IMPORTANT]
            > This all leads to the conclusion that...
  AST:      Div .important > [ Div .title > Para "Important", Para "This all…" ]
  ```

  `Important` was never typed. A naive "every AST block is a node" ingestion
  would mint a node with content the author never wrote, hash it, and make it
  citable — breaking the invariant that a document's rendered text equals its
  source text. The intended fix, when we get to it: treat `Div .title` inside
  an alert as derived presentation, with the alert type as a property of the
  container node and the title regenerated at render. This is a compost-side
  modelling choice, not a pandoc workaround.
- **Byte-identical round-trip is not achieved, and is not the goal.** 4 of 19
  notes come back byte-identical; all 19 come back **AST-identical**. The
  differences are surface only: list indent width, blank-line runs collapsing,
  fenced code blocks rewritten as indented ones, `1.` becoming `1. `, `---`
  redrawn as a long rule.
- **Whitespace is normalised.** Consecutive spaces collapse to one and
  trailing whitespace is dropped, because the AST holds a single `Space` node
  regardless. Content hashes are therefore over normalised text, not over the
  author's bytes.
- **Invented callout types degrade to a quote.** Only `NOTE`, `TIP`,
  `IMPORTANT`, `WARNING`, `CAUTION` map to a `Div`. `> [!HEUREKA]` becomes a
  plain `BlockQuote`; the text survives and the AST is still a fixed point,
  but it writes back with escaped brackets as `\[!HEUREKA\]`.
- **No PDF reader in pandoc.** `pdf` is an output format only, so PDF input
  needs a separate extractor. Deferred.
- **djot.js and the `npx` spawn stay for now**, to be removed as part of 0.2
  rather than ahead of it. Pandoc reads and writes djot natively, so nothing
  blocks it.

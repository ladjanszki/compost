# v0.2 text importer — decisions and known issues

Working document for the pandoc-only importer. Decisions here are settled
unless revisited explicitly; known issues are accepted and *not* being fixed
in this step. Everything is measured against pandoc 3.10.1 / pandoc-types
1.23.1.2 on the 19 notes in `raw/` plus the six root markdown documents.

## The dialect

`.md` input is read as **commonmark_x**, with three extensions disabled.

```
read:   pandoc -f commonmark_x-smart-attributes-fancy_lists -t json
write:  pandoc -f json -t commonmark_x-smart --wrap=preserve
```

*This reverses an earlier decision to use `gfm`, and the reversal is the
reason to keep a corpus around.* On the 25 documents of this repo both score
identically — 1625 addressable blocks, fixed point everywhere — so gfm won on
having the safe defaults. Measured against 112 more documents from a real
documentation site, they separate sharply:

| read / write | fixed point |
|---|---|
| `commonmark_x` tuned | **140 / 152** |
| `markdown` + list extension | 119 / 152 |
| `gfm` | 71 / 152 |

The gfm *writer* loses data that the commonmark_x writer keeps — most of all
code fence info strings containing a comma, which is how every mdBook, Jekyll
and Docusaurus corpus annotates its examples:

```
source        ```rust,ignore        classes: ["rust,ignore"]
gfm writes    ```                   classes: []            <- lost
cmx writes    ``` rust,ignore       classes: ["rust,ignore"]
```

The three disabled extensions each prevent a silent corruption, and none of
them is optional:

- `-attributes` — otherwise `{#fce6a885}` parses as an attribute and a
  *citation* becomes an anchor *definition*: an empty `Span` carrying that id,
  colliding with the real block that owns it.
- `-smart` — otherwise the reader collapses `—`, `---` and `--` into two
  typographic characters before anything is stored. Reader-side, so
  unrecoverable.
- `-fancy_lists` — otherwise it silently suppresses `task_lists` and every
  `- [x]` stays literal text. `--list-extensions` reports `+task_lists` the
  whole time; there is no warning.

The two invariants that outrank the flag list, and that any replacement reader
must satisfy: **`{#...}` stays literal text** and **`---` stays three
hyphens**. Enabling either extension later is a canonization-time change
disguised as a flag. Extensions may be added *additively* because those change
text that was previously inert.

Verified surviving a full read/write/read cycle: handles plain and expanded,
all four dash forms, checked and unchecked task items, all five callout types,
and comma-bearing fence info strings.

## Citations

A reference is written **`{@a1b2c3d4}`**, not `{#a1b2c3d4}`.

`{#x}` means "this element *has* id x" in every markup language that knows the
notation, and both pandoc and djot act on it. Using it to mean "points at x"
was backwards, and any reader with `attributes` enabled silently agreed with
the language rather than with us. The two notations now say what they mean:
`{#x}` assigns, `{@x}` refers. Verified unescaped through a full read/write
cycle, plain and expanded.

**Citation edges are derived, not asserted.** The draft classed them as
asserted alongside `derived_from`, but the stated reason `derived_from` must be
asserted is that no parser can recover it — and a citation is the exact
opposite, sitting in the text where a regex finds it every time.

That is what dissolves the duplication worry. Two copies of a fact can diverge
only if both are authoritative. The text is the source of truth and the edge is
a projection of it, so a stale edge is a rebuild to run rather than a conflict
to resolve — exactly like `contains`. The original text is never rewritten to
remove the reference, and the graph still gets real edges.

**The existing corpus is normalised during migration, not by editing history.**
A line that is exactly `{#xxxxxxxx}` is an assignment and stays one; every
other occurrence is a citation and becomes `{@xxxxxxxx}` in the records the
migration produces. The conversation files on disk are never rewritten, so the
append-only rule holds — the change happens in the translation to a new store,
with the originals preserved.

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
- **Pandoc's writer injects `<!-- -->` separators.** Two adjacent lists that
  would otherwise merge — a task list beside an ordinary list, a list followed
  by a code block inside a quote — are separated by an HTML comment. It
  re-reads as a `RawBlock` that nobody wrote. Same class as the callout title:
  synthesised content the source never contained. Writer-independent.
- **A code block inside a *tight* list item is destroyed.** The writer emits it
  as an indented block with no preceding blank line, and an indented code block
  requires one, so it re-reads as lazy paragraph continuation and the
  `CodeBlock` node is gone. A *loose* list — blank lines between items —
  survives intact. Writer-independent.
- **Inline code adjacent to raw inline HTML is mangled.** `<span>` … `` `a` ``
  … `</span>` comes back with the code merged into the raw inline as
  `` a``</span> ``. Accounts for 5 of the 9 remaining failures on the test
  corpus.
- **Document metadata lives outside `blocks` and is dropped by default.** A
  YAML frontmatter block is parsed into the AST's `meta` field, not into
  `blocks`, and every writer omits it unless `--standalone` is passed:

  ```
  pandoc -f gfm -t json note.md | pandoc -f json -t gfm       -> frontmatter gone
  pandoc -f gfm -t json note.md | pandoc -f json -t gfm -s    -> frontmatter kept
  ```

  This is not a gfm quirk — `markdown`, `commonmark_x`, `djot` and `html` all
  behave the same way. No note in `raw/` has frontmatter today, so it is a
  latent trap rather than a live bug, but the record schema currently models
  only blocks and has nowhere to put `meta`. The importer must read it
  explicitly or a whole class of content vanishes without an error.
- **No PDF reader in pandoc.** `pdf` is an output format only, so PDF input
  needs a separate extractor. Deferred.
- **djot.js and the `npx` spawn stay for now**, to be removed as part of 0.2
  rather than ahead of it. Pandoc reads and writes djot natively, so nothing
  blocks it.

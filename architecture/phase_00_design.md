# Test 00 — Design Document

## 1. Purpose

This document describes the design for **Test 00**: the first concrete implementation step of the v1 knowledge store pipeline. It is self-contained and intended for review before implementation begins.

Test 00 implements the ingestion of a single Djot document into the canonical JSONL storage format defined in the v1 system design (`agentic_local_knowledge_store_v1_design_v4.dj`).

---

## 2. Background

### The v1 knowledge store

The v1 system is a local-first, block-based knowledge store. Its central concepts are:

- **Block**: the atomic versioned content unit. Each block has a stable ID, a type derived from its markup, a content payload, and a SHA-256 hash for change detection.
- **Page**: a document represented as an ordered flat list of block IDs.
- **Canonical storage**: JSONL files (`blocks.jsonl`, `pages.jsonl`). These are the source of truth. All other representations (HTML, SQLite indexes, LadybugDB graph) are derived projections.
- **Authoring format**: Djot (`.dj` files). Djot is a formally parseable light markup language by John MacFarlane (creator of Pandoc and CommonMark). It is close to Markdown but unambiguous and formally specified.
- **Block IDs in Djot**: Djot has native support for block-level attributes. The syntax `{#blk_001}` placed before a block element assigns that element a stable ID. Blocks without an explicit `{#id}` attribute receive an auto-generated ID during ingestion.

### Why this test first

Before building the full pipeline (conversations, operations, mutations, rollback, rendering, LadybugDB indexing), we validate the foundational step: **Djot → Pandoc AST → block records → JSONL**. If this works correctly and produces the expected schema, all later steps can build on it.

---

## 3. Scope

### In scope

- Parse a `.dj` file using Pandoc into its AST JSON representation.
- Walk the AST and extract one block record per block-level element.
- Handle the block types present in the test file: `heading`, `paragraph`, `list_item`.
- Auto-generate UUIDv7 block IDs (no explicit `{#id}` attributes in the test file).
- Reconstruct inline Djot markup from AST inline nodes (preserve bold, italic, softbreaks as Djot syntax).
- Compute SHA-256 hash of the serialized `content` object per block.
- Write block records to `blocks.jsonl` (one JSON object per line).
- Write a page record to `pages.jsonl` (one JSON object).
- Set up the conda environment and install dependencies.

### Out of scope for Test 00

- Explicit `{#id}` attribute handling (no IDs in the test file; deferred to Test 01 or later).
- Block versioning and change detection (no existing blocks to compare against).
- Conversations, operations, mutations, rollback.
- SQLite index building.
- HTML rendering.
- LadybugDB ingestion (planned for Test 01).
- Any block type not present in the test file (code, table, quote, image, math, div).

---

## 4. Test input

The test file is a minimal Djot document that exercises the core block types: heading (two levels), paragraph, and list items. It has no explicit `{#id}` attributes.

```djot
# Example heading - for the test file

I'm writing the first paragraph which has *bold* and _italic_
And maybe other text

Another paragraph about lorem ipsum
And the beauty of life

## This is a nested heading

And in this part we'll have a list as well

- just
- for
- the
- fun
```

Blank lines after each heading are required in Djot to terminate the heading element. Without them, Pandoc treats the following paragraph as a continuation of the heading. This file is saved as `tests/test_00/test_00.dj`.

---

## 5. Pandoc AST structure

Pandoc parses Djot into a typed AST. The key findings from inspecting the actual AST output for this file:

### `{#id}` attributes and `Div` wrappers

When a block has an explicit `{#id}` attribute, Pandoc wraps it in a `Div` node that carries the ID:

- A `{#id}` on a **heading** → `Div` with class `section` and the given ID, containing the `Header` node and all sibling content until the next same-level heading.
- A `{#id}` on a **paragraph, list item, etc.** → `Div` with attribute `wrapper: 1` and the given ID, containing just that one block element.

The `Div` is Pandoc's ID carrier, not a meaningful document container. The walker treats `Div` nodes as transparent: it extracts the ID from the `Div` and derives the block type and content from the child element inside.

### Section nesting

Pandoc wraps each heading and its following content in a `Div(section)`. This is an AST representation artifact — it does not map to a container node in our schema. The page `root` array is a **flat** ordered list of block IDs. Heading hierarchy is implicit in the `level` field of heading blocks, consistent with the v1 design.

### List items

Each `- item` in a bullet list becomes a separate `BulletList` node in the AST containing one `Plain` node. When each list item has its own `{#id}`, each gets its own `Div(wrapper)`. This confirms the one-`{#id}`-one-block mapping is clean.

### Inline nodes

Inline content (bold, italic, text, line breaks) is represented as a list of typed tokens:

| AST node | Djot reconstruction |
|----------|-------------------|
| `Str` | literal string value |
| `Space` | `" "` |
| `SoftBreak` | `"\n"` |
| `Strong` → children | `*...*` |
| `Emph` → children | `_..._` |

Inline markup is reconstructed as raw Djot and stored as-is in `content.text`. It is not parsed further and not stored as sub-nodes.

---

## 6. Block schema (from v1 design)

Each block record follows `block.v1`:

```json
{
  "id": "019xxxxxxxxxxxxxxxxxxxxxxxxx",
  "version": 1,
  "schema": "block.v1",
  "type": "paragraph",
  "content": {
    "text": "I'm writing the first paragraph which has *bold* and _italic_\nAnd maybe other text"
  },
  "created_by": "human:test",
  "created_at": "2026-05-08T10:00:00Z",
  "hash": "sha256:abc123..."
}
```

### Type-specific content fields

| Block type | Content fields |
|------------|---------------|
| `heading` | `text`, `level` (integer 1–6) |
| `paragraph` | `text` |
| `list_item` | `text`, `style` (`"unordered"`) |

`text` always contains Djot inline markup as-is (e.g. `*bold*`, `_italic_`).

### Block ID

UUIDv7. Chosen because:
- Globally unique with negligible collision probability.
- Embeds a millisecond-precision creation timestamp, making IDs sortable by creation time without a separate index.
- When a human later adds an explicit `{#id}` attribute to a block, that named ID takes precedence over the auto-generated UUIDv7.

### Hash

SHA-256 of the JSON-serialized `content` object (keys sorted, no extra whitespace). Used in future ingestion passes for change detection: if the hash of the incoming block matches the stored hash, no new version is created.

---

## 7. Page schema (from v1 design)

```json
{
  "id": "page-test_00",
  "schema": "page.v1",
  "title": "Example heading - for the test file",
  "root": [
    "019xxx-blk1",
    "019xxx-blk2",
    "019xxx-blk3",
    "019xxx-blk4",
    "019xxx-blk5",
    "019xxx-blk6",
    "019xxx-blk7"
  ],
  "created_by": "human:test",
  "created_at": "2026-05-08T10:00:00Z",
  "updated_at": "2026-05-08T10:00:00Z"
}
```

- `root` is a **flat** ordered list of all block IDs in document order.
- `title` is derived from the first `heading` block's text.
- The page ID is derived from the source filename for Test 00.

---

## 8. AST walker logic

The walker processes the Pandoc AST recursively. The rules:

```
visit(node):

  Div with class "section":
    → extract id from Div attrs (or generate UUIDv7 if absent)
    → the first child is a Header → emit heading block using this id
    → recurse into remaining children

  Div with attr "wrapper":
    → extract id from Div attrs (or generate UUIDv7 if absent)
    → the single child is the real block element → process it with this id

  Header(level, _, inlines):
    → emit block: type=heading, level=level, text=reconstruct_inline(inlines)

  Para(inlines):
    → emit block: type=paragraph, text=reconstruct_inline(inlines)

  BulletList(items):
    → for each item: emit block: type=list_item, style=unordered,
                                 text=reconstruct_inline(item[0].inlines)

  (other node types: recurse into children, no block emitted)


reconstruct_inline(inlines):
  Str(s)       → s
  Space        → " "
  SoftBreak    → "\n"
  Strong(kids) → "*" + reconstruct_inline(kids) + "*"
  Emph(kids)   → "_" + reconstruct_inline(kids) + "_"
  (others)     → recurse or skip
```

---

## 9. Expected output for the test file

Given the test input, the walker should produce **9 blocks** in this order:

| Position | Type | Key content |
|----------|------|-------------|
| 1 | `heading` | level=1, text=`"Example heading - for the test file"` |
| 2 | `paragraph` | text=`"I'm writing the first paragraph which has *bold* and _italic_\nAnd maybe other text"` |
| 3 | `paragraph` | text=`"Another paragraph about lorem ipsum\nAnd the beauty of life"` |
| 4 | `heading` | level=2, text=`"This is a nested heading"` |
| 5 | `paragraph` | text=`"And in this part we'll have a list as well"` |
| 6 | `list_item` | style=unordered, text=`"just"` |
| 7 | `list_item` | style=unordered, text=`"for"` |
| 8 | `list_item` | style=unordered, text=`"the"` |
| 9 | `list_item` | style=unordered, text=`"fun"` |

9 blocks total. The page `root` array contains these 9 IDs in order.

---

## 10. Environment setup

- Conda environment: `knowledge-graph`
- Python dependencies: `uuid6` (UUIDv7), `hashlib` (stdlib), `subprocess` (stdlib), `json` (stdlib)
- System dependency: `pandoc` (already installed at `/usr/local/bin/pandoc` or via conda)

### `environment.yml`

```yaml
name: knowledge-graph
channels:
  - conda-forge
dependencies:
  - python=3.12
  - pip
  - pip:
    - uuid6
```

---

## 11. File layout

```
knowledge-graph/
  environment.yml
  src/
    ingest/
      __init__.py
      pandoc_ast.py       ← subprocess call to pandoc, returns parsed AST dict
      ast_walker.py       ← walks AST, emits block dicts
      inline_reconstruct.py ← reconstructs Djot inline markup from AST inlines
      block_schema.py     ← builds block.v1 and page.v1 dicts, computes hash+id
      jsonl_writer.py     ← appends records to JSONL files
      ingest_page.py      ← top-level function: path → blocks.jsonl + pages.jsonl
  tests/
    test_00/
      test_00.dj          ← test input file
      expected_blocks.json ← expected output for verification
  workspace/
    store/
      blocks.jsonl
      pages.jsonl
```

---

## 12. Verification

Test 00 is considered passing when:

1. Running `ingest_page("tests/test_00/test_00.dj", author="human:test")` completes without error.
2. `blocks.jsonl` contains exactly 9 lines (or the correct count after resolving the merged-header edge case).
3. Every block record validates against the `block.v1` schema: required fields present, `hash` is a valid SHA-256 hex string prefixed `sha256:`, `id` is a valid UUIDv7.
4. The page record in `pages.jsonl` has `root` containing the same block IDs in the same order as `blocks.jsonl`.
5. Block at position 1 has `type: heading`, `level: 1`.
6. Block at position 2 has `type: paragraph` and `content.text` containing `*bold*` and `_italic_` (Djot inline markup preserved).
7. The four list item blocks have `type: list_item` and `content.style: "unordered"`.

# Phase 03 — Design Document

## 1. Purpose

This document describes the design for **Phase 03**: rendering block records back into Djot text and verifying the internal roundtrip is lossless.

After Phase 03, the system has a proven guarantee: `djot → blocks → djot` produces semantically identical output. This is the foundation everything else builds on.

---

## 2. Background

### Why roundtrip verification before anything else?

Before ingesting real-world content (Phase 04), before enrichment (Phase 05), before tools (Phase 06-07), we need confidence that the ingestion pipeline doesn't lose data. The roundtrip test proves it:

```
source.dj  →  djot.js AST  →  blocks  →  render as djot  →  re-parse  →  compare
```

If the re-parsed blocks match the original blocks (same types, same content text), the pipeline is lossless.

### Token efficiency (secondary benefit)

The renderer also serves as the output format for LLM tools (Phases 06-07). Rendered Djot is ~5x more token-efficient than raw JSON block records. But the primary purpose of Phase 03 is verification, not LLM optimization.

---

## 3. Scope

### In scope

- Implement `src/render/blocks_to_djot.py` — render any sequence of blocks as valid Djot.
- Handle all block types from Phase 02: heading, paragraph, code_block, block_quote, table, list_item, definition_item, thematic_break, div, raw_block.
- Include block IDs as `{#id}` attributes (optional, toggleable).
- Implement the roundtrip test: ingest → render → re-ingest → compare.
- Define what "semantically identical" means precisely.
- Test with the `all_elements.dj` file from Phase 02 and the Phase 00 test files.

### Out of scope for Phase 03

- Rendering from LadybugDB queries (Phase 06 uses the renderer but queries are not in scope here).
- Markdown conversion (Phase 04).
- LLM tool interface (Phase 06).
- Annotations, metadata rendering (nice-to-have, deferred).

---

## 4. Renderer interface

```python
def render_blocks(blocks: list[dict], options: dict = None) -> str:
    """
    Render an ordered list of block.v1 records as a Djot document.
    
    Options:
        include_ids: bool (default True) — emit {#id} before each block
        compact: bool (default False) — minimal blank lines
    
    Returns a valid Djot string.
    """

def render_page(page: dict, blocks: list[dict], options: dict = None) -> str:
    """Render a full page with its blocks in order."""

def render_context(sections: list[dict], options: dict = None) -> str:
    """Render multiple sections separated by thematic breaks."""
```

---

## 5. Rendering rules by block type

| Block type | Djot output |
|-----------|-------------|
| `heading` | `{#id}\n` + `#` × level + ` ` + text + `\n` |
| `paragraph` | `{#id}\n` + text + `\n` |
| `code_block` | `{#id}\n` + `` ``` `` lang + `\n` + text + `\n` + `` ``` `` + `\n` |
| `block_quote` | `{#id}\n` + text (already `> ` prefixed) + `\n` |
| `list_item` (unordered) | `{#id}\n` + `- ` + text |
| `list_item` (ordered) | `{#id}\n` + `1. ` + text |
| `table` | `{#id}\n` + text (pipe syntax) + `\n` |
| `definition_item` | `{#id}\n` + `: ` + term + `\n` + `: ` + definition + `\n` |
| `thematic_break` | `{#id}\n` + `---` + `\n` |
| `div` | `{#id}\n` + `::: ` + class + `\n` + children rendered + `\n` + `:::` + `\n` |
| `raw_block` | `{#id}\n` + `` ``` `` `{=format}` + `\n` + text + `\n` + `` ``` `` + `\n` |

### Blank line rules

- Blank line between all blocks EXCEPT consecutive list items of the same style.
- Blank line required after headings (djot syntax requirement).

---

## 6. Roundtrip test definition

### What "semantically identical" means

After `djot → blocks → render → re-parse → blocks`, for each block at position i:

1. `original[i].type == roundtripped[i].type`
2. `original[i].content.text.strip() == roundtripped[i].content.text.strip()` (whitespace-normalized)
3. `original[i].content.level == roundtripped[i].content.level` (for headings)
4. `original[i].content.style == roundtripped[i].content.style` (for list items)
5. `original[i].content.language == roundtripped[i].content.language` (for code blocks)
6. Block count matches: `len(original) == len(roundtripped)`

### What is NOT required to match

- Block IDs (they're re-generated on re-ingestion).
- Hashes (content might have normalized whitespace).
- Timestamps.
- Exact whitespace in `text` (leading/trailing stripped).

### Edge cases

- **Table column widths**: pipe table rendering may produce different column padding. This is cosmetic — the re-parsed content is identical.
- **Soft breaks vs hard breaks**: preserved in content.text, renderer emits them correctly.
- **Block quote children**: stored as pre-formatted `> ` text, rendered as-is, re-parsed correctly.

---

## 7. File layout after Phase 03

```
knowledge-graph/
  src/
    render/
      __init__.py
      blocks_to_djot.py     ← render_blocks, render_page, render_context
  tests/
    test_03/
      test_roundtrip.py     ← automated roundtrip verification
```

---

## 8. Verification

Phase 03 is passing when:

1. `render_blocks()` produces valid Djot for all block types (parseable by djot.js).
2. Roundtrip test passes for `tests/test_02/all_elements.dj` (the comprehensive file).
3. Roundtrip test passes for `tests/test_00/test_00.dj` (regression).
4. Roundtrip test passes for all 6 files in `tests/test_00/extra_inputs/`.
5. Token efficiency: rendered Djot is 3-5x smaller than JSON serialization of the same blocks.

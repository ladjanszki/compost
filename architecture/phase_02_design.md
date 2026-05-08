# Phase 02 — Design Document

## 1. Purpose

This document describes the design for **Phase 02**: switching from Pandoc to the djot.js reference parser and implementing full Djot ingestion (all block and inline element types).

After Phase 02, any valid Djot document ingests without data loss. The parser is the djot reference implementation, and every djot construct maps to a block or inline representation flattened to Parquet and loaded directly into the Kuzu graph database.

---

## 2. Background

### Why switch from Pandoc to djot.js?

Pandoc was used in Phases 00-01 as a convenient Djot parser. However:

1. **Pandoc's AST is generic** — designed for 50+ formats. Djot elements are translated into Pandoc's intermediate types (`Div`, `Span`, `Header`, etc.) with attributes encoded as `[id, [classes], [[k,v]]]` triples. This requires a complex translation layer.
2. **Coverage gaps** — the current walker handles only 31% of Djot elements fully. Of 32 total element types, 12 either crash or silently lose content.
3. **Djot.js is the reference implementation** — maintained by John MacFarlane (the creator of Djot, Pandoc, and CommonMark). It produces a native typed AST where node types map 1:1 to our block types.

### djot.js AST structure (confirmed by inspection)

The AST is a JSON tree. Every node has a `tag` field. Key observations:

- **Sections are explicit**: `{tag: "section", children: [heading, ...blocks], attributes: {id: "..."}}`
- **Block IDs are direct**: `{#my-id}` before a block produces `node.attributes.id = "my-id"`
- **Code blocks are simple**: `{tag: "code_block", text: "...", lang: "python"}`
- **Tables are clean**: `{tag: "table", children: [caption, row, row, ...]}` with `{tag: "cell", children: [inlines]}`
- **Nested lists are natural**: `list_item` contains multiple children (para, nested list, etc.)
- **Inline types are named**: `verbatim`, `inline_math`, `display_math`, `link`, `image`, `subscript`, `superscript`, `delete`, `insert`, `mark`, `footnote_reference`

Compare: in Pandoc, inline code is `{"t": "Code", "c": [["",[], []], "text"]}`. In djot.js it's `{"tag": "verbatim", "text": "text"}`.

---

## 3. Scope

### In scope

- Replace `src/ingest/pandoc_ast.py` with `src/ingest/djot_ast.py` (calls djot.js via subprocess).
- Rewrite `src/ingest/ast_walker.py` against the djot.js native AST.
- Rewrite `src/ingest/inline_reconstruct.py` against the djot.js inline node types.
- Handle ALL djot block types: `heading`, `para`, `bullet_list`, `ordered_list`, `code_block`, `block_quote`, `table`, `definition_list`, `thematic_break`, `div`, `raw_block`.
- Handle ALL djot inline types: `str`, `soft_break`, `hard_break`, `emph`, `strong`, `verbatim`, `inline_math`, `display_math`, `link`, `image`, `subscript`, `superscript`, `delete`, `insert`, `mark`, `span`, `footnote_reference`, `raw_inline`.
- Handle `{#id}` attributes on blocks (explicit block IDs from source).
- Handle nested list items (multi-paragraph, nested sub-lists).
- Handle `section` nodes (transparent, same as Pandoc's Div-section).
- Extract links for `LINKS_TO` edges (internal link detection).
- Remove `blocks.jsonl` / `pages.jsonl` logic entirely. The target is Kuzu via temporary Parquet files.
- Add Node.js/npx as a system dependency.
- Create comprehensive test files exercising all element types.

### Out of scope for Phase 02

- Block → Djot rendering (Phase 03).
- Markdown → Djot conversion (Phase 04).
- Semantic enrichment (Phase 05).
- Tool interface (Phase 06-07).

---

## 4. djot.js AST node reference

### Block-level nodes

| djot.js `tag` | Our block type | Key fields |
|---------------|---------------|------------|
| `heading` | `heading` | `level`, `children` (inlines) |
| `para` | `paragraph` | `children` (inlines) |
| `code_block` | `code_block` | `text`, `lang` (nullable) |
| `block_quote` | `block_quote` | `children` (blocks) |
| `bullet_list` | container (not a block itself) | `children` (list_items), `tight`, `style` |
| `ordered_list` | container (not a block itself) | `children` (list_items), `start`, `tight`, `style` |
| `list_item` | `list_item` | `children` (blocks — may be multiple) |
| `definition_list` | container | `children` (definition_list_items) |
| `definition_list_item` | `definition_item` | `children` ([term, definition]) |
| `table` | `table` | `children` ([caption, rows]) |
| `thematic_break` | `thematic_break` | (no content) |
| `div` | `div` | `children` (blocks), `attributes` |
| `raw_block` | `raw_block` | `text`, `format` |
| `section` | transparent (not a block) | `children` (heading + blocks), `attributes` |

### Inline nodes

| djot.js `tag` | Djot reconstruction |
|---------------|---------------------|
| `str` | literal `text` field |
| `soft_break` | `\n` |
| `hard_break` | `\` + `\n` |
| `emph` | `_..._` |
| `strong` | `*...*` |
| `verbatim` | `` `text` `` |
| `inline_math` | `$` `` ` `` `text` `` ` `` `$` |
| `display_math` | `$$` `` ` `` `text` `` ` `` `$$` |
| `link` | `[children](destination)` |
| `image` | `![children](destination)` |
| `subscript` | `~children~` |
| `superscript` | `^children^` |
| `delete` | `{-children-}` |
| `insert` | `{+children+}` |
| `mark` | `{=children=}` |
| `span` | `[children]{attributes}` |
| `footnote_reference` | `[^text]` |
| `raw_inline` | `` `text`{=format} `` |

---

## 5. Walker design (rewritten)

The new walker is dramatically simpler because node types map directly:

```python
def walk(ast: dict) -> list[dict]:
    """Walk the djot.js AST. Returns ordered list of block dicts."""
    results = []
    _walk_children(ast.get("children", []), results)
    return results

def _walk_children(nodes: list, results: list):
    for node in nodes:
        _walk_node(node, results)

def _walk_node(node: dict, results: list):
    tag = node.get("tag")
    attrs = node.get("attributes", {})
    block_id = attrs.get("id")  # explicit {#id} from source
    
    if tag == "section":
        _walk_children(node["children"], results)
    
    elif tag == "heading":
        text, links = reconstruct(node["children"])
        emit(results, "heading", {"text": text, "level": node["level"], "links": links}, block_id)
    
    elif tag == "para":
        text, links = reconstruct(node["children"])
        emit(results, "paragraph", {"text": text, "links": links}, block_id)
    
    elif tag == "code_block":
        emit(results, "code_block", {"text": node["text"], "language": node.get("lang")}, block_id)
    
    elif tag == "block_quote":
        # Recurse into children, collect as nested blocks
        child_blocks = []
        _walk_children(node["children"], child_blocks)
        # Store as single block with child text reconstructed
        text = _reconstruct_block_quote(child_blocks)
        emit(results, "block_quote", {"text": text}, block_id)
    
    elif tag == "bullet_list":
        for item in node["children"]:
            _walk_list_item(item, "unordered", results)
    
    elif tag == "ordered_list":
        for item in node["children"]:
            _walk_list_item(item, "ordered", results)
    
    elif tag == "definition_list":
        for item in node["children"]:
            _walk_definition_item(item, results)
    
    elif tag == "table":
        _walk_table(node, results)
    
    elif tag == "thematic_break":
        emit(results, "thematic_break", {}, block_id)
    
    elif tag == "div":
        # Transparent: recurse, but capture the div's ID for the first child
        _walk_children(node["children"], results)
    
    elif tag == "raw_block":
        emit(results, "raw_block", {"text": node["text"], "format": node.get("format")}, block_id)
```

### List item handling (multi-paragraph, nested)

```python
def _walk_list_item(item: dict, style: str, results: list):
    """Handle a list_item which may contain multiple paragraphs or nested lists."""
    attrs = item.get("attributes", {})
    block_id = attrs.get("id")
    children = item.get("children", [])
    
    # Simple case: single para child → emit as one list_item block
    if len(children) == 1 and children[0]["tag"] == "para":
        text, links = reconstruct(children[0]["children"])
        content = {"text": text, "style": style}
        if links:
            content["links"] = links
        emit(results, "list_item", content, block_id)
    else:
        # Complex case: multiple children (paragraphs, nested lists, code, etc.)
        # Emit as a list_item block with text from all para children joined,
        # then recurse into nested block-level children
        text_parts = []
        all_links = []
        for child in children:
            if child["tag"] == "para":
                t, l = reconstruct(child["children"])
                text_parts.append(t)
                all_links.extend(l)
            elif child["tag"] in ("bullet_list", "ordered_list"):
                # Nested list: recurse (emits separate blocks)
                _walk_node(child, results)
            else:
                # Other block inside list item: recurse
                _walk_node(child, results)
        
        if text_parts:
            content = {"text": "\n\n".join(text_parts), "style": style}
            if all_links:
                content["links"] = all_links
            emit(results, "list_item", content, block_id)
```

---

## 6. Inline reconstruction (rewritten)

```python
def reconstruct(inlines: list) -> tuple[str, list[dict]]:
    """Reconstruct djot inline markup from djot.js AST inline nodes."""
    links_acc = []
    text = _reconstruct_inner(inlines, links_acc)
    return text, links_acc

def _reconstruct_inner(inlines: list, links_acc: list) -> str:
    parts = []
    for node in inlines:
        tag = node.get("tag")
        
        if tag == "str":
            parts.append(node["text"])
        elif tag == "soft_break":
            parts.append("\n")
        elif tag == "hard_break":
            parts.append("\\\n")
        elif tag == "emph":
            parts.append("_" + _reconstruct_inner(node["children"], links_acc) + "_")
        elif tag == "strong":
            parts.append("*" + _reconstruct_inner(node["children"], links_acc) + "*")
        elif tag == "verbatim":
            parts.append("`" + node["text"] + "`")
        elif tag == "inline_math":
            parts.append("$`" + node["text"] + "`$")
        elif tag == "display_math":
            parts.append("$$`" + node["text"] + "`$$")
        elif tag == "link":
            link_text = _reconstruct_inner(node["children"], links_acc)
            dest = node.get("destination", "")
            parts.append(f"[{link_text}]({dest})")
            links_acc.append({"text": link_text, "url": dest})
        elif tag == "image":
            alt = _reconstruct_inner(node["children"], links_acc)
            src = node.get("destination", "")
            parts.append(f"![{alt}]({src})")
        elif tag == "subscript":
            parts.append("~" + _reconstruct_inner(node["children"], links_acc) + "~")
        elif tag == "superscript":
            parts.append("^" + _reconstruct_inner(node["children"], links_acc) + "^")
        elif tag == "delete":
            parts.append("{-" + _reconstruct_inner(node["children"], links_acc) + "-}")
        elif tag == "insert":
            parts.append("{+" + _reconstruct_inner(node["children"], links_acc) + "+}")
        elif tag == "mark":
            parts.append("{=" + _reconstruct_inner(node["children"], links_acc) + "=}")
        elif tag == "footnote_reference":
            parts.append("[^" + node["text"] + "]")
        elif tag == "span":
            inner = _reconstruct_inner(node["children"], links_acc)
            attrs = _format_attrs(node.get("attributes", {}))
            parts.append(f"[{inner}]{{{attrs}}}")
        elif tag == "raw_inline":
            fmt = node.get("format", "")
            parts.append(f"`{node['text']}`{{={fmt}}}")
        else:
            # Unknown inline: emit children if present, otherwise skip
            if "children" in node:
                parts.append(_reconstruct_inner(node["children"], links_acc))
    
    return "".join(parts)
```

This covers **every inline type** in the djot spec. No silent drops, no crashes.

---

## 7. Block ID handling

In the djot.js AST, explicit `{#id}` attributes appear in two places:

1. **On a section**: `section.attributes.id` — this ID belongs to the heading inside.
2. **On any other block**: `node.attributes.id` — this ID belongs to that block directly.

The walker extracts `attributes.id` when present and passes it to `emit()`. If no explicit ID exists, `make_block()` generates a UUIDv7 (same as Phase 00).

---

## 8. Link extraction

Same design as before: links are collected during inline reconstruction. A link is **internal** if its destination doesn't start with `http://`/`https://` and doesn't start with `#`. Internal links produce `LINKS_TO` edges in Kuzu.

---

## 9. Extended Kuzu schema

Same as previously designed:
- `Block` node gets `language STRING` column.
- New `LINKS_TO(FROM Block TO Page, link_text STRING, url STRING)` relationship table.

---

## 10. Test input file

A single comprehensive Djot file exercising all element types:

**`tests/test_02/all_elements.dj`** — contains at least one instance of every block and inline type.

Plus the cross-linked corpus from the previous design (3 interlinked pages for LINKS_TO verification).

---

## 11. File layout after Phase 02

```
knowledge-graph/
  src/
    ingest/
      djot_ast.py             ← NEW: calls djot.js, returns parsed AST
      pandoc_ast.py           ← KEPT but unused by main pipeline (available for Phase 04)
      ast_walker.py           ← REWRITTEN: walks djot.js AST
      inline_reconstruct.py   ← REWRITTEN: handles all djot inline types
      block_schema.py         ← unchanged
      parquet_writer.py       ← NEW: writes AST output to Parquet
      ingest_page.py          ← MODIFIED: calls djot_ast, writes parquet, copies to Kuzu
    index/                    ← DEPRECATED (merged into ingest pipeline)
  tests/
    test_02/
      all_elements.dj         ← comprehensive test file
      cross_linked_corpus/
        geography.dj
        danube.dj
        europe.dj
```

---

## 12. Environment update

```yaml
# No changes to environment.yml — Node.js is a system dependency like pandoc
```

System requirements: `node` (v18+) and `npx` must be available on PATH.

---

## 13. Verification

Phase 02 is passing when:

1. `ingest_page("tests/test_02/all_elements.dj", ...)` completes without error.
2. Every element type in the test file produces a block with the correct `type`.
3. Inline markup is losslessly reconstructed (inline code, math, links, subscript, etc. all present in `content.text`).
4. Explicit `{#id}` attributes are captured as block IDs.
5. Cross-linked corpus produces `LINKS_TO` edges in Kuzu.
6. Phase 00 regression: `test_00.dj` still produces 9 blocks with identical content text.

---

## 14. Backward compatibility

- The `reconstruct()` return type changes from `str` to `(str, links)` — breaking change, same as before.
- `pandoc_ast.py` is kept for Phase 04 (markdown → djot conversion).
- Block content schema is unchanged (`block.v1`), but it is stored directly in Kuzu. JSONL is deprecated.

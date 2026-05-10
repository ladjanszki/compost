# Phase 02 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Phase 02. It assumes the reader has read `phase_02_design.md`.

The goal of Phase 02 is:

```
.dj file  →  djot.js (native AST)  →  Python walker  →  Parquet files (temp) → LadybugDB Graph Database
```

---

## 2. Prerequisites

- [ ] Phase 00 and Phase 01 are complete and passing.
- [ ] Node.js (v18+) and `npx` are available: `node --version`, `npx --version`.
- [ ] djot.js is available: `npx @djot/djot --version` returns a version.
- [ ] The `knowledge-graph` conda environment is active.

---

## 3. Steps

### Step 1 — Verify djot.js availability

```bash
node --version       # expect v18+
npx @djot/djot --version  # expect 0.3.x
echo "# Hello" | npx @djot/djot --to ast  # expect JSON AST
```

If `npx @djot/djot` is not cached, run `npm install -g @djot/djot` or rely on npx auto-fetch.

---

### Step 2 — Create test input file

**`tests/test_02/all_elements.dj`** — one instance of every djot element:

```djot
{#sec-intro}
# All Djot Elements

{#para-1}
A paragraph with *bold*, _italic_, `inline code`, and $`e=mc^2`$ math.

Also a [link](https://example.com) and an ![image](photo.png).

Subscript: H~2~O. Superscript: x^2^. Deleted: {-old-}. Inserted: {+new+}. Marked: {=highlight=}.

A hard line break here\
and the next line.

A footnote reference[^1].

## Code and Quotes

```python
def hello():
    print("world")
```

> A block quote.
> With two lines.

## Lists

- Simple unordered
- Second item

1. Ordered first
2. Ordered second

- Complex item with two paragraphs.

  Second paragraph in the same item.

  - Nested sub-item
  - Another nested

- Back to top level

## Definition List

: Term one
: The definition of term one.

: Term two
: The definition of term two.

## Table

| Name  | Age |
|-------|-----|
| Alice | 30  |
| Bob   | 25  |

---

## Div and Raw

::: warning
This is inside a div with class "warning".
:::

```{=html}
<video src="demo.mp4"></video>
```

## Cross-references

See the [Geography](geography.dj) page and the [Danube](danube.dj) page.

[^1]: This is the footnote content.
```

Also create the cross-linked corpus (3 files: `geography.dj`, `danube.dj`, `europe.dj`) as specified in the design doc.

**Verification**: `npx @djot/djot --to ast tests/test_02/all_elements.dj` produces valid JSON.

---

### Step 3 — Implement `src/ingest/djot_ast.py`

```python
"""
djot_ast.py — run djot.js on a .dj file and return the native AST as a dict.
"""
import json
import shutil
import subprocess


def _find_executable(name: str, fallbacks: list[str] = None) -> str:
    """Find an executable on PATH or in fallback locations."""
    path = shutil.which(name)
    if path:
        return path
    for fb in (fallbacks or []):
        if shutil.which(fb):
            return fb
    raise RuntimeError(f"{name} not found. Install Node.js and run: npm install -g @djot/djot")


def get_ast(djot_path: str) -> dict:
    """
    Run djot.js on the given .dj file and return the parsed AST as a dict.
    Raises RuntimeError if djot.js exits non-zero.
    """
    npx = _find_executable("npx")
    
    with open(djot_path, "r") as f:
        source = f.read()
    
    result = subprocess.run(
        [npx, "@djot/djot", "--to", "ast"],
        input=source,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"djot.js failed for {djot_path!r}:\n{result.stderr.strip()}"
        )
    return json.loads(result.stdout)
```

**Verification**: `get_ast("tests/test_02/all_elements.dj")` returns a dict with `tag: "doc"` and `children` list.

---

### Step 4 — Rewrite `src/ingest/inline_reconstruct.py`

Complete rewrite against djot.js inline nodes. Full implementation in design doc section 6.

Key differences from old code:
- No more `"t"` / `"c"` — now `"tag"` and named fields (`text`, `children`, `destination`).
- Returns `(str, list[dict])` — text and links.
- Every inline type has an explicit branch. No fallback recursion into `"c"`.

**Verification**: parse `all_elements.dj`, extract the first paragraph's inlines, reconstruct. Confirm output contains `*bold*`, `_italic_`, `` `inline code` ``, `$` `` ` `` `e=mc^2` `` ` `` `$`, `[link](https://example.com)`, `![image](photo.png)`.

---

### Step 5 — Rewrite `src/ingest/ast_walker.py`

Complete rewrite against djot.js block nodes. Full implementation in design doc section 5.

Key changes:
- Walk `node["children"]` (not `node["c"]`).
- Match on `node["tag"]` (not `node["t"]`).
- `section` is transparent (recurse into children).
- `bullet_list` / `ordered_list` are containers — iterate their `list_item` children.
- `list_item` may contain multiple blocks (multi-paragraph items, nested lists).
- `code_block` has `text` and `lang` directly.
- `table` has `row` children with `cell` children.
- `definition_list` has `definition_list_item` children.
- `block_quote` children are walked and reconstructed.
- Block ID comes from `node.get("attributes", {}).get("id")`.

**Verification**: walk the AST from `all_elements.dj`. Confirm at least:
- 1 heading (level 1), 1 heading (level 2)
- Multiple paragraphs
- 1 code_block with language "python"
- 1 block_quote
- Unordered and ordered list items
- Definition items
- 1 table
- 1 thematic_break
- 1 div
- 1 raw_block

---

### Step 6 — Update `src/ingest/ingest_page.py`

Change import from `pandoc_ast` to `djot_ast`. Also, remove JSONL writing. Instead, accumulate blocks in memory, write them to temporary Parquet files, and use LadybugDB's `COPY FROM` to ingest them directly into the graph.

```python
# Before:
from .pandoc_ast import get_ast
from .jsonl_writer import append_record

# After:
from .djot_ast import get_ast
from .parquet_writer import write_blocks_to_parquet
# ... logic to COPY FROM parquet into LadybugDB ...
```

---

### Step 7 — Update LadybugDB schema and Ingest Integration

Add `language STRING` to Block table. Add `LINKS_TO` relationship table. Update parquet generation and loading to occur at the end of `ingest_page.py` rather than relying on a separate `build_index()` command. The `index/` directory logic should be merged directly into the ingestion pipeline, cementing LadybugDB as the canonical storage.

---

### Step 8 — Phase 00 regression test

```bash
python -c "
import os
import real_ladybug as lb
# Clear store
import shutil
if os.path.exists('workspace/store/ladybug/db'):
    shutil.rmtree('workspace/store/ladybug/db')

from src.ingest.ingest_page import ingest_page
page_id = ingest_page('tests/test_00/test_00.dj', 'human:test')
print(f'Page: {page_id}')

db = lb.Database('workspace/store/ladybug/db')
conn = lb.Connection(db)
result = conn.execute("MATCH (b:Block) RETURN b.type, b.text ORDER BY b.id")
blocks = []
while result.has_next():
    blocks.append(result.get_next())

assert len(blocks) == 9, f'Expected 9 blocks, got {len(blocks)}'
assert blocks[0][0] == 'heading'
assert '*bold*' in blocks[1][1]
assert '_italic_' in blocks[1][1]
print('Phase 00 regression: PASS')
"
```

---

### Step 9 — Full element verification

```bash
python -c "
import os, shutil
import real_ladybug as lb
if os.path.exists('workspace/store/ladybug/db'):
    shutil.rmtree('workspace/store/ladybug/db')

from src.ingest.ingest_page import ingest_page
page_id = ingest_page('tests/test_02/all_elements.dj', 'human:test')

db = lb.Database('workspace/store/ladybug/db')
conn = lb.Connection(db)
result = conn.execute("MATCH (b:Block) RETURN b.type, b.text")
blocks = []
types_found = set()
while result.has_next():
    row = result.get_next()
    blocks.append(row)
    types_found.add(row[0])

expected_types = {'heading', 'paragraph', 'code_block', 'block_quote', 'list_item', 
                  'table', 'thematic_break', 'definition_item', 'div', 'raw_block'}
missing = expected_types - types_found
assert not missing, f'Missing block types: {missing}'

print(f'All elements test: PASS ({len(blocks)} blocks, types: {sorted(types_found)})')
"
```

---

### Step 10 — Cross-linked corpus and LINKS_TO verification

```bash
python -c "
import os, shutil
import real_ladybug as lb
if os.path.exists('workspace/store/ladybug/db'):
    shutil.rmtree('workspace/store/ladybug/db')

from src.ingest.ingest_page import ingest_page
for fname in ['geography.dj', 'danube.dj', 'europe.dj']:
    ingest_page(f'tests/test_02/cross_linked_corpus/{fname}', 'human:test')

db = lb.Database('workspace/store/ladybug/db')
conn = lb.Connection(db)
for label, q in [
    ('Blocks', 'MATCH (b:Block) RETURN count(b)'),
    ('Pages', 'MATCH (p:Page) RETURN count(p)'),
    ('LINKS_TO', 'MATCH ()-[r:LINKS_TO]->() RETURN count(r)'),
]:
    r = conn.execute(q)
    print(f'{label}: {r.get_next()[0]}')
"
```

Expected: 3 pages, ~12-15 blocks, 6+ LINKS_TO edges.

---

## 4. Implementation order

```
Step 1  (verify djot.js)     — prerequisite check
Step 2  (test file)          — no code dependency
Step 3  (djot_ast.py)        — no code dependency
Step 4  (inline_reconstruct) — no code dependency
Step 5  (ast_walker)         — depends on Step 4
Step 6  (ingest_page)        — depends on Steps 3, 5
Step 7  (ladybug schema)        — independent of Steps 3-6
Step 8  (regression)         — depends on Steps 3-6
Step 9  (full element test)  — depends on Steps 3-6
Step 10 (links test)         — depends on Steps 3-7
```

Steps 3, 4, 7 can be done in parallel. Step 5 needs Step 4.

---

## 5. What Phase 02 does NOT validate

- **Lossless roundtrip** (djot → blocks → djot): that's Phase 03.
- **Markdown conversion**: that's Phase 04.
- **Semantic enrichment**: that's Phase 05.
- **Performance**: single-file ingestion. Not optimized for batch (fine at this scale).

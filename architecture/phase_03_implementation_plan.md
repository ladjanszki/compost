# Phase 03 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Phase 03. It assumes the reader has read `phase_03_design.md`.

The goal of Phase 03 is:

```
blocks  →  render_blocks()  →  valid Djot  →  re-parse with djot.js  →  compare to original blocks
```

---

## 2. Prerequisites

- [ ] Phase 02 is complete (djot.js parser + full element support).
- [ ] `tests/test_02/all_elements.dj` produces blocks for all element types.
- [ ] The `knowledge-graph` conda environment is active.

---

## 3. Steps

### Step 1 — Create directory structure

```bash
mkdir -p src/render
mkdir -p tests/test_03
touch src/render/__init__.py
touch src/render/blocks_to_djot.py
touch tests/test_03/test_roundtrip.py
```

---

### Step 2 — Implement `blocks_to_djot.py`

Full implementation of `render_blocks`, `render_page`, `render_context`. See design doc section 5 for rendering rules per block type.

---

### Step 3 — Roundtrip test

`tests/test_03/test_roundtrip.py`:

```python
"""Roundtrip: djot → blocks → render → re-parse → blocks. Compare."""
import json, os, sys, tempfile
sys.path.insert(0, ".")

from src.ingest.djot_ast import get_ast
from src.ingest.ast_walker import walk
from src.render.blocks_to_djot import render_blocks


def roundtrip_test(djot_path: str) -> list[str]:
    """Returns list of discrepancies (empty = pass)."""
    # Step 1: Original ingestion
    ast = get_ast(djot_path)
    original_blocks = walk(ast)
    
    # Step 2: Render to Djot (without IDs — they'd create {#uuid} noise)
    djot_text = render_blocks(original_blocks, {"include_ids": False})
    
    # Step 3: Re-parse the rendered Djot
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".dj", delete=False)
    tmp.write(djot_text)
    tmp.close()
    
    try:
        re_ast = get_ast(tmp.name)
        re_blocks = walk(re_ast)
    finally:
        os.unlink(tmp.name)
    
    # Step 4: Compare
    issues = []
    if len(original_blocks) != len(re_blocks):
        issues.append(f"Count mismatch: {len(original_blocks)} → {len(re_blocks)}")
        return issues
    
    for i, (orig, rt) in enumerate(zip(original_blocks, re_blocks)):
        if orig["type"] != rt["type"]:
            issues.append(f"Block {i}: type {orig['type']} → {rt['type']}")
            continue
        
        orig_text = orig["content"].get("text", "").strip()
        rt_text = rt["content"].get("text", "").strip()
        if orig_text != rt_text:
            issues.append(f"Block {i} ({orig['type']}): text differs\n  orig: {orig_text[:80]!r}\n  rt:   {rt_text[:80]!r}")
        
        for key in ("level", "style", "language"):
            if orig["content"].get(key) != rt["content"].get(key):
                issues.append(f"Block {i}: {key} differs: {orig['content'].get(key)} → {rt['content'].get(key)}")
    
    return issues


def main():
    test_files = [
        "tests/test_00/test_00.dj",
        "tests/test_02/all_elements.dj",
    ]
    # Add extra inputs
    import glob
    test_files.extend(sorted(glob.glob("tests/test_00/extra_inputs/*.dj")))
    
    all_pass = True
    for path in test_files:
        if not os.path.exists(path):
            print(f"SKIP (not found): {path}")
            continue
        issues = roundtrip_test(path)
        if issues:
            print(f"FAIL: {path}")
            for issue in issues:
                print(f"  {issue}")
            all_pass = False
        else:
            ast = get_ast(path)
            blocks = walk(ast)
            print(f"PASS: {path} ({len(blocks)} blocks)")
    
    if all_pass:
        print("\nAll roundtrip tests PASSED.")
    else:
        print("\nSome tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Run**: `python tests/test_03/test_roundtrip.py`

---

### Step 4 — Token efficiency check

```bash
python -c "
import json, sys
sys.path.insert(0, '.')
from src.ingest.djot_ast import get_ast
from src.ingest.ast_walker import walk
from src.ingest.block_schema import make_block
from src.render.blocks_to_djot import render_blocks

ast = get_ast('tests/test_02/all_elements.dj')
raw_blocks = walk(ast)
block_records = [make_block(b['type'], b['content'], 'human:test') for b in raw_blocks]

json_size = sum(len(json.dumps(b)) for b in block_records)
djot_text = render_blocks(block_records, {'include_ids': True})
djot_size = len(djot_text)
print(f'JSON: {json_size} chars, Djot: {djot_size} chars, ratio: {json_size/djot_size:.1f}x')
"
```

Expected: 3-5x reduction.

---

## 4. Implementation order

```
Step 1  (directories)      — no dependencies
Step 2  (renderer)         — no dependencies
Step 3  (roundtrip test)   — depends on Step 2 + Phase 02
Step 4  (token check)      — depends on Steps 2, 3
```

---

## 5. What Phase 03 does NOT validate

- **Markdown conversion**: Phase 04 handles external content sourcing.
- **Rendering from Kuzu**: the renderer takes block dicts, not Cypher results. Phase 06 queries Kuzu and passes blocks to the renderer.
- **Annotations/metadata in rendered output**: deferred.

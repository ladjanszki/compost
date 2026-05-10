# Test 00 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Test 00. It assumes the reader has read `test_00_design.md`. It is intended for review before any code is written.

The goal of Test 00 is to implement and verify the pipeline:

```
test_00.dj  →  pandoc (AST JSON)  →  Python walker  →  blocks.jsonl + pages.jsonl
```

---

## 2. Prerequisites

Before writing any code, the following must be in place:

- [ ] `pandoc` is available on the system (`pandoc --version` returns 3.x).
- [ ] The conda environment `knowledge-graph` is created from `environment.yml`.
- [ ] The working directory is the repo root (`knowledge-graph/`).

---

## 3. Steps

### Step 1 — Repo structure

Create the directory layout defined in the design doc. No code yet, just empty files and directories.

```
mkdir -p src/ingest
mkdir -p tests/test_00
mkdir -p workspace/store
touch src/__init__.py
touch src/ingest/__init__.py
touch src/ingest/pandoc_ast.py
touch src/ingest/ast_walker.py
touch src/ingest/inline_reconstruct.py
touch src/ingest/block_schema.py
touch src/ingest/jsonl_writer.py
touch src/ingest/ingest_page.py
```

**Deliverable**: directory tree exists, all `.py` files are empty.

---

### Step 2 — Conda environment

Create `environment.yml` at the repo root:

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

Then create the environment:

```bash
conda env create -f environment.yml
conda activate knowledge-graph
```

**Verification**: `python -c "import uuid6; print(uuid6.uuid7())"` prints a UUID.

---

### Step 3 — Save the test input file

Save the test Djot snippet to `tests/test_00/test_00.dj`:

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

Blank lines after each heading are required in Djot to terminate the heading element.

**Verification**: `pandoc -f djot -t json tests/test_00/test_00.dj` produces valid JSON with no errors.

---

### Step 4 — `pandoc_ast.py`

Implement one function:

```python
def get_ast(djot_path: str) -> dict:
    """
    Run pandoc on the given .dj file and return the parsed AST as a Python dict.
    Raises RuntimeError if pandoc exits non-zero.
    """
```

Implementation: `subprocess.run(["pandoc", "-f", "djot", "-t", "json", djot_path], ...)`, parse stdout with `json.loads`.

**Verification**: call `get_ast("tests/test_00/test_00.dj")` in a REPL and confirm the returned dict has a `"blocks"` key.

---

### Step 5 — `inline_reconstruct.py`

Implement one function:

```python
def reconstruct(inlines: list) -> str:
    """
    Reconstruct Djot inline markup from a list of Pandoc AST inline nodes.
    Returns a plain Djot string.
    """
```

Rules (from design doc section 8):

| AST node | Output |
|----------|--------|
| `{"t": "Str", "c": s}` | `s` |
| `{"t": "Space"}` | `" "` |
| `{"t": "SoftBreak"}` | `"\n"` |
| `{"t": "Strong", "c": kids}` | `"*" + reconstruct(kids) + "*"` |
| `{"t": "Emph", "c": kids}` | `"_" + reconstruct(kids) + "_"` |
| anything else | recurse into `"c"` if it is a list, otherwise skip |

**Verification**: unit test with the inline list from the first paragraph node. Expected output: `"I'm writing the first paragraph which has *bold* and _italic_\nAnd maybe other text"`.

---

### Step 6 — `block_schema.py`

Implement two functions:

```python
def make_block(block_type: str, content: dict, author: str) -> dict:
    """
    Build a block.v1 record.
    Generates a UUIDv7 id, computes SHA-256 hash of content, sets version=1.
    """

def make_page(page_id: str, title: str, block_ids: list[str], author: str) -> dict:
    """
    Build a page.v1 record.
    """
```

Hash computation: `sha256:` + `hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()`.

UUIDv7: `str(uuid6.uuid7())`.

**Verification**: call `make_block("paragraph", {"text": "hello"}, "human:test")` and confirm all required fields are present and the hash prefix is `sha256:`.

---

### Step 7 — `ast_walker.py`

Implement one function:

```python
def walk(ast: dict) -> list[dict]:
    """
    Walk the Pandoc AST and return an ordered list of block content dicts.
    Each dict has the keys needed to call make_block():
      - type: str
      - content: dict
    Does not generate IDs or hashes — that is block_schema's job.
    """
```

Walker rules (from design doc section 8):

```
process_blocks(nodes) → list of (type, content) tuples:

  for each node in nodes:

    t == "Div":
      attrs = node["c"][0]
      children = node["c"][1]
      class = attrs[1]  ← list of classes
      kvs = attrs[2]    ← list of [key, value] pairs

      if "section" in class:
        → first child must be a Header → process it
        → recurse into remaining children
      elif any kv[0] == "wrapper":
        → process the single child inside

    t == "Header":
      level = node["c"][0]
      inlines = node["c"][2]
      → yield (type="heading", content={"text": reconstruct(inlines), "level": level})

    t == "Para":
      inlines = node["c"]
      → yield (type="paragraph", content={"text": reconstruct(inlines)})

    t == "BulletList":
      items = node["c"]
      for item in items:
        plain_node = item[0]   ← each item is a list with one Plain node
        inlines = plain_node["c"]
        → yield (type="list_item", content={"text": reconstruct(inlines), "style": "unordered"})

    (other types): recurse into children if present, no block emitted
```

**Verification**: run walker on the test AST, confirm 9 (type, content) tuples are returned in the expected order.

---

### Step 8 — `jsonl_writer.py`

Implement one function:

```python
def append_record(jsonl_path: str, record: dict) -> None:
    """
    Append a single JSON record as one line to a JSONL file.
    Creates the file if it does not exist.
    Uses file locking (fcntl.flock) to serialize concurrent writes.
    """
```

**Verification**: call twice with different dicts, confirm the file has two lines and each is valid JSON.

---

### Step 9 — `ingest_page.py`

Implement the top-level function:

```python
def ingest_page(djot_path: str, author: str,
                blocks_jsonl: str = "workspace/store/blocks.jsonl",
                pages_jsonl: str = "workspace/store/pages.jsonl") -> str:
    """
    Full pipeline: parse .dj file → walk AST → write blocks + page to JSONL.
    Returns the page ID.
    """
```

Steps inside:
1. Call `get_ast(djot_path)`.
2. Call `walk(ast)` → list of `(type, content)` tuples.
3. For each tuple: call `make_block(type, content, author)` → block dict.
4. Call `append_record(blocks_jsonl, block)` for each block.
5. Collect block IDs in order.
6. Derive `page_id` from filename stem with `page-` prefix: `"page-" + Path(djot_path).stem` (e.g. `"page-test_00"`). The caller owns the prefix; `make_page` stores whatever ID it receives.
7. Derive `title` from the first heading block's `content.text`.
8. Call `make_page(page_id, title, block_ids, author)`.
9. Call `append_record(pages_jsonl, page)`.
10. Return `page_id`.

**Verification**: run `ingest_page("tests/test_00/test_00.dj", "human:test")` and inspect the output files.

---

### Step 10 — End-to-end verification

Run the full pipeline and check each condition from the design doc section 12:

```bash
conda activate knowledge-graph
python -c "
from src.ingest.ingest_page import ingest_page
page_id = ingest_page('tests/test_00/test_00.dj', 'human:test')
print('Page ID:', page_id)
"
```

Then verify:

```bash
# Count blocks
wc -l workspace/store/blocks.jsonl        # expect 9

# Inspect block types in order
python -c "
import json
with open('workspace/store/blocks.jsonl') as f:
    for i, line in enumerate(f, 1):
        b = json.loads(line)
        print(i, b['type'], b['content'])
"

# Inspect page root
python -c "
import json
with open('workspace/store/pages.jsonl') as f:
    page = json.loads(f.readline())
    print('title:', page['title'])
    print('root count:', len(page['root']))
    print('root:', page['root'])
"
```

Expected results:

| Check | Expected |
|-------|----------|
| `blocks.jsonl` line count | 9 |
| Block 1 | `type: heading`, `level: 1` |
| Block 2 | `type: paragraph`, `text` contains `*bold*` and `_italic_` |
| Blocks 6–9 | `type: list_item`, `style: unordered` |
| Page `root` length | 9 |
| Page `title` | `"Example heading - for the test file"` |
| All blocks | `schema: block.v1`, `version: 1`, `hash` starts with `sha256:` |

---

## 4. Implementation order and dependencies

```
Step 1  (repo structure)     — no dependencies
Step 2  (conda env)          — no dependencies
Step 3  (test input file)    — no dependencies
Step 4  (pandoc_ast)         — depends on Step 3
Step 5  (inline_reconstruct) — no code dependencies
Step 6  (block_schema)       — depends on Step 2 (uuid6)
Step 7  (ast_walker)         — depends on Steps 4, 5
Step 8  (jsonl_writer)       — no code dependencies
Step 9  (ingest_page)        — depends on Steps 4, 6, 7, 8
Step 10 (verification)       — depends on Step 9
```

Steps 1–3 can be done in parallel. Steps 4, 5, 6, 8 can be implemented in parallel. Step 7 requires 4 and 5. Step 9 requires all prior steps.

---

## 5. What Test 00 does NOT validate

The following are explicitly deferred and will be addressed in later tests:

- **Explicit `{#id}` handling**: the test file has no block IDs. The `Div`-as-ID-carrier pattern is understood (confirmed by AST inspection) but not exercised here.
- **Change detection**: no existing blocks to compare hashes against.
- **Block versioning**: all blocks are version 1.
- **LadybugDB ingestion**: planned for Test 01.
- **SQLite index**: planned for later.
- **Other block types**: code, table, quote, image, math, div.

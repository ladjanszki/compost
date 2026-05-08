# Knowledge Graph — Agentic Local Knowledge Store

## What this project is

This is a local-first, block-based knowledge store designed for safe human and agent interaction. It is built incrementally through a series of numbered tests, each adding one layer of the system.

The goal is a substrate where:

- documents can be read locally in a browser;
- conversations can happen over those documents;
- agents can participate in conversations and mutate content;
- all changes are traceable and rollbackable;
- the canonical format is JSON, readable without any editor or application;
- both humans and agents author content in Djot.

This is **not** a general-purpose note-taking app, a rich editor, or an Obsidian/Anytype replacement.

---

## Architecture overview

### Layers

```
Djot (.dj files)        — authoring surface for humans and agents
JSONL files             — canonical storage (source of truth)
SQLite index            — derived, rebuilt on demand (planned)
Kuzu graph database     — derived index for graph queries (planned)
HTML (generated pages)  — rendered reading surface (planned)
```

The canonical data lives in `workspace/store/*.jsonl`. Everything else is a projection that can be deleted and rebuilt.

### Four object kinds

| Kind | Description |
|------|-------------|
| `block` | Versioned content unit. Atomic. Has a stable ID, type, content, hash, author, timestamp. |
| `page` | Renderable document — an ordered flat list of block IDs. |
| `conversation` | Ordered sequence of messages with optional block attachments. |
| `operation` | Groups related block mutations for batch rollback. |

### Block schema (`block.v1`)

```json
{
  "id": "019e085d-5062-7ca2-8ac1-e448c3d0299b",
  "version": 1,
  "schema": "block.v1",
  "type": "paragraph",
  "content": {
    "text": "The cache is invalidated when the source document changes."
  },
  "created_by": "human:istvan",
  "created_at": "2026-05-08T10:00:00+00:00",
  "hash": "sha256:abc123..."
}
```

Block types derived from Djot AST: `heading`, `paragraph`, `list_item`, `code`, `quote`, `image`, `table`, `math`, `div`.

Content fields by type:

| Type | Content fields |
|------|---------------|
| `heading` | `text` (Djot inline), `level` (1–6) |
| `paragraph` | `text` (Djot inline) |
| `list_item` | `text` (Djot inline), `style` (`unordered` or `ordered`) |
| `code` | `text`, `language` |
| `quote` | `text` |
| `image` | `src`, `alt`, `caption` |
| `table` | `headers`, `rows`, `alignments` |
| `math` | `tex`, `display` |
| `div` | `children` (list of block IDs), `class` |

`text` fields always store Djot inline markup as-is (e.g. `*bold*`, `_italic_`). Inline markup is parsed to HTML at render time by pandoc, never stored as sub-nodes.

### Block ID

UUIDv7. Embeds a millisecond-precision creation timestamp — IDs are sortable by creation time. When a Djot block has an explicit `{#id}` attribute, that named ID takes precedence over auto-generation.

### Hash

SHA-256 of the JSON-serialized `content` object (keys sorted, compact). Prefixed `sha256:`. Used for change detection: if the hash of incoming content matches the stored hash, no new version is created.

### Page schema (`page.v1`)

```json
{
  "id": "page-test_00",
  "schema": "page.v1",
  "title": "Example heading",
  "root": ["019e...", "019f...", "019g..."],
  "created_by": "human:istvan",
  "created_at": "2026-05-08T10:00:00+00:00",
  "updated_at": "2026-05-08T10:00:00+00:00"
}
```

`root` is a flat ordered list of block IDs. Hierarchy is implicit in heading levels, not encoded in the page structure.

### Authoring format: Djot

Djot is a formally parseable light markup language by John MacFarlane (creator of Pandoc and CommonMark). It looks like Markdown but is unambiguous and parses in linear time with no backtracking.

Key Djot features used here:

- `{#blk_001}` before any block assigns a stable ID to that block — native Djot syntax, not a custom extension.
- `*bold*` for strong, `_italic_` for emphasis (reversed from Markdown).
- Blank lines required after headings to terminate them.

Blocks without an explicit `{#id}` get an auto-generated UUIDv7 during ingestion.

Example well-formed Djot page:

```djot
{#blk_001}
# Cache invalidation

{#blk_002}
The cache is invalidated when the source document changes.

{#blk_003}
- Concurrent writes may cause stale reads.

{#blk_004}
- Circular dependencies must be detected.
```

### Pandoc AST and the ingestion pipeline

Ingestion uses Pandoc to parse Djot into a typed JSON AST, then walks the AST to extract blocks.

```
.dj file  →  pandoc -f djot -t json  →  Pandoc AST  →  Python walker  →  block.v1 records  →  blocks.jsonl
                                                                        →  page.v1 record   →  pages.jsonl
```

Key AST facts:

- A `{#id}` attribute wraps the block in a `Div` node that carries the ID. The `Div` is transparent — the ID is extracted from it, and the real block type is determined by the child element (`Header`, `Para`, `BulletList`, etc.).
- A `{#id}` on a heading → `Div` with class `section` containing the `Header` and all following sibling content until the next same-level heading.
- A `{#id}` on any other block → `Div` with attribute `wrapper: 1` containing that one element.
- Each `- list item` with its own `{#id}` becomes a separate single-item `BulletList` in its own `Div`.

### Inline reconstruction

Pandoc AST inline nodes are reconstructed back to Djot markup:

| AST node | Djot output |
|----------|-------------|
| `Str` | literal string |
| `Space` | `" "` |
| `SoftBreak` | `"\n"` |
| `Strong` → children | `*...*` |
| `Emph` → children | `_..._` |

---

## Repository layout

```
knowledge-graph/
  README.md                    ← this file
  TODO.md                      ← task tracking
  environment.yml              ← conda environment definition

  architecture/
    prompt.md                  ← original project brief
    design-docs/
      agentic_local_knowledge_store_v1_design_v4.dj   ← full v1 system design
      test_00_design.md        ← design doc for Test 00
      test_00_implementation_plan.md  ← implementation plan for Test 00
      test_00_review.md        ← review of Test 00 docs (resolved)

  src/
    ingest/
      pandoc_ast.py            ← run pandoc, return AST dict
      inline_reconstruct.py   ← reconstruct Djot inline markup from AST nodes
      ast_walker.py            ← walk AST, emit (type, content) tuples
      block_schema.py          ← build block.v1 and page.v1 dicts, compute hash+id
      jsonl_writer.py          ← append records to JSONL files with file locking
      ingest_page.py           ← top-level function: .dj path → blocks.jsonl + pages.jsonl

  tests/
    test_00/
      test_00.dj               ← test input: minimal Djot document

  workspace/
    store/
      blocks.jsonl             ← canonical block storage (appended by ingestion)
      pages.jsonl              ← canonical page storage (appended by ingestion)
```

---

## Environment setup

Requires: `conda` (miniconda or anaconda), `pandoc` (system install).

```bash
conda env create -f environment.yml
conda activate knowledge-graph
```

Verify:

```bash
python -c "import uuid6; print(uuid6.uuid7())"
pandoc --version
```

Pandoc is **not** installed inside the conda env — it is expected as a system binary. The `pandoc_ast.py` module uses `shutil.which` to locate it, with fallbacks to `/path/to/home/miniconda3/bin/pandoc`, `/usr/local/bin/pandoc`, and `/opt/homebrew/bin/pandoc`.

If pandoc is not found, install it system-wide or via conda base:

```bash
conda install -c conda-forge pandoc   # in base env, or add to environment.yml
```

---

## Running Test 00

```bash
conda activate knowledge-graph
python -c "
from src.ingest.ingest_page import ingest_page
page_id = ingest_page('tests/test_00/test_00.dj', 'human:test')
print('Page ID:', page_id)
"
```

Expected output: `Page ID: page-test_00`

Verify:

```bash
# 9 blocks
wc -l workspace/store/blocks.jsonl

# inspect blocks
python -c "
import json
with open('workspace/store/blocks.jsonl') as f:
    for i, line in enumerate(f, 1):
        b = json.loads(line)
        print(i, b['type'], b['content'])
"

# inspect page
python -c "
import json
with open('workspace/store/pages.jsonl') as f:
    page = json.loads(f.readline())
    print(page['title'], len(page['root']), 'blocks')
"
```

---

## Source module reference

### `src/ingest/pandoc_ast.py`

```python
get_ast(djot_path: str) -> dict
```

Runs `pandoc -f djot -t json` on the given file. Returns the parsed AST as a Python dict. Raises `RuntimeError` if pandoc is not found or exits non-zero.

### `src/ingest/inline_reconstruct.py`

```python
reconstruct(inlines: list) -> str
```

Walks a list of Pandoc AST inline nodes and returns Djot inline markup as a plain string. Handles `Str`, `Space`, `SoftBreak`, `Strong`, `Emph`. Unknown nodes with list children are recursed into silently.

### `src/ingest/ast_walker.py`

```python
walk(ast: dict) -> list[dict]
```

Walks the Pandoc AST and returns an ordered list of `{"type": ..., "content": {...}}` dicts. Does not assign IDs or compute hashes. Currently handles: `heading`, `paragraph`, `list_item` (ordered and unordered). `Div` nodes (section and wrapper) are transparent — the walker recurses into their children.

### `src/ingest/block_schema.py`

```python
make_block(block_type: str, content: dict, author: str) -> dict
make_page(page_id: str, title: str, block_ids: list, author: str) -> dict
```

`make_block` generates a UUIDv7 ID, computes SHA-256 of serialized content, and returns a complete `block.v1` dict at version 1.

`make_page` returns a complete `page.v1` dict. The caller is responsible for constructing the full `page_id` (e.g. `"page-" + stem`).

### `src/ingest/jsonl_writer.py`

```python
append_record(jsonl_path: str, record: dict) -> None
```

Appends a JSON record as a single line to a JSONL file. Creates the file and parent directories if needed. Uses `fcntl.flock` for write serialization.

### `src/ingest/ingest_page.py`

```python
ingest_page(
    djot_path: str,
    author: str,
    blocks_jsonl: str = "workspace/store/blocks.jsonl",
    pages_jsonl: str = "workspace/store/pages.jsonl",
) -> str
```

Top-level pipeline function. Calls `get_ast` → `walk` → `make_block` (per block) → `append_record` (per block) → `make_page` → `append_record`. Returns the page ID.

---

## Design decisions log

These are the key decisions made during design. An agent working on this project should not relitigate them without strong reason.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Authoring format | Djot | Formally parseable, unambiguous, native block-level `{#id}` attributes, close to Markdown for agents |
| Canonical storage | JSONL | Append-friendly, inspectable, git-friendly, migratable to DuckDB/MongoDB later |
| Graph index | Kuzu (planned) | Embeddable, no server, SQLite-of-graphs, Cypher queries, fast bulk COPY |
| Block identity | UUIDv7 | Sortable by creation time, globally unique, timestamp embedded |
| Change detection | SHA-256 of content | Deterministic, fast, collision-resistant |
| Page structure | Flat `root` array | Hierarchy is implicit in heading levels, no tree in storage |
| Inline markup storage | Djot as-is | Parsed to HTML at render time by pandoc, never stored as sub-nodes |
| Pandoc's role | Djot parser only | Pandoc AST is an implementation detail of ingestion, not exposed in storage |
| `Div` nodes in AST | Transparent | Divs carry `{#id}` attributes; real block type is always the child element |
| Page ID prefix | Caller's responsibility | `ingest_page` constructs `"page-" + stem`; `make_page` stores whatever it receives |
| `fcntl.flock` for writes | Yes | Serializes concurrent agent writes to JSONL at v1 scale |

---

## What is explicitly out of scope for v1

- API server or web application framework
- Browser-side writing (browser is a reader only)
- WYSIWYG editor
- Real-time collaboration, CRDTs, multi-user
- Remote sync or public deployment
- Plugin system
- Automatic page regeneration (manual `render` call required)
- Page versioning (block content is versioned; page structure is not)

---

## Key dependencies

| Dependency | Role |
|------------|------|
| `pandoc` | Djot parsing, AST generation, HTML rendering |
| `python 3.12` | All tooling |
| `uuid6` | UUIDv7 generation |
| `sqlite3` | Derived indexes (stdlib, planned) |
| `kuzu` | Graph index (planned, Test 01) |

---

## Full design reference

The complete v1 system design is in:
`architecture/design-docs/agentic_local_knowledge_store_v1_design_v4.dj`

Test-specific design and implementation docs are in:
`architecture/design-docs/test_00_design.md`
`architecture/design-docs/test_00_implementation_plan.md`

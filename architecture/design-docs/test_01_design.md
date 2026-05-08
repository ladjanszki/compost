# Test 01 — Design Document

## 1. Purpose

This document describes the design for **Test 01**: loading the JSONL output of Test 00 into a Kuzu graph database as a derived index.

It is self-contained and intended for review before implementation begins. A reviewer does not need to have read earlier documents, but references are provided for traceability.

---

## 2. Background

### The v1 knowledge store (summary)

The v1 system stores documents as versioned blocks. The canonical source of truth is a set of JSONL files:

- `workspace/store/blocks.jsonl` — one `block.v1` JSON record per line
- `workspace/store/pages.jsonl` — one `page.v1` JSON record per line

These files are append-only and human-readable. All other representations are derived projections.

### What Test 00 produced

Test 00 implemented the ingestion pipeline:

```
test_00.dj  →  pandoc AST  →  Python walker  →  blocks.jsonl + pages.jsonl
```

Running `ingest_page("tests/test_00/test_00.dj", "human:test")` produces:

- **9 block records** in `blocks.jsonl`: 1 heading (level 1), 2 paragraphs, 1 heading (level 2), 1 paragraph, 4 list items
- **1 page record** in `pages.jsonl` with `root` containing those 9 block IDs in document order

### Why a graph index?

The JSONL files are authoritative but not queryable beyond sequential scan. A graph database allows:

- finding all blocks belonging to a page in order
- traversing block sequences (next/previous)
- future: cross-document entity links, conversation-to-block attachments, mention queries

**Kuzu** is chosen as the graph index because it is embeddable (no server), zero-config, uses Cypher, and supports high-speed bulk `COPY FROM` for Parquet files. It is the "SQLite of graph databases."

The Kuzu database is a **derived index** — it can be deleted and rebuilt from JSONL at any time. It is never the source of truth.

---

## 3. Scope

### In scope

- Add `kuzu` and `pyarrow` to the conda environment.
- Define the Kuzu schema: node tables and relationship tables.
- Flatten `blocks.jsonl` → Parquet file suitable for Kuzu `COPY FROM`.
- Flatten `pages.jsonl` + `blocks.jsonl` → Parquet files for relationships.
- Load all Parquet files into Kuzu using `COPY FROM`.
- Verify the loaded data with a Cypher query.

### Out of scope for Test 01

- Block versioning in the graph (all blocks are version 1 in Test 00 output).
- Conversation nodes and edges.
- Operation nodes.
- `NEXT` edges between blocks within a page (deferred — see section 7).
- Entity nodes and semantic edges (future semantic enrichment layer).
- Incremental updates (re-running build clears and rebuilds the index).

---

## 4. Kuzu schema

### Design principles

- **Nodes** are things worth querying independently: `Block`, `Page`.
- **Relationships** are the structural links: a page contains blocks in order.
- **Properties** are queryable attributes on nodes: type, content text, hash, author, timestamp.
- The schema is minimal for Test 01. It will grow in later tests.

### Node tables

#### `Block`

Maps directly from `block.v1` records in `blocks.jsonl`.

| Column | Kuzu type | Source field | Notes |
|--------|-----------|--------------|-------|
| `id` | `STRING` | `block.id` | Primary key. UUIDv7 string. |
| `version` | `INT64` | `block.version` | Always 1 in Test 01. |
| `schema` | `STRING` | `block.schema` | Always `"block.v1"`. |
| `type` | `STRING` | `block.type` | `heading`, `paragraph`, `list_item`. |
| `text` | `STRING` | `block.content.text` | Djot inline markup. Null for types without `text`. |
| `level` | `INT64` | `block.content.level` | Heading level. Null for non-heading blocks. |
| `style` | `STRING` | `block.content.style` | `"unordered"` or `"ordered"`. Null for non-list blocks. |
| `created_by` | `STRING` | `block.created_by` | Author in `namespace:name` format. |
| `created_at` | `STRING` | `block.created_at` | ISO 8601 timestamp string. |
| `hash` | `STRING` | `block.hash` | `sha256:...` content fingerprint. |

The `content` object is not stored as a nested JSON blob in Kuzu. Its fields are flattened into top-level columns. This makes the columns directly queryable without JSON path expressions.

#### `Page`

Maps from `page.v1` records in `pages.jsonl`.

| Column | Kuzu type | Source field | Notes |
|--------|-----------|--------------|-------|
| `id` | `STRING` | `page.id` | Primary key. |
| `schema` | `STRING` | `page.schema` | Always `"page.v1"`. |
| `title` | `STRING` | `page.title` | Derived from first heading block. |
| `created_by` | `STRING` | `page.created_by` | Author. |
| `created_at` | `STRING` | `page.created_at` | ISO 8601 timestamp string. |
| `updated_at` | `STRING` | `page.updated_at` | ISO 8601 timestamp string. |

`root` (the ordered list of block IDs) is not stored as a column. It is represented as `HAS_BLOCK` relationships with a `position` property.

### Relationship tables

#### `HAS_BLOCK` — `(Page) → (Block)`

Represents membership: this block belongs to this page at this position.

| Column | Kuzu type | Notes |
|--------|-----------|-------|
| `position` | `INT64` | 0-indexed position in the page's `root` array. Enables ordered retrieval. |

This relationship is derived by iterating `page.root` and emitting one row per `(page_id, block_id, position)` triple.

### Schema DDL (Cypher)

```cypher
CREATE NODE TABLE Block(
    id STRING,
    version INT64,
    schema STRING,
    type STRING,
    text STRING,
    level INT64,
    style STRING,
    created_by STRING,
    created_at STRING,
    hash STRING,
    PRIMARY KEY (id)
);

CREATE NODE TABLE Page(
    id STRING,
    schema STRING,
    title STRING,
    created_by STRING,
    created_at STRING,
    updated_at STRING,
    PRIMARY KEY (id)
);

CREATE REL TABLE HAS_BLOCK(
    FROM Page TO Block,
    position INT64
);
```

---

## 5. Parquet intermediate files

Kuzu's `COPY FROM` command is the high-performance bulk load path. It reads Parquet files directly in C++, bypassing Python row-by-row insertion. PyArrow is used to write the Parquet files.

### Three Parquet files

**`workspace/indexes/kuzu/parquet/blocks.parquet`**

One row per block. Columns match the `Block` node table exactly:

```
id, version, schema, type, text, level, style, created_by, created_at, hash
```

Derived by reading each line of `blocks.jsonl` and flattening `content`:
- `text` ← `content.get("text")` (None if absent)
- `level` ← `content.get("level")` (None if absent)
- `style` ← `content.get("style")` (None if absent)

**`workspace/indexes/kuzu/parquet/pages.parquet`**

One row per page. Columns match the `Page` node table:

```
id, schema, title, created_by, created_at, updated_at
```

**`workspace/indexes/kuzu/parquet/has_block.parquet`**

One row per `(page, block)` membership. Three columns:

```
from, to, position
```

Where `from` is `page.id`, `to` is the block ID at that position, and `position` is the 0-indexed offset in `page.root`.

### `COPY FROM` commands

```cypher
COPY Block FROM 'workspace/indexes/kuzu/parquet/blocks.parquet';
COPY Page FROM 'workspace/indexes/kuzu/parquet/pages.parquet';
COPY HAS_BLOCK FROM 'workspace/indexes/kuzu/parquet/has_block.parquet';
```

---

## 6. Database location

The Kuzu database is stored at `workspace/indexes/kuzu/db/`. This directory is created by Kuzu on first use. It is excluded from git (covered by `workspace/indexes/` in `.gitignore`).

The Parquet intermediate files are stored at `workspace/indexes/kuzu/parquet/`. These are also excluded from git as derived data.

---

## 7. Deferred: `NEXT` edges between blocks

A `(Block)-[:NEXT]->(Block)` relationship expressing sequential order within a page is a natural addition. It is deferred from Test 01 because:

- The `position` property on `HAS_BLOCK` already encodes order. `NEXT` is redundant for Test 01's verification query.
- It adds a second relationship table and a second pass over the `root` array.
- It is straightforward to add in a later test once the base schema is stable.

---

## 8. Expected state after Test 01

Six additional Djot test files were created and validated during review (`tests/test_00/extra_inputs/`). All 7 files are ingested before the Kuzu index is built.

| Object | Count | Notes |
|--------|-------|-------|
| `Block` nodes | 47 | Across 7 pages |
| `Page` nodes | 7 | `test_00.dj` + 6 extra files |
| `HAS_BLOCK` edges | 47 | One per block, positions 0-based per page |

### Verification query

```cypher
MATCH (p:Page {id: 'page-test_00'})-[r:HAS_BLOCK]->(b:Block)
RETURN b.id, b.type, b.text, b.level, r.position
ORDER BY r.position;
```

Expected: 9 rows in document order, matching the block sequence from Test 00.

---

## 9. File layout after Test 01

```
knowledge-graph/
  src/
    index/
      __init__.py
      kuzu_schema.py      ← create node and relationship tables in Kuzu
      jsonl_to_parquet.py ← flatten JSONL files to Parquet
      kuzu_loader.py      ← COPY FROM Parquet into Kuzu
      build_index.py      ← top-level function: JSONL → Kuzu

  workspace/
    store/
      blocks.jsonl        ← unchanged canonical source
      pages.jsonl         ← unchanged canonical source
    indexes/
      kuzu/
        db/               ← Kuzu database directory (excluded from git)
        parquet/          ← intermediate Parquet files (excluded from git)
```

---

## 10. Updated environment

Two new dependencies are added to `environment.yml`:

```yaml
- pip:
  - uuid6
  - kuzu
  - pyarrow
```

`kuzu` provides the embedded graph database and Python API.
`pyarrow` provides Parquet read/write.

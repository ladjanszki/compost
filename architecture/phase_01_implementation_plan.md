# Test 01 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Test 01. It assumes the reviewer has read `test_01_design.md`. It is intended for review before any code is written.

The goal of Test 01 is to implement and verify the pipeline:

```
blocks.jsonl + pages.jsonl  →  Parquet files  →  LadybugDB graph database
```

This loads the JSONL output of Test 00 into a LadybugDB derived index. The JSONL files remain the canonical source of truth and are not modified.

---

## 2. Prerequisites

- [ ] Test 00 has been run: `workspace/store/blocks.jsonl` and `workspace/store/pages.jsonl` exist and contain valid data.
- [ ] The `knowledge-graph` conda environment is active.

---

## 3. Steps

### Step 1 — Update `environment.yml`

Add `ladybug` and `pyarrow` to the pip dependencies section:

```yaml
name: knowledge-graph
channels:
  - conda-forge
dependencies:
  - python=3.12
  - pip
  - pip:
    - uuid6
    - real-ladybug==0.15.3
    - pyarrow
```

Recreate the environment:

```bash
conda env update -f environment.yml --prune
```

**Verification**:

```bash
conda run -n knowledge-graph python -c "import real_ladybug as lb; print(ladybug.__version__)"
conda run -n knowledge-graph python -c "import pyarrow; print(pyarrow.__version__)"
```

Both should print a version string without error.

---

### Step 2 — Create directory structure

```bash
mkdir -p src/index
mkdir -p workspace/indexes/ladybug/db
mkdir -p workspace/indexes/ladybug/parquet
touch src/index/__init__.py
touch src/index/ladybug_schema.py
touch src/index/jsonl_to_parquet.py
touch src/index/ladybug_loader.py
touch src/index/build_index.py
```

**Deliverable**: directory tree exists, all `.py` files are empty.

---

### Step 3 — `ladybug_schema.py`

Implement one function:

```python
def create_schema(db_path: str) -> None:
    """
    Open (or create) a LadybugDB database at db_path and create all node and
    relationship tables. Safe to call on an existing empty database.
    Raises if tables already exist (caller must clear the db before rebuilding).
    """
```

The function executes the following DDL in order:

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

Implementation notes:
- Open the database with `lb.Database(db_path)` and get a connection with `lb.Connection(db)`.
- Execute each `CREATE` statement separately via `conn.execute(...)`.

**Verification**: call `create_schema("workspace/indexes/ladybug/db")`, then open the database and run `CALL show_tables() RETURN *` — expect three tables: `Block`, `Page`, `HAS_BLOCK`.

---

### Step 4 — `jsonl_to_parquet.py`

Implement three functions:

```python
def blocks_to_parquet(blocks_jsonl: str, output_path: str) -> int:
    """
    Read blocks.jsonl and write a Parquet file with one row per block.
    Returns the number of rows written.

    Columns: id, version, schema, type, text, level, style,
             created_by, created_at, hash
    """

def pages_to_parquet(pages_jsonl: str, output_path: str) -> int:
    """
    Read pages.jsonl and write a Parquet file with one row per page.
    Returns the number of rows written.

    Columns: id, schema, title, created_by, created_at, updated_at
    """

def has_block_to_parquet(pages_jsonl: str, output_path: str) -> int:
    """
    Read pages.jsonl and write a Parquet file with one row per
    (page, block, position) triple derived from each page's root array.
    Returns the number of rows written.

    Columns: from, to, position
    """
```

Implementation notes for `blocks_to_parquet`:
- Read each line of `blocks_jsonl` with `json.loads`.
- Extract `content.get("text")`, `content.get("level")`, `content.get("style")` — use `None` for absent fields.
- Collect all rows into a list of dicts.
- Build a `pyarrow.Table` from the list and write with `pyarrow.parquet.write_table`.

Implementation notes for `has_block_to_parquet`:
- For each page record, iterate `enumerate(page["root"])` to get `(position, block_id)` pairs.
- Emit `{"from": page["id"], "to": block_id, "position": position}` for each pair.

**Verification**: call all three functions, then read back the Parquet files with `pyarrow.parquet.read_table(path).to_pydict()` and confirm row counts and column names match expectations.

---

### Step 5 — `ladybug_loader.py`

Implement one function:

```python
def load_from_parquet(
    db_path: str,
    blocks_parquet: str,
    pages_parquet: str,
    has_block_parquet: str,
) -> None:
    """
    Run COPY FROM on all three Parquet files to load data into LadybugDB.
    Assumes the schema already exists (ladybug_schema.create_schema was called first).
    """
```

The function executes three `COPY FROM` statements in order:

```cypher
COPY Block FROM '{blocks_parquet}';
COPY Page FROM '{pages_parquet}';
COPY HAS_BLOCK FROM '{has_block_parquet}';
```

Order matters: `Block` and `Page` nodes must exist before `HAS_BLOCK` edges can reference them.

Implementation note: LadybugDB's `COPY FROM` command requires an **absolute path** to the Parquet file. Use `os.path.abspath(...)` on each path before interpolating into the Cypher string.

**Verification**: after loading, run a count query and confirm expected numbers.

---

### Step 6 — `build_index.py`

Implement the top-level function:

```python
def build_index(
    blocks_jsonl: str = "workspace/store/blocks.jsonl",
    pages_jsonl: str = "workspace/store/pages.jsonl",
    db_path: str = "workspace/indexes/ladybug/db",
    parquet_dir: str = "workspace/indexes/ladybug/parquet",
) -> None:
    """
    Full pipeline: JSONL files → Parquet → LadybugDB.

    Clears and rebuilds the LadybugDB database on each run.
    The JSONL source files are never modified.
    """
```

Steps inside:
1. If `db_path` exists, delete it entirely (`shutil.rmtree`) so the rebuild starts clean.
2. Re-create `db_path` and `parquet_dir` directories.
3. Call `create_schema(db_path)`.
4. Write Parquet files:
   - `blocks_to_parquet(blocks_jsonl, parquet_dir + "/blocks.parquet")`
   - `pages_to_parquet(pages_jsonl, parquet_dir + "/pages.parquet")`
   - `has_block_to_parquet(pages_jsonl, parquet_dir + "/has_block.parquet")`
5. Call `load_from_parquet(db_path, ...)` with the three Parquet paths.

**Verification**: run `build_index()` and confirm it completes without error.

---

### Step 7 — Ingest all test files before building the index

The review added 6 extra test files in `tests/test_00/extra_inputs/` that were validated against the Test 00 pipeline. All 7 files (original + 6 extras) must be ingested before running `build_index()` to give the graph a realistic dataset.

First, clear any previous JSONL output from earlier Test 00 runs:

```bash
rm -f workspace/store/blocks.jsonl workspace/store/pages.jsonl
```

Then ingest all 7 files:

```bash
conda activate knowledge-graph
python -c "
import glob
from src.ingest.ingest_page import ingest_page

files = ['tests/test_00/test_00.dj'] + sorted(glob.glob('tests/test_00/extra_inputs/*.dj'))
for f in files:
    page_id = ingest_page(f, 'human:test')
    print('Ingested:', page_id)
"
```

Expected: 7 page IDs printed, no errors.

Verify JSONL line counts:

```bash
wc -l workspace/store/blocks.jsonl workspace/store/pages.jsonl
# Expected: 47 blocks, 7 pages
```

---

### Step 8 — End-to-end verification

Run the full index build:

```bash
python -c "
from src.index.build_index import build_index
build_index()
print('Index built.')
"
```

Run node and edge counts:

```bash
python -c "
import real_ladybug as lb
db = lb.Database('workspace/indexes/ladybug/db')
conn = lb.Connection(db)
for label, q in [
    ('Block nodes',     'MATCH (b:Block) RETURN count(b)'),
    ('Page nodes',      'MATCH (p:Page)  RETURN count(p)'),
    ('HAS_BLOCK edges', 'MATCH ()-[r:HAS_BLOCK]->() RETURN count(r)'),
]:
    r = conn.execute(q)
    print(label + ':', r.get_next()[0])
"
```

Expected counts:

| Check | Expected |
|-------|----------|
| `Block` node count | 47 |
| `Page` node count | 7 |
| `HAS_BLOCK` edge count | 47 |

Run the primary verification query — all blocks for `page-test_00` in order:

```bash
python -c "
import real_ladybug as lb
db = lb.Database('workspace/indexes/ladybug/db')
conn = lb.Connection(db)
result = conn.execute(\"\"\"
    MATCH (p:Page {id: 'page-test_00'})-[r:HAS_BLOCK]->(b:Block)
    RETURN b.id, b.type, b.text, b.level, r.position
    ORDER BY r.position
\"\"\")
while result.has_next():
    print(result.get_next())
"
```

Expected: 9 rows in document order.

| Row (position) | Expected |
|----------------|----------|
| 0 | `type=heading`, `level=1`, `text="Example heading - for the test file"` |
| 1 | `type=paragraph`, text contains `*bold*` and `_italic_` |
| 2 | `type=paragraph` |
| 3 | `type=heading`, `level=2` |
| 4 | `type=paragraph` |
| 5–8 | `type=list_item` |

Spot-check 1 — ordered list items have `style="ordered"` in the graph:

```bash
python -c "
import real_ladybug as lb
db = lb.Database('workspace/indexes/ladybug/db')
conn = lb.Connection(db)
result = conn.execute(\"\"\"
    MATCH (b:Block {type: 'list_item'})
    RETURN b.style, count(b)
    ORDER BY b.style
\"\"\")
while result.has_next():
    print(result.get_next())
# Expected: both 'ordered' and 'unordered' rows
"
```

Spot-check 2 — a multi-section page returns blocks in correct positional order:

```bash
python -c "
import real_ladybug as lb
db = lb.Database('workspace/indexes/ladybug/db')
conn = lb.Connection(db)
result = conn.execute(\"\"\"
    MATCH (p:Page {id: 'page-deep_headings'})-[r:HAS_BLOCK]->(b:Block)
    RETURN b.type, b.level, r.position
    ORDER BY r.position
\"\"\")
while result.has_next():
    print(result.get_next())
# Expected: headings and paragraphs in document order, levels 1-4 present
"
```

---

## 4. Implementation order and dependencies

```
Step 1  (environment)      — no code dependencies
Step 2  (directories)      — depends on Step 1
Step 3  (ladybug_schema)      — depends on Step 1 (ladybug installed)
Step 4  (jsonl_to_parquet) — depends on Step 1 (pyarrow installed)
Step 5  (ladybug_loader)      — depends on Steps 3, 4
Step 6  (build_index)      — depends on Steps 3, 4, 5
Step 7  (ingest all files) — depends on Step 6 (re-uses Test 00 pipeline)
Step 8  (verification)     — depends on Step 7
```

Steps 3 and 4 can be implemented in parallel after Step 1.

---

## 5. What Test 01 does NOT validate

- **Block versioning in LadybugDB**: all blocks are version 1. Multiple versions of the same block ID are not tested.
- **Incremental updates**: `build_index` always clears and rebuilds. Partial updates are deferred.
- **`NEXT` edges**: sequential block ordering is encoded only via `HAS_BLOCK.position`, not as a separate relationship.
- **Conversation and operation nodes**: not yet in the schema.
- **Entity nodes and semantic edges**: future semantic enrichment layer, not in scope for v1 indexing tests.
- **Large file performance**: Test 01 uses 9 blocks. The Parquet/COPY path is used regardless, establishing the correct pattern for future scale.

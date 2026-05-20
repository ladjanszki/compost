# Delta Ingestion & Block Versioning — Design Document

## 1. Purpose and Scope

This document resolves two high-severity architectural debts that must be addressed before Phase 05
(semantic enrichment) goes to production:

- **Risk #7** (`README.md` — Ingestion pipeline): No incremental re-ingestion. Full-rebuild on every
  run makes Phase 05 infeasible at any real corpus size.
- **Risk #11** (`README.md` — LadybugDB / graph database): Block versioning. In-place editing
  of a block under a stable `id` destroys historical identity and silently corrupts annotation
  references (e.g., a user note that says "regarding this block" points to different text after an
  edit).

The document covers: context, design options considered, the chosen architecture and its constraints,
the implementation plan, and a complete test specification.

This document is self-contained. An implementor does not need to read any prior document, but
cross-references are provided for traceability.

---

## 2. Context

### 2.1 How ingestion works today (after Phase 02)

The current ingestion entry point is `src/ingest/ingest_page.py: ingest_page()`. Its current
behaviour:

```
.dj file → djot.js AST → ast_walker → blocks (list[dict]) → Parquet (temp) → LadybugDB COPY FROM
```

Before writing, `ingest_page()` wipes all nodes belonging to the page and rebuilds from scratch.
This is documented explicitly in Phase 02 design as the "full-replace" strategy.

### 2.2 Why this fails in Phase 05

Phase 05 (`phase_05_design.md`) adds LLM-based entity and relation extraction. The extractor calls
the LLM **once per eligible block**. A 500-block corpus costs 500 API calls and meaningful wall-clock
time. If the pipeline must wipe and rebuild the graph on every ingest run, it must also re-run
enrichment on every block, every time — including the 490 blocks that were not touched. This is
both expensive and architecturally wrong.

### 2.3 Why stable block IDs alone are insufficient

The Phase 02 schema uses `id STRING PRIMARY KEY` on the `Block` node table (see `block_schema.py`).
This is correct for the identity of a block across the life of a document. However:

When an agent or human edits a paragraph, the current design's only options are:
- **Delete + re-insert** with a new UUID: breaks the identity. Any `MENTIONS`, `HAS_BLOCK`, or
  `LINKS_TO` edge pointing to the old `id` becomes a dangling reference.
- **Upsert `text` in place**: loses the old text entirely. An annotation written as
  `"regarding {#para-1}"` now silently references different content than when it was written.

### 2.4 The commenting workflow (primary use case that constrains the design)

The system serves two consumer surfaces:
1. **LLM agents**: receive rendered Djot as context.
2. **Human operator**: reads the knowledge base as a locally-served static HTML wiki.

The human workflow is:
1. Read a rendered HTML page in the browser.
2. Click on a block to copy its `{#block-id}` to clipboard.
3. Write a note: *"Regarding `{#para-1}` — I think this is incomplete."*
4. That note, as a new block in any `.dj` file, is ingested into the graph.
5. Agents can later query: *"What annotations exist for block `{#para-1}`?"*

**The constraint this imposes:** The reference `{#para-1}` in the note was written while the user
was looking at a specific version of the text. If the text of `{#para-1}` later changes, the
annotation does not automatically follow. The system must be able to answer:
*"What was the exact content of `{#para-1}` when this annotation was written?"*

A plain graph upsert (writing new text over the old) destroys this capability entirely.

---

## 3. Options Considered

### Option A — Identity/State split (Anytype CRDT pattern)

Split each block into two node types: `BlockIdentity` (stable `id`) and `BlockVersion`
(content-addressed by hash). All semantic edges attach to `BlockVersion`. A `HAS_CURRENT_STATE`
edge connects identity to the latest version.

**Why rejected:** Every LLM tool query (Phase 06) and every LLM-generated Cypher query (Phase 07)
must traverse an additional hop. The LLM must consistently produce
`(page)-[:HAS_BLOCK]->(identity)-[:HAS_CURRENT_STATE]->(version)-[:MENTIONS]->(entity)` instead
of `(page)-[:HAS_BLOCK]->(block)-[:MENTIONS]->(entity)`. LLM-generated Cypher failures are
expected to be frequent if the schema is non-obvious. This complexity tax is paid on every single
query, every day, for a history feature that is expected to be needed rarely.

### Option B — Temporal nodes, append-only graph (Strategy C)

Keep a single `Block` node type. Every edit inserts a new node with a composite primary key
(`id + "_" + hash`). Old nodes get `is_latest = False` and a `[:SUPERSEDES]` edge to the old
node.

**Why rejected:** All tool queries must include `WHERE b.is_latest = True`. This is a filter the
LLM must reliably emit in Phase 07 for every single query. Missing it returns results polluted
with stale block content, which is a hard-to-detect failure mode. Additionally, on edit, semantic
edges (`MENTIONS`) are attached to the now-stale node and must be fully migrated or regenerated,
with no clear ownership of that migration logic.

### Option C — Lean current-state graph + immutable Parquet event log (chosen)

Keep the graph as the **current state only**: one `Block` node per `{#id}`, always representing
the latest content. History lives in an **append-only Parquet event log** stored outside the graph.

Cross-references in annotations encode both the stable block ID and the content hash at the time of
writing (a compound reference). Resolving a historical reference first queries the graph; if the
hash no longer matches, the resolver falls back to the event log to retrieve the exact text.

**Why chosen:** described in full in Section 4.

---

## 4. Chosen Architecture

### 4.1 Principle

> LadybugDB holds the present. The Parquet event log holds the past. The graph schema is never
> more complex than it needs to be to serve today's queries.

### 4.2 Content hash

Every block gets a deterministic `content_hash` computed as:

```python
import hashlib, json

def block_hash(block: dict) -> str:
    """SHA-256 of the canonical JSON of (type, content) — stable across runs."""
    payload = json.dumps(
        {"type": block["type"], "content": block["content"]},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
```

The hash is a 16-char hex prefix (64 bits of SHA-256). Collision probability across a realistic
knowledge base (~100k blocks) is negligible (~5 × 10⁻¹⁰). The full 64-char hash is stored in
the event log; only the prefix is stored in the graph for space efficiency.

### 4.3 The `Block` node schema (updated)

```cypher
CREATE NODE TABLE Block(
    id          STRING,          -- stable Djot {#block-id} or generated UUIDv7
    type        STRING,          -- paragraph, heading, code_block, etc.
    text        STRING,          -- current rendered text
    hash        STRING,          -- 16-char content hash of current version
    page_id     STRING,          -- owning page id (denormalized for fast lookup)
    position    INT64,           -- ordinal position in page (0-indexed)
    language    STRING,          -- for code_block; null otherwise
    author      STRING,          -- who last wrote this block
    created_at  STRING,          -- ISO 8601 — first ingestion of this block_id
    updated_at  STRING,          -- ISO 8601 — last content change
    PRIMARY KEY (id)
);
```

New columns relative to Phase 02: `hash`, `page_id`, `position`, `created_at`, `updated_at`.
`author` was already present in Phase 02 design.

### 4.4 The event log

Location: `workspace/store/event_log/ingest_events.parquet`

The event log is an **append-only columnar file**. Each row represents one ingest event for one
block at one point in time. It is written by the ingestion pipeline and never modified after
writing.

Schema:

| Column        | Type    | Description                                    |
|---------------|---------|------------------------------------------------|
| `event_id`    | STRING  | UUIDv7 — globally unique event identifier      |
| `event_type`  | STRING  | `insert`, `update`, `delete`                   |
| `block_id`    | STRING  | The stable Djot `{#id}` of the block           |
| `page_id`     | STRING  | The page this block belongs to                 |
| `hash`        | STRING  | Full 64-char SHA-256 of (type + content)       |
| `block_type`  | STRING  | paragraph, heading, code_block, etc.           |
| `text`        | STRING  | Full text content at this version              |
| `author`      | STRING  | Ingestion author (`human:name`, `agent:name`)  |
| `timestamp`   | STRING  | ISO 8601 UTC timestamp                         |
| `position`    | INT64   | Ordinal position in the page at this timestamp |

The event log is written by appending new Parquet row groups. It is never read during normal
ingestion — only during reference resolution and point-in-time graph replay.

### 4.5 The delta-ingestion pipeline

`ingest_page()` is refactored to:

```
.dj file
  → djot.js AST
  → ast_walker  →  blocks: list[dict]  →  hash each block
  → query LadybugDB: SELECT id, hash FROM Block WHERE page_id = ?
  → diff in Python memory:
      NEW      = blocks whose id is absent from the graph
      MODIFIED = blocks whose id exists but hash differs
      DELETED  = block ids in the graph not present in the new parse
      UNCHANGED = blocks whose id and hash both match
  → for NEW:
      write to Parquet → COPY FROM into Block table
      append `insert` events to event log
      enqueue for Phase 05 enrichment
  → for MODIFIED:
      update Block node (text, hash, updated_at) via Cypher MERGE/SET
      append `update` events to event log
      DELETE existing MENTIONS edges for this block id
      enqueue for Phase 05 re-enrichment
  → for DELETED:
      DELETE Block node (LadybugDB cascades edges)
      append `delete` events to event log
  → for UNCHANGED:
      skip entirely (no graph write, no enrichment)
  → update HAS_BLOCK edge positions for the page (always, since positions may shift)
```

The Phase 05 enrichment queue is a simple list of block IDs returned by `ingest_page()` as a
structured result. The caller (or a top-level orchestrator) passes this list to
`enrich_blocks()`.

### 4.6 Compound block references (the annotation contract)

When the static HTML renderer emits a block, it encodes both identifiers in the element:

```html
<p id="para-1" data-hash="3f7a2b9c1e8d4f0a">
  This is the paragraph text.
</p>
```

When the user copies a block reference, the UI copies the compound form:

```
{#para-1:3f7a2b9c1e8d4f0a}
```

The colon-separated `id:hash` is the **versioned block reference**. A plain `{#para-1}` (no hash)
is an **unversioned block reference** that always resolves to the current state.

The `query_block_ref(ref: str)` tool (added in Phase 06 or later) resolves both forms:

```
1. Parse ref: split on ":" → block_id, hash (or None if no hash present)
2. MATCH (b:Block {id: block_id}) RETURN b.hash, b.text
3. If hash is None OR b.hash == hash: return b.text  ← current graph
4. If b.hash != hash:
      SELECT text FROM event_log WHERE block_id = ? AND hash = ?
      return event_log result with a note: "resolved from history (current version differs)"
```

This means annotations are **never broken** by edits. They silently fall back to the event log.

### 4.7 Enrichment interaction (Phase 05 contract)

The delta pipeline returns an `IngestResult` object:

```python
@dataclass
class IngestResult:
    page_id: str
    inserted: list[str]   # block ids that are new
    updated: list[str]    # block ids whose content changed
    deleted: list[str]    # block ids removed from the document
    unchanged: list[str]  # block ids with identical hash — no action needed
```

The Phase 05 enrichment entry point accepts `block_ids: list[str]` and only processes those IDs.
On `update`, the enrichment pipeline first deletes all existing `MENTIONS` edges for those block
IDs before running the LLM, because:

- We cannot determine semantically whether a change is significant without calling the LLM.
- A partial edit may break one entity mention while leaving another intact.
- The safe default is always: full re-extraction for any block whose text hash changed.

### 4.8 Point-in-time graph replay

For rare debugging or reproducibility needs, a utility script replays the event log up to a given
timestamp into a fresh LadybugDB instance:

```
workspace/store/event_log/ingest_events.parquet
  → filter rows WHERE timestamp <= target_timestamp
  → group by block_id, take last event per block_id
  → reconstruct the graph state at that point in time
  → write into a separate LadybugDB instance at a user-specified path
```

This script is **not part of the hot path**. It is a maintenance utility. The assumption is that
replays are rare (e.g., debugging why a stochastic LLM answer was produced on a given date), not
a daily operation.

---

## 5. Architectural Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | History storage location | Append-only Parquet event log, outside LadybugDB | Keeps graph schema simple for LLM queries. History queries are infrequent. |
| D2 | Graph represents | Current state only | One node per block ID. No temporal edges. Zero schema tax on Phase 06/07 tools. |
| D3 | Hash algorithm | SHA-256, 16-char prefix in graph, full hash in event log | 16 chars is sufficient for collision avoidance at realistic corpus sizes. Full hash in log for exact-match lookups. |
| D4 | Compound reference format | `{#id:hash}` | Embeds both stable identity and point-in-time version. Parseable with a single `str.split(":", 1)`. Backward-compatible: plain `{#id}` still works. |
| D5 | Enrichment on edit | Full re-extraction (delete MENTIONS + re-run LLM) | Cannot determine semantic change without LLM. Partial migration of old edges is more dangerous than a clean slate. |
| D6 | Event log file format | Parquet (append via row groups) | Consistent with the existing ingestion pipeline technology. DuckDB can query it directly if needed for replay or auditing. |
| D7 | Deleted block handling | Hard delete from LadybugDB; `delete` event appended to log | Deleted blocks are gone from the live graph. Their text remains in the event log for annotation resolution. |
| D8 | No git assumption | System manages its own history via event log | The `.dj` files may or may not be in a git repo. The system does not depend on git for reproducibility. |

---

## 6. Constraints and Prioritization Factors

These are the factors that made certain decisions non-negotiable.

**C1 — Phase 07 (LLM-to-Cypher) schema legibility**
The Phase 07 tool accepts natural language questions and generates Cypher. An LLM generating
Cypher must understand the schema from a brief description. Every additional node type or edge
type multiplies the chance of the LLM emitting an incorrect query. This is the primary reason
temporal nodes (Option B) and identity/state split (Option A) were rejected.

**C2 — Phase 05 cost at scale**
Per `README.md` Risk #15: a 500-block corpus = 500 LLM API calls. Enrichment must only run on
blocks that actually changed. This makes the hash-based delta detection a hard requirement, not
an optimization.

**C3 — Annotation durability (commenting workflow)**
The human operator copies block references while reading a specific version of the wiki. Those
references must remain resolvable even after the source block is edited. This rules out a pure
current-state-only approach (Strategy B without the event log). The event log's fallback lookup
is the minimal mechanism that satisfies this requirement.

**C4 — No git dependency**
The project's canonical storage is LadybugDB (per `README.md` Design Decisions). The `.dj` files
are the authoring surface, but the system must function correctly even if they are not tracked by
git. Therefore, the event log is self-managed.

**C5 — Backwards compatibility with block IDs assigned in Phase 02**
Blocks in the test corpus already have UUIDv7 IDs (auto-generated) or explicit `{#id}` attributes.
The delta mechanism must be additive: the `hash` and timestamp columns are new, but the `id`
primary key semantics are unchanged.

---

## 7. New and Modified Files

```
knowledge-graph/
  src/
    ingest/
      block_hash.py          ← NEW: block_hash(block) → str
      event_log.py           ← NEW: append_events(events: list[IngestEvent]) → None
      ingest_page.py         ← MODIFIED: delta logic, returns IngestResult
      ingest_result.py       ← NEW: IngestResult dataclass
    tools/
      query_block_ref.py     ← NEW (Phase 06): resolves {#id} and {#id:hash} references

  workspace/
    store/
      ladybug/               ← unchanged path, schema gets new columns
      event_log/
        ingest_events.parquet ← NEW: append-only event log

  tests/
    test_delta/
      fixtures/
        v1_simple.dj         ← initial version of a test document
        v2_edit_one.dj       ← same doc with one paragraph edited
        v2_add_one.dj        ← same doc with one paragraph added
        v2_delete_one.dj     ← same doc with one paragraph removed
        v2_reorder.dj        ← same doc with blocks reordered (unchanged content)
      test_delta_ingestion.py ← test runner
      test_event_log.py      ← test runner
      test_ref_resolution.py ← test runner
```

---

## 8. Test Specification

Tests follow the pattern established in `tests/test_03/test_roundtrip.py`: standalone Python
scripts that print `PASS`/`FAIL` per case and `sys.exit(1)` on any failure.

---

### Test Suite 1 — `test_delta_ingestion.py`

Tests the correctness of the delta diff logic in `ingest_page()`.

#### TC-D1: Unchanged document produces no writes

```
Setup:   Ingest v1_simple.dj into a fresh DB.
Action:  Ingest v1_simple.dj a second time (identical content).
Assert:  IngestResult.inserted == []
         IngestResult.updated  == []
         IngestResult.deleted  == []
         IngestResult.unchanged == [all block ids from v1]
         LadybugDB block count unchanged.
         Event log row count unchanged (no new events appended).
```

**Rationale:** This is the hot path for a large corpus. An unchanged file must produce zero writes.

#### TC-D2: Single edited paragraph is detected as MODIFIED

```
Setup:   Ingest v1_simple.dj. Record the hash of block {#para-edit-target}.
Action:  Ingest v2_edit_one.dj (same doc, {#para-edit-target} has different text).
Assert:  IngestResult.updated == ["{#para-edit-target}"]
         IngestResult.inserted == []
         IngestResult.deleted  == []
         Block in LadybugDB has new text and new hash.
         Block updated_at > created_at.
         Event log has exactly one new row: event_type="update", block_id="{#para-edit-target}".
```

#### TC-D3: New block is detected as INSERTED

```
Setup:   Ingest v1_simple.dj.
Action:  Ingest v2_add_one.dj (adds a new block {#para-new}).
Assert:  IngestResult.inserted == ["{#para-new}"]
         New block exists in LadybugDB with correct text and hash.
         created_at == updated_at (first seen).
         Event log has exactly one new row: event_type="insert", block_id="{#para-new}".
```

#### TC-D4: Removed block is detected as DELETED

```
Setup:   Ingest v1_simple.dj.
Action:  Ingest v2_delete_one.dj (removes block {#para-to-delete}).
Assert:  IngestResult.deleted == ["{#para-to-delete}"]
         Block {#para-to-delete} is absent from LadybugDB.
         Event log has exactly one new row: event_type="delete", block_id="{#para-to-delete}".
```

#### TC-D5: Reordered blocks are all UNCHANGED

```
Setup:   Ingest v1_simple.dj.
Action:  Ingest v2_reorder.dj (same blocks, different order, no text changes).
Assert:  IngestResult.unchanged == [all block ids]
         IngestResult.updated == []
         HAS_BLOCK edge positions updated to reflect new order.
         No new event log rows.
```

**Rationale:** Position changes are structural (edge property), not content changes. They do not
invalidate content hashes or enrichment results.

#### TC-D6: Multi-page isolation — editing page A does not affect page B

```
Setup:   Ingest two separate pages: page_a.dj and page_b.dj.
Action:  Ingest page_a.dj with one block edited.
Assert:  All blocks in page_b are UNCHANGED.
         IngestResult for page_a correctly identifies the modified block.
```

---

### Test Suite 2 — `test_event_log.py`

Tests the correctness of the event log writer.

#### TC-E1: Event log is created if it does not exist

```
Setup:   Remove event_log directory.
Action:  Ingest v1_simple.dj.
Assert:  workspace/store/event_log/ingest_events.parquet exists.
         All blocks in v1_simple.dj have a corresponding "insert" event row.
         Each row has a non-null event_id, block_id, hash, text, timestamp.
```

#### TC-E2: Event log appends, never overwrites

```
Setup:   Ingest v1_simple.dj (N rows in log).
Action:  Ingest v2_edit_one.dj (M new events expected).
Assert:  Total rows in event log == N + M.
         Original N rows are byte-identical (no mutation).
```

#### TC-E3: Event log contains full text, not just the hash

```
Setup:   Ingest v1_simple.dj with a block whose text is "Hello, world."
Assert:  Event log row for that block has text == "Hello, world."
         Event log row has hash == block_hash({"type": ..., "content": {"text": "Hello, world."}})
```

#### TC-E4: Deleted block text is preserved in event log

```
Setup:   Ingest v1_simple.dj (block {#para-to-delete} has text "Preserved content.").
Action:  Ingest v2_delete_one.dj.
Assert:  Block {#para-to-delete} absent from LadybugDB.
         Event log contains a row with block_id="{#para-to-delete}", event_type="delete",
         text="Preserved content." (text at time of deletion recorded).
```

---

### Test Suite 3 — `test_ref_resolution.py`

Tests the `query_block_ref()` resolver.

#### TC-R1: Unversioned reference resolves to current graph state

```
Setup:   Ingest v1_simple.dj. Block {#para-stable} has text "Original text."
Action:  query_block_ref("{#para-stable}")
Assert:  Returns "Original text."
         No event log lookup performed.
```

#### TC-R2: Versioned reference resolves correctly when hash matches current state

```
Setup:   Ingest v1_simple.dj. Compute hash H for block {#para-stable}.
Action:  query_block_ref("{#para-stable}:" + H)
Assert:  Returns "Original text." (from graph, no event log lookup).
```

#### TC-R3: Versioned reference resolves correctly after block is edited (fallback path)

```
Setup:   Ingest v1_simple.dj. Record hash H1 for block {#para-edit-target}.
         Ingest v2_edit_one.dj. Block {#para-edit-target} now has text "Edited text." and hash H2.
Action:  query_block_ref("{#para-edit-target}:" + H1)
Assert:  Returns "Original text." (retrieved from event log, NOT "Edited text.").
         Response is annotated: resolved="history" (current version differs).
```

**Rationale:** This is the core annotation durability guarantee.

#### TC-R4: Versioned reference for a deleted block resolves from event log

```
Setup:   Ingest v1_simple.dj. Record hash H for block {#para-to-delete}.
         Ingest v2_delete_one.dj. Block {#para-to-delete} is removed.
Action:  query_block_ref("{#para-to-delete}:" + H)
Assert:  Returns "Preserved content." from event log.
         Response annotated: resolved="history" (block no longer exists in graph).
```

#### TC-R5: Reference to unknown id returns structured error, not exception

```
Action:  query_block_ref("{#nonexistent-id}")
Assert:  Returns a structured error dict: {"error": "not_found", "block_id": "nonexistent-id"}
         No exception raised.
```

---

### Test Suite 4 — `test_enrichment_contract.py` (Phase 05 integration)

Tests that the delta pipeline correctly communicates with the enrichment layer.

#### TC-X1: Unchanged blocks are NOT passed to enrichment

```
Setup:   Ingest v1_simple.dj. Run mock enrichment (creates MENTIONS edges).
Action:  Ingest v1_simple.dj again (identical).
Assert:  IngestResult.inserted == [] and IngestResult.updated == [].
         Mock enrichment is called with an empty block list.
         MENTIONS edge count unchanged.
```

#### TC-X2: Modified block triggers MENTIONS deletion before re-enrichment

```
Setup:   Ingest v1_simple.dj. Run mock enrichment on block {#para-edit-target}
         (creates N MENTIONS edges).
Action:  Ingest v2_edit_one.dj. Call enrichment on IngestResult.updated.
Assert:  Before enrichment: MENTIONS edges for {#para-edit-target} == 0 (deleted by delta pipeline).
         After enrichment: MENTIONS edges for {#para-edit-target} == M (re-extracted from new text).
         MENTIONS edges for unchanged blocks are unmodified.
```

#### TC-X3: Deleted block's MENTIONS edges are removed with the node

```
Setup:   Ingest v1_simple.dj. Run mock enrichment on block {#para-to-delete}.
Action:  Ingest v2_delete_one.dj.
Assert:  Block {#para-to-delete} absent from LadybugDB.
         No orphaned MENTIONS edges pointing to {#para-to-delete}.
```

---

## 9. Implementation Plan

### Prerequisites

- [ ] Phase 02 is complete and passing (full djot ingestion works).
- [ ] Phase 03 roundtrip tests pass (`tests/test_03/test_roundtrip.py`).
- [ ] `tests/test_delta/fixtures/` directory exists.

---

### Step 1 — Create test fixtures

Create `tests/test_delta/fixtures/`. Write the following `.dj` files:

**`v1_simple.dj`** — baseline document with explicitly named block IDs:

```djot
{#para-stable}
This paragraph never changes across versions.

{#para-edit-target}
This is the original text of the editable paragraph.

{#para-to-delete}
Preserved content.

{#para-reorder-a}
First block in original order.

{#para-reorder-b}
Second block in original order.
```

**`v2_edit_one.dj`** — identical to v1 except `{#para-edit-target}` has new text:

```djot
{#para-stable}
This paragraph never changes across versions.

{#para-edit-target}
Edited text. The content of this paragraph has been changed.

{#para-to-delete}
Preserved content.

{#para-reorder-a}
First block in original order.

{#para-reorder-b}
Second block in original order.
```

**`v2_add_one.dj`** — identical to v1 plus a new block `{#para-new}`:

```djot
{#para-stable}
This paragraph never changes across versions.

{#para-edit-target}
This is the original text of the editable paragraph.

{#para-to-delete}
Preserved content.

{#para-new}
This block was added in version 2.

{#para-reorder-a}
First block in original order.

{#para-reorder-b}
Second block in original order.
```

**`v2_delete_one.dj`** — identical to v1 but `{#para-to-delete}` is removed:

```djot
{#para-stable}
This paragraph never changes across versions.

{#para-edit-target}
This is the original text of the editable paragraph.

{#para-reorder-a}
First block in original order.

{#para-reorder-b}
Second block in original order.
```

**`v2_reorder.dj`** — identical content to v1, different block order:

```djot
{#para-reorder-b}
Second block in original order.

{#para-reorder-a}
First block in original order.

{#para-stable}
This paragraph never changes across versions.

{#para-edit-target}
This is the original text of the editable paragraph.

{#para-to-delete}
Preserved content.
```

**Verification:** `npx @djot/djot --to ast tests/test_delta/fixtures/v1_simple.dj` produces
valid JSON with 5 paragraph blocks and correct `attributes.id` values.

---

### Step 2 — Implement `src/ingest/block_hash.py`

```python
"""
block_hash.py — deterministic content hash for a block dict.
"""
import hashlib
import json


def block_hash(block: dict) -> str:
    """
    Return a 64-char hex SHA-256 hash of the block's (type, content).
    Stable across Python versions because sort_keys=True and ensure_ascii=False
    give a canonical JSON encoding.
    """
    payload = json.dumps(
        {"type": block["type"], "content": block["content"]},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def block_hash_short(block: dict) -> str:
    """16-char prefix — used as the `hash` column in the LadybugDB Block table."""
    return block_hash(block)[:16]
```

**Verification:**
```python
b = {"type": "paragraph", "content": {"text": "Hello."}}
assert len(block_hash(b)) == 64
assert block_hash(b) == block_hash(b)           # deterministic
b2 = {"type": "paragraph", "content": {"text": "Hello!"}}
assert block_hash(b) != block_hash(b2)          # sensitive to content
```

---

### Step 3 — Implement `src/ingest/ingest_result.py`

```python
"""
ingest_result.py — result dataclass returned by ingest_page().
"""
from dataclasses import dataclass, field


@dataclass
class IngestResult:
    page_id:   str
    inserted:  list[str] = field(default_factory=list)  # block ids new to the graph
    updated:   list[str] = field(default_factory=list)  # block ids with changed hash
    deleted:   list[str] = field(default_factory=list)  # block ids removed from the doc
    unchanged: list[str] = field(default_factory=list)  # block ids with identical hash

    @property
    def dirty(self) -> list[str]:
        """Block ids that need Phase 05 enrichment (re-)run."""
        return self.inserted + self.updated
```

---

### Step 4 — Implement `src/ingest/event_log.py`

```python
"""
event_log.py — append events to the immutable Parquet event log.
"""
import os
from dataclasses import dataclass
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq
import uuid6

EVENT_LOG_PATH = "workspace/store/event_log/ingest_events.parquet"

EVENT_SCHEMA = pa.schema([
    pa.field("event_id",   pa.string()),
    pa.field("event_type", pa.string()),  # insert | update | delete
    pa.field("block_id",   pa.string()),
    pa.field("page_id",    pa.string()),
    pa.field("hash",       pa.string()),  # full 64-char SHA-256
    pa.field("block_type", pa.string()),
    pa.field("text",       pa.string()),
    pa.field("author",     pa.string()),
    pa.field("timestamp",  pa.string()),  # ISO 8601 UTC
    pa.field("position",   pa.int64()),
])


@dataclass
class IngestEvent:
    event_type: Literal["insert", "update", "delete"]
    block_id:   str
    page_id:    str
    hash:       str   # full 64-char
    block_type: str
    text:       str
    author:     str
    timestamp:  str
    position:   int


def append_events(events: list[IngestEvent]) -> None:
    """Append a batch of events to the Parquet event log as a new row group."""
    if not events:
        return
    os.makedirs(os.path.dirname(EVENT_LOG_PATH), exist_ok=True)

    table = pa.table({
        "event_id":   [str(uuid6.uuid7()) for _ in events],
        "event_type": [e.event_type for e in events],
        "block_id":   [e.block_id   for e in events],
        "page_id":    [e.page_id    for e in events],
        "hash":       [e.hash       for e in events],
        "block_type": [e.block_type for e in events],
        "text":       [e.text       for e in events],
        "author":     [e.author     for e in events],
        "timestamp":  [e.timestamp  for e in events],
        "position":   [e.position   for e in events],
    }, schema=EVENT_SCHEMA)

    writer = pq.ParquetWriter(EVENT_LOG_PATH, EVENT_SCHEMA)
    if os.path.exists(EVENT_LOG_PATH):
        # Append by reading existing + writing combined.
        # For production scale, use row-group append or a dedicated log segment approach.
        existing = pq.read_table(EVENT_LOG_PATH)
        table = pa.concat_tables([existing, table])
    writer.write_table(table)
    writer.close()
```

**Note on append semantics:** The implementation above reads and rewrites the full Parquet file.
This is acceptable for the expected corpus sizes (< 10k events). For larger corpora, consider
writing per-ingest Parquet segment files in `event_log/segments/` and merging lazily.

**Verification:**
```python
# Clean state
import os; os.remove(EVENT_LOG_PATH) if os.path.exists(EVENT_LOG_PATH) else None
from src.ingest.event_log import append_events, IngestEvent
e = IngestEvent("insert","blk-1","pg-1","abc"*21+"x","paragraph","Hello.","human:test","2026-01-01T00:00:00Z",0)
append_events([e])
import pyarrow.parquet as pq
t = pq.read_table(EVENT_LOG_PATH)
assert len(t) == 1
assert t["text"][0].as_py() == "Hello."
append_events([e])   # second call appends, not replaces
t2 = pq.read_table(EVENT_LOG_PATH)
assert len(t2) == 2
```

---

### Step 5 — Update LadybugDB schema

Add `hash`, `page_id`, `position`, `created_at`, `updated_at` columns to the `Block` node table.

Since the project is pre-production (no live data to migrate), the migration strategy is:
wipe and rebuild (as stated in `README.md` Risk #12 — acceptable through Phase 04).

The schema update is applied in the `_ensure_schema()` function of `ingest_page.py`. The `CREATE
NODE TABLE` statement is updated to include the new columns. The existing `language` column
(added in Phase 02) is preserved.

**Verification:**
```python
import real_ladybug as lb
db = lb.Database("workspace/store/ladybug/db")
conn = lb.Connection(db)
r = conn.execute("MATCH (b:Block) RETURN b.id, b.hash, b.created_at LIMIT 1")
row = r.get_next()
assert row is not None
assert len(row[1]) == 16   # hash is 16-char prefix
```

---

### Step 6 — Refactor `src/ingest/ingest_page.py`

This is the core step. `ingest_page()` gains delta detection logic.

Pseudocode for the new `ingest_page(djot_path, author) -> IngestResult`:

```python
def ingest_page(djot_path: str, author: str) -> IngestResult:
    # 1. Parse
    ast = get_ast(djot_path)
    blocks = walk(ast)               # list[dict] from ast_walker
    page_id = derive_page_id(djot_path)

    # 2. Hash all incoming blocks
    incoming = {b["id"]: (b, block_hash_short(b), block_hash(b)) for b in blocks}
    # (note: block["id"] must be set by ast_walker before this point)

    # 3. Query current graph state for this page
    existing = query_existing_hashes(conn, page_id)  # dict[block_id -> hash_short]

    # 4. Diff
    incoming_ids = set(incoming)
    existing_ids = set(existing)
    new_ids      = incoming_ids - existing_ids
    deleted_ids  = existing_ids - incoming_ids
    common_ids   = incoming_ids & existing_ids
    modified_ids = {bid for bid in common_ids if incoming[bid][1] != existing[bid]}
    unchanged_ids= common_ids - modified_ids

    # 5. Apply inserts (new blocks)
    if new_ids:
        new_blocks = [incoming[bid][0] for bid in new_ids]
        write_blocks_to_parquet_and_copy(new_blocks, conn, author, now)

    # 6. Apply updates (modified blocks)
    for bid in modified_ids:
        block, hash_short, hash_full = incoming[bid]
        conn.execute("""
            MATCH (b:Block {id: $id})
            SET b.text = $text, b.hash = $hash, b.updated_at = $now
        """, {"id": bid, "text": block["content"]["text"],
              "hash": hash_short, "now": now})
        conn.execute("MATCH (b:Block {id: $id})-[r:MENTIONS]->() DELETE r", {"id": bid})

    # 7. Apply deletes
    for bid in deleted_ids:
        conn.execute("MATCH (b:Block {id: $id}) DETACH DELETE b", {"id": bid})

    # 8. Update HAS_BLOCK positions (always — positions may have shifted)
    update_has_block_positions(conn, page_id, blocks)

    # 9. Write event log
    events = build_events(new_ids, modified_ids, deleted_ids, incoming, existing, ...)
    append_events(events)

    return IngestResult(
        page_id=page_id,
        inserted=list(new_ids),
        updated=list(modified_ids),
        deleted=list(deleted_ids),
        unchanged=list(unchanged_ids),
    )
```

**Verification:** Run TC-D1 through TC-D6 (Step 11).

---

### Step 7 — Implement `src/tools/query_block_ref.py`

```python
def query_block_ref(ref: str, conn, event_log_path: str = EVENT_LOG_PATH) -> dict:
    """
    Resolve a block reference of the form {#id} or {#id:hash}.
    Returns dict with keys: block_id, text, resolved ("graph" | "history"), hash.
    On not-found: {"error": "not_found", "block_id": ..., "ref": ...}
    """
    ref = ref.strip().lstrip("{#").rstrip("}")
    if ":" in ref:
        block_id, requested_hash = ref.split(":", 1)
    else:
        block_id, requested_hash = ref, None

    # Query graph
    r = conn.execute("MATCH (b:Block {id: $id}) RETURN b.text, b.hash",
                     {"id": block_id})
    if r.has_next():
        text, current_hash = r.get_next()
        if requested_hash is None or current_hash == requested_hash[:16]:
            return {"block_id": block_id, "text": text,
                    "hash": current_hash, "resolved": "graph"}
        # Hash mismatch — fall through to event log

    # Fall back to event log
    if os.path.exists(event_log_path):
        table = pq.read_table(event_log_path,
                              filters=[("block_id", "=", block_id)])
        if requested_hash:
            mask = [row["hash"].startswith(requested_hash[:16])
                    for row in table.to_pylist()]
            rows = [r for r, m in zip(table.to_pylist(), mask) if m]
        else:
            rows = table.to_pylist()

        if rows:
            # Return the most recent matching event
            rows.sort(key=lambda r: r["timestamp"], reverse=True)
            row = rows[0]
            return {"block_id": block_id, "text": row["text"],
                    "hash": row["hash"][:16], "resolved": "history"}

    return {"error": "not_found", "block_id": block_id, "ref": ref}
```

**Verification:** Run TC-R1 through TC-R5 (Step 12).

---

### Step 8 — Write `tests/test_delta/test_delta_ingestion.py`

Implement TC-D1 through TC-D6 as described in Section 8.

Each test case:
1. Wipes the LadybugDB store to a clean state.
2. Ingests the relevant fixture files.
3. Asserts the `IngestResult` fields.
4. Runs a confirming Cypher query against the graph.

Pattern (mirrors `test_roundtrip.py`):
```python
def test_TC_D1_unchanged_produces_no_writes():
    reset_db()
    r1 = ingest_page("tests/test_delta/fixtures/v1_simple.dj", "human:test")
    r2 = ingest_page("tests/test_delta/fixtures/v1_simple.dj", "human:test")
    assert r2.inserted == []
    assert r2.updated  == []
    assert r2.deleted  == []
    assert len(r2.unchanged) == 5
    print("TC-D1: PASS")
```

---

### Step 9 — Write `tests/test_delta/test_event_log.py`

Implement TC-E1 through TC-E4 as described in Section 8.

Each test:
1. Removes the event log file before starting.
2. Ingests fixture files.
3. Reads the Parquet event log directly with `pyarrow.parquet.read_table()`.
4. Asserts row counts and column values.

---

### Step 10 — Write `tests/test_delta/test_ref_resolution.py`

Implement TC-R1 through TC-R5 as described in Section 8.

---

### Step 11 — Run delta ingestion tests

```bash
python tests/test_delta/test_delta_ingestion.py
```

Expected output:
```
TC-D1: PASS
TC-D2: PASS
TC-D3: PASS
TC-D4: PASS
TC-D5: PASS
TC-D6: PASS
All delta ingestion tests PASSED.
```

---

### Step 12 — Run reference resolution tests

```bash
python tests/test_delta/test_ref_resolution.py
```

Expected output:
```
TC-R1: PASS
TC-R2: PASS
TC-R3: PASS  ← the annotation durability guarantee
TC-R4: PASS
TC-R5: PASS
All reference resolution tests PASSED.
```

---

### Step 13 — Run event log tests

```bash
python tests/test_delta/test_event_log.py
```

Expected output:
```
TC-E1: PASS
TC-E2: PASS
TC-E3: PASS
TC-E4: PASS
All event log tests PASSED.
```

---

### Step 14 — Phase 02 regression

Confirm that the refactored `ingest_page()` does not break the Phase 02 test cases:

```bash
python tests/test_03/test_roundtrip.py
```

All existing roundtrip tests must still pass.

---

### Step 15 — Update README.md risks

After all tests pass:
- Mark Risk #7 as **Resolved** with a pointer to this document.
- Mark Risk #11 as **Resolved** with a pointer to this document.

---

### Implementation order

```
Step 1  (fixtures)      — no code dependency, do first
Step 2  (block_hash)    — independent
Step 3  (ingest_result) — independent
Step 4  (event_log)     — depends on Step 3
Step 5  (DB schema)     — independent
Step 6  (ingest_page)   — depends on Steps 2, 3, 4, 5
Step 7  (query_block_ref) — depends on Step 4
Steps 8-10 (test files) — can be written alongside Steps 2-7
Step 11 (run delta tests) — depends on Step 6, 8
Step 12 (run ref tests)   — depends on Step 7, 10
Step 13 (run log tests)   — depends on Step 4, 9
Step 14 (regression)      — depends on Step 6
Step 15 (README update)   — last
```

Steps 1, 2, 3, 5 can be done in parallel. Step 4 needs Step 3. Step 6 needs 2, 3, 4, 5.

---

## 10. What This Document Does NOT Cover

- **Schema migrations for existing live data** — this design is implemented before any production
  data exists. The migration strategy remains "wipe and rebuild" through Phase 04.
- **Multi-writer concurrency** — addressed separately in Risk #10. The event log append is not
  concurrency-safe for simultaneous writers. A single writer is assumed.
- **Event log compaction** — for very large corpora (100k+ events), the read-then-rewrite append
  strategy in `event_log.py` will become slow. Segmented log files are the natural next step.
- **HTML renderer for compound references** — the `data-hash` attribute in HTML output and the
  copy-to-clipboard UI are rendering concerns for the static site generator (not yet designed).
  The contract is defined here; the renderer implements it.
- **Phase 06 tool registration** — `query_block_ref` is implemented here but registered as an
  LLM-callable tool in Phase 06 alongside the other six tools.
- **TC-X1 through TC-X3 (enrichment contract tests)** — these require Phase 05 mock enrichment
  to be in place. They are defined here for completeness but are executed as part of the Phase 05
  implementation plan.

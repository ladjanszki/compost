# TODO

Tasks are grouped by test. Each test builds on the previous one.

---

## Test 00 — Djot → JSONL ingestion pipeline

Goal: ingest a single Djot document into `blocks.jsonl` and `pages.jsonl`.

- [x] Write v1 system design doc (`architecture/design-docs/agentic_local_knowledge_store_v1_design_v4.dj`)
- [x] Write Test 00 design doc (`architecture/design-docs/test_00_design.md`)
- [x] Write Test 00 implementation plan (`architecture/design-docs/test_00_implementation_plan.md`)
- [x] Review Test 00 docs and resolve all issues (`architecture/design-docs/test_00_review.md`)
- [x] Create repo directory structure (`src/ingest/`, `tests/test_00/`, `workspace/store/`)
- [x] Create `environment.yml` and `knowledge-graph` conda environment
- [x] Save corrected test input (`tests/test_00/test_00.dj`)
- [x] Implement `src/ingest/pandoc_ast.py` — run pandoc, return AST dict
- [x] Implement `src/ingest/inline_reconstruct.py` — reconstruct Djot inline markup from AST nodes
- [x] Implement `src/ingest/block_schema.py` — build `block.v1` and `page.v1` records, UUIDv7 IDs, SHA-256 hash
- [x] Implement `src/ingest/jsonl_writer.py` — append records to JSONL with `fcntl.flock`
- [x] Implement `src/ingest/ast_walker.py` — walk Pandoc AST, emit `(type, content)` tuples
- [x] Implement `src/ingest/ingest_page.py` — top-level pipeline function
- [x] End-to-end verification: 9 blocks, correct types and content, valid `page.v1` record

---

## Test 01 — JSONL → Kuzu ingestion

Goal: load the JSONL output from ingestion into a Kuzu graph database as a derived index.

- [x] Write Test 01 design doc (`architecture/design-docs/test_01_design.md`)
- [x] Write Test 01 implementation plan (`architecture/design-docs/test_01_implementation_plan.md`)
- [x] Review Test 01 docs and resolve all issues (`architecture/design-docs/test_01_review.md`)
- [x] Add 6 extra test Djot files in `tests/test_00/extra_inputs/` (created by reviewer)
- [x] Add `kuzu` and `pyarrow` to `environment.yml` and update conda environment
- [x] Create `src/index/` directory structure
- [x] Implement `src/index/kuzu_schema.py` — create `Block`, `Page`, `HAS_BLOCK` tables
- [x] Implement `src/index/jsonl_to_parquet.py` — flatten JSONL to Parquet for `COPY FROM`
- [x] Implement `src/index/kuzu_loader.py` — bulk load Parquet into Kuzu
- [x] Implement `src/index/build_index.py` — top-level pipeline: JSONL → Parquet → Kuzu
- [x] Ingest all 7 test files (47 blocks, 7 pages)
- [x] End-to-end verification: 47 Block nodes, 7 Page nodes, 47 HAS_BLOCK edges
- [x] Spot-check: ordered list items have `style="ordered"` in Kuzu
- [x] Spot-check: multi-section page (`deep_headings`) returns blocks in correct positional order

---

## Backlog (future tests, not yet planned)

- [ ] Test 02 — Explicit `{#id}` handling: ingest a Djot file with explicit block IDs; verify IDs are preserved from Djot attributes, not auto-generated
- [ ] Test 03 — Block versioning and change detection: re-ingest a modified Djot file; verify new versions are created for changed blocks and unchanged blocks are skipped (hash match)
- [ ] Test 04 — Additional block types: `code`, `quote`, `table`, `image`, `math`, `div` (Djot `:::`)
- [ ] Test 05 — Conversation ingestion: parse a conversation `.dj` file with YAML frontmatter into `conversations.jsonl`
- [ ] Test 06 — SQLite index: build `block_latest`, `attachment_index`, `mention_index` from JSONL
- [ ] Test 07 — HTML rendering: generate a static HTML page from a page record, with block IDs embedded in the output
- [ ] Test 08 — CLI tool wrappers: `ingest_page`, `new_conversation`, `add_message`, `render`, `rollback` as CLI commands

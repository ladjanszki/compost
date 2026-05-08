# CHANGELOG

## Phase 01 — 2026-05-08

JSONL → Kuzu graph index. Implemented `src/index/` module: `kuzu_schema.py`, `jsonl_to_parquet.py`, `kuzu_loader.py`, `build_index.py`. Loads blocks and pages from JSONL into Kuzu via Parquet COPY FROM. Full rebuild on each run. Verified: 47 Block nodes, 7 Page nodes, 47 HAS_BLOCK edges from the test corpus.

Dependencies added: `kuzu`, `pyarrow`.

## Phase 00 — 2026-05-08

Djot → JSONL ingestion pipeline. Implemented `src/ingest/` module: pandoc-based parser, AST walker, inline reconstructor, block schema builder, JSONL writer. Ingests a Djot file into `blocks.jsonl` + `pages.jsonl`. Handles heading, paragraph, list_item (ordered + unordered). Verified: 9 blocks from test file, 47 blocks from full test corpus (7 files).

Dependencies: `python 3.12`, `uuid6`, `pandoc` (system).

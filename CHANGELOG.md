# CHANGELOG

## Phase 02 & 03 — 2026-05-16

Implemented Phase 02: Rewrote ingestion to bypass Pandoc and use native `djot.js`. Dropped JSONL intermediate representation to write blocks directly into Parquet files, which are immediately loaded into LadybugDB during `ingest_page()`. Extended Block schema with `language` field and added `LINKS_TO` relationships for explicit cross-links. Re-wrote `inline_reconstruct.py` and `ast_walker.py` against the native AST.

Implemented Phase 03: Built Djot rendering via `blocks_to_djot.py` that formats structured Block dictionaries back into raw Djot text. Added a roundtrip validation harness (`test_roundtrip.py`) validating `Djot -> Blocks -> Djot` without data loss (whitespace-normalized, structural fidelity). Passed verification for 31 block types. Achieved ~4.6x token reduction compared to raw JSON block representation.

## 2026-05-10 — Kuzu to LadybugDB Migration
Replaced Kuzu with LadybugDB (community fork) as the embedded graph database, following
Apple's acquisition and archiving of the Kuzu repository. Renamed `kuzu_schema.py` →
`ladybug_schema.py`, `kuzu_loader.py` → `ladybug_loader.py`. Updated all design docs,
implementation plans, and workspace paths. Python package changed from `kuzu` to
`real-ladybug==0.15.3`. Import alias: `import real_ladybug as lb`.
LadybugDB now supports `OPTIONAL MATCH` — constraint removed from Phase 07 design and
implementation plans. Added defensive parsing guidance for `SHOW_TABLES()` output change.
No data migration was needed (no existing database on disk).

## Phase 01 — 2026-05-08

JSONL → LadybugDB graph index. Implemented `src/index/` module: `ladybug_schema.py`, `jsonl_to_parquet.py`, `ladybug_loader.py`, `build_index.py`. Loads blocks and pages from JSONL into LadybugDB via Parquet COPY FROM. Full rebuild on each run. Verified: 47 Block nodes, 7 Page nodes, 47 HAS_BLOCK edges from the test corpus.

Dependencies added: `ladybug`, `pyarrow`.

## Phase 00 — 2026-05-08

Djot → JSONL ingestion pipeline. Implemented `src/ingest/` module: pandoc-based parser, AST walker, inline reconstructor, block schema builder, JSONL writer. Ingests a Djot file into `blocks.jsonl` + `pages.jsonl`. Handles heading, paragraph, list_item (ordered + unordered). Verified: 9 blocks from test file, 47 blocks from full test corpus (7 files).

Dependencies: `python 3.12`, `uuid6`, `pandoc` (system).

# CHANGELOG

This file overarches versions. Entries below the `v0` marker describe the
LadybugDB-centric architecture that `v0` closes out.

## v0.1 — 2026-08-04 — the mechanical loop

The write → submit → canonize → read → reference → submit loop works end to
end, with no LLM anywhere in it. Wiki generation is still unbuilt.

**New**

- `kg` on PATH via `pip install -e .`, working from any directory. The base is
  found via `--root`, `$KG_HOME`, or a `.kg` marker in any parent.
- `kg init` creates a base anywhere, which defers the tool/data split to a
  runtime choice rather than an architectural commitment.
- `kg new` opens `$EDITOR` and submits on exit — never on save, so saving
  mid-thought stays free.
- Static site with click-to-copy. Click a block for `{#uuid:hash}`,
  shift-click for `{#uuid:hash+++}`. Holding Shift while hovering highlights
  the subtree, so what will be copied is visible before committing.
- Backlinks: a note referencing a block appears as "Referenced by" on the note
  containing it. Computed at render time, so it works retroactively.
- Reverse-chronological index, dated from the UUIDv7 timestamp.

**Fixed — correctness**

- `loosen()` moved into canonization. Djot drops a list item's id in HTML
  unless the list is loose, so every list item and todo was unaddressable.
  Since notes are immutable this could not have been repaired later: notes
  canonized before the fix would have been permanently degraded.
- Backlink scanning reads parsed block text rather than the raw file. Pandoc
  escapes references on disk as `\{#uuid:hash\}`, so scanning the file found
  nothing.

**Docs**

- `README.md` restored — the repo had no entry point since the cleanup.
- `DEVELOPMENT.md` added: architecture, the non-obvious pandoc and djot
  behaviours, the sabotage-verification practice, and where the next work is.

## 2026-08-03 — Architecture pivot and repository cleanup

**Tagged `v0-graph-architecture`.** Everything removed in this cleanup remains
reachable there (`git show v0-graph-architecture:<path>`).

The product changed shape after a workflow interview (`my-workflow.md`,
`mvp-interview.md`). The new design is in `mvp-design.md`:

- **`.dj` files in git are the source of truth.** LadybugDB is no longer
  canonical storage. Any graph that returns will be a derived, disposable cache.
- **Notes are immutable and human-written; wiki pages are agent-written.** The
  human never writes the wiki, agents never write notes.
- **Lineage replaces semantic extraction.** Every wiki block cites the note or
  source block it derives from. Recorded at generation time rather than
  extracted afterwards — free, exact, and it doubles as the anti-slop
  mechanism: a block with nothing to cite is invalid.
- **Deleted, not deferred:** Phase 05 (entity/relation extraction), Phase 07
  (LLM-to-Cypher), temporal quadruplets, `Annotation` nodes, the Parquet event
  log (git supersedes it), and HITL diff approval.
- **Retained:** `architecture/delta_ingestion_and_block_versioning.md`. Its
  content-hash and delta mechanisms carry over unchanged; the subject moves
  from human-edited notes to agent-regenerated wiki pages.

Removed 47 files across two commits (superseded docs, then the LadybugDB
ingestion path). ~360 LOC of parsing and rendering carried forward.

**Defects found during the carry-over audit**, both on the MVP critical path
and neither caught by the existing roundtrip test:

1. `ast_walker.py` silently drops `task_list` / `task_list_item`. Djot supports
   them natively (`checkbox: checked|unchecked`); the walker has no branch, so
   todos vanish with no error.
2. Nested list items are emitted *before* their parent, and nesting depth is
   discarded, so `- a` / `- b` (nested) yields `[b, a]` flattened to one level.

*Correction:* an earlier version of this entry claimed nested items were
embedded as raw markup in the parent block. That was wrong. The confusion came
from a probe written without blank lines — **djot requires a blank line before
a nested list**; without one djot itself (not the walker) parses the child as
lazy continuation text of the parent paragraph. That is spec behaviour and a
*canonization* concern, since hand-written notes rarely include those blank
lines. The walker defect is the ordering and depth loss described above.

`test_roundtrip.py` detects none of it: a dropped element is absent from both
sides of the comparison, and reordering survives re-parsing unchanged. The
Phase 03 claim of "no data loss, 31 block types" holds only for the properties
the test actually compares.

---

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

# Phase 05 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Phase 05. It assumes the reader has read `phase_05_design.md`.

The goal of Phase 05 is:

```
LadybugDB Blocks  →  LLM extraction  →  Parquet files  →  LadybugDB (Entities + Relations + Mentions)
```

---

## 2. Prerequisites

- [ ] Phase 02 (full djot ingestion) is complete.
- [ ] Phase 03 (roundtrip verification) is passing.
- [ ] `OPENAI_API_KEY` is set (or mock extractor used).

---

## 3. Steps

### Step 1 — Update environment, create directories

Add `openai`. Create `src/enrich/`, `tests/test_05/corpus/`.

### Step 2 — Create geography corpus (5 djot files)

Same content as previously defined: europe.dj, danube.dj, germany.dj, austria.dj, hungary.dj.

### Step 3 — Ingest corpus

Ingest all 5 files through Phase 02 pipeline.

### Step 4 — Implement `entity_schema.py`

`make_entity()`, `make_relation()`, `entity_id_from_name()`.

### Step 5 — Implement `mock_extractor.py`

Regex-based: capitalized phrases → entities. No relations.

### Step 6 — Implement `extractor.py`

LLM-based: structured JSON output. Entity + relation extraction per block.

### Step 7 — Implement `enrich_blocks.py`

Top-level pipeline: iterate blocks, call extractor, write JSONL, handle dedup.

### Step 8 — Update LadybugDB schema and index builder

Add Entity node, MENTIONS edge, RELATES_TO edge. Update parquet generation and loading.

### Step 9 — Mock verification

Enrich with mock → build index → count entities and mentions in LadybugDB.

### Step 10 — LLM verification

Enrich with real LLM → verify cross-document queries work.

---

## 4. Implementation order

```
Steps 1-3  (setup + corpus)       — independent
Steps 4-5  (schema + mock)        — independent
Step 6     (LLM extractor)        — depends on Step 4
Step 7     (pipeline)             — depends on Steps 4, 5, 6
Step 8     (LadybugDB updates)         — independent of Steps 4-7
Steps 9-10 (verification)        — depends on Steps 7, 8
```

---

## 5. What Phase 05 does NOT validate

- Vector embeddings (separate concern, separate index).
- Coreference resolution.
- Incremental enrichment (always full rebuild).
- Multi-block context for extraction.

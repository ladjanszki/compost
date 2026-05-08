# Knowledge Graph — Agentic Local Knowledge Store

## What this project is

A local-first, block-based knowledge store with semantic enrichment and LLM-facing tool interface. Documents are authored as Djot files, ingested into an embedded Kuzu graph database via Parquet bulk loading, enriched with entity and relation extraction, and queried through tool functions that return readable Djot text.

The system is designed to serve as a context provider for LLM agents — the Kuzu graph handles scalable traversal and retrieval, the tools return token-efficient readable text, and the LLM reasons over the assembled context.

### Core loop

```
Source documents (.dj) → Djot AST → Parquet (memory/temp) → Kuzu Graph Database (canonical)
                                                                 ↓
                      LLM answer  ←  Djot context  ←  tool call  ←  LLM question
```

### Design principles

- **Canonical storage is Kuzu** — Kuzu acts as our canonical graph database. It handles complex relationships and concurrent access better than file locks on JSON files.
- **Parquet for Ingestion** — Instead of appending to JSONL, Djot documents are parsed into an AST, flattened into Parquet formats, and efficiently bulk-loaded (`COPY FROM`) into Kuzu.
- **Djot as authoring and reading format** — formally parseable, close to Markdown, native block-level `{#id}` attributes.
- **Tools return Djot, not JSON** — token-efficient, attention-friendly, LLMs parse it natively.
- **Flat block list with implicit hierarchy** — heading levels encode structure, no tree in storage.

---

## Project status

| Phase | Description | Status |
|-------|-------------|--------|
| 00 | Djot → blocks → JSONL (Deprecated proof of concept) | Historical |
| 01 | JSONL → Kuzu structural index (Deprecated proof of concept) | Historical |
| 02 | Switch to djot.js parser + Djot → Parquet → Kuzu ingestion | Pending |
| 03 | Kuzu → Djot renderer + internal roundtrip verification | Designed |
| 04 | Markdown → Djot conversion via pandoc (preprocessing) | Designed |
| 05 | Semantic enrichment (entities, relations via LLM) | Designed |
| 06 | Template query tools (LLM-callable functions) | Designed |
| 07 | LLM-to-Cypher (open-ended graph queries) | Designed |

**Usable system milestone**: after Phase 06. At that point, tools return rendered Djot context from the enriched graph.

---

## Architecture overview

### Storage layers

```
Djot (.dj files)        — authoring surface for humans and agents
Parquet files (temp)    — intermediate batching format for ingestion
Kuzu graph database     — canonical storage (source of truth) for all nodes and edges
```

The canonical data lives in `workspace/store/kuzu/`. The graph is populated by `ingest_page()`.

### Object kinds

| Kind | Storage | Description |
|------|---------|-------------|
| `Block` | Kuzu Node | Versioned content unit. Has stable ID, type, content, hash, author, timestamp. |
| `Page` | Kuzu Node | Document — ordered flat list of block IDs. |
| `Entity` | Kuzu Node | Canonical concept (person, place, etc.) extracted from text. (Phase 04) |
| `Relation`| Kuzu Edge | Semantic triple between entities. (Phase 04) |

### Kuzu graph schema (full, after Phase 04)

```
Nodes:  Block, Page, Entity
Edges:  HAS_BLOCK (Page→Block), LINKS_TO (Block→Page),
        MENTIONS (Block→Entity), RELATES_TO (Entity→Entity)
```

### Tool interface (Phase 06)

Six tool functions, callable by any LLM via tool/function calling:

| Tool | Purpose | Returns |
|------|---------|---------|
| `query_entity` | Entity page: mentions, relationships, context | Djot |
| `query_connection` | How two entities relate | Djot |
| `query_page` | Full page content | Djot |
| `search_mentions` | Find blocks mentioning a term | Djot |
| `query_cypher` | Run raw Cypher | JSON table or Djot |
| `ask_graph` | Natural language → auto-generated Cypher | Djot |

Tools are plain Python functions with JSON Schema parameter definitions. Serve them over MCP, OpenAI function calling, or any protocol.

---

## Repository layout

```
knowledge-graph/
  README.md
  TODO.md
  environment.yml

  architecture/
    phase_02_design.md + phase_02_implementation_plan.md
    phase_03_design.md + phase_03_implementation_plan.md
    phase_04_design.md + phase_04_implementation_plan.md
    phase_05_design.md + phase_05_implementation_plan.md
    phase_06_design.md + phase_06_implementation_plan.md
    phase_07_design.md + phase_07_implementation_plan.md
    OVERALL_ARCHITECTURE_REVIEW_PRE_IMPLEMENTATION.md

  src/
    ingest/          ← Phase 02: Djot → Parquet → Kuzu
    index/           ← Deprecated (merged into ingest logic)
    render/          ← Phase 03: Kuzu → Djot text (roundtrip verified)
    convert/         ← Phase 04: Markdown → Djot via pandoc (planned)
    enrich/          ← Phase 05: Entity/relation extraction (planned)
    tools/           ← Phase 06: LLM-callable query functions (planned)

  tests/
    test_02/         ← Phase 02 test fixtures

  workspace/
    store/           
      kuzu/          ← Canonical graph database storage
```

---

## Environment setup

Requires:
- `conda` (miniconda or anaconda)
- `pandoc` 3.x (system install — used for markdown → djot conversion in Phase 04)
- `node` v18+ and `npx` (system install — used for djot.js parser from Phase 02 onward)

```bash
conda env create -f environment.yml
conda activate knowledge-graph
```

Verify:
```bash
python -c "import uuid6; print(uuid6.uuid7())"
python -c "import kuzu; print(kuzu.__version__)"
pandoc --version
node --version
npx @djot/djot --version
```

If djot.js is not available, install it globally:
```bash
npm install -g @djot/djot
```

---

## Development workflow

1. Read the design doc for the next phase (`architecture/phase_XX_design.md`).
2. Follow the implementation plan step by step (`architecture/phase_XX_implementation_plan.md`).
3. Each step has a verification check — confirm it passes before moving to the next.
4. **Commit after each step.** Each step in an implementation plan should result in a git commit. The commit message should reference the phase and step (e.g. `phase-02: step 3 — rewrite inline_reconstruct`).
5. **Commit at minimum after each phase.** If step-level commits feel too granular, at minimum commit after completing an entire phase with all verifications passing.
6. Test fixtures are added incrementally in `tests/` as each phase introduces new capabilities.
7. **Update CHANGELOG.md** after completing each phase. Record what was implemented, what changed, and any deviations from the design doc.

### CHANGELOG policy

`CHANGELOG.md` is maintained at the repo root. After each phase is complete:
- Add a dated entry with the phase number and a 2-3 sentence summary.
- List any deviations from the design doc (decisions made during implementation).
- List any new system dependencies introduced.

The CHANGELOG serves as a human-readable history for someone picking up the project. It is NOT auto-generated — it is written by the implementor after each phase.

---

## Design decisions log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Authoring format | Djot | Formally parseable, native `{#id}` attributes, unambiguous |
| Canonical storage | Kuzu | Embedded graph DB replaces JSONL to solve concurrency and enable Cypher traversal |
| Ingestion format | Parquet | AST is flattened to Parquet for fast batch `COPY FROM` loading into Kuzu |
| Block identity | UUIDv7 | Sortable by creation time, globally unique |
| Page structure | Flat `root` array | Heading levels encode hierarchy, no tree needed |
| LLM context format | Rendered Djot | ~5x fewer tokens than JSON, LLMs parse natively |
| Tool interface | Plain Python functions | Protocol-agnostic, serve over MCP/OpenAI/etc. |
| Enrichment | LLM-based extraction | Entity + relation extraction per block |

---

## Key dependencies

| Dependency | Role | Phase |
|------------|------|-------|
| `python 3.12` | All tooling | 00+ |
| `uuid6` | UUIDv7 generation | 00+ |
| `kuzu` | Embedded canonical graph database | 02+ |
| `pyarrow` | Parquet intermediary for Kuzu COPY FROM | 02+ |
| `djot.js` | Reference Djot AST parser | 02+ |
| `pandoc` 3.x | Markdown parsing | 04+ |
| `beautifulsoup4` | HTML normalization for roundtrip verification | 03 |
| `openai` | LLM extraction + Cypher generation | 04, 07 |

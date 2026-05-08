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

---

## Known risks, limitations & open questions

This section is the **single source of truth** for all known risks, concerns, architectural limitations, and open questions. Nothing should be left undocumented elsewhere. If a risk is discovered during implementation, it is added here.

### Platform & environment

| # | Severity | Risk | Mitigation |
|---|----------|------|------------|
| 1 | Low | **Unix-only assumption** — `jsonl_writer.py` (Phase 00/01, deprecated) uses `fcntl` which is POSIX-only. Future code must not introduce platform-specific imports without documenting it. | Document as Unix/macOS only. Windows is not a target. |
| 2 | Medium | **No Python packaging** — `src/` is not an installable package. All scripts assume CWD is the repo root. `from src.ingest.xxx import` fails if run from a subdirectory. | Either add a `pyproject.toml` with editable install, or document "always run from repo root" as a hard requirement. |
| 3 | Medium | **No version pinning on `@djot/djot`** — `npx @djot/djot` resolves to whatever version npm fetches. A breaking release of djot.js could silently change AST structure. | Pin the version in subprocess calls: `npx @djot/djot@0.3.1 --to ast`. Document the expected version. |
| 4 | Medium | **Kuzu is pre-1.0** — The `environment.yml` does not pin a Kuzu version. Kuzu has had breaking API changes between minor versions (connection API, COPY FROM syntax, Cypher dialect). | Pin in `environment.yml`: `kuzu==0.x.y`. Test against that specific version. |
| 5 | Low | **Node.js is a silent system dependency** — If `node`/`npx` is missing, the error message is a generic `RuntimeError`. No pre-flight check exists. | Phase 02 Step 1 is a manual verification. Consider adding a startup check in `djot_ast.py` with a clear error message. |

### Ingestion pipeline

| # | Severity | Risk | Mitigation |
|---|----------|------|------------|
| 6 | Medium | **`npx` subprocess cold-start latency** — Each `get_ast()` call spawns a new Node.js process (~100-300ms). For batch ingestion of hundreds of files, this compounds to minutes of pure overhead. | Acceptable for single-file. For batch: implement a persistent Node.js worker (stdin/stdout JSON-RPC), or wait for a native Python djot parser. Not blocking for Phase 02. |
| 7 | Medium | **No incremental re-ingestion** — `ingest_page()` does full-replace. Re-ingesting a corpus means wiping the entire Kuzu database and rebuilding from scratch. There is no content-hash diffing to skip unchanged documents. | Acceptable for early phases. Becomes a problem once Phase 05 enrichment data (expensive LLM calls) lives in the graph. Design a delta-detection mechanism before Phase 05 goes to production scale. |
| 8 | Medium | **No error recovery / rollback** — If ingestion fails mid-way (e.g., Parquet written but Kuzu COPY fails), partial state may remain. There is no transaction wrapper around the full ingest-page operation. | Wrap the Kuzu ingestion in a transaction. On failure, roll back. Alternatively, use temp directory for Parquet and only commit on success. |
| 9 | Low | **Backward-incompatible API change in Phase 02** — `reconstruct()` return type changes from `str` to `(str, list[dict])`. Any code calling the old signature breaks. | Phase 00/01 code is deprecated. No external consumers. Document the break in CHANGELOG. |

### Kuzu / graph database

| # | Severity | Risk | Mitigation |
|---|----------|------|------------|
| 10 | Medium | **Write concurrency limits** — Kuzu (embedded mode) enforces single-writer semantics. If multiple agents attempt simultaneous writes, they will block or error. | For the single-agent use case this is fine. For multi-agent: introduce a write queue (Python `asyncio.Lock` or a dedicated writer process). Document that concurrent writes are not supported out of the box. |
| 11 | **High** | **Block versioning in a graph DB** — The design principle is "no content is ever destroyed" (immutable, versioned blocks). But the Kuzu schema uses `id STRING PRIMARY KEY` with no version column. Updating a block either requires a new ID (losing identity) or an upsert (losing history). | Must be resolved before any "edit" workflow is implemented. Options: (a) composite key `(id, version)`, (b) append-only with `superseded_by` edges, (c) accept that ingestion is always full-rebuild (current approach). Current design defers this — acceptable for now, but this is the single biggest architectural debt. |
| 12 | **High** | **Schema migration path** — Each phase adds tables/columns (Phase 02: `language`, `LINKS_TO`; Phase 05: `Entity`, `MENTIONS`, `RELATES_TO`). The only migration strategy is "wipe and rebuild." This breaks once enrichment data (Phase 05) is expensive to regenerate. | Acceptable through Phase 04 (cheap to rebuild). Before Phase 05 goes to production: design a migration strategy (Kuzu DDL `ALTER TABLE` or versioned schema scripts). |
| 13 | Low | **Kuzu does NOT support OPTIONAL MATCH** — Phase 07 Cypher generation must avoid this pattern. The LLM may generate it anyway since it's common in Neo4j examples on the internet. | Documented in Phase 07 prompt instructions. The retry loop should catch syntax errors. Add explicit "DO NOT use OPTIONAL MATCH" to the few-shot prompt. |
| 14 | Low | **Kuzu path syntax differs from Neo4j** — Complex path queries (variable-length paths, shortest path) use different syntax. LLM-generated Cypher may fail on these. | Documented as a known limitation in Phase 07. The 6/8 test battery accounts for this. |

### LLM dependencies (Phase 05, 07)

| # | Severity | Risk | Mitigation |
|---|----------|------|------------|
| 15 | **High** | **Cost at scale** — Phase 05 entity extraction calls the LLM once per eligible block. A 500-block corpus = 500 API calls. No batching, budgeting, or cost estimation is designed. | Add a `--dry-run` flag that estimates cost before running. Implement batching (multiple blocks per prompt where feasible). Add a cost cap or confirmation prompt. |
| 16 | Medium | **Rate limiting** — No retry/backoff logic for OpenAI API rate limits (429 responses). A large enrichment run will hit rate limits and crash. | Add exponential backoff with jitter. Consider `tenacity` or similar retry library. |
| 17 | Low | **Model lock-in** — Phase 07 is tested only with `gpt-4o-mini`. Other models (Claude, local LLMs) may need different prompts. The system assumes OpenAI-compatible API. | The `openai` library is used directly. For other providers: abstract behind a thin interface. Not blocking, but note that prompt tuning is model-specific. |
| 18 | Low | **No caching of LLM results** — Repeated enrichment of the same block re-calls the LLM. Repeated similar questions in Phase 07 re-generate Cypher each time. | Acceptable for now. Future optimization: hash-based cache for enrichment, query cache for Cypher generation. |

### Testing & quality

| # | Severity | Risk | Mitigation |
|---|----------|------|------------|
| 19 | Medium | **No test harness** — There is no `pytest` dependency, no `conftest.py`, no test runner, no CI. Tests are ad-hoc Python scripts embedded in implementation plans. Regression detection is manual. | Add `pytest` to `environment.yml`. Convert verification scripts to proper test functions in `tests/`. This should happen alongside Phase 02. |
| 20 | Low | **No linting or formatting** — No `ruff`, `black`, `mypy`, or type checking configured. Code style consistency is not enforced. | Not blocking, but recommended: add `ruff` config for basic linting. |

### Scope & design boundaries (explicitly out of scope)

These are **not risks** but documented boundaries — things the system intentionally does not do:

- **Vector embeddings / semantic search** — separate concern, separate index (noted in Phase 05).
- **Coreference resolution** — not attempted in entity extraction.
- **Transport/serving layer** — tools are Python functions; MCP/HTTP wrappers are the caller's responsibility.
- **LLM orchestration** — calling the LLM and dispatching tool_calls is external to this system.
- **Automatic tool routing** — deciding which tool to call is the LLM's job based on tool descriptions.
- **Multi-block context for extraction** — Phase 05 extracts per-block; cross-block reasoning is not attempted.
- **Performance at millions of blocks** — designed for thousands; optimization deferred.

---

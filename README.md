# Knowledge Graph — Agentic Local Knowledge Store

## What this project is

A local-first, block-based knowledge store with semantic enrichment and LLM-facing tool interface. Documents are ingested as versioned blocks, linked in a graph database, enriched with entity and relation extraction, and queried through tool functions that return readable Djot text.

The system is designed to serve as a context provider for LLM agents — the graph handles retrieval, the tools return token-efficient readable text, and the LLM reasons over the assembled context.

### Core loop

```
Source documents (.md/.dj)  →  blocks (JSONL)  →  Kuzu graph (structural + semantic edges)
                                                           ↓
                      LLM answer  ←  Djot context  ←  tool call  ←  LLM question
```

### Design principles

- **Canonical storage is JSONL** — human-readable, append-only, git-friendly. Everything else is a derived projection.
- **Djot as authoring and reading format** — formally parseable, close to Markdown, native block-level `{#id}` attributes.
- **Graph index is derived** — Kuzu can be deleted and rebuilt from JSONL at any time.
- **Tools return Djot, not JSON** — token-efficient, attention-friendly, LLMs parse it natively.
- **Flat block list with implicit hierarchy** — heading levels encode structure, no tree in storage.

---

## Project status

| Phase | Description | Status |
|-------|-------------|--------|
| 00 | Djot → blocks → JSONL (subset of djot) | Done |
| 01 | JSONL → Kuzu structural index | Done |
| 02 | Switch to djot.js parser + full Djot support + LINKS_TO edges | Designed |
| 03 | Block → Djot renderer + internal roundtrip verification | Designed |
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
JSONL files             — canonical storage (source of truth)
Kuzu graph database     — derived index for structural + semantic queries
```

The canonical data lives in `workspace/store/*.jsonl`. The Kuzu index is rebuilt by `build_index()`.

### Object kinds

| Kind | Storage | Description |
|------|---------|-------------|
| `block.v1` | `blocks.jsonl` | Versioned content unit. Has stable ID, type, content, hash, author, timestamp. |
| `page.v1` | `pages.jsonl` | Document — ordered flat list of block IDs. |
| `entity.v1` | `entities.jsonl` | Canonical concept (person, place, etc.) extracted from text. (Phase 04) |
| `relation.v1` | `relations.jsonl` | Semantic triple between entities. (Phase 04) |

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
    ARCHITECT_REVIEW.md

  src/
    ingest/          ← Phase 00+02: Djot → blocks → JSONL (djot.js parser from Phase 02)
    index/           ← Phase 01: JSONL → Kuzu
    render/          ← Phase 03: Blocks → Djot text (roundtrip verified)
    convert/         ← Phase 04: Markdown → Djot via pandoc (planned)
    enrich/          ← Phase 05: Entity/relation extraction (planned)
    tools/           ← Phase 06: LLM-callable query functions (planned)

  tests/
    test_00/         ← Phase 00 test fixtures (Djot input files)
      test_00.dj
      extra_inputs/

  workspace/
    store/           ← Canonical JSONL storage
      blocks.jsonl
      pages.jsonl
    indexes/
      kuzu/          ← Derived graph index (excluded from git)
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

## Running Phase 00 (Djot → JSONL)

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

## Running Phase 01 (JSONL → Kuzu)

```bash
python -c "
from src.index.build_index import build_index
build_index()
"
```

---

## Development workflow

1. Read the design doc for the next phase (`architecture/phase_XX_design.md`).
2. Follow the implementation plan step by step (`phase_XX_implementation_plan.md`).
3. Each step has a verification check — confirm it passes before moving to the next.
4. **Commit after each step.** Each step in an implementation plan should result in a git commit. The commit message should reference the phase and step (e.g. `phase-02: step 3 — rewrite inline_reconstruct`).
5. **Commit at minimum after each phase.** If step-level commits feel too granular, at minimum commit after completing an entire phase with all verifications passing.
6. Test fixtures are added incrementally in `tests/` as each phase introduces new capabilities.
7. After implementation, `build_index()` rebuilds the full Kuzu graph from JSONL.
8. **Update CHANGELOG.md** after completing each phase. Record what was implemented, what changed, and any deviations from the design doc.

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
| Canonical storage | JSONL | Append-friendly, inspectable, git-friendly |
| Graph index | Kuzu | Embeddable, Cypher, fast COPY FROM, no server |
| Block identity | UUIDv7 | Sortable by creation time, globally unique |
| Page structure | Flat `root` array | Heading levels encode hierarchy, no tree needed |
| LLM context format | Rendered Djot | ~5x fewer tokens than JSON, LLMs parse natively |
| Tool interface | Plain Python functions | Protocol-agnostic, serve over MCP/OpenAI/etc. |
| Enrichment | LLM-based extraction | Entity + relation extraction per block |

---

## Key dependencies

| Dependency | Role | Phase |
|------------|------|-------|
| `pandoc` 3.x | Djot/Markdown parsing, AST generation | 00+ |
| `python 3.12` | All tooling | 00+ |
| `uuid6` | UUIDv7 generation | 00+ |
| `kuzu` | Embedded graph database | 01+ |
| `pyarrow` | Parquet for Kuzu COPY FROM | 01+ |
| `beautifulsoup4` | HTML normalization for roundtrip verification | 03 |
| `openai` | LLM extraction + Cypher generation | 04, 07 |

---

## Full design reference

- Phase docs: `architecture/phase_XX_design.md` + `phase_XX_implementation_plan.md`
- Open questions: (See end of this file)
# Open Questions and Discussion Items (v4)

Items that surfaced during the v1 design review and revision process.

---

## Resolved

**Block identity model** — Stable IDs with version numbers. Two-reference-pattern: pages use bare IDs (latest), conversation attachments include version (exact snapshot).

**Inline markup / authoring format** — Djot. Both humans and agents author in Djot. Parsed by pandoc. No custom parser. Block-level structure comes from the AST; inline markup is stored as-is in text fields.

**Operation IDs for batch mutations** — `operations.jsonl` with `operation.v1` schema. Batch rollback targets an operation ID.

**Conversation participants** — Derived index in SQLite, not a canonical field.

**Index storage** — Single SQLite database file, rebuilt from JSONL on demand.

**Human authoring format** — Djot. The `{#block_id}` attribute syntax provides native block-level identity. Ingestion parses `.djot` files into canonical JSONL blocks.

**Agent writing format** — Djot for content generation. Tool calls (Python functions) for structural operations. Djot is close enough to Markdown that agents write it fluently; parser feedback handles errors.

**API server** — Cut from v1. All operations through Python library + CLI wrappers. API can be added later by wrapping the same functions.

**Block content types** — Derived from Djot AST during ingestion, not hand-specified by the author. The `type` field in the block schema is set by the ingestion tool.

**Page document structure (flat vs tree)** — Flat list + heading levels for page `root`. Djot `div` containers (`::: ... :::`) provide explicit grouping when needed, mapped to a `div` block type with `children`.

**List representation** — Djot's list syntax handles this naturally. The Djot parser produces list items as distinct AST nodes. Each becomes a block. Grouping is handled by the AST structure, not a custom `list_group` field.

---

## Open

### Q1: Ingestion behavior for existing pages

**Context:** When the human or agent re-ingests a `.djot` file for a page that already exists:

- Blocks with existing IDs and unchanged content: no action (detected via hash).
- Blocks with existing IDs and changed content: create new version.
- Blocks with new IDs: create new block (version 1).
- Blocks that existed in the page but are absent from the new `.djot` file: ???

**The question:** What happens to blocks that are removed from the page structure? The block itself should not be deleted (nothing is ever destroyed). But should it be removed from the page's `root` array? If so, orphaned blocks need to be handled somehow.

**Recommendation to discuss:** Remove absent blocks from the page's `root` array. The block records remain in `blocks.jsonl` (they are never deleted). Any conversations referencing those blocks remain valid because attachments reference blocks by ID + version. An "orphaned blocks" view or query could list blocks not referenced by any page.

---

### Q2: Page versioning

**Status:** Deferred in design doc, but still open for discussion.

If agents restructure pages (add/remove/reorder blocks in `root`), page versioning may be needed for rollback. Clarify: will agents modify page structure in v1, or only block content?

---

### Q3: ID generation strategy

**Context:** Block IDs can be human-assigned (`{#blk_001}`) in Djot or auto-generated during ingestion.

**The question:** What format for auto-generated IDs?

**Options:**
- Prefixed ULIDs (`blk_01HX9QZ8...`): sortable, no collision risk, but long.
- Prefixed short random (`blk_x7k9m2`): shorter, low collision risk at v1 scale.
- Sequential with a counter in the SQLite index (`blk_001`, `blk_002`): human-friendly, requires coordination.

**Recommendation:** Prefixed ULIDs for auto-generated IDs. Human-authored IDs can be any string — the system treats IDs as opaque.

---

### Q4: Conversation message immutability

**Context:** Are conversation messages immutable like block versions?

**Recommendation:** Yes. Corrections are new messages. Retractions are new messages with a `retraction_of` field. This keeps conversations as reliable timelines.

---

### Q5: Block ID display UX in rendered HTML

**Questions:**
- Always visible or hover-only?
- Click to copy just the ID, or also the version?
- Any convenience for copying a formatted attachment reference?

**Recommendation:** Small monospaced badge in the right margin, always visible. Click copies the block ID. Version shown as a separate badge. Formatted attachment copying is a nice-to-have for a future editor plugin.

---

### Q6: Scale assumptions

**Recommendation:** Document explicitly:
- Pages: 10–200
- Blocks per page: 10–100
- Total block versions: 1,000–50,000
- Conversations: 50–1,000
- Messages per conversation: 5–50
- Operations: 50–500
- Active agents: 1–5

---

### Q7: Positioning and prior art document

Create a separate `positioning_and_prior_art.md` tracking the relationship to Obsidian, Anytype, Notion, etc. Serves as a living sanity check.

---

### Q8: Djot-to-block mapping details

**Context:** The ingestion tool walks the pandoc AST and produces block records. The exact mapping needs to be defined for edge cases:

- How are nested lists represented? (Each item is a block, but what about sub-lists?)
- How are multi-paragraph list items handled?
- How are footnotes handled (if at all in v1)?
- How are definition lists handled?
- How does the Djot `div` container map to blocks with children?

**Recommendation:** Define the mapping by example during implementation. Start with the common cases (paragraphs, headings, code, lists, quotes, tables, math, images) and handle edge cases as they arise. Document the mapping as it stabilizes.

---

### Q9: Djot file retention after ingestion

**Context:** After a `.djot` file is ingested into JSONL blocks, is the `.djot` file kept or discarded?

**Options:**
- Keep it as a source record (useful for re-editing, git history).
- Discard it (canonical data is in JSONL; the `.djot` file is input, not truth).
- Keep it but mark it as "ingested" (e.g., move to an archive directory).

**Recommendation to discuss:** Keep the `.djot` files in the `authoring/` directory. They are not canonical, but they are useful for re-editing and for git history. The ingestion tool could add a comment or frontmatter noting the ingestion timestamp.

---

### Q10: Conversation authoring — frontmatter format details

**Context:** The design proposes YAML frontmatter + Djot body for conversation messages. The exact frontmatter schema needs to be pinned down:

- Required fields vs optional fields.
- How to indicate "new conversation" vs "append to existing."
- How to specify the conversation title (for new conversations).
- Whether the tool auto-fills fields (timestamp, message ID, author from config).

**Recommendation:** Define a minimal required set:
```yaml
---
conversation: conv_001    # or "new" for a new conversation
author: human:istvan      # could be auto-filled from config
title: "Optional title"   # only for new conversations
attachments: []           # optional
mentions: []              # optional
---
```
Everything else (message ID, timestamp) is auto-generated by the tool.

---

### Q11: Agent reading format

**Context:** When an agent needs to read a page or block before deciding what to do, what format is it given?

**Options:**
- Raw JSON from JSONL (verbose, token-expensive).
- Djot rendered from internal blocks (token-efficient, includes block IDs, agents read it fluently).
- Plain text summary.

**Recommendation:** Render internal blocks back to Djot for agent consumption. This is token-efficient, includes `{#block_id}` attributes, and agents can read it as naturally as Markdown. The `query` library should have a function like `render_page_as_djot(page_id)` that produces this output. Pandoc supports `json → djot` conversion natively.

---

### Q12: Write Concurrency and File Locking (JSONL vs Kuzu)

**Context:** The current design (`v4`) explicitly states that JSONL is the long-term canonical source of truth and that *all writes* hit `blocks.jsonl` / `conversations.jsonl` using file locks (`fcntl.flock`). Kuzu (and SQLite) are documented purely as *derived, regenerable projections*. However, there is confusion about whether Kuzu is supposed to mitigate write concurrency, or if JSONL storage is actually meant to be deprecated.

**The Problem:**
If JSONL remains the canonical write target, Kuzu does *not* solve write concurrency. Every agent making an edit or adding a message must lock the `.jsonl` files. Under heavy agent collaboration, this file-level locking will create bottlenecks and timeouts. If Kuzu *is* intended to handle concurrent writes, the entire "JSONL as canonical truth" premise of v1 is violated.

**Solution Options:**
1. **Option A: Keep JSONL as Canonical (Status Quo)**
   - *Pros:* Git-friendly, heavily append-based, zero vendor lock-in, incredibly robust.
   - *Cons:* OS-level file locking (`fcntl`) doesn't scale to high-throughput concurrent agent processes.
   - *Mitigation:* Implement a proper local write-queue or background worker to serialize writes safely rather than raw file locking.

2. **Option B: Make Kuzu or SQLite the Canonical Write Target**
   - *Pros:* Native database-level concurrency and ACID transactions. Solves concurrent agent writes instantly.
   - *Cons:* Violates the "text/JSON canonical format" design principle. Makes the repo less git-diffable (binary db blobs). You lose the "inspectable with standard command-line tools" benefit.

3. **Option C: Hybrid (JSONL as Event Log)**
   - *Pros:* Agents write concurrent operations as separate small JSON files (or a robust queue), and a single background reconciler appends them to the canonical JSONL.

**Recommendation to discuss:** Clarify the architectural intent. If JSONL is truly canonical, we must document how we handle high-throughput agent write concurrency beyond basic file locks, or explicitly state that agent operations are strictly synchronous/sequential in v1.

# TODO

Phases are implemented sequentially. Each phase builds on the previous one.

---

## Phase 00 — Djot → JSONL ingestion pipeline ✓

- [x] Design doc and implementation plan written and reviewed
- [x] Conda environment created (`knowledge-graph`)
- [x] `src/ingest/` implemented (pandoc-based, subset of djot)
- [x] End-to-end verification: 9 blocks from `test_00.dj`
- [x] 6 additional test files created in `tests/test_00/extra_inputs/`

---

## Phase 01 — JSONL → LadybugDB graph index ✓

- [x] Design doc and implementation plan written and reviewed
- [x] `src/index/` implemented: ladybug_schema, jsonl_to_parquet, ladybug_loader, build_index
- [x] End-to-end verification: 47 Block nodes, 7 Page nodes, 47 HAS_BLOCK edges

---

## Phase 02 — Switch to djot.js + full Djot support + LINKS_TO

- [x] Design doc: `architecture/design-docs/phase_02_design.md`
- [x] Implementation plan: `architecture/design-docs/phase_02_implementation_plan.md`
- [ ] Verify Node.js and djot.js availability (`npx @djot/djot --version`)
- [ ] Implement `src/ingest/djot_ast.py` — call djot.js, return native AST
- [ ] Rewrite `src/ingest/inline_reconstruct.py` — all djot inline types (verbatim, math, link, image, sub/super, delete, insert, mark, span, footnote_ref, raw_inline)
- [ ] Rewrite `src/ingest/ast_walker.py` — all djot block types (code_block, block_quote, table, definition_list, thematic_break, div, raw_block, nested list items)
- [ ] Update `src/ingest/ingest_page.py` — use djot_ast instead of pandoc_ast
- [ ] Handle `{#id}` attributes from source (section.attributes.id, node.attributes.id)
- [ ] Extract links for LINKS_TO edges (internal link classification)
- [ ] Update LadybugDB schema: add `language` column, add `LINKS_TO` table
- [ ] Create `tests/test_02/all_elements.dj` (every djot element type)
- [ ] Create `tests/test_02/cross_linked_corpus/` (3 interlinked pages)
- [ ] Phase 00 regression test passes with new parser
- [ ] All-elements test: every block type present, inline markup lossless
- [ ] Cross-linked corpus: LINKS_TO edges in LadybugDB

---

## Phase 03 — Block → Djot renderer + roundtrip verification

- [x] Design doc: `architecture/design-docs/phase_03_design.md`
- [x] Implementation plan: `architecture/design-docs/phase_03_implementation_plan.md`
- [ ] Implement `src/render/blocks_to_djot.py` — render_blocks, render_page, render_context
- [ ] Handle all block types (heading, paragraph, code_block, block_quote, list_item, table, definition_item, thematic_break, div, raw_block)
- [ ] Block IDs emitted as `{#id}` attributes (toggleable)
- [ ] Roundtrip test: `all_elements.dj` → blocks → render → re-parse → compare = PASS
- [ ] Roundtrip test: `test_00.dj` + all extra_inputs = PASS
- [ ] Token efficiency confirmed: 3-5x reduction vs raw JSON

---

## Phase 04 — Markdown → Djot conversion (preprocessing)

- [x] Design doc: `architecture/design-docs/phase_04_design.md`
- [x] Implementation plan: `architecture/design-docs/phase_04_implementation_plan.md`
- [ ] Add `beautifulsoup4` to environment
- [ ] Implement `src/convert/md_to_djot.py` — pandoc wrapper, raw HTML detection
- [ ] Implement `src/convert/html_roundtrip.py` — HTML normalization + comparison
- [ ] Implement `src/convert/batch_convert.py` — directory-level conversion
- [ ] Create test fixtures in `tests/test_04/fixtures/` (clean, gfm, edge_cases)
- [ ] Clean fixtures: external HTML roundtrip passes
- [ ] Clean fixtures: internal Phase 03 roundtrip passes on converted files
- [ ] Integration: converted files ingest into LadybugDB without error

---

## Phase 05 — Semantic enrichment (entities + relations)

- [x] Design doc: `architecture/design-docs/phase_05_design.md`
- [x] Implementation plan: `architecture/design-docs/phase_05_implementation_plan.md`
- [ ] Add `openai` to environment
- [ ] Implement `src/enrich/` (entity_schema, mock_extractor, extractor, enrich_blocks)
- [ ] Create geography corpus in `tests/test_05/corpus/` (5 pages)
- [ ] Update LadybugDB schema: Entity node, MENTIONS edge, RELATES_TO edge
- [ ] Mock enrichment: entities loaded into LadybugDB
- [ ] LLM enrichment: relations extracted, cross-document queries work

---

## Phase 06 — Template query tools (LLM-callable interface)

- [x] Design doc: `architecture/design-docs/phase_06_design.md`
- [x] Implementation plan: `architecture/design-docs/phase_06_implementation_plan.md`
- [ ] Implement `src/tools/` (registry, query_entity, query_connection, query_page, search_mentions, query_cypher)
- [ ] All tools return rendered Djot text (via Phase 03 renderer)
- [ ] TOOLS registry importable with JSON Schema parameter definitions
- [ ] `dispatch()` function routes tool calls by name
- [ ] End-to-end: all tools work against Phase 05 geography corpus

---

## Phase 07 — LLM-to-Cypher (open-ended queries)

- [x] Design doc: `architecture/design-docs/phase_07_design.md`
- [x] Implementation plan: `architecture/design-docs/phase_07_implementation_plan.md`
- [ ] Implement `src/tools/schema_describer.py` — schema from LadybugDB metadata
- [ ] Implement `src/tools/ask_graph.py` — LLM Cypher generation + retry
- [ ] Add `ask_graph` to tool registry
- [ ] Test battery: ≥6/8 natural language questions correct

---

## Implementation order

```
Phase 02 (djot.js + full djot) → Phase 03 (renderer + roundtrip)
                                       ↓
                                 Phase 04 (md → djot)
                                       ↓
                                 Phase 05 (enrichment)
                                       ↓
                                 Phase 06 (tools) → Phase 07 (LLM Cypher)
```

Phases are strictly sequential. Each depends on the previous.

# Phase 05 — Design Document

## 1. Purpose

This document describes the design for **Phase 05**: adding semantic enrichment to the knowledge graph — entity extraction, relation extraction, and new graph edges that don't exist in the source documents.

After Phase 05, the graph contains `Entity` nodes, `MENTIONS` edges, and `RELATES_TO` edges. Cross-document queries like "which pages mention the Danube?" become possible.

---

## 2. Background

### Current state after Phases 02-04

The graph contains:
- **Block nodes** with full text content (all djot element types).
- **Page nodes** representing documents.
- **HAS_BLOCK** edges (structural ordering).
- **LINKS_TO** edges (explicit hyperlinks between pages).

This is useful but limited. Mentions of entities without explicit links are invisible to the graph.

### What enrichment adds

1. **Named entity recognition** — identify places, people, organizations, concepts in block text.
2. **Entity linking** — deduplicate mentions into canonical entities.
3. **Relation extraction** — subject-predicate-object triples from text.

---

## 3. Scope

### In scope

- Define `Entity` node table, `MENTIONS` and `RELATES_TO` relationship tables in Kuzu.
- Implement LLM-based extraction (configurable model).
- Implement mock extractor for cost-free pipeline testing.
- Store extraction results directly via Parquet load into Kuzu.
- Process blocks in batches with rate limiting.
- Test with 5-page geography corpus.
- Naive entity deduplication (normalized name matching).

### Out of scope

- Vector embeddings / similarity search.
- Coreference resolution.
- Confidence thresholds or human review loop.
- Real-time extraction.

---

## 4. Entity model

### Entity schema (`entity.v1`)

```json
{
  "id": "entity-danube",
  "schema": "entity.v1",
  "name": "Danube",
  "type": "river",
  "aliases": ["Donau", "the Danube"],
  "created_by": "llm:gpt-4o",
  "created_at": "2026-05-08T10:00:00Z"
}
```

### Relation schema (`relation.v1`)

```json
{
  "id": "rel-019xxx",
  "schema": "relation.v1",
  "subject": "entity-danube",
  "predicate": "flows_through",
  "object": "entity-germany",
  "source_block": "019xxx-block-id",
  "confidence": 0.92,
  "created_by": "llm:gpt-4o",
  "created_at": "2026-05-08T10:00:00Z"
}
```

---

## 5. Kuzu schema additions

```cypher
CREATE NODE TABLE Entity(id STRING, schema STRING, name STRING, type STRING,
    created_by STRING, created_at STRING, PRIMARY KEY (id));

CREATE REL TABLE MENTIONS(FROM Block TO Entity, mention_text STRING, confidence DOUBLE);

CREATE REL TABLE RELATES_TO(FROM Entity TO Entity, predicate STRING,
    source_block STRING, confidence DOUBLE);
```

---

## 6. Extraction pipeline

```
Kuzu blocks → filter eligible blocks → LLM extraction per block → memory → Parquet → Kuzu entities + relations + mentions
```

- Skip `code_block`, `raw_block`, `thematic_break` (no natural language).
- Skip blocks with < 20 characters of text.
- Mock extractor: regex for capitalized phrases. No relations.
- LLM extractor: structured JSON output prompt.

---

## 7. Test corpus

5 geography pages in `tests/test_05/corpus/`: europe.dj, danube.dj, germany.dj, austria.dj, hungary.dj.

---

## 8. Environment update

```yaml
- pip:
  - openai
```

---

## 9. File layout after Phase 05

```
knowledge-graph/
  src/
    enrich/
      __init__.py
      extractor.py
      mock_extractor.py
      entity_schema.py
      enrich_blocks.py
  workspace/
    store/
      kuzu/
  tests/
    test_05/
      corpus/
```

---

## 10. Verification

- Mock enrichment: entities extracted, loaded into Kuzu.
- LLM enrichment: relations extracted for geography corpus.
- Cross-document query works: "which pages mention the Danube?" returns 4+ pages.

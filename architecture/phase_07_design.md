# Phase 07 — Design Document

## 1. Purpose

This document describes the design for **Phase 07**: enabling an LLM to generate Cypher queries dynamically when template queries (Step 06) aren't sufficient.

After Phase 07, the system can handle open-ended questions that require multi-hop graph traversal or complex filtering — questions where no pre-built template exists.

---

## 2. Background

### When templates aren't enough

Step 06's template queries cover common patterns:
- "Tell me about X" → `query_entity`
- "How are X and Y connected?" → `query_connection`
- "Show me page Z" → `query_page`
- "Find mentions of Q" → `search_mentions`

But some questions require bespoke graph traversal:
- "Which entities are mentioned in more than 3 pages?"
- "Find all rivers that flow through countries mentioned in the same page as Austria"
- "What is the shortest path from Berlin to the Black Sea through geographic relations?"

These need ad-hoc Cypher. Rather than anticipating every possible query pattern, we let the LLM generate the Cypher based on the graph schema.

### Why this is Step 07 (last)

LLM-generated Cypher is:
- **Expensive**: requires an LLM call just for query generation (before the actual answering call).
- **Fragile**: LLMs produce syntactically invalid Cypher ~20-30% of the time.
- **Slow**: adds latency (LLM call + query execution + retry on failure).
- **A fallback**: most real queries are answered by templates.

It's valuable to have but should be reached only when templates fail.

---

## 3. Scope

### In scope

- Implement a `generate_cypher` function that takes a natural language question and the graph schema, and produces a Cypher query via LLM.
- Implement retry logic: if the generated Cypher fails to execute, send the error back to the LLM for correction (up to 3 attempts).
- Integrate with Step 06's `query_cypher` tool for execution and rendering.
- Define the schema description format that's fed to the LLM as context.
- Test with 5-10 questions of varying complexity against the geography corpus.

### Out of scope for Phase 07

- Automatic routing (deciding when to use templates vs. Cypher generation). The caller decides which tool to invoke.
- Query plan optimization.
- Caching generated Cypher for repeated similar questions.
- Fine-tuning a model on Cypher generation.

---

## 4. Architecture

```
Natural language question
        │
        ▼
┌──────────────────────────────┐
│  generate_cypher()            │
│  - Schema description         │
│  - Few-shot examples          │
│  - LLM call → Cypher string   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Execute Cypher against Kuzu  │
│  (via query_cypher tool)      │
└──────────────┬───────────────┘
               │
       ┌───────┴───────┐
       │ Success       │ Failure (syntax error)
       ▼               ▼
┌────────────┐  ┌─────────────────────┐
│ Return     │  │ Send error + query   │
│ results    │  │ back to LLM for     │
│ as Djot    │  │ correction (retry)  │
└────────────┘  └─────────────────────┘
```

---

## 5. Schema description for the LLM

The LLM needs to know what nodes, relationships, and properties exist. This is provided as a structured prompt section:

```
Graph Schema:

Node tables:
  Block(id STRING [PK], version INT64, schema STRING, type STRING, text STRING,
        level INT64, style STRING, language STRING, created_by STRING,
        created_at STRING, hash STRING)
  Page(id STRING [PK], schema STRING, title STRING, created_by STRING,
       created_at STRING, updated_at STRING)
  Entity(id STRING [PK], schema STRING, name STRING, type STRING,
         created_by STRING, created_at STRING)

Relationship tables:
  HAS_BLOCK(FROM Page TO Block, position INT64)
  LINKS_TO(FROM Block TO Page, link_text STRING, url STRING)
  MENTIONS(FROM Block TO Entity, mention_text STRING, confidence DOUBLE)
  RELATES_TO(FROM Entity TO Entity, predicate STRING, source_block STRING,
             confidence DOUBLE)

Notes:
  - Block.type is one of: heading, paragraph, list_item, code_block, block_quote, table
  - Entity.type is one of: person, place, organization, concept, event, river, country, city, other
  - RELATES_TO.predicate examples: flows_through, is_capital_of, is_located_in, is_part_of, is_bordered_by
  - Page.id format: "page-{filename_stem}" (e.g. "page-danube", "page-europe")
  - Entity.id format: "entity-{lowercase-name}" (e.g. "entity-danube", "entity-germany")
```

This schema description is generated programmatically from the Kuzu metadata (not hardcoded), so it stays accurate as the schema evolves.

---

## 6. Prompt design

```
You are a Cypher query generator for a Kùzu graph database.
Given a natural language question about a knowledge graph, generate a Cypher query
that retrieves the answer.

{schema_description}

Rules:
- Use only the node and relationship tables listed above.
- Kuzu uses the Cypher query language (similar to Neo4j but not identical).
- Property access: node.property (e.g. b.text, e.name)
- String matching: use CONTAINS for substring, = for exact match.
- Variable-length paths: -[:REL_TYPE*1..3]->
- Return readable columns (e.g. RETURN e.name, not RETURN e).
- If the question asks for content/text, include b.text in the return.
- If the question asks "which pages", return p.title.
- ORDER BY and LIMIT when appropriate.
- Do NOT use OPTIONAL MATCH (Kuzu does not support it).
- Do NOT use MERGE, CREATE, SET, or DELETE (read-only queries only).

Respond with ONLY the Cypher query. No explanation, no markdown fencing.
```

### Few-shot examples (included in prompt)

```
Q: Which entities appear in more than 2 pages?
A: MATCH (p:Page)-[:HAS_BLOCK]->(b:Block)-[:MENTIONS]->(e:Entity)
   WITH e, count(DISTINCT p) AS page_count
   WHERE page_count > 2
   RETURN e.name, e.type, page_count
   ORDER BY page_count DESC

Q: What rivers flow through Germany?
A: MATCH (e:Entity)-[r:RELATES_TO]->(target:Entity {name: 'Germany'})
   WHERE r.predicate = 'flows_through' AND e.type = 'river'
   RETURN e.name

Q: Find all blocks in the Danube page that mention a country
A: MATCH (p:Page {id: 'page-danube'})-[:HAS_BLOCK]->(b:Block)-[:MENTIONS]->(e:Entity {type: 'country'})
   RETURN b.text, e.name
   ORDER BY b.id
```

---

## 7. Retry logic

When generated Cypher fails to execute:

1. Capture the error message from Kuzu.
2. Send a follow-up prompt to the LLM:

```
The following Cypher query failed:

```cypher
{failed_query}
```

Error: {error_message}

Please fix the query. Respond with ONLY the corrected Cypher.
```

3. Try again (up to `max_retries=3`).
4. If all retries fail, return a readable error message to the caller:
   `"Failed to generate a working query after 3 attempts. Last error: ..."`

---

## 8. Integration with the tool interface

Step 07 doesn't add a new tool. It enhances how `query_cypher` can be used. The flow for an LLM that wants to ask an open-ended question:

**Option A** (manual): The LLM generates Cypher itself and calls `query_cypher(cypher="...")`. This works if the LLM already knows the schema (e.g. from system prompt).

**Option B** (assisted): A new tool wraps the generation:

```python
TOOLS.append({
    "name": "ask_graph",
    "description": "Ask a natural language question about the knowledge graph. Generates and executes a Cypher query automatically.",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Natural language question about the knowledge graph"},
        },
        "required": ["question"],
    },
})
```

The `ask_graph` tool:
1. Calls `generate_cypher(question)` to get a Cypher query.
2. Executes the query via `query_cypher(cypher, render_blocks=True)`.
3. Returns the result.

The LLM doesn't need to know Cypher — it just asks a question in English.

---

## 9. Cost management

Each `ask_graph` call costs 1-4 LLM invocations (generation + retries). To manage costs:

- Use a cheap/fast model for Cypher generation (`gpt-4o-mini` or similar). The schema is small; this doesn't need a frontier model.
- Cache schema descriptions (they only change when `build_index` runs).
- The few-shot examples are static and short (~200 tokens).
- Total prompt for generation: ~500-800 tokens input, ~50-100 tokens output. Very cheap per call.

---

## 10. File layout after Phase 07

```
knowledge-graph/
  src/
    tools/
      registry.py           ← MODIFIED: adds ask_graph tool definition
      ask_graph.py          ← NEW: generate_cypher + execute + retry
      schema_describer.py   ← NEW: generates schema description from Kuzu metadata
      query_cypher.py       ← unchanged
      ... (other tools unchanged)
  tests/
    test_07/
      test_questions.py     ← test battery of natural language questions
```

---

## 11. Test questions

The following questions test increasing complexity against the geography corpus:

| # | Question | Difficulty | Expected to need |
|---|----------|-----------|------------------|
| 1 | "What type of entity is the Danube?" | Trivial | Simple MATCH + RETURN |
| 2 | "Which pages mention rivers?" | Easy | JOIN Entity type filter |
| 3 | "What entities appear in more than 2 pages?" | Medium | Aggregation + HAVING |
| 4 | "What countries does the Danube flow through?" | Medium | RELATES_TO with predicate filter |
| 5 | "Which entities are mentioned in both the Germany and Austria pages?" | Hard | Two-path matching |
| 6 | "Find the shortest path between Berlin and the Black Sea" | Hard | Variable-length path |
| 7 | "Which page has the most entity mentions?" | Medium | Aggregation + ordering |
| 8 | "What predicates connect river entities to country entities?" | Medium | Type-filtered relation scan |

Expected: questions 1-5 should generate working Cypher on the first attempt. Questions 6-8 may require 1-2 retries due to Kuzu-specific syntax differences from Neo4j.

---

## 12. Expected state after Phase 07

- `ask_graph("What countries does the Danube flow through?")` returns a rendered answer containing Germany, Austria, Hungary.
- At least 6/8 test questions produce correct results within 3 attempts.
- Failed generations return useful error messages (not crashes).
- The schema description is generated dynamically from Kuzu metadata.
- Total system: 6 tools available (query_entity, query_connection, query_page, search_mentions, query_cypher, ask_graph).

---

## 13. Complete system state after all tests

After Tests 00–07, the full system is:

```
Source (.md/.dj files)
  → Phase 04: convert md → djot
  → Phase 02: djot.js AST → blocks (full djot support)
  → Phase 00: blocks → JSONL (canonical store)
  → Phase 05: enrich with entities + relations (LLM)
  → Phase 01: load into Kuzu (structural edges)
  → Phase 02: LINKS_TO edges
  → Phase 05: MENTIONS + RELATES_TO edges
  → Phase 03: render blocks → Djot (verified roundtrip)
  → Phase 06: template query tools (5 functions)
  → Phase 07: open-ended Cypher generation tool

LLM interaction:
  Question → tool call → Kuzu query → blocks → Djot → LLM context → answer
```

The knowledge graph is usable: ingest documents, enrich semantically, query via tools, get readable context for LLM reasoning.

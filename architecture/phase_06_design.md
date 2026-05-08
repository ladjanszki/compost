# Phase 06 — Design Document

## 1. Purpose

This document describes the design for **Phase 06**: template-based queries exposed as tool-callable Python functions. These are the primary interface through which LLMs interact with the knowledge graph.

After Phase 06, an LLM can call well-defined tool functions to retrieve context from the knowledge graph as rendered Djot text. This is the user-facing (LLM-facing) interface of the system.

---

## 2. Background

### The retrieval problem

The knowledge graph contains blocks, pages, entities, and their relationships. To answer a question, an LLM needs relevant context extracted from the graph and presented in a readable format. The question is: how does the retrieval happen?

### Template queries vs. LLM-generated Cypher

Two approaches:
- **Template queries** (this step): pre-built parameterized Cypher patterns. Deterministic, cheap, fast, cover 80%+ of use cases.
- **LLM-generated Cypher** (Step 07): the LLM writes ad-hoc Cypher. Flexible but expensive, slow, and error-prone.

Template queries handle the common patterns: "tell me about entity X", "how are X and Y connected", "show me page Z". The LLM's job at query time is lightweight — identify which tool to call with which parameters, then reason over the returned context.

### The tool interface pattern

The functions are designed as **LLM tool calls**:
- Clear name and description (the LLM reads these to decide which tool to use).
- JSON Schema parameters (the LLM fills these in).
- Return value is always **Djot text** (the LLM reads this as context).

These functions are pure Python. They can be served over any protocol (MCP, OpenAI function calling, direct invocation). The transport layer is the caller's concern — we just provide the functions with the right signatures and schemas.

---

## 3. Scope

### In scope

- Implement 5 tool functions with clear interfaces.
- Each function: opens Kuzu → runs parameterized Cypher → fetches block records → renders as Djot via Step 05's renderer.
- Define JSON Schema for each tool's parameters (for LLM consumption).
- Define a tool registry (a list of tool definitions with name, description, parameter schema).
- Test each function against the Phase 05 geography corpus.

### Out of scope for Phase 06

- Transport layer (MCP, HTTP, etc.) — caller's responsibility.
- LLM orchestration loop (calling the LLM, parsing tool_call responses, dispatching).
- LLM-generated Cypher (Step 07).
- Caching of query results.
- Access control or multi-tenancy.

---

## 4. Tool definitions

### Tool 1: `query_entity`

**Description**: Get a rendered Djot document about an entity — its type, which pages mention it, the blocks where it appears, and its relationships to other entities.

**Parameters**:
```json
{
  "name": {"type": "string", "description": "Entity name to look up (e.g. 'Danube', 'Germany')"},
  "depth": {"type": "integer", "description": "How many hops of relationships to include (1=direct, 2=neighbors of neighbors)", "default": 1, "minimum": 1, "maximum": 3}
}
```

**Returns**: Djot text containing:
- Entity name and type as heading.
- List of pages that mention this entity.
- The actual block texts where the entity is mentioned (with block IDs).
- Direct relationships (predicate + target entity) at depth 1.
- At depth 2+: neighboring entities and their relationships.

**Cypher pattern** (depth=1):
```cypher
// Entity info
MATCH (e:Entity {name: $name})
RETURN e;

// Mentions: which blocks mention this entity, and which pages contain them
MATCH (p:Page)-[h:HAS_BLOCK]->(b:Block)-[m:MENTIONS]->(e:Entity {name: $name})
RETURN p.id, p.title, b.id, b.text, m.mention_text, h.position
ORDER BY p.id, h.position;

// Relations: what does this entity relate to
MATCH (e:Entity {name: $name})-[r:RELATES_TO]->(other:Entity)
RETURN r.predicate, other.name, other.type;

MATCH (other:Entity)-[r:RELATES_TO]->(e:Entity {name: $name})
RETURN other.name, r.predicate, other.type;
```

**Example output**:
```djot
# Danube (river)

## Mentioned in

### Europe
{#019xxx}
Major rivers include the [Danube](danube.dj), the Rhine, and the Volga.

### Germany
{#019yyy}
The Rhine and the [Danube](danube.dj) are the two longest rivers in Germany.

### Austria
{#019zzz}
Its capital and largest city is Vienna, which sits on the [Danube](danube.dj).

## Relationships

- flows_through → Germany (country)
- flows_through → Austria (country)
- flows_through → Hungary (country)
- empties_into → Black Sea (body_of_water)
```

---

### Tool 2: `query_connection`

**Description**: Find how two entities are connected in the knowledge graph — direct relationships, shared pages, and shortest paths.

**Parameters**:
```json
{
  "entity_a": {"type": "string", "description": "First entity name"},
  "entity_b": {"type": "string", "description": "Second entity name"}
}
```

**Returns**: Djot text showing:
- Direct relationships between the two entities (if any).
- Pages that mention both.
- Blocks where both are mentioned together (same block).
- Shortest path through intermediate entities (if no direct connection).

**Cypher pattern**:
```cypher
// Direct relations
MATCH (a:Entity {name: $entity_a})-[r:RELATES_TO]-(b:Entity {name: $entity_b})
RETURN a.name, r.predicate, b.name;

// Shared pages
MATCH (p:Page)-[:HAS_BLOCK]->(b1:Block)-[:MENTIONS]->(a:Entity {name: $entity_a}),
      (p)-[:HAS_BLOCK]->(b2:Block)-[:MENTIONS]->(b:Entity {name: $entity_b})
RETURN DISTINCT p.id, p.title;

// Co-occurring in same block
MATCH (b:Block)-[:MENTIONS]->(a:Entity {name: $entity_a}),
      (b)-[:MENTIONS]->(e:Entity {name: $entity_b})
RETURN b.id, b.text;

// Shortest path (if no direct connection)
MATCH path = shortestPath(
    (a:Entity {name: $entity_a})-[:RELATES_TO*..4]-(b:Entity {name: $entity_b})
)
RETURN path;
```

---

### Tool 3: `query_page`

**Description**: Retrieve a full page rendered as Djot. Useful when the LLM needs the complete context of a document.

**Parameters**:
```json
{
  "page_id": {"type": "string", "description": "Page ID (e.g. 'page-danube') or page title"}
}
```

**Returns**: The full page content as Djot, with block IDs included.

**Cypher pattern**:
```cypher
// Find the page (by ID or title)
MATCH (p:Page)
WHERE p.id = $page_id OR p.title = $page_id
RETURN p;

// Get all blocks in order
MATCH (p:Page)-[h:HAS_BLOCK]->(b:Block)
WHERE p.id = $resolved_page_id
RETURN b
ORDER BY h.position;
```

The function reconstructs full block records from the Kuzu row data (mapping back to the block.v1 dict format) and passes them to `render_page()`.

---

### Tool 4: `search_mentions`

**Description**: Find all blocks across all pages that mention a given term or entity. Returns matching blocks with their page context.

**Parameters**:
```json
{
  "query": {"type": "string", "description": "Search term (entity name or text substring)"},
  "limit": {"type": "integer", "description": "Maximum number of blocks to return", "default": 10, "maximum": 50}
}
```

**Returns**: Djot text with matching blocks, grouped by page, with surrounding context.

**Implementation**: two search strategies combined:
1. Entity-based: `MATCH (b:Block)-[:MENTIONS]->(e:Entity) WHERE e.name CONTAINS $query`
2. Text-based: `MATCH (b:Block) WHERE b.text CONTAINS $query`

Deduplicate and limit results.

---

### Tool 5: `query_cypher`

**Description**: Run a raw Cypher query against the knowledge graph. For advanced queries not covered by other tools. Returns structured results.

**Parameters**:
```json
{
  "cypher": {"type": "string", "description": "Cypher query to execute"},
  "render_blocks": {"type": "boolean", "description": "If true and results contain block IDs, render those blocks as Djot", "default": false}
}
```

**Returns**: JSON result rows (as a formatted string), or rendered Djot if `render_blocks=true`.

This is the escape hatch. In Step 07, the LLM generates the Cypher itself. In Step 06, a human or system provides it directly.

---

## 5. Tool registry

The tool registry is a Python data structure that can be serialized to any tool-calling format:

```python
TOOLS = [
    {
        "name": "query_entity",
        "description": "Get a rendered Djot document about an entity — its type, mentions across pages, and relationships to other entities.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entity name to look up"},
                "depth": {"type": "integer", "description": "Relationship hops (1-3)", "default": 1},
            },
            "required": ["name"],
        },
    },
    {
        "name": "query_connection",
        "description": "Find how two entities are connected — direct relationships, shared pages, and shortest paths between them.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_a": {"type": "string", "description": "First entity name"},
                "entity_b": {"type": "string", "description": "Second entity name"},
            },
            "required": ["entity_a", "entity_b"],
        },
    },
    {
        "name": "query_page",
        "description": "Retrieve a full page rendered as readable Djot text with block IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID or page title"},
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "search_mentions",
        "description": "Find blocks across all pages that mention a given term or entity.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
                "limit": {"type": "integer", "description": "Max results", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_cypher",
        "description": "Run a raw Cypher query against the knowledge graph for advanced retrieval.",
        "parameters": {
            "type": "object",
            "properties": {
                "cypher": {"type": "string", "description": "Cypher query"},
                "render_blocks": {"type": "boolean", "description": "Render block results as Djot", "default": False},
            },
            "required": ["cypher"],
        },
    },
]
```

This list is importable. Whoever serves the tools (MCP, OpenAI wrapper, etc.) reads this registry and exposes the tools in the appropriate protocol format.

---

## 6. Architecture

```
┌──────────────────────────────────────────┐
│  Caller (MCP server, script, etc.)       │
│  imports tool functions + TOOLS registry  │
└──────────────┬───────────────────────────┘
               │ calls function with params
               ▼
┌──────────────────────────────────────────┐
│  src/tools/                               │
│    query_entity(name, depth)              │
│    query_connection(entity_a, entity_b)   │
│    query_page(page_id)                    │
│    search_mentions(query, limit)          │
│    query_cypher(cypher, render_blocks)    │
└──────────────┬───────────────────────────┘
               │ Cypher queries
               ▼
┌──────────────────────────────────────────┐
│  Kuzu (workspace/indexes/kuzu/db)         │
│    Block, Page, Entity nodes              │
│    HAS_BLOCK, LINKS_TO, MENTIONS,         │
│    RELATES_TO edges                       │
└──────────────┬───────────────────────────┘
               │ result rows
               ▼
┌──────────────────────────────────────────┐
│  src/render/blocks_to_djot.py             │
│    render_blocks() → Djot text            │
└──────────────┬───────────────────────────┘
               │ Djot string
               ▼
┌──────────────────────────────────────────┐
│  Returned to caller → fed to LLM          │
└──────────────────────────────────────────┘
```

---

## 7. Kuzu connection management

Each tool function opens a Kuzu connection, runs queries, and closes it. For the initial implementation this is simple and stateless:

```python
DB_PATH = "workspace/indexes/kuzu/db"

def _get_connection():
    import kuzu
    db = kuzu.Database(DB_PATH)
    return kuzu.Connection(db)
```

If performance becomes a concern (unlikely at this scale), a connection pool can be added later. For Phase 06, open-query-close per call is fine.

---

## 8. Error handling

Each tool function handles errors gracefully:
- **Entity not found**: return a Djot message `"No entity found with name '{name}'. Available entities: ..."` (list top-5 by mention count).
- **Page not found**: return `"No page found with ID or title '{page_id}'. Available pages: ..."`.
- **Cypher syntax error**: return the error message as text (so the LLM can see it and retry with corrected syntax in Step 07).
- **Empty results**: return a clear message `"No results found for query."`.

Errors are never raised — they're returned as text that the LLM can read and act on.

---

## 9. File layout after Phase 06

```
knowledge-graph/
  src/
    tools/
      __init__.py
      registry.py          ← TOOLS list and tool metadata
      query_entity.py      ← query_entity function
      query_connection.py  ← query_connection function
      query_page.py        ← query_page function
      search_mentions.py   ← search_mentions function
      query_cypher.py      ← query_cypher function
    render/
      blocks_to_djot.py    ← from Step 05 (unchanged)
  tests/
    test_06/
      test_tools.py        ← end-to-end tests for each tool
```

---

## 10. Expected state after Phase 06

- All 5 tool functions work against the Phase 05 geography corpus.
- `query_entity("Danube")` returns a multi-page Djot document with mentions from 4+ pages and relationships.
- `query_connection("Germany", "Austria")` shows shared entities and pages.
- `query_page("page-europe")` returns the full rendered page.
- `search_mentions("capital")` finds blocks about capital cities across pages.
- `query_cypher(...)` runs arbitrary Cypher and returns results.
- The `TOOLS` registry is importable and contains valid JSON Schema for all tools.

### Verification queries

```python
from src.tools.query_entity import query_entity
from src.tools.query_connection import query_connection
from src.tools.query_page import query_page

# These should all return non-empty Djot text
assert len(query_entity("Danube")) > 100
assert "Germany" in query_entity("Danube")
assert "Austria" in query_connection("Germany", "Austria")
assert "# Europe" in query_page("page-europe")
```

---

## 11. How an LLM uses these tools (example interaction)

```
User: "What rivers flow through countries that border Austria?"

LLM thinks: I need to know about Austria's neighbors and rivers.
LLM calls: query_entity(name="Austria", depth=2)

Tool returns:
  # Austria (country)
  ## Mentioned in
  [blocks from austria.dj, europe.dj]
  ## Relationships
  - is_bordered_by → Germany (country)
  - is_bordered_by → Hungary (country)
  - has_river → Danube (river)
  ## Depth 2: Germany
  - has_river → Danube (river)
  - has_river → Rhine (river)
  ## Depth 2: Hungary
  - has_river → Danube (river)
  - has_river → Tisza (river)

LLM answers: "Rivers flowing through Austria's neighboring countries include
the Danube (Germany, Hungary), the Rhine (Germany), and the Tisza (Hungary)."
```

The LLM didn't need to write Cypher. It called one tool and got enough context to answer.

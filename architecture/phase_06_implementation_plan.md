# Phase 06 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Phase 06. It assumes the reader has read `phase_06_design.md`.

The goal of Phase 06 is to implement and verify:

```
Tool call (name, params)  →  Cypher query  →  LadybugDB results  →  rendered Djot text
```

---

## 2. Prerequisites

- [ ] Phase 05 has been implemented: LadybugDB has Entity, MENTIONS, RELATES_TO data.
- [ ] Phase 03 has been implemented: `render_blocks()` works correctly.
- [ ] The Phase 05 geography corpus (5 pages) is ingested and indexed, with enrichment run.
- [ ] The `knowledge-graph` conda environment is active.

---

## 3. Steps

### Step 1 — Create directory structure

```bash
mkdir -p src/tools
mkdir -p tests/test_06
touch src/tools/__init__.py
touch src/tools/registry.py
touch src/tools/query_entity.py
touch src/tools/query_connection.py
touch src/tools/query_page.py
touch src/tools/search_mentions.py
touch src/tools/query_cypher.py
touch tests/test_06/test_tools.py
```

---

### Step 2 — `registry.py`

Define the tool registry and shared utilities:

```python
"""
Tool registry — defines all available tools with their schemas.
Import TOOLS to get the list of tool definitions for any serving protocol.
"""

DB_PATH = "workspace/indexes/ladybug/db"

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


def get_connection():
    """Open a LadybugDB database connection. Caller is responsible for usage."""
    import real_ladybug as lb
    db = lb.Database(DB_PATH)
    return lb.Connection(db)


def dispatch(tool_name: str, params: dict) -> str:
    """
    Dispatch a tool call by name. Returns the tool's text output.
    Used by serving layers (MCP, function-calling wrappers, etc.).
    """
    from . import query_entity, query_connection, query_page, search_mentions, query_cypher
    
    handlers = {
        "query_entity": query_entity.run,
        "query_connection": query_connection.run,
        "query_page": query_page.run,
        "search_mentions": search_mentions.run,
        "query_cypher": query_cypher.run,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}"
    return handler(**params)
```

---

### Step 3 — `query_page.py`

Start with the simplest tool:

```python
"""query_page — retrieve a full page as rendered Djot."""
from .registry import get_connection
from src.render.blocks_to_djot import render_blocks


def run(page_id: str) -> str:
    """
    Retrieve a page by ID or title, return all blocks rendered as Djot.
    """
    conn = get_connection()
    
    # Resolve page (by ID or title)
    result = conn.execute(
        "MATCH (p:Page) WHERE p.id = $id OR p.title = $id RETURN p.id, p.title",
        {"id": page_id}
    )
    if not result.has_next():
        # Try case-insensitive title match
        result = conn.execute(
            "MATCH (p:Page) WHERE toLower(p.title) CONTAINS toLower($id) RETURN p.id, p.title",
            {"id": page_id}
        )
        if not result.has_next():
            return _page_not_found(conn, page_id)
    
    row = result.get_next()
    resolved_id = row[0]
    title = row[1]
    
    # Get all blocks in order
    result = conn.execute("""
        MATCH (p:Page {id: $pid})-[h:HAS_BLOCK]->(b:Block)
        RETURN b.id, b.type, b.text, b.level, b.style, b.language, h.position
        ORDER BY h.position
    """, {"pid": resolved_id})
    
    blocks = []
    while result.has_next():
        r = result.get_next()
        block = _row_to_block_dict(r)
        blocks.append(block)
    
    if not blocks:
        return f"Page '{page_id}' exists but has no blocks."
    
    return render_blocks(blocks, {"include_ids": True})


def _row_to_block_dict(row) -> dict:
    """Convert a LadybugDB result row to a block dict suitable for render_blocks."""
    block_id, block_type, text, level, style, language, position = row
    content = {}
    if text is not None:
        content["text"] = text
    if level is not None:
        content["level"] = level
    if style is not None:
        content["style"] = style
    if language is not None:
        content["language"] = language
    return {"id": block_id, "type": block_type, "content": content}


def _page_not_found(conn, page_id: str) -> str:
    """Return a helpful message listing available pages."""
    result = conn.execute("MATCH (p:Page) RETURN p.id, p.title ORDER BY p.id")
    pages = []
    while result.has_next():
        r = result.get_next()
        pages.append(f"- {r[0]} ({r[1]})")
    page_list = "\n".join(pages[:10])
    return f"No page found matching '{page_id}'.\n\nAvailable pages:\n{page_list}"
```

**Verification**:
```python
from src.tools.query_page import run
result = run("page-europe")
assert "# Europe" in result
print(result)
```

---

### Step 4 — `query_entity.py`

```python
"""query_entity — entity page with mentions, relationships, and context."""
from .registry import get_connection
from src.render.blocks_to_djot import render_blocks, render_context


def run(name: str, depth: int = 1) -> str:
    """
    Build a context document about an entity:
    - Entity info (name, type)
    - Blocks that mention it (grouped by page)
    - Relationships (outgoing and incoming)
    - At depth > 1: neighboring entities and their relationships
    """
    conn = get_connection()
    
    # Find the entity
    result = conn.execute(
        "MATCH (e:Entity) WHERE e.name = $name OR toLower(e.name) = toLower($name) "
        "RETURN e.id, e.name, e.type",
        {"name": name}
    )
    if not result.has_next():
        return _entity_not_found(conn, name)
    
    row = result.get_next()
    entity_id, entity_name, entity_type = row
    
    parts = []
    parts.append(f"# {entity_name} ({entity_type})\n")
    
    # Mentions grouped by page
    mentions_text = _get_mentions(conn, entity_name)
    if mentions_text:
        parts.append("## Mentioned in\n")
        parts.append(mentions_text)
    
    # Relationships
    rels_text = _get_relationships(conn, entity_name)
    if rels_text:
        parts.append("## Relationships\n")
        parts.append(rels_text)
    
    # Depth > 1: neighboring entities
    if depth >= 2:
        neighbors_text = _get_neighbors(conn, entity_name, depth)
        if neighbors_text:
            parts.append("## Related entities\n")
            parts.append(neighbors_text)
    
    return "\n".join(parts)


def _get_mentions(conn, entity_name: str) -> str:
    """Get all blocks mentioning this entity, grouped by page."""
    result = conn.execute("""
        MATCH (p:Page)-[h:HAS_BLOCK]->(b:Block)-[m:MENTIONS]->(e:Entity {name: $name})
        RETURN p.title, b.id, b.type, b.text, b.level, b.style, b.language, h.position
        ORDER BY p.title, h.position
    """, {"name": entity_name})
    
    pages = {}  # title → list of block dicts
    while result.has_next():
        r = result.get_next()
        page_title = r[0]
        block = _row_to_block_dict(r[1:])
        pages.setdefault(page_title, []).append(block)
    
    parts = []
    for title, blocks in pages.items():
        parts.append(f"### {title}\n")
        parts.append(render_blocks(blocks, {"include_ids": True}))
    
    return "\n".join(parts)


def _get_relationships(conn, entity_name: str) -> str:
    """Get direct relationships (both directions)."""
    lines = []
    
    # Outgoing
    result = conn.execute("""
        MATCH (e:Entity {name: $name})-[r:RELATES_TO]->(other:Entity)
        RETURN r.predicate, other.name, other.type
    """, {"name": entity_name})
    while result.has_next():
        r = result.get_next()
        lines.append(f"- {r[0]} → {r[1]} ({r[2]})")
    
    # Incoming
    result = conn.execute("""
        MATCH (other:Entity)-[r:RELATES_TO]->(e:Entity {name: $name})
        RETURN other.name, r.predicate, other.type
    """, {"name": entity_name})
    while result.has_next():
        r = result.get_next()
        lines.append(f"- {r[1]} ← {r[0]} ({r[2]})")
    
    return "\n".join(lines) + "\n" if lines else ""


def _get_neighbors(conn, entity_name: str, depth: int) -> str:
    """Get neighboring entities at the specified depth."""
    result = conn.execute("""
        MATCH (e:Entity {name: $name})-[:RELATES_TO]-(neighbor:Entity)
        RETURN DISTINCT neighbor.name, neighbor.type
    """, {"name": entity_name})
    
    neighbors = []
    while result.has_next():
        r = result.get_next()
        neighbors.append((r[0], r[1]))
    
    parts = []
    for n_name, n_type in neighbors[:10]:  # Limit to avoid huge outputs
        parts.append(f"### {n_name} ({n_type})")
        # Get this neighbor's relationships
        result = conn.execute("""
            MATCH (e:Entity {name: $name})-[r:RELATES_TO]->(other:Entity)
            RETURN r.predicate, other.name
            LIMIT 5
        """, {"name": n_name})
        while result.has_next():
            r = result.get_next()
            parts.append(f"- {r[0]} → {r[1]}")
        parts.append("")
    
    return "\n".join(parts)


def _row_to_block_dict(row) -> dict:
    """Convert query row to block dict for rendering."""
    block_id, block_type, text, level, style, language, position = row
    content = {}
    if text is not None:
        content["text"] = text
    if level is not None:
        content["level"] = level
    if style is not None:
        content["style"] = style
    if language is not None:
        content["language"] = language
    return {"id": block_id, "type": block_type, "content": content}


def _entity_not_found(conn, name: str) -> str:
    """Helpful message with suggestions."""
    result = conn.execute(
        "MATCH (e:Entity) RETURN e.name, e.type ORDER BY e.name LIMIT 15"
    )
    entities = []
    while result.has_next():
        r = result.get_next()
        entities.append(f"- {r[0]} ({r[1]})")
    entity_list = "\n".join(entities)
    return f"No entity found matching '{name}'.\n\nAvailable entities:\n{entity_list}"
```

**Verification**:
```python
from src.tools.query_entity import run
result = run("Danube", depth=1)
assert "river" in result
assert "Mentioned in" in result
print(result[:500])
```

---

### Step 5 — `query_connection.py`

```python
"""query_connection — find how two entities are related."""
from .registry import get_connection
from src.render.blocks_to_djot import render_blocks


def run(entity_a: str, entity_b: str) -> str:
    """Find connections between two entities."""
    conn = get_connection()
    
    parts = [f"# Connection: {entity_a} ↔ {entity_b}\n"]
    
    # Direct relationships
    direct = _get_direct_relations(conn, entity_a, entity_b)
    if direct:
        parts.append("## Direct relationships\n")
        parts.append(direct)
    
    # Shared pages
    shared = _get_shared_pages(conn, entity_a, entity_b)
    if shared:
        parts.append("## Both mentioned in\n")
        parts.append(shared)
    
    # Co-occurring blocks
    cooccur = _get_cooccurrences(conn, entity_a, entity_b)
    if cooccur:
        parts.append("## Mentioned together in\n")
        parts.append(cooccur)
    
    if not direct and not shared and not cooccur:
        parts.append(f"No connection found between '{entity_a}' and '{entity_b}'.")
    
    return "\n".join(parts)


def _get_direct_relations(conn, a: str, b: str) -> str:
    result = conn.execute("""
        MATCH (ea:Entity {name: $a})-[r:RELATES_TO]->(eb:Entity {name: $b})
        RETURN ea.name, r.predicate, eb.name
    """, {"a": a, "b": b})
    
    lines = []
    while result.has_next():
        r = result.get_next()
        lines.append(f"- {r[0]} → {r[1]} → {r[2]}")
    
    # Also check reverse direction
    result = conn.execute("""
        MATCH (eb:Entity {name: $b})-[r:RELATES_TO]->(ea:Entity {name: $a})
        RETURN eb.name, r.predicate, ea.name
    """, {"a": a, "b": b})
    while result.has_next():
        r = result.get_next()
        lines.append(f"- {r[0]} → {r[1]} → {r[2]}")
    
    return "\n".join(lines) + "\n" if lines else ""


def _get_shared_pages(conn, a: str, b: str) -> str:
    result = conn.execute("""
        MATCH (p:Page)-[:HAS_BLOCK]->(b1:Block)-[:MENTIONS]->(ea:Entity {name: $a}),
              (p)-[:HAS_BLOCK]->(b2:Block)-[:MENTIONS]->(eb:Entity {name: $b})
        RETURN DISTINCT p.title, p.id
    """, {"a": a, "b": b})
    
    lines = []
    while result.has_next():
        r = result.get_next()
        lines.append(f"- {r[0]} ({r[1]})")
    
    return "\n".join(lines) + "\n" if lines else ""


def _get_cooccurrences(conn, a: str, b: str) -> str:
    result = conn.execute("""
        MATCH (b:Block)-[:MENTIONS]->(ea:Entity {name: $a}),
              (b)-[:MENTIONS]->(eb:Entity {name: $b})
        RETURN b.id, b.type, b.text, b.level, b.style, b.language
    """, {"a": a, "b": b})
    
    blocks = []
    while result.has_next():
        r = result.get_next()
        content = {}
        if r[2] is not None: content["text"] = r[2]
        if r[3] is not None: content["level"] = r[3]
        if r[4] is not None: content["style"] = r[4]
        if r[5] is not None: content["language"] = r[5]
        blocks.append({"id": r[0], "type": r[1], "content": content})
    
    if blocks:
        return render_blocks(blocks, {"include_ids": True})
    return ""
```

**Verification**:
```python
from src.tools.query_connection import run
result = run("Germany", "Austria")
assert len(result) > 50
print(result)
```

---

### Step 6 — `search_mentions.py`

```python
"""search_mentions — text and entity search across all blocks."""
from .registry import get_connection
from src.render.blocks_to_djot import render_blocks


def run(query: str, limit: int = 10) -> str:
    """
    Search for blocks mentioning a term.
    Combines entity-based search with text substring search.
    """
    conn = get_connection()
    limit = min(limit, 50)
    
    blocks_found = {}  # block_id → (block_dict, page_title)
    
    # Strategy 1: entity-based
    result = conn.execute("""
        MATCH (p:Page)-[h:HAS_BLOCK]->(b:Block)-[:MENTIONS]->(e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($q)
        RETURN b.id, b.type, b.text, b.level, b.style, b.language, p.title, h.position
        ORDER BY h.position
        LIMIT $lim
    """, {"q": query, "lim": limit})
    
    while result.has_next():
        r = result.get_next()
        block_id = r[0]
        if block_id not in blocks_found:
            content = {}
            if r[2] is not None: content["text"] = r[2]
            if r[3] is not None: content["level"] = r[3]
            if r[4] is not None: content["style"] = r[4]
            if r[5] is not None: content["language"] = r[5]
            blocks_found[block_id] = (
                {"id": block_id, "type": r[1], "content": content},
                r[6]
            )
    
    # Strategy 2: text substring (fill up to limit)
    remaining = limit - len(blocks_found)
    if remaining > 0:
        result = conn.execute("""
            MATCH (p:Page)-[h:HAS_BLOCK]->(b:Block)
            WHERE b.text CONTAINS $q AND NOT b.id IN $existing
            RETURN b.id, b.type, b.text, b.level, b.style, b.language, p.title, h.position
            ORDER BY h.position
            LIMIT $lim
        """, {"q": query, "existing": list(blocks_found.keys()), "lim": remaining})
        
        while result.has_next():
            r = result.get_next()
            block_id = r[0]
            if block_id not in blocks_found:
                content = {}
                if r[2] is not None: content["text"] = r[2]
                if r[3] is not None: content["level"] = r[3]
                if r[4] is not None: content["style"] = r[4]
                if r[5] is not None: content["language"] = r[5]
                blocks_found[block_id] = (
                    {"id": block_id, "type": r[1], "content": content},
                    r[6]
                )
    
    if not blocks_found:
        return f"No blocks found mentioning '{query}'."
    
    # Group by page
    pages = {}
    for block_dict, page_title in blocks_found.values():
        pages.setdefault(page_title, []).append(block_dict)
    
    parts = [f"# Search results for '{query}'\n"]
    parts.append(f"Found {len(blocks_found)} blocks across {len(pages)} pages.\n")
    
    for title, blocks in pages.items():
        parts.append(f"## {title}\n")
        parts.append(render_blocks(blocks, {"include_ids": True}))
    
    return "\n".join(parts)
```

**Verification**:
```python
from src.tools.search_mentions import run
result = run("capital")
assert "Budapest" in result or "Vienna" in result or "Berlin" in result
print(result)
```

---

### Step 7 — `query_cypher.py`

```python
"""query_cypher — raw Cypher execution (escape hatch)."""
import json
from .registry import get_connection
from src.render.blocks_to_djot import render_blocks


def run(cypher: str, render_blocks_flag: bool = False) -> str:
    """
    Execute a raw Cypher query and return results.
    If render_blocks_flag=True and results contain block data, render as Djot.
    """
    conn = get_connection()
    
    try:
        result = conn.execute(cypher)
    except Exception as e:
        return f"Cypher error: {e}\n\nQuery was:\n```\n{cypher}\n```"
    
    rows = []
    columns = result.get_column_names()
    while result.has_next():
        rows.append(result.get_next())
    
    if not rows:
        return "Query returned no results."
    
    # If render_blocks requested and we have block-like columns
    if render_blocks_flag and _looks_like_blocks(columns):
        blocks = _rows_to_blocks(columns, rows)
        if blocks:
            return render_blocks(blocks, {"include_ids": True})
    
    # Default: format as readable text
    parts = [f"Query returned {len(rows)} rows.\n"]
    parts.append("| " + " | ".join(str(c) for c in columns) + " |")
    parts.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows[:50]:  # Limit display
        parts.append("| " + " | ".join(str(v)[:60] for v in row) + " |")
    if len(rows) > 50:
        parts.append(f"\n... and {len(rows) - 50} more rows.")
    
    return "\n".join(parts)


def _looks_like_blocks(columns: list) -> bool:
    """Check if result columns look like block data."""
    col_set = set(str(c).lower() for c in columns)
    return "b.id" in col_set or "b.text" in col_set or "b.type" in col_set


def _rows_to_blocks(columns: list, rows: list) -> list:
    """Attempt to reconstruct block dicts from query results."""
    col_map = {str(c).lower(): i for i, c in enumerate(columns)}
    blocks = []
    for row in rows:
        block = {
            "id": row[col_map.get("b.id", 0)] if "b.id" in col_map else "unknown",
            "type": row[col_map.get("b.type", 0)] if "b.type" in col_map else "paragraph",
            "content": {},
        }
        if "b.text" in col_map and row[col_map["b.text"]] is not None:
            block["content"]["text"] = row[col_map["b.text"]]
        if "b.level" in col_map and row[col_map["b.level"]] is not None:
            block["content"]["level"] = row[col_map["b.level"]]
        if "b.style" in col_map and row[col_map["b.style"]] is not None:
            block["content"]["style"] = row[col_map["b.style"]]
        blocks.append(block)
    return blocks
```

**Verification**:
```python
from src.tools.query_cypher import run
result = run("MATCH (e:Entity) RETURN e.name, e.type LIMIT 5")
assert "rows" in result
print(result)
```

---

### Step 8 — End-to-end test

`tests/test_06/test_tools.py`:

```python
"""End-to-end tests for all tools against the geography corpus."""
import sys
sys.path.insert(0, ".")

from src.tools.registry import dispatch


def test_all():
    # query_page
    result = dispatch("query_page", {"page_id": "page-europe"})
    assert "Europe" in result, f"query_page failed: {result[:100]}"
    assert "{#" in result, "Block IDs missing"
    print("✓ query_page")
    
    # query_entity
    result = dispatch("query_entity", {"name": "Danube"})
    assert "Mentioned in" in result or "Danube" in result, f"query_entity failed: {result[:100]}"
    print("✓ query_entity")
    
    # query_entity with depth
    result = dispatch("query_entity", {"name": "Danube", "depth": 2})
    assert len(result) > 200, "Depth 2 should produce more content"
    print("✓ query_entity (depth=2)")
    
    # query_connection
    result = dispatch("query_connection", {"entity_a": "Germany", "entity_b": "Austria"})
    assert "Germany" in result and "Austria" in result
    print("✓ query_connection")
    
    # search_mentions
    result = dispatch("search_mentions", {"query": "capital"})
    assert "capital" in result.lower() or "Berlin" in result or "Vienna" in result or "Budapest" in result
    print("✓ search_mentions")
    
    # query_cypher
    result = dispatch("query_cypher", {"cypher": "MATCH (e:Entity) RETURN e.name LIMIT 3"})
    assert "rows" in result or "name" in result
    print("✓ query_cypher")
    
    # Error handling: entity not found
    result = dispatch("query_entity", {"name": "Narnia"})
    assert "not found" in result.lower() or "No entity" in result
    print("✓ error handling (entity not found)")
    
    # Error handling: bad cypher
    result = dispatch("query_cypher", {"cypher": "INVALID QUERY SYNTAX"})
    assert "error" in result.lower()
    print("✓ error handling (bad cypher)")
    
    # Dispatch unknown tool
    result = dispatch("nonexistent_tool", {})
    assert "Unknown tool" in result
    print("✓ error handling (unknown tool)")
    
    print("\nAll tests passed.")


if __name__ == "__main__":
    test_all()
```

**Run**:
```bash
conda activate knowledge-graph
python tests/test_06/test_tools.py
```

---

### Step 9 — Token efficiency demonstration

```bash
python -c "
from src.tools.registry import dispatch

# Compare: same content in JSON vs Djot
import json

# Get raw blocks for comparison
from src.tools.query_page import run as query_page_run
djot_output = query_page_run('page-danube')

# Get raw blocks for comparison via LadybugDB
import real_ladybug as lb
db = lb.Database('workspace/store/ladybug/db')
conn = lb.Connection(db)
res = conn.execute("MATCH (p:Page {id: 'page-danube'})-[r:HAS_BLOCK]->(b:Block) RETURN b ORDER BY r.position")
page_blocks = []
while res.has_next():
    page_blocks.append(res.get_next()[0])

json_output = json.dumps(page_blocks, indent=2)

print(f'JSON size: {len(json_output)} chars')
print(f'Djot size: {len(djot_output)} chars')
print(f'Reduction: {len(json_output) / len(djot_output):.1f}x')
print()
print('--- Djot output (what the LLM sees) ---')
print(djot_output)
"
```

---

## 4. Implementation order and dependencies

```
Step 1  (directories)       — no dependencies
Step 2  (registry)          — no dependencies
Step 3  (query_page)        — depends on Step 2 + Phase 03 renderer
Step 4  (query_entity)      — depends on Step 2 + Phase 03 renderer
Step 5  (query_connection)  — depends on Step 2 + Phase 03 renderer
Step 6  (search_mentions)   — depends on Step 2 + Phase 03 renderer
Step 7  (query_cypher)      — depends on Step 2
Step 8  (e2e test)          — depends on all prior steps
Step 9  (token demo)        — depends on Steps 3, 8
```

Steps 3–7 are independent of each other and can be implemented in any order.

---

## 5. What Phase 06 does NOT validate

- **Transport/serving layer**: the tools are Python functions. MCP, HTTP, etc. wrappers are the caller's responsibility.
- **LLM orchestration**: calling the LLM, passing tool definitions, dispatching tool_calls — not implemented here.
- **LLM-generated Cypher quality** (Step 07): `query_cypher` just executes whatever Cypher it receives. Step 07 adds the LLM query generation logic.
- **Performance at scale**: tested with 5 pages / ~30 blocks. Acceptable for thousands of blocks; may need optimization for millions (unlikely in practice for this system).
- **Concurrent access**: single-connection per call is fine for tool-calling patterns (sequential, not concurrent).

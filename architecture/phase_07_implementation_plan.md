# Phase 07 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Phase 07. It assumes the reader has read `phase_07_design.md`.

The goal of Phase 07 is to implement and verify:

```
Natural language question  →  LLM generates Cypher  →  execute  →  render results as Djot
```

---

## 2. Prerequisites

- [ ] Phase 06 has been implemented: all template tools work, `query_cypher` tool exists.
- [ ] Phase 05 geography corpus is enriched and indexed in LadybugDB.
- [ ] `OPENAI_API_KEY` is set (or a compatible API endpoint is available).
- [ ] The `knowledge-graph` conda environment is active.

---

## 3. Steps

### Step 1 — Create files

```bash
touch src/tools/ask_graph.py
touch src/tools/schema_describer.py
mkdir -p tests/test_07
touch tests/test_07/test_questions.py
```

---

### Step 2 — `schema_describer.py`

Generate a human/LLM-readable schema description from the live LadybugDB database:

```python
"""schema_describer — generate a text description of the LadybugDB schema."""
from .registry import get_connection


def describe_schema(db_path: str = None) -> str:
    """
    Query LadybugDB metadata and return a formatted schema description
    suitable for inclusion in an LLM prompt.
    """
    conn = get_connection()
    
    parts = ["Graph Schema:\n"]
    
    # Node tables
    parts.append("Node tables:")
    node_tables = _get_node_tables(conn)
    for table_name, columns in node_tables.items():
        cols_str = ", ".join(
            f"{col['name']} {col['type']}" + (" [PK]" if col.get("primary") else "")
            for col in columns
        )
        parts.append(f"  {table_name}({cols_str})")
    
    parts.append("")
    
    # Relationship tables
    parts.append("Relationship tables:")
    rel_tables = _get_rel_tables(conn)
    for table_name, info in rel_tables.items():
        cols_str = ", ".join(f"{col['name']} {col['type']}" for col in info["columns"])
        parts.append(f"  {table_name}(FROM {info['from']} TO {info['to']}, {cols_str})")
    
    parts.append("")
    
    # Add useful notes
    parts.append("Notes:")
    parts.append("  - Block.type values: heading, paragraph, list_item, code_block, block_quote, table")
    parts.append("  - Page.id format: 'page-{filename_stem}' (e.g. 'page-danube')")
    parts.append("  - Entity.id format: 'entity-{lowercase-name}' (e.g. 'entity-germany')")
    parts.append("  - RELATES_TO.predicate examples: flows_through, is_capital_of, is_located_in, is_part_of")
    parts.append("  - Only read queries (no CREATE, MERGE, SET, DELETE)")
    
    return "\n".join(parts)


def _get_node_tables(conn) -> dict:
    """Get node table schemas from LadybugDB metadata."""
    # LadybugDB's SHOW_TABLES() includes an additional database name column (for its attached-database feature).
    # Do NOT use hardcoded tuple unpacking (e.g., name, type, ... = row).
    # Access data defensively via dictionaries or column indices verified against the result headers.
    result = conn.execute("CALL show_tables() RETURN *")
    tables = {}
    while result.has_next():
        row = result.get_next()
        table_name = row[0]
        table_type = row[1]
        if table_type == "NODE":
            columns = _get_table_columns(conn, table_name)
            tables[table_name] = columns
    return tables


def _get_rel_tables(conn) -> dict:
    """Get relationship table schemas from LadybugDB metadata."""
    result = conn.execute("CALL show_tables() RETURN *")
    tables = {}
    while result.has_next():
        row = result.get_next()
        table_name = row[0]
        table_type = row[1]
        if table_type == "REL":
            columns = _get_table_columns(conn, table_name)
            # Get FROM/TO info
            conn_info = _get_rel_connection(conn, table_name)
            tables[table_name] = {
                "from": conn_info["from"],
                "to": conn_info["to"],
                "columns": [c for c in columns if c["name"] not in ("_id", "_label")],
            }
    return tables


def _get_table_columns(conn, table_name: str) -> list:
    """Get column definitions for a table."""
    result = conn.execute(f"CALL table_info('{table_name}') RETURN *")
    columns = []
    while result.has_next():
        row = result.get_next()
        # Row format depends on LadybugDB version — adapt as needed
        columns.append({
            "name": row[1],   # column name
            "type": row[2],   # data type
            "primary": row[3] if len(row) > 3 else False,
        })
    return columns


def _get_rel_connection(conn, table_name: str) -> dict:
    """Get FROM and TO table names for a relationship table."""
    result = conn.execute(f"CALL show_connection('{table_name}') RETURN *")
    if result.has_next():
        row = result.get_next()
        return {"from": row[0], "to": row[1]}
    return {"from": "?", "to": "?"}
```

**Verification**:
```python
from src.tools.schema_describer import describe_schema
schema = describe_schema()
print(schema)
assert "Block" in schema
assert "Entity" in schema
assert "RELATES_TO" in schema
```

---

### Step 3 — `ask_graph.py`

The core function: natural language → Cypher → results.

```python
"""ask_graph — LLM-generated Cypher queries against the knowledge graph."""
import os
import time

from openai import OpenAI

from .registry import get_connection
from .schema_describer import describe_schema
from .query_cypher import run as run_cypher


# Configuration
DEFAULT_MODEL = "gpt-4o-mini"
MAX_RETRIES = 3

# Few-shot examples
FEW_SHOT_EXAMPLES = """
Q: What type of entity is the Danube?
A: MATCH (e:Entity {name: 'Danube'}) RETURN e.name, e.type

Q: Which pages mention rivers?
A: MATCH (p:Page)-[:HAS_BLOCK]->(b:Block)-[:MENTIONS]->(e:Entity {type: 'river'})
RETURN DISTINCT p.title, e.name

Q: What entities appear in more than 2 pages?
A: MATCH (p:Page)-[:HAS_BLOCK]->(b:Block)-[:MENTIONS]->(e:Entity)
WITH e, count(DISTINCT p) AS page_count
WHERE page_count > 2
RETURN e.name, e.type, page_count
ORDER BY page_count DESC

Q: What countries does the Danube flow through?
A: MATCH (e:Entity {name: 'Danube'})-[r:RELATES_TO]->(target:Entity)
WHERE r.predicate = 'flows_through'
RETURN target.name, target.type

Q: Find all blocks in the Danube page that mention a country
A: MATCH (p:Page {id: 'page-danube'})-[h:HAS_BLOCK]->(b:Block)-[:MENTIONS]->(e:Entity {type: 'country'})
RETURN b.id, b.type, b.text, e.name
ORDER BY h.position
""".strip()


def run(question: str) -> str:
    """
    Answer a natural language question by generating and executing Cypher.
    
    Returns rendered results (Djot or table) or an error message.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Error: OPENAI_API_KEY not set. Cannot generate Cypher queries."
    
    schema = describe_schema()
    cypher = _generate_cypher(question, schema, api_key)
    
    if not cypher:
        return "Error: LLM returned empty response."
    
    # Try to execute, with retries on failure
    last_error = None
    for attempt in range(MAX_RETRIES):
        result = _try_execute(cypher)
        if result["success"]:
            return result["output"]
        
        last_error = result["error"]
        
        # Retry: ask LLM to fix the query
        if attempt < MAX_RETRIES - 1:
            cypher = _fix_cypher(cypher, last_error, schema, api_key)
            if not cypher:
                break
    
    return (
        f"Failed to generate a working query after {MAX_RETRIES} attempts.\n\n"
        f"Last query:\n```cypher\n{cypher}\n```\n\n"
        f"Last error: {last_error}"
    )


def _generate_cypher(question: str, schema: str, api_key: str) -> str:
    """Call LLM to generate a Cypher query."""
    client = OpenAI(api_key=api_key)
    
    system_prompt = f"""You are a Cypher query generator for a Kùzu graph database.
Given a natural language question, generate a Cypher query that retrieves the answer.

{schema}

Rules:
- Use only the node and relationship tables listed above.
- Property access: node.property (e.g. b.text, e.name)
- String matching: use CONTAINS for substring, = for exact match.
- Variable-length paths: -[:REL_TYPE*1..3]->
- Return readable columns (e.g. RETURN e.name, not RETURN e).
- If the question asks for text content, include b.text in the return.
- If the question asks "which pages", return p.title.
- ORDER BY and LIMIT when appropriate.
- Do NOT use MERGE, CREATE, SET, or DELETE (read-only queries only).

Respond with ONLY the Cypher query. No explanation, no markdown fencing, no backticks.

Examples:
{FEW_SHOT_EXAMPLES}"""

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Q: {question}"},
        ],
        temperature=0,
        max_tokens=300,
    )
    
    return response.choices[0].message.content.strip()


def _fix_cypher(failed_query: str, error: str, schema: str, api_key: str) -> str:
    """Ask LLM to fix a failed query."""
    client = OpenAI(api_key=api_key)
    
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": f"You are a Cypher query fixer. Fix the query based on the error. Respond with ONLY the corrected query.\n\n{schema}"},
            {"role": "user", "content": f"Query:\n{failed_query}\n\nError:\n{error}\n\nFix the query:"},
        ],
        temperature=0,
        max_tokens=300,
    )
    
    return response.choices[0].message.content.strip()


def _try_execute(cypher: str) -> dict:
    """Attempt to execute Cypher. Returns success/failure with output/error."""
    conn = get_connection()
    try:
        result = conn.execute(cypher)
        
        # Format results
        rows = []
        columns = result.get_column_names()
        while result.has_next():
            rows.append(result.get_next())
        
        if not rows:
            return {"success": True, "output": "Query executed successfully but returned no results."}
        
        # Format as table
        parts = [f"Query returned {len(rows)} rows.\n"]
        parts.append("| " + " | ".join(str(c) for c in columns) + " |")
        parts.append("|" + "|".join("---" for _ in columns) + "|")
        for row in rows[:50]:
            parts.append("| " + " | ".join(str(v)[:80] for v in row) + " |")
        if len(rows) > 50:
            parts.append(f"\n... and {len(rows) - 50} more rows.")
        
        return {"success": True, "output": "\n".join(parts)}
    
    except Exception as e:
        return {"success": False, "error": str(e)}
```

**Verification**:
```python
from src.tools.ask_graph import run
# Requires OPENAI_API_KEY
result = run("What type of entity is the Danube?")
print(result)
assert "river" in result.lower()
```

---

### Step 4 — Update `registry.py`

Add the new tool to the registry:

```python
# Add to TOOLS list:
{
    "name": "ask_graph",
    "description": "Ask a natural language question about the knowledge graph. Generates and executes a Cypher query automatically. Use this for complex questions not covered by other tools.",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Natural language question"},
        },
        "required": ["question"],
    },
}
```

Update the `dispatch` function to include `ask_graph`:

```python
from . import ask_graph
handlers["ask_graph"] = ask_graph.run
```

---

### Step 5 — Test battery

`tests/test_07/test_questions.py`:

```python
"""Test battery: natural language questions → Cypher → correct answers."""
import os
import sys
sys.path.insert(0, ".")

from src.tools.ask_graph import run


TEST_QUESTIONS = [
    {
        "question": "What type of entity is the Danube?",
        "expected_in_result": ["river"],
        "difficulty": "trivial",
    },
    {
        "question": "Which pages mention rivers?",
        "expected_in_result": ["danube", "germany", "europe"],
        "difficulty": "easy",
    },
    {
        "question": "What entities appear in more than 2 pages?",
        "expected_in_result": ["Danube"],  # Danube appears in 4+ pages
        "difficulty": "medium",
    },
    {
        "question": "What countries does the Danube flow through?",
        "expected_in_result": ["Germany", "Austria", "Hungary"],
        "difficulty": "medium",
    },
    {
        "question": "Which entities are mentioned in both the Germany and Austria pages?",
        "expected_in_result": ["Danube", "Europe"],
        "difficulty": "hard",
    },
    {
        "question": "Which page has the most entity mentions?",
        "expected_in_result": [],  # Any valid answer is fine
        "difficulty": "medium",
    },
    {
        "question": "What predicates connect river entities to country entities?",
        "expected_in_result": ["flows_through"],
        "difficulty": "medium",
    },
    {
        "question": "What is the capital of Hungary according to the knowledge graph?",
        "expected_in_result": ["Budapest"],
        "difficulty": "medium",
    },
]


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set. Skipping LLM tests.")
        print("Set the variable and re-run to test Cypher generation.")
        return
    
    passed = 0
    failed = 0
    errors = []
    
    for i, test in enumerate(TEST_QUESTIONS, 1):
        question = test["question"]
        expected = test["expected_in_result"]
        difficulty = test["difficulty"]
        
        print(f"\n{'='*60}")
        print(f"Q{i} [{difficulty}]: {question}")
        
        result = run(question)
        
        # Check if expected terms appear in result
        result_lower = result.lower()
        missing = [term for term in expected if term.lower() not in result_lower]
        
        if "Failed to generate" in result or "Error:" in result:
            print(f"  FAILED (execution error)")
            print(f"  Result: {result[:200]}")
            failed += 1
            errors.append((i, question, "Execution failed"))
        elif missing:
            print(f"  PARTIAL — missing: {missing}")
            print(f"  Result preview: {result[:200]}")
            failed += 1
            errors.append((i, question, f"Missing: {missing}"))
        else:
            print(f"  PASSED")
            passed += 1
        
        print(f"  Result: {result[:150]}...")
    
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{len(TEST_QUESTIONS)} passed, {failed} failed")
    
    if errors:
        print("\nFailed questions:")
        for i, q, reason in errors:
            print(f"  Q{i}: {q}")
            print(f"       Reason: {reason}")
    
    # Success threshold: at least 6/8 should pass
    if passed >= 6:
        print("\nOverall: PASS (≥75% success rate)")
    else:
        print("\nOverall: NEEDS IMPROVEMENT (<75% success rate)")


if __name__ == "__main__":
    main()
```

**Run**:
```bash
conda activate knowledge-graph
OPENAI_API_KEY=... python tests/test_07/test_questions.py
```

---

### Step 6 — Schema description test (no LLM needed)

Verify the schema describer works independently:

```bash
python -c "
from src.tools.schema_describer import describe_schema
schema = describe_schema()
print(schema)
print()
print(f'Schema length: {len(schema)} chars (~{len(schema)//4} tokens)')

# Verify it contains all expected tables
assert 'Block' in schema
assert 'Page' in schema
assert 'Entity' in schema
assert 'HAS_BLOCK' in schema
assert 'LINKS_TO' in schema
assert 'MENTIONS' in schema
assert 'RELATES_TO' in schema
print('Schema description: OK')
"
```

---

## 4. Implementation order and dependencies

```
Step 1  (files)             — no dependencies
Step 2  (schema_describer)  — depends on LadybugDB db existing (Phase 05)
Step 3  (ask_graph)         — depends on Steps 2 + OPENAI_API_KEY
Step 4  (registry update)   — depends on Step 3
Step 5  (test battery)      — depends on Steps 3, 4 + OPENAI_API_KEY
Step 6  (schema test)       — depends on Step 2 only (no LLM)
```

Step 2 and Step 6 can be done and verified without an API key. Steps 3-5 require the key.

---

## 5. What Phase 07 does NOT validate

- **Automatic tool routing**: deciding whether to use `query_entity` or `ask_graph` for a given question is left to the calling LLM's judgment (based on tool descriptions).
- **Query caching**: repeated similar questions re-generate Cypher each time.
- **Complex path queries**: LadybugDB's path syntax differs from Neo4j. Some complex path queries may not work. This is documented as a known limitation.
- **Prompt optimization**: the few-shot examples are static. A future improvement could select examples most relevant to the incoming question.
- **Model comparison**: only tested with `gpt-4o-mini`. Other models (Claude, local) may need prompt adjustments.

---

## 6. Final system summary

After Phase 07, the complete tool set is:

| Tool | Use case | LLM cost |
|------|----------|----------|
| `query_entity` | "Tell me about X" | None (template) |
| `query_connection` | "How are X and Y related?" | None (template) |
| `query_page` | "Show me document Z" | None (template) |
| `search_mentions` | "Find references to Q" | None (template) |
| `query_cypher` | Run specific Cypher (power user) | None |
| `ask_graph` | Open-ended questions | 1-4 LLM calls for Cypher gen |

The recommended usage pattern for an LLM agent:
1. Try template tools first (free, deterministic, fast).
2. Fall back to `ask_graph` only for complex multi-hop questions.
3. Use `query_cypher` directly only if the agent already knows the exact Cypher needed.

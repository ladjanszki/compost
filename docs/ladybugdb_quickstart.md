# LadybugDB & Graph Knowledge Base: Quickstart & Cheat Sheet

Welcome to your Graph Database learning journey! This guide will help you understand how your Djot files are converted into a Graph and how you can query that structure to uncover insights.

We will use three sample files about probability and math to demonstrate how nodes (entities) and edges (relationships) form a knowledge graph.

---

## 1. The Graph Model (How to think about the data)

In our Agentic Local Knowledge Store, we don't just store text. We break it down hierarchically and semantically. 

Think of the database conceptually as two types of **Nodes** (circles) and two types of **Edges** (arrows):
1. **`Page` Node**: Represents an entire document (e.g., "Probability Theory").
2. **`Block` Node**: Represents a specific paragraph, heading, list, or code block within that page.
3. **`HAS_BLOCK` Edge**: Connects a `Page` to its `Block`s. It has a `position` property so we know the order of blocks.
4. **`LINKS_TO` Edge**: Connects a `Block` directly to a target `Page` if that block contains a Markdown/Djot link (e.g., `[Stochastic Process](stochastic_process.dj)`).

### Cypher Syntax Basics
LadybugDB uses **Cypher**, a declarative graph query language. 
- Nodes are wrapped in parentheses: `(p:Page)` means "Match a node of type Page and assign it to the variable `p`".
- Edges are wrapped in brackets: `-[r:LINKS_TO]->` means "Match an edge of type LINKS_TO pointing to the right, and assign it to variable `r`".
- Together, they form ASCII art of the graph pattern: `(p:Page)-[:HAS_BLOCK]->(b:Block)`

---

## 2. Ingesting the Sample Data

We have prepared three Djot files in `sample_data/math/`:
- `probability.dj`
- `stochastic_process.dj`
- `markov_chain.dj`

You can test the ingestion pipeline using the provided `run_quickstart.py` script.
```bash
conda run -n knowledge-graph python run_quickstart.py
```

---

## 3. Query Cookbook

Here are a few ways to query the graph, ranging from basic to advanced. 
You can run these queries in your Python code via `conn.execute(query)`.

### Recipe 1: Retrieve all pages
**Goal**: Just see what documents exist in our graph.
```cypher
MATCH (p:Page) 
RETURN p.id, p.title
```
*How to think about it*: We aren't looking for edges here, just grabbing every node labeled `Page`.

### Recipe 2: Reconstruct a page sequentially
**Goal**: Find all blocks that belong to the "Markov Chain" page and put them in reading order.
```cypher
MATCH (p:Page {title: 'Markov Chain'})-[r:HAS_BLOCK]->(b:Block) 
RETURN b.type, b.text
ORDER BY r.position
```
*How to think about it*: Find a specific Page node. Follow its `HAS_BLOCK` arrows to the `Block` nodes. Sort the results based on the `position` property stored *on the edge* (`r`).

### Recipe 3: Block content search
**Goal**: Find any block in the entire database that mentions "random".
```cypher
MATCH (p:Page)-[:HAS_BLOCK]->(b:Block)
WHERE b.text CONTAINS 'random'
RETURN p.title, b.type, b.text
```
*How to think about it*: Graph DBs are great at structural queries, but you can also do basic text filtering. Notice how we return the `p.title` so we know *which* page contains the text.

---

## 4. "Interesting" Graph Queries (Network Analysis)

This is where Graph DBs shine compared to SQL or Document databases. 

### Recipe 4: Page-to-Page Citation Map
**Goal**: Which pages cite which other pages?
Because our links go from `Block` -> `Page`, we have to traverse: `Page -> Block -> Page`.
```cypher
MATCH (p1:Page)-[:HAS_BLOCK]->(b:Block)-[:LINKS_TO]->(p2:Page)
RETURN p1.title AS source_page, p2.title AS target_page, b.text AS context
```
*How to think about it*: We are drawing a path: "Find a Page (`p1`), that has a Block (`b`), that links to another Page (`p2`)". 
This immediately generates a citation network and gives you the exact sentence (`b.text`) where the citation occurred!

### Recipe 5: Finding Backlinks (What links to "Probability Theory"?)
**Goal**: Find all paragraphs (and their source documents) that reference Probability.
```cypher
MATCH (source_page:Page)-[:HAS_BLOCK]->(b:Block)-[:LINKS_TO]->(target:Page {title: 'Probability Theory'})
RETURN source_page.title, b.text
```
*How to think about it*: We anchor the right side of the query to a specific target page, and ask the graph engine to traverse *backwards* through incoming links to find the sources.

### Recipe 6: Aggregating Graph Data
**Goal**: Which page has the most code blocks?
```cypher
MATCH (p:Page)-[:HAS_BLOCK]->(b:Block {type: 'code_block'})
RETURN p.title, count(b) AS code_block_count
ORDER BY code_block_count DESC
```
*How to think about it*: Cypher automatically groups by the non-aggregated variables in the `RETURN` clause (in this case, `p.title`), and calculates the `count(b)` for each group.

---

## 5. Next Steps for Learning

As you continue building the Agentic Local Knowledge Store:
1. Try modifying `sample_data/math/probability.dj` by adding a link to a file that *doesn't exist* yet. Run the ingestion. Query the database to find "Dangling Links" (Pages that exist as a target of `LINKS_TO` but have no outgoing `HAS_BLOCK` edges).
2. Think about how LLM Agents could use Recipe 5 (Backlinks) to quickly summarize the context surrounding a concept.
3. The graph makes features like "Local Graph View" (the connected nodes visualization you see in Obsidian or Roam) a simple `MATCH (p1)-[*1..2]-(p2)` query!

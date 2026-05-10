# Product Evolution & Deferred Architectural Decisions

This document captures the in-depth history, debates, and technical assessments of visionary product features that were discussed during the conceptualization of the Agentic Local Knowledge Store. 

While the current codebase strictly implements a headless `Djot → Parquet → LadybugDB` pipeline, the topics below outline the broader "LLM Wiki" product vision. They are structured as Architectural Decision Records (ADRs) to preserve the original reasoning and evaluate their feasibility against today's technical reality.

---

## 1. The Human / Reader Interface (Static HTML & Block IDs)

**Context:** 
The knowledge graph was never intended to be exclusively read by LLMs. The user required a way to read documents on mobile devices and easily reference specific sections without needing a complex code editor.

**The Debate (WYSIWYG vs. Dumb Frontend):**
There was a significant debate regarding how users would interact with the system. One approach considered integrating a rich WYSIWYG editor (like BlockNote) to allow live, block-based editing in the browser. The competing approach argued that building and maintaining a reliable read/write web editor is notoriously difficult and couples the frontend too tightly to the backend graph schema. 

**The Historical Decision:**
The project explicitly rejected the WYSIWYG editor approach. The decision was to completely remove the browser as a write surface. Instead, the frontend would be "dumb"—a statically rendered HTML site generated from the Djot files. The only interactivity required was a lightweight JavaScript snippet that allowed a user to click on a rendered block to copy its native Djot `{#block_id}` to the clipboard. 

**Technical Assessment (Relevance Today):**
*Status: Highly Relevant & Feasible*
This decision perfectly aligns with the current `djot.js` implementation. Djot natively supports block IDs, and pandoc/djot parsers can trivially render these documents into static HTML with `<div id="block_id">` tags. Because the current LadybugDB database acts purely as a headless backend, an independent script (e.g., `render.py`) could easily read the `.dj` files and output a static site without disrupting the core ingestion pipeline.

---

## 2. The Async Editing & Commenting Workflow

**Context:**
If the browser is strictly read-only, how does a user make edits or leave notes while reading on a mobile device? 

**The Debate (Direct Edits vs. Decoupled Annotations):**
The standard model is to open an editor, find the typo, and fix it directly. However, the user workflow prioritized capturing thoughts "on the go." Forcing a user to open a Markdown editor on a mobile phone to fix a typo or add a thought creates high friction. The alternative was a decoupled, asynchronous loop where comments are submitted separately from the document source.

**The Historical Decision:**
The project adopted the "Async Commenting" model. A user reading the static HTML copies a block ID (e.g., `{#para-123}`), pastes it into an arbitrary external text channel (like an email, Apple Notes, or a dedicated chat interface), and writes their comment (e.g., *"#para-123 This assumption is wrong, update it based on the new API docs"*).
Crucially, these comments do *not* instantly mutate the document. They are processed by an LLM agent which proposes a diff. The user later reviews this proposed diff on their desktop (via Neovim or terminal) in a Human-In-The-Loop (HITL) review step before the canonical Djot file is altered.

**Technical Assessment (Relevance Today):**
*Status: Relevant, but technically blocked by Block ID Lifecycle (Risk #11)*
The workflow is conceptually brilliant for AI-assisted workspaces. However, the current LadybugDB/Djot implementation does not explicitly manage Block ID stability upon edits. If an LLM or user manually edits a Djot file and the parser generates a *new* block ID for that paragraph during the next ingestion, any pending asynchronous comments pointing to the *old* ID will become orphaned ("dangling references"). Implementing this requires solving the block versioning problem first.

---

## 3. Expanded Graph Schema (Annotations & Temporal Quadruplets)

**Context:**
The current LadybugDB schema is structural (`Page -> HAS_BLOCK -> Block`) and minimally semantic (`Block -> MENTIONS -> Entity`). To support the async workflow and rich historical analysis, the graph needs to hold more complex data.

**The Debate (Triplets vs. Quadruplets & Edge Properties vs. Reified Nodes):**
1. *Annotations:* Should comments just be appended to the source text, or treated as graph entities?
2. *Time:* Standard semantic extraction creates triplets (`Subject - Predicate -> Object`). But knowledge changes over time. The debate centered on how to store time: as a simple timestamp property on the edge, or by upgrading triplets to "Quadruplets" (`Subject, Predicate, Object, Time`). Furthermore, should complex relationships be stored as properties on LadybugDB edges, or as distinct "Reified Statement Nodes" (RDF-star style) so that other nodes can point *to the relationship itself*?

**The Historical Decision:**
1. Comments must be first-class `Annotation` nodes in the graph, linked to `Block` nodes, carrying provenance (author, timestamp, source channel).
2. The semantic layer must support temporal dimensions (Quadruplets) to track when relationships are valid.

**Technical Assessment (Relevance Today):**
*Status: Partially Feasible, Requires Schema Upgrades*
Adding an `Annotation` node to LadybugDB is trivial; it just requires a schema migration script. 
However, implementing Temporal Quadruplets requires careful design in LadybugDB's strict property graph model. LadybugDB does not natively support edges pointing to other edges (reification). Therefore, complex time-bound relationships might need to be modeled as intermediate nodes (e.g., an `Employment` node connecting a `Person` and a `Company` with `start_date` and `end_date` properties), rather than simple edges. This will significantly complicate the Cypher queries planned for Phase 06/07.

---

## 4. Advanced Data Lifecycle & Ingestion

**Context:**
Currently, when a Djot file is updated, the entire LadybugDB database is wiped and rebuilt from scratch via bulk Parquet loading. 

**The Debate (Wipe-and-Rebuild vs. Incremental Deltas):**
In the early proof-of-concept phase, wipe-and-rebuild was acceptable because structural parsing is fast. However, as the project planned for Phase 05 (Semantic Extraction via LLMs), it became obvious that re-extracting entities for thousands of unchanged blocks on every file save would be prohibitively expensive in terms of API costs and rate limits. 

**The Historical Decision:**
The system *must* eventually support incremental delta ingestion. The database should only ingest new or modified blocks, preserving the historical versions of old blocks so that annotations and semantic edges remain intact.

**Technical Assessment (Relevance Today):**
*Status: Critical Tech Debt (Risks #7 and #11)*
This is the most pressing technical friction in the current architecture. LadybugDB's embedded, single-writer nature makes complex incremental upserts (`MERGE` statements) much slower than bulk `COPY FROM` operations. 
To implement delta detection, the ingestion script (`ingest_page.py`) must be upgraded to:
1. Hash the incoming Djot block content.
2. Query LadybugDB to see if a block with that ID and hash already exists.
3. If it exists, skip it. If it changed, insert the new block and either delete the old one or mark it as `superseded_by`.
This logic must be built in Python *before* Phase 05 is operationalized at scale.

---

## 5. Orchestration & Ecosystem (LangGraph)

**Context:**
Managing complex workflows—like taking a raw document, extracting entities, checking against existing canonical entities, resolving duplicates, generating proposed diffs, and waiting for HITL approval—requires state management.

**The Debate (Python Tools vs. Agentic Frameworks):**
Should the system use a heavy framework like LangGraph, or keep everything as minimal, pure Python functions? The user heavily values transparency, minimal scaffolding, and auditability ("no parts which are not auditable between my message and the API call"). However, managing mid-extraction crash recovery and HITL pauses in pure Python requires reinventing a state machine.

**The Historical Decision:**
The project initially explored LangGraph for the extraction pipeline. However, the documented decision in the current repository explicitly scoped out "LLM Orchestration," settling on exposing pure Python tool functions (Phase 06) and letting the external caller (whatever LLM client the user prefers) manage the state.

**Technical Assessment (Relevance Today):**
*Status: Strategically Resolved*
The current approach—providing raw, stateless Python tools that return token-efficient Djot text—is highly robust. It allows the knowledge graph to remain a pure, fast, embeddable database. If the user decides to reintroduce LangGraph, it should exist in a completely separate repository (the "Agent Client") that imports the `knowledge-graph` as a library, rather than tangling LangGraph dependencies into this core storage engine.
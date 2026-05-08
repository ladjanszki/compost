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

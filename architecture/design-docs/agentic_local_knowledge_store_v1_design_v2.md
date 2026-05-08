# Agentic Local Knowledge Store — v1 Design (Revised)

## 1. Purpose

This document defines the v1 architecture for a local-first, block-based knowledge system designed for safe human and agent interaction.

The goal is to create a small, auditable substrate where:

- documents can be rendered locally and read in a browser;
- conversations can happen over those documents;
- agents can participate in conversations and mutate content;
- all changes are traceable and rollbackable;
- the canonical format is JSON, readable without any editor or application.

The goal is **not** to build a general-purpose note-taking app, a rich document editor, or an Anytype/Obsidian replacement.

## 2. Core user requirements

These are the load-bearing requirements that drive every design decision. If a feature or constraint cannot be traced back to one of these, it does not belong in v1.

| ID | Requirement |
|----|-------------|
| R1 | I can read rendered documents locally in a browser, including tables, math, images, and syntax-highlighted code. |
| R2 | Every rendered block carries a stable, copyable unique identifier so I can reference it precisely from any external tool. |
| R3 | I can have free-standing conversations not attached to any document. This is a primary working mode. |
| R4 | Agents can participate in conversations and mutate documents. |
| R5 | Agents cannot silently destroy content. All mutations create new block versions; all previous versions are retained. |
| R6 | The canonical format is JSON, readable and parseable without any editor or application. |
| R7 | The system is local-first. No internet, no auth, no multi-user. |
| R8 | I can author and edit canonical documents in a text editor (vim). The browser is a reader, not a writer. |

## 3. Core thesis

The system treats documentation, comments, agent discussions, and review feedback as structured data, not as mutable Markdown files.

The central design rule is:

> No content is ever destroyed. All changes produce new block versions. All previous versions are retained. Every mutation is traceable to an author and a point in time.

### Why JSON and not Markdown as canonical format?

The choice of JSON over Markdown was driven by experience with Markdown-based workflows (Obsidian). In Markdown:

- block-level identity is fragile, dependent on convention rather than enforcement;
- agent edits cannot be reliably scoped to specific blocks — an agent asked to modify one paragraph can accidentally overwrite adjacent content;
- two-way sync between a canonical format and rendered Markdown is error-prone and creates a large class of subtle bugs.

JSON blocks with stable IDs make immutability and targeting enforceable rather than conventional.

Markdown may still be supported later as an export format, but it is not the canonical storage format in v1.

## 4. v1 scope

### Included in v1

1. Canonical JSON-based storage in JSONL files.
2. Versioned blocks with stable IDs.
3. Page documents composed of block references.
4. Conversation documents for both free-standing chats and contextual comments.
5. Mutations as the atomic unit of change, with full rollback capability.
6. Pre-rendered local HTML pages generated from page documents.
7. Stable, copyable block IDs embedded in rendered HTML.
8. Message-level attachments linking messages to blocks, pages, or other conversations.
9. Agent mentions in messages to signal that a specific agent's input is requested.
10. Local-only serving through a localhost web server.
11. Human authoring through a text editor (vim or equivalent).

### Excluded from v1

1. Any browser-side writing — no comment box, no sidebar chat, no accept button, no text input.
2. A WYSIWYG document editor.
3. Markdown round-tripping.
4. Real-time collaboration.
5. Multi-user permissions.
6. Remote sync.
7. CRDTs.
8. Public internet deployment.
9. Mobile apps.
10. A plugin system.
11. Rich database views.
12. Semantic folder-based collections.
13. A separate comment object model (comments are conversations).
14. Proposal-based review workflow (replaced by direct mutation with rollback).
15. A browser-based conversation UI (conversations are authored in a text editor or via API).

## 5. Local-first assumption

The system is designed to run locally.

A typical v1 deployment is:

```text
localhost web server (serves generated HTML, exposes API)
+ JSONL files as canonical storage
+ a renderer that generates HTML from canonical data
+ local agent processes that interact via API
+ a human who authors content in a text editor
```

This means v1 does not need to solve:

- account management;
- authentication or authorization;
- remote synchronization;
- collaborative conflict resolution;
- encryption for network transport;
- public hosting security.

## 6. Storage model

### Logical model

The store contains three object kinds:

```text
block       — versioned content unit
page        — renderable document composed of block references
conversation — ordered sequence of messages with optional attachments
```

Mutations are not a separate object kind. A mutation is a new version of an existing block. The block version history *is* the mutation log.

### Physical storage: JSONL files

In v1, each object kind is stored in a single JSONL file (one JSON object per line). This aligns naturally with a future migration to a document database where each line becomes a document in a collection.

```text
store/
  blocks.jsonl
  pages.jsonl
  conversations.jsonl

site/
  generated/
    index.html
    docs/
      doc_001.html
      doc_002.html
    assets/
      style.css
```

### Why JSONL?

- One file per object kind, not thousands of tiny files.
- Append-friendly — new block versions and new messages are appended.
- Directly loadable into document databases (MongoDB, DuckDB) when the time comes.
- Inspectable with standard command-line tools (`grep`, `jq`, `head`).
- Git-friendly for line-level diffs.

### Design note: physical storage is an implementation detail

The design is independent of the physical storage format. JSONL is chosen for v1. A later version may use DuckDB, MongoDB, or another document database. The logical model (blocks, pages, conversations) remains the same regardless of backend.

## 7. Blocks

A block is a versioned content unit. It represents a paragraph, heading, list item, code block, image reference, quote, or other content element.

### Block identity model

A block has a **stable ID** that persists across all versions. When a block is mutated, the ID stays the same and a new version is created. All previous versions are retained.

This means:

- every reference to a block (from pages, attachments, conversations) uses the stable block ID;
- references never need to be remapped when a block changes;
- the current content of a block is always the latest version;
- any previous version is retrievable by ID + version number.

### Block schema

```json
{
  "id": "blk_456",
  "version": 1,
  "schema": "block.v1",
  "type": "paragraph",
  "content": {
    "text": "The cache is invalidated when the source document changes."
  },
  "created_by": "human:istvan",
  "created_at": "2026-05-06T12:00:00Z",
  "hash": "sha256:abc123..."
}
```

After mutation:

```json
{
  "id": "blk_456",
  "version": 2,
  "schema": "block.v1",
  "type": "paragraph",
  "content": {
    "text": "The cache is invalidated when the source document or any declared dependency changes."
  },
  "created_by": "agent:writer",
  "created_at": "2026-05-06T12:10:00Z",
  "hash": "sha256:def789...",
  "parent_version": 1,
  "mutation_context": {
    "conversation_id": "conv_002",
    "message_id": "msg_004"
  }
}
```

Both versions exist in `blocks.jsonl`. The page document references `blk_456` without specifying a version — the renderer always uses the latest version.

### Key fields

| Field | Purpose |
|-------|---------|
| `id` | Stable block identity. Never changes across versions. |
| `version` | Integer version counter. Monotonically increasing per block ID. |
| `schema` | Schema identifier. In v1, always `"block.v1"`. Exists to support future format evolution. |
| `type` | Content type: `paragraph`, `heading`, `code`, `list_item`, `quote`, `image`, etc. |
| `content` | Type-specific content payload. See §7.1. |
| `created_by` | Author identifier in `namespace:name` format (e.g., `human:istvan`, `agent:writer`). |
| `created_at` | ISO 8601 timestamp of version creation. |
| `hash` | SHA-256 hash of the serialized `content` field. Computed at creation time. Cheap to produce, useful for integrity verification and future deduplication. |
| `parent_version` | Version number this version was derived from. Absent on version 1. |
| `mutation_context` | Optional. Links this version to the conversation/message that caused it. |

### Why versioned blocks with stable IDs?

The alternative considered was generating a new block ID on every mutation and remapping all references (page document `root` arrays, conversation attachments, etc.). This was rejected because:

- remapping is risky — a missed reference creates a dangling pointer;
- it makes the attachment model fragile — a conversation referencing `blk_456` would break if the block is replaced by `blk_789`;
- it forces every mutation to also update the page document and potentially many conversation records;
- the stable-ID model is more intuitive: "block 456 was updated" vs. "block 456 was deleted and block 789 was created."

With stable IDs:

- pages reference block IDs and always get the latest content on render;
- conversation attachments referencing a block remain valid forever;
- rollback is trivial: point the "current version" back to a previous version number;
- the version history of any block is a simple query: all records with the same `id`, ordered by `version`.

### Why keep the `hash` field?

The hash is computed once at block creation from the serialized `content` field. In Python this is essentially free (`hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()`).

It provides:

- integrity verification — detect corruption in storage or transit;
- deduplication potential — detect when two versions have identical content;
- a foundation for future content-addressing if needed.

The hash does not drive any v1 logic. It is a cheap investment in future capability.

### 7.1 Block content types

The `content` field is type-specific. v1 supports these types:

**paragraph**
```json
{ "text": "The cache is invalidated when the source document changes." }
```

**heading**
```json
{ "text": "Cache invalidation", "level": 2 }
```

**code**
```json
{ "text": "def invalidate(key):\n    cache.pop(key, None)", "language": "python" }
```

**list_item**
```json
{ "text": "Check the source document timestamp.", "style": "unordered" }
```

**quote**
```json
{ "text": "Premature optimization is the root of all evil.", "attribution": "Donald Knuth" }
```

**image**
```json
{ "src": "assets/diagram_001.png", "alt": "Cache flow diagram", "caption": "Figure 1: Cache invalidation flow" }
```

The `text` fields within block content support a lightweight inline markup format. See §7.2.

### 7.2 Inline markup within block content

Block `text` fields are not plain text and not full Markdown. They use a minimal inline markup subset sufficient for emphasis, code spans, and links.

The v1 inline markup vocabulary:

| Syntax | Meaning |
|--------|---------|
| `**bold**` | Bold / strong emphasis |
| `*italic*` | Italic / emphasis |
| `` `code` `` | Inline code span |
| `[text](url)` | Hyperlink |
| `~~strikethrough~~` | Strikethrough |

This is a strict subset of CommonMark inline syntax. It is intentionally minimal.

Block-level structure (headings, lists, code blocks, quotes) is represented by block `type`, not by inline markup. A `text` field inside a heading block does not need `#` prefixes. A `text` field inside a code block does not need triple backticks.

### Why this approach to content format?

The problem: plain text is too limited (no emphasis, no code spans, no links), but a full document grammar for message/block content adds significant complexity.

The solution: reuse a well-known subset of CommonMark inline syntax within text fields. This means:

- humans can write it naturally in vim;
- agents produce it fluently (it is the format they default to);
- parsing is simple — a CommonMark inline parser handles it;
- rendering is straightforward — inline markup maps directly to HTML `<strong>`, `<em>`, `<code>`, `<a>`, `<del>`;
- there is no ambiguity about block structure because block structure is encoded in the block `type`, not in the text content.

This same inline markup is also used in conversation message bodies (§10).

## 8. Page documents

A page document is a renderable document composed of an ordered list of block references.

### Page schema

```json
{
  "id": "doc_001",
  "schema": "page.v1",
  "title": "Cache invalidation",
  "root": [
    "blk_heading_001",
    "blk_456",
    "blk_457"
  ],
  "created_by": "human:istvan",
  "created_at": "2026-05-06T12:00:00Z",
  "updated_at": "2026-05-06T12:00:00Z"
}
```

The `root` field is an ordered list of block IDs. The renderer resolves each ID to its latest version and produces HTML.

### Decision: pages are rendered, not edited in the browser

In v1, pages are rendered to local HTML files. The browser provides no editing capability — not even a comment box.

The browser is a **reading surface** with one interactive affordance: each block displays a copyable unique identifier so the user can reference it precisely from a text editor, conversation, or external tool.

### Why pre-rendered HTML?

Pre-rendering was chosen over on-request server rendering to:

- keep the serving layer trivial (static file server + API for writes);
- make the generated output inspectable as plain HTML files;
- create a natural barrier between generated knowledge artifacts (pages) and input — one cannot write into the finished product, only create new versions through the canonical data layer.

This functional separation increases robustness: the rendered HTML is a pure projection. It can be deleted and regenerated from the store at any time.

### Why no browser-side writing in v1?

The browser is excluded as a write surface in v1 because:

- it avoids building any interactive UI components (sidebar chat, text input, accept/reject buttons);
- the user's primary authoring tool is already a text editor (vim);
- all that is needed from the browser is the ability to copy a block's unique identifier for precise referencing;
- conversations and comments are authored via text editor or API, using the same JSONL files and endpoints that agents use.

A future version may add browser-side interaction, but v1 does not require it.

## 9. Rendered HTML

Each rendered block must include stable, copyable identity metadata.

Example:

```html
<section
  class="doc-block"
  data-doc-id="doc_001"
  data-block-id="blk_456"
  id="blk_456"
>
  <p>The cache is invalidated when the source document changes.</p>
  <span class="block-id" title="Click to copy block ID">blk_456</span>
</section>
```

### Critical invariant

Every rendered block must carry a stable block ID that is visible and copyable.

This invariant enables:

- precise referencing from a text editor or conversation;
- contextual conversations attached to specific blocks;
- mutation targeting;
- source references and attribution;
- audit views showing version history per block;
- future diffing and export/import tooling.

### Rendered page features

A generated page includes:

- the page body rendered from the latest block versions;
- a visible, copyable block ID on every block;
- a version indicator per block (e.g., `v3` badge) showing how many versions exist;
- conversation count per block — how many conversations reference this block;
- a link to the block's version history view;
- page-level metadata (title, last updated, block count).

## 10. Conversations

Conversation is the primary interaction primitive.

There is no separate data model for comments, comment threads, chats, agent discussions, or block annotations. All of these are conversations.

A conversation is an ordered sequence of messages. Each message has an author, a timestamp, a body, and optional attachments.

### Conversation schema

```json
{
  "id": "conv_001",
  "schema": "conversation.v1",
  "title": "Architecture discussion",
  "status": "open",
  "created_at": "2026-05-06T12:00:00Z",
  "updated_at": "2026-05-06T12:00:00Z",
  "messages": [
    {
      "id": "msg_001",
      "author": "human:istvan",
      "created_at": "2026-05-06T12:00:00Z",
      "body": "Help me think through the architecture.",
      "attachments": [],
      "mentions": []
    }
  ]
}
```

### Message body format

Message bodies use the same inline markup as block `text` fields (§7.2): a minimal CommonMark inline subset supporting bold, italic, code spans, links, and strikethrough.

This means messages can contain formatted text, inline code, and links, without requiring a full document grammar. Both humans (writing in vim) and agents (who naturally produce Markdown-like text) can author messages fluently.

### Message attachments

A message may attach references to:

- a block: `{ "type": "block", "doc_id": "doc_001", "block_id": "blk_456" }`
- a page: `{ "type": "page", "doc_id": "doc_001" }`
- another conversation: `{ "type": "conversation", "conversation_id": "conv_002" }`

Attachments are references, not copies. They point to the canonical object by ID.

### Agent mentions

A message may include mentions to signal that a specific agent's (or human's) input is requested:

```json
{
  "id": "msg_005",
  "author": "human:istvan",
  "body": "Can you review this block and suggest improvements?",
  "attachments": [
    { "type": "block", "doc_id": "doc_001", "block_id": "blk_456" }
  ],
  "mentions": [
    "agent:senior-data-engineer"
  ]
}
```

The `mentions` field is a list of participant identifiers in `namespace:name` format.

#### How mentions work

Mentions are the signaling mechanism for agent invocation. An external agent process monitors conversations (via API polling, file watching, or other mechanism) and looks for mentions matching its own identifier.

When an agent sees a mention:

1. It reads the message and its attachments.
2. It reads any referenced blocks or documents.
3. It produces a response by appending a new message to the conversation.
4. If appropriate, it mutates blocks (creating new versions with `mutation_context` pointing to this conversation).

The invocation mechanism itself (how the agent process runs, polls, or gets triggered) is outside the scope of this design. The mention is the *data model* for "I want your input here." The operational trigger is an implementation concern.

#### Why mentions?

Without mentions, there is no tractable way to direct work across many open conversations. A human cannot remember which of dozens of conversations need agent attention. An agent cannot efficiently scan every message. Mentions create an explicit, queryable signal: "this message is addressed to you."

Mentions can be queried from the JSONL store or API:

```text
GET /api/conversations?mention=agent:senior-data-engineer&status=open
```

This returns all open conversations where the specified agent has been mentioned but has not yet responded.

### Free-standing conversations

A free-standing conversation is a conversation where the first message has no block or page attachments. It is started from scratch, not from a rendered document.

Example:

```json
{
  "id": "conv_003",
  "schema": "conversation.v1",
  "title": "Explore new caching strategy",
  "status": "open",
  "created_at": "2026-05-06T14:00:00Z",
  "updated_at": "2026-05-06T14:00:00Z",
  "messages": [
    {
      "id": "msg_010",
      "author": "human:istvan",
      "created_at": "2026-05-06T14:00:00Z",
      "body": "I want to explore whether we should switch from LRU to LFU caching. @agent:architect what do you think?",
      "attachments": [],
      "mentions": ["agent:architect"]
    }
  ]
}
```

Free-standing conversations are a primary working mode. They are used for brainstorming, design discussions, agent-assisted research, and any work that is not yet tied to a specific document.

### Comments as conversations

A "comment" is a conversation whose first message is attached to a block. There is no separate comment model.

When the user wants to comment on a specific block, they:

1. Copy the block ID from the rendered page.
2. Create a new conversation (or append to an existing one) with the block ID as an attachment on the message.

Example:

```json
{
  "id": "conv_004",
  "schema": "conversation.v1",
  "title": "Comment on cache invalidation paragraph",
  "status": "open",
  "created_at": "2026-05-06T12:05:00Z",
  "updated_at": "2026-05-06T12:05:00Z",
  "messages": [
    {
      "id": "msg_011",
      "author": "human:istvan",
      "created_at": "2026-05-06T12:05:00Z",
      "body": "This paragraph needs a concrete example. @agent:writer can you draft one?",
      "attachments": [
        { "type": "block", "doc_id": "doc_001", "block_id": "blk_456" }
      ],
      "mentions": ["agent:writer"]
    }
  ]
}
```

### Decision: unify comments and conversations

During design, separate comment and conversation models were considered and rejected. The key insight was that a comment on a block frequently evolves into a multi-turn discussion with agent participation, block mutation, and resolution. Maintaining two models (comment thread + conversation) would require either migration between them or duplicated behavior. A single conversation model with message-level attachments handles both cases with no additional complexity.

### How conversations for a block are found

To find all conversations referencing a specific block, query messages whose attachments include:

```json
{ "type": "block", "doc_id": "doc_001", "block_id": "blk_456" }
```

This query is used during rendering to show conversation counts on each block.

### Conversation status

A conversation has a `status` field:

- `open` — active, may have unresolved questions or pending work.
- `resolved` — the topic has been addressed. No further input expected.
- `archived` — removed from active views.

## 11. Mutations

A mutation is a new version of an existing block. There is no separate "mutation" or "proposal" object kind. The block version history *is* the mutation log.

### How mutation works

When a block needs to change:

1. A new record is appended to `blocks.jsonl` with the same `id`, an incremented `version`, the new `content`, and metadata about who created it and why.
2. The page document does not change — it still references the block by its stable ID.
3. The renderer picks up the latest version on the next regeneration.

### Who can mutate?

In v1, both humans and agents can create new block versions.

Agents are not gated by a proposal/review workflow. The safety model is:

- **Immutability**: no version is ever deleted or overwritten. The old content is always there.
- **Traceability**: every version records its author, timestamp, parent version, and optionally the conversation that caused it.
- **Rollback**: reverting to a previous version is a new mutation that copies the old version's content forward with a new version number. This preserves the full history.

This is sufficient for v1 because:

- the human cannot realistically review every agent-generated change before it happens;
- the worst case is an agent creating a bad version, which is trivially rolled back;
- the system is local and single-user — there is no risk of conflicting concurrent writes from multiple untrusted parties;
- the rendered pages and conversations provide the natural review surface: the human reads generated content, notices problems, and starts conversations to fix them.

### Decision: mutations over proposals

The original design included a proposal/accept workflow where agents suggest changes and humans approve them before they take effect. This was replaced with direct mutation + rollback because:

- the user cannot audit every change in real-time — the system generates too much content for pre-approval;
- proposals add an entire object kind (proposal), lifecycle states (pending, accepted, rejected), and UI requirements (accept/reject buttons in the browser);
- the immutable version history provides equivalent safety — no content is lost, all changes are traceable, rollback is trivial;
- the workflow matches the user's actual pattern: agents generate, the user reads and corrects, rather than the user pre-approving every change.

### Rollback

To roll back block `blk_456` from version 3 to version 1:

```json
{
  "id": "blk_456",
  "version": 4,
  "schema": "block.v1",
  "type": "paragraph",
  "content": {
    "text": "The cache is invalidated when the source document changes."
  },
  "created_by": "human:istvan",
  "created_at": "2026-05-06T13:00:00Z",
  "hash": "sha256:abc123...",
  "parent_version": 3,
  "rollback_to": 1,
  "mutation_context": {
    "conversation_id": "conv_005",
    "message_id": "msg_020"
  }
}
```

The `rollback_to` field explicitly records that this version is a rollback. The content is copied from version 1. The `parent_version` is 3 (the version that was current before rollback). The hash should match version 1's hash.

## 12. Rendering and regeneration

The renderer converts canonical data into local HTML files.

### Input

```text
blocks.jsonl   (latest version of each block)
pages.jsonl    (page structure)
conversations.jsonl (for conversation counts per block)
```

### Output

```text
site/generated/
  index.html
  docs/
    doc_001.html
    doc_002.html
  blocks/
    blk_456_history.html    (optional: version history view)
  assets/
    style.css
```

### When does regeneration happen?

In v1, regeneration is manually triggered:

- via CLI command: `python render.py` (or equivalent);
- or via API endpoint: `POST /admin/regenerate`.

Automatic regeneration on data change is deferred. The user is responsible for regenerating after block mutations or conversation changes.

### Decision: generated pages are projections

Generated HTML is not canonical. It can be deleted and regenerated from the store.

This gives clean separation:

```text
JSONL files = durable truth
HTML = read-only view
browser = reading surface with copyable block IDs
```

The functional separation is deliberate: one cannot write into the finished product. To change content, you create a new block version through the canonical data layer. This functional-style barrier increases robustness — there is no path from "looking at a page" to "accidentally modifying its source."

## 13. Indexes

Certain queries require scanning all records in a JSONL file. For v1, a lightweight index is needed to make common queries efficient.

### Required indexes

**Attachment index**: maps block/page references in conversation message attachments to conversation IDs. Used during rendering to show conversation counts per block.

**Block latest version index**: maps block IDs to their latest version number and line offset in `blocks.jsonl`. Used during rendering to resolve page block references.

**Mention index**: maps agent/human identifiers to conversation IDs where they are mentioned. Used by agents to find conversations addressed to them.

### Implementation

In v1, indexes are SQLite tables rebuilt from the JSONL files during regeneration or on demand:

```sql
CREATE TABLE attachment_index (
    conversation_id TEXT,
    message_id TEXT,
    target_type TEXT,      -- 'block', 'page', 'conversation'
    target_doc_id TEXT,
    target_block_id TEXT
);

CREATE TABLE block_latest (
    block_id TEXT PRIMARY KEY,
    latest_version INTEGER,
    line_offset INTEGER
);

CREATE TABLE mention_index (
    conversation_id TEXT,
    message_id TEXT,
    mentioned_id TEXT       -- e.g., 'agent:senior-data-engineer'
);
```

Indexes are projections, like HTML. They can be deleted and rebuilt from canonical JSONL files.

## 14. Minimal API shape

The local server exposes endpoints for both the browser (serving generated HTML) and external processes (agents, CLI tools, scripts).

```text
# Serving generated pages
GET  /docs/{doc_id}

# Reading canonical data
GET  /api/blocks/{block_id}
GET  /api/blocks/{block_id}/history
GET  /api/pages/{doc_id}
GET  /api/conversations
GET  /api/conversations/{conversation_id}
GET  /api/conversations?attached_to_block={block_id}
GET  /api/conversations?mention={agent_id}&status=open

# Writing
POST /api/blocks/{block_id}/versions          — create new block version
POST /api/blocks                               — create new block (version 1)
POST /api/pages                                — create new page
PATCH /api/pages/{doc_id}                      — update page structure (root list)
POST /api/conversations                        — create new conversation
POST /api/conversations/{conversation_id}/messages — append message

# Administration
POST /admin/regenerate                         — rebuild HTML and indexes
POST /admin/rollback                           — roll back a block to a previous version
```

The exact routes are not final. The important principles:

- the browser serves only generated static HTML;
- all writes go through the API;
- agents and humans use the same API endpoints;
- the API enforces the block versioning model (appending new versions, never overwriting).

## 15. Minimal v1 user flows

### Flow 1: Read a page

1. User runs `python render.py` to regenerate HTML.
2. User opens `http://localhost:8000/docs/doc_001` in a browser.
3. Browser displays pre-rendered HTML.
4. Each block has a visible, copyable block ID.
5. Blocks show version count and conversation count.

### Flow 2: Start a free-standing conversation

1. User creates a new conversation via text editor (appending to `conversations.jsonl`) or via API (`POST /api/conversations`).
2. The first message has no block attachment.
3. The user may mention an agent: `@agent:architect`.
4. The agent process detects the mention and appends a response.

### Flow 3: Comment on a block

1. User reads a rendered page in the browser.
2. User copies the block ID `blk_456` from the rendered page.
3. User creates a new conversation with the block ID as an attachment on the first message, via text editor or API.
4. This conversation now appears as attached to that block on the next render.

### Flow 4: Agent mutates a block

1. A conversation includes a mention of `agent:writer` with a block attachment.
2. The agent reads the referenced block's current content.
3. The agent creates a new block version via `POST /api/blocks/blk_456/versions`.
4. The new version records the conversation and message as `mutation_context`.
5. On next regeneration, the rendered page shows the updated content and an incremented version count.

### Flow 5: Human rolls back a block

1. User reads a rendered page and notices a bad agent edit.
2. User checks the block's version history (via API or rendered history page).
3. User triggers a rollback: `POST /admin/rollback` with `block_id=blk_456` and `target_version=1`.
4. A new version is created that copies version 1's content forward.
5. On next regeneration, the page shows the rolled-back content.

## 16. Document authoring in v1

In v1, canonical documents are created and edited by the human through direct file editing or API calls.

### Creating a new page

1. Create block records (append to `blocks.jsonl` or use `POST /api/blocks`).
2. Create a page record referencing those block IDs (append to `pages.jsonl` or use `POST /api/pages`).
3. Run the renderer.

### Editing existing content

1. Create a new block version (append to `blocks.jsonl` or use `POST /api/blocks/{block_id}/versions`).
2. Run the renderer.

The page document does not need to be updated because it references block IDs, not version-specific content.

### Restructuring a page

1. Update the page's `root` array to add, remove, or reorder block references.
2. Run the renderer.

### Why this is acceptable for v1

The user is comfortable authoring in vim. The canonical JSONL format is simple enough to hand-edit. Templates or snippets can reduce boilerplate. The rendered HTML provides the comfortable reading experience. The text editor provides the authoring experience. They do not need to be the same tool.

## 17. Risks and mitigations

### Risk: JSONL files grow large

Mitigation: for the expected v1 scale (hundreds of pages, thousands of block versions), JSONL files remain manageable. DuckDB or MongoDB migration is planned for when file size becomes a concern.

### Risk: block version history becomes long

Mitigation: in v1, all versions are retained. A future compaction feature could archive old versions while preserving the latest N and any versions referenced by rollbacks.

### Risk: conversations become noisy

Mitigation: the `status` field (`open`, `resolved`, `archived`) allows filtering. Resolved conversations are hidden from active views.

### Risk: rendered pages become stale

Mitigation: regeneration is an explicit manual step. The user regenerates after making changes. A future version may add file-watching for automatic regeneration.

### Risk: agents create low-quality content

Mitigation: all changes are traceable and rollbackable. The human reads rendered pages and starts conversations to correct problems. There is no silent corruption because the version history preserves all states.

### Risk: agent mention becomes a bottleneck (too many unread mentions)

Mitigation: the mention query API (`GET /api/conversations?mention=agent:X&status=open`) makes it tractable for both humans and agents to find pending work. Conversation resolution (`status: resolved`) clears processed mentions from the queue.

### Risk: hand-editing JSONL is error-prone

Mitigation: the API provides structured endpoints for all write operations. Hand-editing JSONL is an option, not a requirement. Vim snippets or templates can reduce errors. Validation can be added to the API and render pipeline.

## 18. Non-negotiable v1 invariants

1. Canonical data is stored as JSON (JSONL files in v1).
2. Rendered HTML is not canonical — it is a regenerable projection.
3. Every rendered block has a stable, copyable block ID.
4. Blocks are versioned — no content is ever destroyed.
5. All block versions record their author and timestamp.
6. Comments are conversations with block attachments, not separate objects.
7. Free-standing conversations are a primary working mode.
8. Context is attached to messages, not conversations.
9. Mentions are the signaling mechanism for agent invocation.
10. The browser is a reader, not a writer, in v1.
11. The system is local-first — no internet, no auth, no multi-user.

## 19. Deliberately deferred features

### Browser-side writing UI

Deferred because v1 uses text editor + API for authoring. Adding a sidebar chat, comment box, or accept/reject buttons is unnecessary complexity when the user is comfortable in vim.

A future version may add browser-side interaction for convenience.

### Proposal/review workflow

Deferred because the user cannot audit every agent-generated change in real-time. The mutation + rollback model provides equivalent safety with less ceremony. May be reintroduced for multi-user or high-stakes workflows.

### Rich document editing / WYSIWYG

Deferred because v1 focuses on reading, not browser-based editing. A future version may use BlockNote, Tiptap, or ProseMirror.

### Markdown round-trip

Deferred because parsing arbitrary Markdown back into canonical block structures is error-prone. Markdown may become an export format.

### CRDTs and real-time collaboration

Deferred because v1 is local-first and single-user.

### Remote sync

Deferred because local-first operation is accepted. Backup is handled through filesystem backup or Git.

### Public deployment

Deferred because it would require authentication, authorization, and security hardening.

### Multi-user permissions

Deferred because v1 is single-user. Agent "permissions" are implicitly defined by which API endpoints they call.

### Semantic collections / views

Deferred. Semantic grouping should be metadata, query views, or generated indexes rather than storage structure.

### Full event sourcing

Deferred. The block version history provides partial event sourcing. A complete replayable event log for all operations (page creation, page restructuring, conversation creation) is not needed in v1.

### Complex search

Deferred. Basic search can use `grep` on JSONL files or the SQLite indexes.

### Graph visualization

Deferred. The data model supports graph-like relationships through attachments and references, but a graph UI is not needed for v1.

### Automatic regeneration

Deferred. V1 uses manual regeneration. File-watching or event-triggered regeneration may be added later.

### DuckDB / MongoDB backend

Deferred. JSONL files are the v1 backend. The JSONL-per-collection structure is designed to make migration to a document database straightforward.

### Conversation participants field

Deferred. Authorship is tracked per-message. A summary of all participants in a conversation can be derived dynamically if needed. There is no v1 requirement for a pre-computed participants list.

## 20. Schema summary

v1 has three object schemas and one index layer.

### block.v1

```json
{
  "id": "string, stable across versions",
  "version": "integer, monotonically increasing per id",
  "schema": "block.v1",
  "type": "string: paragraph | heading | code | list_item | quote | image",
  "content": "object, type-specific (see §7.1)",
  "created_by": "string, namespace:name format",
  "created_at": "string, ISO 8601",
  "hash": "string, sha256 of serialized content",
  "parent_version": "integer, optional, absent on version 1",
  "rollback_to": "integer, optional, present only on rollback versions",
  "mutation_context": {
    "conversation_id": "string, optional",
    "message_id": "string, optional"
  }
}
```

### page.v1

```json
{
  "id": "string",
  "schema": "page.v1",
  "title": "string",
  "root": ["string array of block IDs, ordered"],
  "created_by": "string, namespace:name format",
  "created_at": "string, ISO 8601",
  "updated_at": "string, ISO 8601"
}
```

### conversation.v1

```json
{
  "id": "string",
  "schema": "conversation.v1",
  "title": "string",
  "status": "string: open | resolved | archived",
  "created_at": "string, ISO 8601",
  "updated_at": "string, ISO 8601",
  "messages": [
    {
      "id": "string",
      "author": "string, namespace:name format",
      "created_at": "string, ISO 8601",
      "body": "string, inline markup (see §7.2)",
      "attachments": [
        {
          "type": "string: block | page | conversation",
          "doc_id": "string, optional",
          "block_id": "string, optional",
          "conversation_id": "string, optional"
        }
      ],
      "mentions": ["string array, namespace:name format"]
    }
  ]
}
```

### Indexes (SQLite, rebuilt from JSONL)

```text
attachment_index(conversation_id, message_id, target_type, target_doc_id, target_block_id)
block_latest(block_id, latest_version, line_offset)
mention_index(conversation_id, message_id, mentioned_id)
```

## 21. Summary

The v1 system is a deliberately narrow local knowledge substrate.

It has three object kinds: **blocks**, **pages**, and **conversations**.

Blocks are versioned with stable IDs. No content is ever destroyed. All changes are traceable to an author, a time, and optionally a conversation.

Pages are ordered lists of block references, rendered to static HTML. The browser is a reader with copyable block IDs, not a writer.

Conversations are the single interaction primitive. A free-standing discussion, a comment on a block, and a request to an agent are all the same thing: a conversation, differing only in whether the first message has attachments and mentions.

Agents and humans use the same API. Agents mutate blocks directly. Safety comes from immutable version history and rollback, not from pre-approval gates.

The system is local-first, authored in a text editor, read in a browser, and stored as JSONL files designed for future migration to a document database.

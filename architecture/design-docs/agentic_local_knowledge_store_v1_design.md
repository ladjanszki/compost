# Agentic Local Knowledge Store — v1 Design

## 1. Purpose

This document defines the v1 architecture for a local-first, block-based knowledge system designed for safe human and agent interaction.

The goal is **not** to build a general-purpose note-taking app, a rich document editor, or an Anytype/Obsidian replacement in v1. The goal is to create a small, auditable substrate where documents can be rendered locally, conversations can happen over those documents, and agents can participate without being able to silently corrupt canonical content.

The v1 system is centered around:

- canonical JSON storage;
- immutable content blocks;
- pre-rendered local webpages;
- conversations as the only interaction primitive;
- message-level attachments to documents, blocks, proposals, or other objects;
- proposals instead of direct agent edits;
- local-first operation.

## 2. Core thesis

The system treats documentation, comments, agent discussions, and review feedback as structured data, not as mutable Markdown files.

The central design rule is:

> Canonical content is never silently overwritten. All meaningful changes are represented as new objects, messages, proposals, or audited mutations.

This is the main reason for preferring block-based JSON storage over Markdown files as the primary substrate.

Markdown may still be supported later as an export format, but it is not the canonical storage format in v1.

## 3. v1 scope

### Included in v1

The v1 system includes:

1. Canonical JSON documents.
2. Immutable blocks.
3. Page documents for renderable content.
4. Conversation documents for both free-standing chats and contextual comments.
5. Pre-rendered local webpages generated from page documents.
6. Stable block IDs embedded into rendered HTML.
7. A unified conversation UI.
8. Message-level attachments.
9. Proposals for suggested changes.
10. Local-only serving through a localhost web app.

### Excluded from v1

The v1 system deliberately excludes:

1. A WYSIWYG document editor.
2. Arbitrary browser-side document editing.
3. Markdown round-tripping.
4. Real-time collaboration.
5. Multi-user permissions.
6. Remote sync.
7. CRDTs.
8. Public internet deployment.
9. Mobile apps.
10. A plugin system.
11. Rich database views comparable to Notion or Anytype.
12. Semantic folder-based collections.
13. A separate comment object model.
14. A separate “ask agent about block” feature.

## 4. Local-first assumption

The system is designed to run locally.

A typical v1 deployment is:

```text
localhost web server
+ canonical JSON files or a local document DB
+ generated HTML pages
+ local agent processes
```

This means v1 does not need to solve:

- account management;
- authentication;
- authorization;
- remote synchronization;
- collaborative conflict resolution;
- encryption for network transport;
- public hosting security.

These are important features in other systems, but they are not necessary for the intended v1 working mode.

## 5. Storage model

The store contains several object kinds:

```text
block
page document
conversation
proposal
mutation, optional in early v1
```

A possible filesystem layout:

```text
store/
  blocks/
    blk_001.json
    blk_002.json

  pages/
    doc_001.json
    doc_002.json

  conversations/
    conv_001.json
    conv_002.json

  proposals/
    prop_001.json
    prop_002.json

  mutations/
    mut_001.json
    mut_002.json

site/
  generated/
    index.html
    docs/
      doc_001.html
      doc_002.html
    assets/
      app.js
      style.css
```

The exact physical layout can change, but the logical model should remain stable: canonical objects are stored independently from rendered views.

## 6. Blocks

Blocks are immutable content units.

A block may represent a paragraph, heading, list item, code block, image reference, quote, or other content element.

Example:

```json
{
  "id": "blk_456",
  "schema": "block.v1",
  "type": "paragraph",
  "content": {
    "text": "The cache is invalidated when the source document changes."
  },
  "created_by": "human:istvan",
  "created_at": "2026-05-06T12:00:00Z",
  "hash": "sha256:..."
}
```

### Decision: blocks are immutable

Blocks should not be edited in place.

If a block needs to change, the system creates a new block and records the relationship through a proposal or mutation.

For example:

```json
{
  "id": "prop_001",
  "schema": "proposal.v1",
  "type": "replace_block",
  "status": "pending",
  "target": {
    "doc_id": "doc_001",
    "block_id": "blk_456"
  },
  "proposed_block": {
    "id": "blk_999",
    "type": "paragraph",
    "content": {
      "text": "The cache is invalidated when the source document or any declared dependency changes."
    }
  },
  "created_by": "agent:writer",
  "created_at": "2026-05-06T12:10:00Z"
}
```

### Why immutable blocks?

Immutable blocks defend against silent data corruption.

With mutable Markdown or mutable rich-text documents, an agent can accidentally overwrite human-written content, overwrite another agent’s work, or destroy context without leaving a reliable trace.

With immutable blocks:

- the original content remains available;
- replacement content is explicit;
- authorship can be tracked;
- review is possible before committing changes;
- previous states can be reconstructed;
- agent actions are auditable.

This is the core safety property of the system.

## 7. Page documents

A page document is a renderable document composed of block references.

Example:

```json
{
  "id": "doc_001",
  "schema": "page.v1",
  "title": "Cache invalidation",
  "root": [
    { "block_id": "blk_heading_001" },
    { "block_id": "blk_456" }
  ],
  "created_at": "2026-05-06T12:00:00Z",
  "updated_at": "2026-05-06T12:00:00Z"
}
```

The page document defines structure. Blocks define content.

### Decision: pages are rendered, not edited directly

In v1, pages are rendered to local webpages. The browser does not provide a full page editor.

The rendered webpage is a reading and interaction surface, not the canonical authoring interface.

### Why pre-rendered webpages?

Pre-rendering greatly reduces v1 complexity.

It avoids building:

- a rich-text editor;
- document transaction logic;
- browser-side block editing;
- live rendering pipelines;
- complex state synchronization;
- Markdown import/export loops.

The browser can remain simple: it displays generated HTML and provides a conversation sidebar.

## 8. Rendered HTML

Each rendered block must include stable identity metadata.

Example:

```html
<section
  class="doc-block"
  data-doc-id="doc_001"
  data-block-id="blk_456"
  id="blk_456"
>
  <p>The cache is invalidated when the source document changes.</p>
  <button class="conversation-button">Comment</button>
</section>
```

### Critical invariant

Every rendered block must carry a stable block ID.

This invariant enables:

- contextual conversations;
- comments on specific blocks;
- proposal targeting;
- source references;
- audit views;
- future diffing;
- future export/import tooling.

Without stable block IDs, the system loses its ability to connect human and agent discussion to specific content units.

## 9. Conversations

Conversation is the only interaction primitive in v1.

There is no separate data model for:

- comments;
- comment threads;
- chats;
- agent discussions;
- block annotations.

All of these are represented as conversations.

A conversation may be free-standing or contextual. The difference is not a separate object type. The difference is whether its messages contain attachments.

## 10. Free-standing conversations

Free-standing conversations are required in v1.

They are one of the primary working modes of the system.

A free-standing conversation starts from the conversation UI rather than from a rendered block.

Example:

```json
{
  "id": "conv_001",
  "schema": "conversation.v1",
  "title": "Architecture discussion",
  "status": "open",
  "participants": [
    "human:istvan",
    "agent:architect"
  ],
  "messages": [
    {
      "id": "msg_001",
      "author": "human:istvan",
      "created_at": "2026-05-06T12:00:00Z",
      "body": {
        "format": "plain_text",
        "text": "Help me think through the architecture."
      },
      "attachments": []
    }
  ],
  "created_at": "2026-05-06T12:00:00Z",
  "updated_at": "2026-05-06T12:00:00Z"
}
```

## 11. Comments as conversations

A comment is not a separate object.

A comment is a conversation whose first message is attached to a block.

When the user clicks “Comment” beside a rendered block, the UI opens the same conversation interface used for free-standing chats. The only difference is that the first message is pre-attached to the selected block.

Example:

```json
{
  "id": "conv_002",
  "schema": "conversation.v1",
  "title": "Comment on cache invalidation paragraph",
  "status": "open",
  "participants": [
    "human:istvan"
  ],
  "messages": [
    {
      "id": "msg_001",
      "author": "human:istvan",
      "created_at": "2026-05-06T12:05:00Z",
      "body": {
        "format": "plain_text",
        "text": "This paragraph needs a concrete example."
      },
      "attachments": [
        {
          "type": "block",
          "doc_id": "doc_001",
          "block_id": "blk_456",
          "role": "comment_target"
        }
      ]
    }
  ],
  "created_at": "2026-05-06T12:05:00Z",
  "updated_at": "2026-05-06T12:05:00Z"
}
```

### Decision: unify comments and conversations

The system deliberately does not distinguish between comments and conversations in the data model.

### Why?

A comment can naturally become a discussion.

For example:

1. A human comments on a block.
2. An agent replies.
3. The human asks for a proposed fix.
4. The agent creates a proposal.
5. The human accepts or rejects it.

This is not fundamentally different from a chat. It is a chat with context.

By using one conversation model:

- the UI is simpler;
- the storage model is simpler;
- agents do not need separate handling for comments versus chats;
- contextual and free-standing work modes share the same infrastructure;
- comment threads can evolve into agent-assisted discussions without migration.

## 12. Message-level attachments

Context is attached to messages, not only to conversations.

A message may attach:

- a block;
- a page;
- a proposal;
- another conversation;
- a generated view;
- future object types.

Example:

```json
{
  "id": "msg_003",
  "author": "human:istvan",
  "created_at": "2026-05-06T12:15:00Z",
  "body": {
    "format": "plain_text",
    "text": "This proposal looks good, but can you make the example shorter?"
  },
  "attachments": [
    {
      "type": "proposal",
      "proposal_id": "prop_001",
      "role": "discussed_object"
    }
  ]
}
```

### Decision: attach context to messages, not only conversations

A conversation can drift over time. It may start from one block, then reference other blocks, proposals, or documents.

If context were only stored at the conversation level, the model would become too rigid.

Message-level attachments allow the conversation to remain a timeline of contextual statements.

### How comments are found for a block

To find conversations attached to a block, query messages with an attachment matching:

```json
{
  "type": "block",
  "doc_id": "doc_001",
  "block_id": "blk_456",
  "role": "comment_target"
}
```

The rendered webpage can display a comment count next to each block based on this query.

## 13. Unified conversation UI

The local website has two primary surfaces:

```text
/docs/{doc_id}
/conversations
```

### Document page

A document page displays pre-rendered HTML.

Each block can open a conversation sidebar.

Clicking “Comment” on a block:

1. opens the conversation sidebar;
2. creates a new conversation if needed;
3. pre-attaches the block ID to the first message;
4. stores the result as a normal conversation.

### Conversation page

The conversation page is used for free-standing conversations.

It supports:

- creating a new conversation;
- selecting an existing conversation;
- sending messages;
- adding participants, including agents;
- viewing message attachments;
- attaching context manually if needed.

### Decision: no separate “Ask agent about block” function

There is no separate feature called “Ask agent about block.”

If the user wants to ask an agent about a block, that is simply a conversation message with a block attachment and an agent participant.

The UI may offer conveniences later, but the data model does not need a distinct concept.

### Why?

“Ask agent about block” and “comment on block” are the same underlying operation:

```text
create or open a conversation
attach block context
send a message
optionally include an agent participant
```

Splitting this into separate features would create unnecessary conceptual duplication.

## 14. Proposals

Agents should not directly mutate canonical page documents in v1.

Instead, agents create proposals.

Example:

```json
{
  "id": "prop_001",
  "schema": "proposal.v1",
  "type": "replace_block",
  "status": "pending",
  "target": {
    "doc_id": "doc_001",
    "block_id": "blk_456"
  },
  "proposed_block": {
    "id": "blk_999",
    "schema": "block.v1",
    "type": "paragraph",
    "content": {
      "text": "The cache is invalidated when the source document or any declared dependency changes."
    }
  },
  "created_by": "agent:writer",
  "created_from": {
    "conversation_id": "conv_002",
    "message_id": "msg_004"
  },
  "created_at": "2026-05-06T12:20:00Z"
}
```

### Decision: agents create proposals, not direct edits

This is a central safety rule.

Agents may:

- read pages;
- read conversations;
- participate in conversations;
- attach context;
- create comments;
- create proposals.

Agents should not silently overwrite canonical blocks or page structures.

### Why?

The system is designed to support agentic workflows without sacrificing trust.

A proposal-based workflow ensures:

- human review is possible;
- agent output is traceable;
- generated changes can be rejected;
- source conversation can be linked;
- original blocks remain intact;
- corruption is recoverable.

## 15. Mutations

A mutation records an accepted change to canonical state.

Example:

```json
{
  "id": "mut_001",
  "schema": "mutation.v1",
  "type": "accept_replace_block_proposal",
  "proposal_id": "prop_001",
  "document_id": "doc_001",
  "old_block_id": "blk_456",
  "new_block_id": "blk_999",
  "created_by": "human:istvan",
  "created_at": "2026-05-06T12:30:00Z"
}
```

### v1 position on mutations

Explicit mutation objects are recommended, but the earliest implementation may treat accepted proposals as the audit log.

The important invariant is that canonical changes must be traceable.

If mutation objects are deferred, accepted proposals must still record:

- who accepted the change;
- when it was accepted;
- what changed;
- which old block was replaced;
- which new block was introduced.

## 16. Rendering and regeneration

The renderer converts canonical page documents into local HTML files.

Input:

```text
blocks
pages
conversations
proposals
```

Output:

```text
site/generated/docs/{doc_id}.html
```

The generated page may include:

- the page body;
- block IDs;
- conversation counts;
- unresolved conversation indicators;
- pending proposal indicators;
- links to related conversations.

### Decision: generated pages are projections

Generated HTML is not canonical.

It can be deleted and regenerated from the store.

### Why?

This gives clean separation:

```text
canonical JSON = durable truth
HTML = view
browser = interaction surface
```

The system can later support other views, such as:

- Markdown export;
- static site export;
- PDF export;
- API responses;
- search indexes;
- graph visualizations.

## 17. Relationship to Anytype

The v1 system overlaps with Anytype in that both involve local-first, block-oriented knowledge work.

However, the center of gravity is different.

Anytype is primarily a human-facing knowledge workspace with objects, types, properties, blocks, queries, sync, encryption, and collaboration.

This v1 system is primarily an agent-safe local knowledge substrate with immutable blocks, rendered views, conversations, and proposal-based mutation.

The system deliberately does not attempt to reproduce Anytype’s:

- polished editor;
- object database UX;
- sync network;
- collaboration features;
- mobile apps;
- end-user workspace abstractions;
- template/database ecosystem.

## 18. Relationship to Obsidian and Markdown

The system also differs from an Obsidian/Markdown workflow.

Markdown files are human-readable and portable, but they are mutable text blobs. It is difficult to guarantee that agents will not overwrite human edits or modify unrelated content.

The proposed v1 uses Markdown-like rendering only as a possible future export target. It does not use Markdown as the canonical data layer.

The reason is safety:

```text
mutable Markdown file
  → hard to protect against silent overwrite

immutable blocks + proposals
  → explicit change history and reviewable mutation
```

## 19. Deliberately deferred features

### Rich document editing

Deferred because the system does not yet need arbitrary editing of page bodies in the browser.

V1 focuses on reading, commenting, conversations, and proposals.

### WYSIWYG block editor

Deferred because editor complexity is high and not necessary for the first working model.

A future version may use BlockNote, Tiptap, ProseMirror, or a custom editor, but the canonical format should remain independent of the editor.

### Markdown round-trip

Deferred because parsing arbitrary Markdown back into canonical block structures is error-prone.

Markdown can be an export format later.

### CRDTs and real-time collaboration

Deferred because v1 is local-first and single-user oriented.

The system avoids the need for conflict-free distributed editing by design.

### Remote sync

Deferred because local-first operation is accepted.

Backup can initially be handled through normal filesystem backup or Git.

### Public deployment

Deferred because exposing the system to the internet would require authentication, authorization, secure networking, and threat modeling.

### Multi-user permissions

Deferred because v1 is not a collaborative multi-user system.

Agent permissions may be implemented locally as API policies, but not as a full user/role system.

### Semantic collections

Deferred because semantic grouping should be represented as metadata, query views, or generated indexes rather than storage folders.

The v1 storage boundary should be a workspace/store, not a folder like “engineering” or “product.”

### Separate comment model

Deferred or rejected because comments are conversations with contextual attachments.

Introducing separate comment threads would duplicate conversation behavior.

### Separate “ask agent about block” feature

Rejected because asking an agent about a block is just a conversation message with a block attachment and an agent participant.

### Full event sourcing

Deferred because a complete event-sourced architecture may be more complex than v1 requires.

The system should preserve the option by storing proposals and accepted-change records, but v1 does not need full replayable state from an event log.

### Complex search

Deferred. Basic search can be file-based or implemented through a simple SQLite index later.

### Graph visualization

Deferred. The data model supports graph-like relationships through attachments and references, but graph UI is not needed for v1.

## 20. Minimal API shape

The local server may expose endpoints such as:

```text
GET  /docs/{doc_id}
GET  /conversations
GET  /conversations/{conversation_id}
POST /conversations
POST /conversations/{conversation_id}/messages
GET  /api/conversations?attached_to=block&doc_id=doc_001&block_id=blk_456
POST /proposals
PATCH /proposals/{proposal_id}/accept
PATCH /proposals/{proposal_id}/reject
POST /admin/regenerate
```

The exact routes are not final. The important point is that browser writes go through controlled operations.

The browser should not write canonical page content directly.

## 21. Minimal v1 user flows

### Flow 1: Read a page

1. User opens `/docs/doc_001`.
2. Browser displays pre-rendered HTML.
3. Each block has a stable block ID.
4. Existing conversations attached to blocks are indicated.

### Flow 2: Start a free-standing conversation

1. User opens `/conversations`.
2. User clicks “New conversation.”
3. User writes a message.
4. The system saves a conversation with no initial attachments.
5. Agents may participate if selected.

### Flow 3: Comment on a block

1. User opens a rendered document.
2. User clicks “Comment” beside a block.
3. The same conversation UI opens.
4. User writes a message.
5. The message is saved with a block attachment.
6. The conversation appears as attached to that block.

### Flow 4: Ask an agent about a block

This is not a separate feature.

The user starts a conversation from the block and includes an agent participant.

The message is a normal conversation message with a block attachment.

### Flow 5: Agent creates a proposal

1. Agent participates in a conversation.
2. Agent creates a proposal instead of editing the document.
3. Proposal references the conversation/message that produced it.
4. Human reviews the proposal.
5. If accepted, canonical state changes in a traceable way.

## 22. Risks and mitigations

### Risk: too many small JSON files

Mitigation: start with files for inspectability; later move to SQLite/document DB or JSONL if necessary.

### Risk: block IDs become unstable

Mitigation: block IDs are assigned at canonical object creation and never regenerated during rendering.

### Risk: conversations become noisy

Mitigation: support status fields such as `open`, `resolved`, and `archived`.

### Risk: proposal review becomes too manual

Mitigation: keep human approval in v1; later add policy-based auto-accept for low-risk changes.

### Risk: rendered pages become stale

Mitigation: provide explicit regeneration command or endpoint. Generated pages are projections and can be rebuilt.

### Risk: agents create too much low-quality content

Mitigation: agents can participate in conversations and create proposals, but canonical mutation remains controlled.

## 23. Non-negotiable v1 invariants

1. Canonical documents are JSON-based.
2. Rendered HTML is not canonical.
3. Every rendered block has a stable block ID.
4. Comments are conversations, not separate objects.
5. Free-standing conversations exist in v1.
6. Context is attached to messages.
7. Agents do not silently overwrite canonical content.
8. Agent changes are represented as proposals.
9. Page body editing in the browser is out of scope.
10. The system is local-first.

## 24. Summary

The v1 system is a deliberately narrow local knowledge substrate.

It does not try to compete with Anytype, Obsidian, Notion, or a full block editor. It instead provides a safer foundation for agentic work:

```text
immutable blocks
+ renderable pages
+ unified conversations
+ message-level context
+ proposal-based mutation
+ local-first operation
```

The most important simplification is that the system has only one interaction primitive: conversation.

A free-standing chat is a conversation without initial attachments.

A comment is a conversation whose first message is attached to a block.

Asking an agent about a block is not a special feature; it is the same conversation mechanism with an agent participant.

This unified model keeps v1 small while preserving the core requirements for agent-safe knowledge work.


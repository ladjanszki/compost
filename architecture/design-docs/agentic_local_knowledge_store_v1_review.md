# Design Review: Agentic Local Knowledge Store — v1

**Reviewer:** Senior Data Engineer (agent)  
**Document reviewed:** `agentic_local_knowledge_store_v_1_design.md`  
**Supporting material consulted:** ChatGPT and Gemini conversation transcripts  
**Date:** 2026-05-06

---

## Executive Summary

The design document is well-structured, clearly scoped, and internally consistent. The core thesis — immutable blocks, proposal-based mutation, unified conversations, pre-rendered views — is sound and well-defended.

However, the document has **three categories of problems**:

1. **Residual complexity from the design journey** — features and structures that made sense during brainstorming but survived into the final doc without justification or despite being superseded by later simplifications.
2. **Implicit knowledge** — decisions that only make sense if you were present for the Obsidian migration story, but that are not self-contained in this document.
3. **Scope ambiguity** — a few areas where "v1" and "maybe later" blur, which will cause implementation confusion.

Below I walk through each, with specific recommendations.

---

## Part 1: Core Requirements Clarity Check

**Verdict: Mostly clear, but not explicitly enumerated as requirements.**

The document defines 10 "non-negotiable v1 invariants" (§23), which function as requirements. However, the document never separates **user requirements** (what the system must *do* for the user) from **architectural invariants** (how the system is *built*). This matters because a reviewing agent — or an implementing one — needs to know which constraints are load-bearing for the user's workflow and which are engineering choices that could be swapped.

### Recommendation: Add an explicit "Core Requirements" section

Distill the user-facing requirements from the conversation history. Based on my reading, they are:

| # | Requirement | Source |
|---|---|---|
| R1 | I can read rendered documents locally in a browser | Conversation: "serve local websites" |
| R2 | I can comment on any specific block of a document | Conversation: "how exactly will I write the comments" |
| R3 | I can have free-standing conversations (not attached to any document) | Conversation: "free standing conversations are a must from the get go" |
| R4 | Agents can participate in conversations | Conversation: "agentic system from the ground up" |
| R5 | Agents cannot silently overwrite canonical content | Conversation: "immutable blocks which can only be replaced" |
| R6 | Agent changes are reviewable before commitment | Conversation: "proposals instead of direct edits" |
| R7 | The canonical format is JSON, readable without any editor/app | Conversation: "I want the JSON documents to be accessible WITHOUT the editor" |
| R8 | The system is local-first; no internet, no auth, no multi-user | Conversation: "I'm going to accept that this is going to be local first" |

Everything else in the doc should be traceable back to one of these. If it isn't, it's either implicit knowledge that needs to be made explicit, or it's scope creep.

---

## Part 2: Historical / Residual Constraints

These are parts of the design that were relevant during the brainstorming journey but appear to be "left there" in the final document.

### 2.1 — Blocks stored as individual JSON files (§5, §22)

**The problem:** The filesystem layout shows `blocks/blk_001.json`, `blocks/blk_002.json` — one file per block. The risk section (§22) even acknowledges "too many small JSON files" as a risk.

**Why this is residual:** During the conversation, you converged on blocks being immutable content-addressed units. For a document with 50 blocks, that's 50 files *just for one page*. The conversation itself mentioned JSONL as an alternative. Yet the design presents per-file storage as the primary layout with JSONL/SQLite as a future mitigation.

**Recommendation:** Don't present per-file block storage as the default layout. Present it as an option for inspectability during development, but make the design *agnostic* to physical storage. The logical model (§5: "the logical model should remain stable") is the right call — lean into it harder. Remove the specific filesystem layout or label it explicitly as "example only; physical layout is an implementation detail."

### 2.2 — Mutation objects as a separate entity (§15)

**The problem:** The document introduces mutations as a separate object kind, then immediately hedges: "Explicit mutation objects are recommended, but the earliest implementation may treat accepted proposals as the audit log."

**Why this is residual:** The conversation evolved through event-sourcing ideas → append-only mutation logs → simpler proposal-based workflow. Mutations are a ghost of the full event-sourcing idea. The document itself says proposals can serve as the audit log, which makes mutations redundant for v1.

**Recommendation:** Remove mutations from the v1 object model entirely. Add a field to the proposal schema for acceptance status, accepted-by, accepted-at. State explicitly: "In v1, the proposal is the audit record. A separate mutation log is deferred." This cuts an entire object kind and simplifies the storage model, API, and mental model.

### 2.3 — The `hash` field on blocks (§6)

**The problem:** The block example includes `"hash": "sha256:..."`. Content-addressing is mentioned once and never referenced again. No part of the design depends on content hashing — not deduplication, not integrity verification, not sync.

**Why this is residual:** Content-addressing was discussed in the context of Git-like immutable objects. It's an interesting property but nothing in v1 uses it.

**Recommendation:** Remove `hash` from the v1 block schema. Add a note: "Content hashing may be added later for integrity verification or deduplication, but v1 does not depend on it." This reduces schema complexity and avoids questions like "who computes the hash?" and "what happens if the hash is wrong?"

### 2.4 — The `schema` field on every object

**The problem:** Every example object includes `"schema": "block.v1"`, `"schema": "conversation.v1"`, etc. This implies a schema versioning/validation system.

**Why this is potentially residual:** Schema versioning is important for long-lived systems. But if v1 only has one version of each schema, the field is inert. The document never describes what happens when a schema version changes or how migration works.

**Recommendation:** Keep the field (it's cheap insurance), but add one sentence: "In v1, there is only one version of each schema. The `schema` field exists to support future format evolution. Schema validation and migration are deferred." This prevents an implementing agent from building a schema registry.

### 2.5 — Section 17 (Relationship to Anytype) and Section 18 (Relationship to Obsidian/Markdown)

**The problem:** These sections are ~300 words of "we are not Anytype" and "we are not Obsidian." They list features the system does *not* have.

**Why this is residual:** These comparisons were essential during the design conversation to clarify positioning. In a *finished* design doc for a reviewing/implementing agent, they are background noise. The "Excluded from v1" list (§3) already covers the scope boundary. The comparisons add no new constraints or decisions.

**Recommendation:** Collapse both into a single short paragraph in a "Design Context" or "Background" section: "This system was designed as an alternative to Obsidian/Markdown (which lacks agent-safe mutation) and Anytype (which includes collaboration, sync, and editor complexity beyond v1 scope). The system deliberately does not replicate their feature sets." Move detail to an appendix if desired.

---

## Part 3: Implicit Knowledge That Should Be Made Explicit

These are decisions in the document that only make sense if you know the Obsidian backstory, but which are presented without sufficient rationale.

### 3.1 — Why JSON and not Markdown as canonical format?

**What the doc says (§2):** "The central design rule is: Canonical content is never silently overwritten. [...] This is the main reason for preferring block-based JSON storage over Markdown files."

**What's implicit:** The real reason, from the conversation, is that Markdown files are mutable text blobs where agents can accidentally overwrite unrelated content, and there's no reliable way to do block-level addressing, attribution, or immutability. The Obsidian experience proved this — you tried to build a comment system *within* Obsidian using specially formatted links and block IDs, and it was fragile.

**Recommendation:** Add 2-3 sentences making this explicit: "The choice of JSON over Markdown was driven by experience with Markdown-based workflows (Obsidian). In Markdown, block-level identity is fragile (dependent on convention, not enforcement), agent edits cannot be reliably scoped to specific blocks, and two-way sync between a canonical format and Markdown is error-prone. JSON blocks with stable IDs make immutability and targeting enforceable rather than conventional."

### 3.2 — Why pre-rendered HTML and not server-rendered on request?

**What the doc says (§7, §16):** Pages are pre-rendered. Generated HTML is not canonical.

**What's implicit:** The conversation explicitly discussed this tradeoff (Pattern 1: server-rendered vs. Pattern 2: static generation). The choice was static generation because it's simpler, inspectable, and avoids building a rendering pipeline into the request path.

**Recommendation:** Add to §7 or §16: "Pre-rendering was chosen over on-request server rendering to keep the serving layer trivial (static file server + API for writes). The renderer runs as an explicit command or endpoint, not on every page load. This makes the system easier to debug and keeps the generated output inspectable."

### 3.3 — Why conversations and not a richer annotation model?

**What the doc says (§9-§11):** Comments are conversations. There is no separate annotation model.

**What's implicit:** The conversation went through several iterations — separate comment objects → comment threads → comment threads + conversations → unified conversations. The simplification was driven by the realization that a "comment" naturally becomes a discussion, and separating them creates migration pain.

**Recommendation:** §11's "Why?" section partially covers this, but should be sharper: "During design, separate comment and conversation models were considered and rejected. The key insight was that a comment on a block frequently evolves into a multi-turn discussion with agent participation, proposal creation, and resolution. Maintaining two models (comment thread + conversation) would require either migration between them or duplicated behavior. A single conversation model with message-level attachments handles both cases."

---

## Part 4: Scope Ambiguity / Tightening

### 4.1 — Message body format: structured blocks or plain text?

**The problem:** The conversation examples show message bodies as both plain text strings and structured block arrays:

```json
"body": { "format": "plain_text", "text": "..." }
```

vs. the earlier conversation transcript showing:

```json
"body": { "format": "mydoc-inline.v1", "blocks": [...] }
```

The design doc uses `plain_text` format. But if messages are "mini-documents" with their own block structure, that's significantly more complex.

**Recommendation:** For v1, commit to plain text message bodies. State it explicitly: "In v1, message bodies are plain text. Rich/structured message content (formatted text, embedded code, etc.) is deferred. This keeps the conversation UI simple — a textarea and a save button."

### 4.2 — What triggers regeneration?

**The problem:** §16 says "provide explicit regeneration command or endpoint" and §22 lists "rendered pages become stale" as a risk. But the design never specifies *when* regeneration should happen.

**Recommendation:** Be explicit: "In v1, regeneration is manually triggered via CLI command or API endpoint. Automatic regeneration on data change is deferred. The user is responsible for regenerating after accepting proposals or when comment counts need updating."

### 4.3 — How are agents invoked?

**The problem:** The document says agents can participate in conversations, read documents, and create proposals. But it never says *how* an agent is invoked. Is it a background process polling for new messages? A webhook? A CLI tool the user runs?

**Recommendation:** This doesn't need a full agent framework design, but it needs a boundary: "In v1, agent invocation is out of scope for this design. Agents are external processes that interact with the system through the same API endpoints as the browser UI. How agents are triggered (manually, via polling, via webhook) is an implementation concern, not a storage/interaction model concern."

### 4.4 — Proposal types beyond `replace_block`

**The problem:** The only proposal example is `replace_block`. But there are other meaningful operations: `add_block`, `remove_block`, `reorder_blocks`, `replace_page_title`, etc.

**Recommendation:** Either enumerate the v1 proposal types explicitly, or state: "In v1, only `replace_block` proposals are supported. Other structural changes (adding, removing, reordering blocks) are performed directly by the human through canonical JSON editing or a future tool."

### 4.5 — How does the human author/edit canonical documents in v1?

**The problem:** The design says the browser is not an editor. Agents propose changes. But the document never says how a human *creates* or *edits* a page document. Is it by hand-editing JSON? A CLI tool? An import command?

**Why this matters:** If the human has to hand-write JSON block files and page documents to create content, the system will be unusable for its own author.

**Recommendation:** Be explicit: "In v1, canonical documents are created and edited by the human through direct JSON authoring (text editor), CLI tools, or agent-assisted generation via conversations. The system does not include a graphical document editor. This is acceptable because the primary v1 workflow is reading, commenting, discussing, and reviewing agent proposals — not high-volume manual content creation."

---

## Part 5: Engineering Review (Senior Data Engineer Perspective)

### 5.1 — The per-block file model won't survive contact with reality

Even with the "too many files" risk acknowledged, I want to be blunt: at 50-200 blocks per document and 20+ documents, you'll have 1,000-4,000 tiny JSON files in `blocks/`. Filesystem listing, backup, git operations, and any query ("find all blocks by agent:writer") become painful immediately.

**Strong recommendation:** Design the logical model around individual blocks, but store them *within* the page document JSON in v1. A page document already references blocks by ID — just inline the block content:

```json
{
  "id": "doc_001",
  "schema": "page.v1",
  "title": "Cache invalidation",
  "blocks": {
    "blk_001": { "type": "heading", "content": { "text": "Cache invalidation" } },
    "blk_002": { "type": "paragraph", "content": { "text": "..." } }
  },
  "root": ["blk_001", "blk_002"]
}
```

Blocks remain identifiable by ID. Immutability is enforced by the API, not by physical file separation. If you later need cross-document block references or deduplication, *then* extract blocks to a separate store.

This is the classic mistake of optimizing for a future need (cross-document block sharing, content-addressing) that v1 doesn't have.

### 5.2 — The attachment query model needs an index from day one

§12 describes finding conversations for a block by querying message attachments:

```json
{ "type": "block", "doc_id": "doc_001", "block_id": "blk_456", "role": "comment_target" }
```

If conversations are stored as individual JSON files, this requires scanning *every* conversation file and *every* message within it to find block attachments. With 100 conversations averaging 10 messages each, that's 1,000 message scans per page render (to show comment counts on blocks).

**Recommendation:** Add a lightweight index requirement to v1. Something as simple as a SQLite table:

```sql
CREATE TABLE attachment_index (
    conversation_id TEXT,
    message_id TEXT,
    target_type TEXT,
    target_doc_id TEXT,
    target_block_id TEXT
);
```

This is rebuilt from canonical JSON on regeneration. It's a projection, like the HTML.

### 5.3 — The `role` field on attachments is underspecified

Attachments have a `role` field (`"comment_target"`, `"discussed_object"`). The document never defines the valid roles or what they mean for queries.

**Recommendation:** Either enumerate the v1 roles (`comment_target`, `discussed_object`, `resolution_source`) or drop the `role` field in v1 and derive intent from context (the first attachment on the first message of a conversation = comment target).

### 5.4 — Conversation `participants` field: who populates it?

The schema shows `"participants": ["human:istvan", "agent:architect"]`. But when a human clicks "Comment" on a block and writes a message, the participants list only has the human. If an agent later joins, is the participants list updated? Is it derived from messages? Is it set at creation time?

**Recommendation:** Define this clearly. I'd recommend: "The `participants` field is derived from message authors and does not need to be set at creation time. It is a convenience field updated whenever a new author posts a message."

---

## Part 6: What to Cut to Simplify Without Losing Core Requirements

Here is my concrete cut list, mapped back to core requirements to show nothing is lost:

| Cut | What it removes | Why it's safe to cut | Requirements preserved |
|---|---|---|---|
| Remove `mutation` as a v1 object kind | One entire entity type, storage, API endpoints | Proposals with accept/reject status provide the same audit trail | R5, R6 |
| Remove per-file block storage; inline blocks in page documents | `blocks/` directory, block file management | Blocks are still addressable by ID within documents | R2, R5, R7 |
| Remove `hash` field from blocks | Content-addressing complexity | Nothing in v1 uses it | None affected |
| Remove §17 and §18 (Anytype/Obsidian comparison) | ~600 words of positioning text | Covered by the exclusion list in §3 | None affected |
| Remove `body.format` flexibility; v1 messages are plain text | Structured message body parsing, rendering | Free-standing conversations and comments work with plain text | R2, R3, R4 |
| Remove `role` field from attachments | Role taxonomy, role-based queries | Attachment semantics are derivable from position/context | R2 |
| Commit to explicit proposal types (`replace_block` only in v1) | Open-ended proposal type design | Structural edits are human-authored directly in v1 | R5, R6 |

**Net result:** 5 object kinds → 3 (page, conversation, proposal). The storage model, API surface, and schema complexity shrink significantly.

---

## Part 7: Summary of Recommended Actions

### Must-do (clarity and correctness)
1. Add an explicit **Core User Requirements** section (R1-R8 above or similar).
2. Make implicit Obsidian/Markdown reasoning explicit in the JSON and pre-rendering rationale sections.
3. Define how humans create/edit canonical documents in v1.
4. Define how/when regeneration is triggered.
5. State that agent invocation is out of scope for this design.

### Should-do (simplification)
6. Remove mutations from v1 object model; use proposal status as audit trail.
7. Inline blocks within page documents instead of per-file block storage.
8. Remove `hash` from v1 block schema.
9. Collapse Anytype/Obsidian comparison sections.
10. Commit to plain-text message bodies in v1.
11. Add an index requirement for attachment queries.

### Nice-to-do (polish)
12. Enumerate valid attachment roles or defer the `role` field.
13. Clarify the `participants` field derivation rule.
14. Add a `schema` versioning clarification note.
15. Enumerate supported proposal types for v1.

---

## Closing Assessment

This is a good design. The core thesis is sound: immutable blocks, proposal-based mutation, unified conversations, and pre-rendered views form a coherent and defensible v1 for agent-safe local knowledge work.

The main risks are not architectural — they are **scope discipline**. The document carries traces of the brainstorming journey (mutations, content hashing, per-file blocks, lengthy positioning against other tools) that add surface area without adding user value. Trimming these will make the design easier to implement, easier to review, and easier to evolve.

The single most important simplification: **inline blocks into page documents and remove the separate block store.** This eliminates a whole storage layer while preserving every core invariant. Block-level immutability can be enforced by the API layer, not by physical file isolation.

The single most important addition: **make the "how does a human actually create content in v1?" question explicit.** Without this, the first implementation will stall.

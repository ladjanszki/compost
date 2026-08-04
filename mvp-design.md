# MVP Design — Notes-to-Wiki with Lineage

Status: agreed as of 2026-08-03. Derived from `my-workflow.md` and `mvp-interview.md`.
This document supersedes `README.md` and `architecture/phase_0*.md` for everything it covers.

---

## 1. What this is

A system that turns notes into a wiki you can actually re-enter after weeks away.

You write notes in neovim and submit them. Agents generate a wiki from those notes. You read the
wiki as HTML, copy a block ID, write a note reacting to it, and submit again. The wiki improves
iteratively under your direction. You never write the wiki; agents never write your notes.

The problem it solves: **the gap between conversation and knowledge.** Thinking happens in prose
and in chat, and then it's stranded — unfindable, unstructured, gone at the next context switch.
This turns that stream into something re-enterable.

The user runs 3–5 active projects and has hundreds of dormant ones. Cheap context re-entry is the
entire point.

---

## 2. Invariants

These must never break. Everything else is negotiable.

1. **`.dj` files in git are the source of truth.** Every other artifact — HTML, any index, any
   graph — is derived and disposable.
2. **Notes are immutable.** Once submitted and canonized, a note file never changes again.
3. **Humans write notes. Agents write the wiki.** Never the reverse. The filesystem enforces it.
4. **Every wiki block cites its sources.** A block with empty lineage is invalid and is rejected.
5. **Block IDs are stable.** A block ID, once assigned, refers to that block forever.

Invariant 4 is doing double duty — see §5.

---

## 3. Content model

| Kind | Location | Written by | Mutable | Notes |
|---|---|---|---|---|
| **Draft** | `raw/<uuid>.md` | Human (nvim) | No | Exactly what was written, frozen at submit |
| **Note** | `notes/<uuid>.dj` | Human, via canonize | No | Same uuid as its draft |
| **Source** | inside a note | Human | No | `[title](url)` + why it mattered |
| **Wiki page** | `wiki/<uuid>.dj` | Agent | Yes | Generated; carries lineage. **Absent in v0.** |
| **Todo state** | `state/` | UI action | Yes | Done/undone, keyed by block ID |
| **HTML** | `site/` | Generator | Derived | pandoc + css + js |

The draft and the note share a uuid, so provenance is a filename lookup rather than a `git show`.
Keeping the markdown original is cheap and makes "what did I actually write" answerable without
git archaeology.

**There is only one kind of submission: a note.** A "conversation" is not a storage type — it's a
*view*, rendering the chain of notes and agent replies that reference each other by ID. Nothing is
decided at submit time, because submit time is where friction would kill adoption.

Filenames are `<uuid>.dj` and are meaningless. Pages and blocks are real; files are containers.

---

## 4. The loop

```
write (nvim)  →  submit  →  canonize  →  generate  →  render  →  read  →  reference
   prose          buffer      .dj with     agent      HTML +     browser    copy ID,
                  close        IDs        writes      click-     on         write note
                                          wiki        to-copy    localhost
```

**write** — a CLI command creates `notes/<uuid>.dj` in a fixed location (never in `pwd`) and opens
nvim on it. Plain prose. No required structure.

**submit** — happens on buffer close / nvim quit. **Not on save** — saving must stay free, or every
`:w` mid-thought fires an agent.

**canonize** — deterministic, see §4.1. The pre-canonization version is preserved by git; no second
copy is stored. After this the file is frozen.

**generate** — an agent reads the note, decides which wiki pages it affects, and rewrites them.
Every emitted block carries lineage. Unchanged blocks keep their IDs (see §7).

**render** — `wiki/*.dj` → HTML via pandoc, deterministically, with CSS and a small JS snippet that
copies a block's `{#id}` to the clipboard on click.

**read** — served on localhost. Read-only. This is the surface that matters most; if the wiki isn't
worth reading, nothing else saves the project.

### 4.1 Canonization

**Notes are authored in Markdown and stored as Djot.** The user never writes djot. Markdown allows
lazy list nesting (`- a` / `  - b` with no blank line between); djot does not, and would parse the
child as continuation text of the parent paragraph. Pandoc resolves this, so no hand-written
normalizer is needed and djot stays a purely internal format.

```
note.md
  → pandoc -f markdown-smart -t djot --wrap=preserve
  → restore checkbox markers:  "☐ " → "[ ] ",  "☒ " → "[x] "
  → djot.js --to ast
  → inject UUIDv7 ids + SHA-256 hashes
  → djot.js --from ast --to djot
  → notes/<uuid>.dj — frozen
```

Every flag was established by testing; each one prevents a silent rewrite of the user's text:

| Flag | Without it |
|---|---|
| `-f markdown-smart` | Apostrophes become curly quotes — `don't` → `don't`. |
| `--wrap=preserve` | Paragraphs are reflowed to a different width, destroying the line breaks that carry the writing's rhythm. |
| checkbox restore | Pandoc's djot writer has no task-list support, so `- [ ]` becomes a literal `☐` and stops being a task. No pandoc flag avoids this (`-task_lists` yields `\[ \]`, equally inert). |

The checkbox substitution is the only custom logic in the pipeline. `☐` is used as the marker
rather than `\[ \]` because the user would never type it, so it cannot collide with prose.

**Verified properties**, against `my-workflow.md` (15 blocks) and `mvp-interview.md` (142 blocks):

- Zero words lost in either file.
- Line breaks preserved inside paragraph blocks: `'so how do I work.\nIn a lot of ways.'` is one
  block containing the author's newline. Paragraph-level IDs and the original rhythm coexist; no
  line-level IDs are needed.
- `{#id}` references survive. Pandoc escapes them to `\{#id\}` on disk, but they parse back to the
  literal string, inline or standalone, including the compound `{#id:hash}` form.

**Open caveat:** injecting an id on a `list_item` AST node did not survive `--from ast --to djot`;
only the id on the paragraph inside it did. Needs resolving before list items can be referenced.

---

## 5. Lineage — the core mechanism

Every wiki block records what it was derived from:

```
WikiBlock -[DERIVED_FROM]-> Note block | Source | earlier version of itself
```

Stored as block attributes in the `.dj` file, so lineage lives in git alongside the content and
needs no separate database.

This mechanism carries three loads at once:

**Trust.** "What made you write this?" is always answerable, so agents can write freely without a
review gate. No HITL diff approval — approval gates are friction, and friction kills the system.

**Undo.** Everything is traceable and revertible, at block granularity.

**Anti-slop — the important one.** The stated dealbreaker is a 3-sentence note becoming a 5-page
article of general knowledge, diluting the user's own thinking. This looks like a prompt-tuning
problem, which would be unfixable. It isn't: **if every block must cite a note or source, the agent
structurally cannot emit unsourced general knowledge** — it has nothing to cite. A validator rejects
blocks with empty lineage.

When general knowledge *is* wanted ("add a section for the lineup with past members"), that
instruction is itself a note, and the generated blocks cite it. One rule handles both cases, and
the two kinds of block are distinguishable — worth rendering differently, since they carry
different trust.

---

## 6. Identity and versioning

- **Block ID** — UUIDv7, assigned at canonization. Stable forever. Its embedded millisecond
  timestamp gives `parsed_at` for free (`uuid.int >> 80`).
- **Content hash** — SHA-256 of `(type, content)`, 16-char prefix. Doubles as an integrity check.

### 6.1 Reference syntax

| Form | Meaning |
|---|---|
| `{#uuid:hash}` | that block, at that exact version |
| `{#uuid:hash+++}` | that block **and its subtree**, recursively |
| `[title](page.dj)` | a page — naturally "current", since pages are named not versioned |

**Block references are always pinned.** An unversioned `{#uuid}` is not legal. The reason is
provenance: when debugging why an agent wrote something, "which version of this paragraph was fed
to it" must be answerable from the reference alone, not reconstructed from timestamps. Page links
carry the "ongoing" intent that bare block references would otherwise have expressed.

`+++` is deliberately wide rather than a single `+`: it is never typed by hand — the HTML copies it
— so the only thing that matters is how easily it can be spotted next to a 36-character UUID.

The subtree is **derived**, not stored. No parent/child edges exist:

- **heading** → itself plus every block until the next heading of equal or higher level
- **list / task item** → itself plus following items of greater `depth`
- everything else → itself

`level` and `depth` are already recorded by the walker, so subtrees are computable from the flat
block list. `+++` is always fully recursive; a shallow variant could be added later without
changing its meaning.

Verified to survive canonization in every context: inline, several per paragraph, across soft
breaks, and inside list items, headings and task items.

Two kinds of time, and only one is needed:

- **System time / versioning** — "what did this say before", "show me the newest version". Provided
  by git + content hashes + lineage. Needed.
- **Valid time / quadruplets** — modelling when a real-world fact was true. Not needed; nothing is
  extracting world-facts.

---

## 7. Wiki regeneration must preserve IDs

When an agent regenerates a page, blocks whose content is unchanged **must keep their IDs**.
Otherwise every note ever written referencing them is orphaned, and invariant 5 breaks.

This is exactly the delta algorithm from
`architecture/delta_ingestion_and_block_versioning.md` — hash each incoming block, diff against the
existing page, classify as new / modified / deleted / unchanged. The document was written for
human-edited files; its subject now moves to agent-written wiki pages. The algorithm is unchanged.

The Parquet event log from that document is **not** carried over: it existed because the graph was
canonical and had no history. Files are canonical now, and git holds the history.

---

## 8. Repository layout

```
raw/          <uuid>.md   — the draft exactly as written, frozen
notes/        <uuid>.dj   — canonized, addressable, frozen
wiki/         <uuid>.dj   — agent-written, versioned. Absent until v1.
site/                     — generated HTML (gitignored)
state/                    — todo done/undone, keyed by block ID
src/                      — the tooling
```

`notes/` and `wiki/` are separate directories so the filesystem enforces the write boundary — a bug
cannot quietly let an agent into your notes. All `.dj` files sit flat within their directory; there
is no semantic hierarchy on disk. Structure lives in links and index pages, not in folders.

---

## 8.1 v0 — the mechanical loop, no LLM

v0 contains **no agent and no wiki**. It is a self-hosted, addressable notebook: everything is
deterministic and testable, and it delivers capture, addressability and re-entry before a single
API call exists.

```
kg new       create raw/<uuid>.md, open $EDITOR
kg submit    canonize → notes/<uuid>.dj, frozen
kg render    notes + views → site/, click-to-copy (block and subtree)
kg serve     render, then serve site/ statically on localhost
```

**Views** are functions over the corpus — always current, regenerated on every render, free:

- all notes, reverse-chronological
- all open todos (the "what was I in the middle of" view)
- backlinks for a block — which is just a view scoped to one id

These are distinct from the **curated index pages** described in §12: a view is computed, an index
page is agent-written wiki content. Both feel like entry points, which is why both get called
"index", but only the second needs an LLM.

Wiki generation, when it arrives, is explicit and manual: assemble notes, hand them to an agent,
take the result back. No embedding store, no retrieval — a model reads the notes directly. At a
few hundred notes the whole corpus fits in context, and retrieval only becomes necessary later.

The HTML shows the subtree copy action **only on blocks that have children**, so the affordance
itself tells the reader whether a subtree exists.

---

## 9. In scope for v1

- CLI: create-note, submit, generate, render, serve
- Canonization per §4.1: markdown → djot via pandoc, block IDs injected, file frozen
- Persistent djot parser worker (`npx` cold start is ~100–300 ms/file and would otherwise dominate)
- Agent generation of wiki pages with enforced lineage
- Lineage validator (rejects uncited blocks)
- ID-preserving regeneration (§7)
- HTML render with click-to-copy block IDs
- Todo toggle: instant, via `state/`, no regeneration
- Hierarchy via links and index pages

## 10. Explicitly out of scope for v1

- Tags — hierarchy first; may never be needed
- Any graph database — deferred until something actually needs traversal
- Entity extraction, relation extraction (old Phase 05) — **deleted, not deferred**
- LLM-to-Cypher (old Phase 07) — **deleted, not deferred**
- Vector search, full-text index

---

## 11. Acceptance test

**This conversation must run inside the system.**

An agent generates its questions as djot → renders to HTML → the user reads it in a browser →
copies block IDs → writes answers in nvim → submits → the agent responds. If v1 can carry an
interview like this one, it can carry a project.

Better than any feature checklist, and testable on day one.

---

## 12. Deferred — decided, not now

Each of these is agreed in principle; only the timing is deferred.

| Item | Note |
|---|---|
| **Context assembly** | "Give me everything about topic T." Expected to work by walking the wiki hierarchy from an index page and pruning. The pruning strategy is undesigned. |
| **Importing foreign markdown** | Chat exports (`.md` from a third-party plugin, or `.json` from captured API traffic). ~10–20 conversations for one publication-candidate topic. Needs original-preservation with file-level provenance — a different tier from hand-written notes. Note that the *conversion* half is no longer deferred: pandoc markdown → djot is on the core path per §4.1. What remains deferred is provenance for foreign material. |
| **`context-harvest/`** | Leave in place. Do not export, do not delete. May be deleted entirely once the wiki works. |
| **Archiving source content** | Saving the actual page/video/image, not just the URL. |
| **Browser extension** | Current flow (extension copies `[title](url)`, paste into a note) is good enough. |
| **nvim plugin** | Tag pickers, metadata menus. Premature until the plain workflow has been run. |
| **Cross-cutting todo view** | "All open tasks." Straightforward once blocks are queryable; per-page is enough for now. |
| **Async agents + notifications** | v1 is synchronous and blocking. |
| **Mobile / remote serving** | localhost only for v1. |
| **"UI notes"** | UI actions submitting notes on the user's behalf (ID copied, todo flipped) as an event log. Good idea, not load-bearing. |
| **Sources view per topic** | "Every URL I saved about watchmaking." Ships with context assembly. |

---

## 13. Open questions

Ordered by how much they'd cost to get wrong.

**Q1 — How does an agent know which wiki page a note affects?** *Deferred as its own initiative.*
Solving this properly means semantic linking between blocks — embeddings or LLM reading — and that
is a large piece of work with recurring cost and probabilistic failure modes. It is also, arguably,
the thing that would make this an actual knowledge graph rather than a linked document store.

Until then v0 uses **explicit reference as ground truth**: a note concerns the blocks whose ids it
cites. That is not a wrong approximation waiting to be corrected — it is a *subset* of the truth,
since a note genuinely does concern the block you clicked. Semantic linking is purely additive on
top, so nothing built now is wasted.

The two graphs should stay distinct edge types, because they have opposite properties:

| | Reference / lineage | Semantic |
|---|---|---|
| Source | ids you typed, or cited at generation | embeddings / inference |
| Accuracy | exact | probabilistic |
| Cost | free | per-block, recurring |
| Fails | never | silently |

When a link turns out to be wrong, the first question is always whether a machine guessed it or a
human asserted it. That must be answerable from the edge type alone.

**Q2 — What is the unit of regeneration?**
One page, a page and its index, or a transitive neighbourhood? Interacts directly with Q1.

**Q3b — Lineage: reject or flag?** Invariant 4 currently says an uncited wiki block is *rejected*.
That is a gate, and gates contradict "agents write freely, revert later". The likely revision is to
check lineage at **render** time and mark uncited blocks visibly in the HTML — making slop visible
rather than silently dropping content that may have been wanted. Not decided; no wiki exists yet.

**Q3 — Reference syntax in prose.** *Resolved 2026-08-03.*
Plain `{#019abc}` works, inline or on its own line, as does the compound `{#019abc:<hash>}`.
Verified to survive markdown → djot → parse intact. No new syntax needed.

**Q4 — Is the paragraph the right block unit?**
Agreed as the default, but the user's prose sometimes packs several thoughts into one paragraph and
sometimes spreads one thought over many short lines.

**Q5 — Model and cost control.**
Which model generates the wiki, and what stops a large note from triggering an expensive cascade?

**Q6 — Directory naming.**
`notes/` and `wiki/` used here provisionally.

**Q7 — Link capture detail.** *(unanswered, `mvp-interview.md:342`)*
Assumed: a source is a line inside a note; the agent may promote it to its own page.

**Q8 — Where is this design over-engineered?** *(unanswered, `mvp-interview.md:453`)*

---

## 14. What is being dropped from the old architecture

| Dropped | Why |
|---|---|
| LadybugDB as canonical storage | Files in git are canonical. A graph, if it returns, is a derived cache. |
| Phase 05 — entity/relation extraction | Never requested. Lineage is the semantic layer, and it's recorded at generation time rather than extracted — free and exact. |
| Phase 07 — LLM-to-Cypher | Nothing needs ad-hoc graph traversal. |
| Temporal quadruplets / RDF-star | Solves valid-time; only system-time is needed. |
| `Annotation` node type | Notes referencing IDs cover it. |
| HITL diff approval | Reversed deliberately: lineage plus revert replaces the approval gate. |
| Parquet event log | Superseded by git. |
| LangGraph | Considered and rejected previously; still rejected. |

`architecture/delta_ingestion_and_block_versioning.md` is **retained** — see §6 and §7.
`independent-audit/architectural_audit_response.md` is stale (claims the code uses Kuzu) — ignore.

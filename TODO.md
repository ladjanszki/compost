# TODO

Everything discussed, by version. See `mvp-design.md` for why, `DEVELOPMENT.md`
for how.

Before adding anything here, decide whether it is a **render-time** change
(backward compatible, works on old notes for free) or a **canonization-time**
change (baked into immutable `.dj` files, recoverable only via an explicit
migration). See DEVELOPMENT.md — it decides urgency more than anything else.

---

## v0 — cleanup and carry-over ✓

- [x] Tag the LadybugDB architecture as `v0-graph-architecture` before cleanup
- [x] Delete 47 superseded files; carry ~360 LOC of parsing and rendering
- [x] Audit carried-over code against real behaviour, not the design docs
- [x] Fix walker: `task_list` / `task_list_item` were silently dropped
- [x] Fix walker: nested items emitted before their parent, depth discarded
- [x] Strengthen roundtrip test with an AST-tag coverage check — a dropped
      element type passed by being absent from both sides of the comparison

## v0.1 — the mechanical loop ✓

- [x] Canonization: Markdown → Djot via pandoc, no hand-written normalizer
- [x] Establish pandoc flags by testing (`-smart`, `-auto_identifiers`,
      `--wrap=preserve`, checkbox restore)
- [x] Inject ids as text via `--sourcepos`, not an AST round-trip
- [x] Verifier that refuses to emit a note with unaddressable blocks
- [x] `loosen()` — list item ids are dropped in HTML unless the list is loose
- [x] Reference syntax: `{#uuid:hash}` / `{#uuid:hash+++}`, always pinned
- [x] `raw/` and `notes/` split, sharing a uuid
- [x] `kg` on PATH via `pip install -e .`
- [x] `kg init` — defers the tool/data split to a runtime choice
- [x] `kg new` / `submit` / `render` / `serve`
- [x] Base resolution: `--root`, `$KG_HOME`, or a `.kg` marker in any parent
- [x] Static site: click for a block, shift-click for its subtree
- [x] Shift-hover highlights the subtree before you commit to copying it
- [x] Backlinks — "Referenced by" on the target note
- [x] Reverse-chronological index, dated from the UUIDv7 timestamp
- [x] `README.md`, `DEVELOPMENT.md`, `CHANGELOG.md`
- [x] Sabotage-verify every guarantee

---

## v0.2 — conversations, and an agent in the loop ✓

- [x] **Fix the walker's div handling** — a div swallowed its children, so every
      block of every folded turn would have been unaddressable
- [x] **8-hex handles** replacing UUIDv7 block ids; id overhead 26.8% → 10.2%
- [x] Optional version pin: `{#handle}` immutable, `{#handle@ver}` artifacts
- [x] `conversations/` and `artifacts/` — the split is mutability, not authorship
- [x] Turns as `{.turn author=...}` divs; authorship in the djot, so in git
- [x] Append verification — earlier blocks must survive unchanged, structure
      included, since the seam failure changes no text
- [x] Thread inferred from the blocks a draft cites; no second handle to copy
- [x] `blocks.json` — the corpus an agent can actually cite from
- [x] `kg check` — dangling references and handle collisions
- [x] `kg import` — a closed Claude Code session becomes a conversation
- [x] Folded tool traffic; per-turn author labels
- [x] `AGENTS.md` — an agent needs the base and this file, not the repo
- [x] Migrate the test base: 248 blocks remapped, zero dangling

## v0.3 — next

- [ ] **Reply affordance in the HTML** — a button that puts you in a draft for
      the block you clicked. The handle is already copied; the missing half is
      not having to switch to a terminal
- [ ] **Open todos view** — "what was I in the middle of". Block type is already
      in `blocks.json`; render-time, so it works retroactively
- [ ] **Backlinks are per-note, not per-block** — a target citing eleven blocks
      shows the same link eleven times with no indication of which block each
      points at. Noise at exactly the moment it should be useful
- [ ] `pytest` wiring and one runner for all five suites; no CI yet
- [ ] Persistent djot worker — `npx` costs ~1 s per spawn and `kg render` parses
      every file twice. One-file-per-conversation keeps this tolerable, but it
      dominates render time
- [ ] Remove `src/ingest/block_schema.py` (legacy; canonize does its own)
- [ ] Restore a copy-confirmation flash outside the repaint cycle
- [ ] Decide whether `+++` should be the *default* on headings, with a
      modifier for the single block

## v1 — artifact generation

The point where an LLM writes rather than converses. Nothing below is
deterministic.

- [ ] Explicit generation: hand `blocks.json` to an agent, take an artifact
      back. No embeddings — a project corpus fits in context
- [ ] **README and TODO as generated artifacts**, in djot, read from the served
      pages. The bootstrap has to sit *outside* the base, since a guide living
      inside it is only findable after you know the base exists
- [ ] Record lineage on every generated block (`DERIVED_FROM` → source block)
- [ ] **Lineage validation** — a block that cites nothing is invalid. Open:
      reject at write time, or flag visibly at render time (§13 Q3b)
- [ ] **Id-preserving regeneration** — unchanged blocks must keep their ids or
      every note referring to them is orphaned. This is the delta algorithm in
      `architecture/delta_ingestion_and_block_versioning.md`
- [ ] Render agent-written general knowledge differently from note-grounded
      blocks; they carry different trust
- [ ] Curated index pages (agent-written entry points, distinct from views)
- [ ] Cost control: which model, and what stops a large note cascading

## v2+ — deferred, agreed in principle

- [ ] **Semantic linking** (§13 Q1) — which page a note affects beyond the
      blocks it cites. Needs embeddings or LLM reading; its own initiative.
      Keep inferred edges in a distinct type from reference/lineage edges
- [ ] **Context assembly** — "everything about topic T", by walking the wiki
      hierarchy and pruning. Pruning strategy undesigned
- [ ] Import foreign markdown: chat exports (`.md` from a plugin, `.json` from
      captured API traffic). ~10–20 conversations for one publication topic.
      Needs file-level provenance — a different tier from hand-written notes
- [ ] Todo state store — flipping a checkbox must not regenerate the wiki.
      Note that a todo written in an immutable note cannot be marked done
      there; the state needs a mutable home
- [ ] "UI notes" — UI actions submitting notes on your behalf, as an event log
- [ ] Archiving source content (page, video, image), not just the URL
- [ ] Browser extension for capture
- [ ] nvim plugin — tag pickers, metadata. Premature until the plain workflow
      has been run for a while
- [ ] Sources view per topic — ships with context assembly
- [ ] Mobile / remote serving
- [ ] Tags — may never be needed; hierarchy plus agent-written index pages may
      cover it

---

## Dangling references

*Case 1 and case 3 are now reported by `kg check` (v0.2).* The rest stands.

Found by submitting this repo's own docs into a knowledge base: `kg render`
reported *"1 referenced"* for the example reference in `README.md`, whose
target uuid exists in no note. The backlink index happily created an entry for
a block that was never submitted. Nothing warned, nothing rendered, nothing
broke — the reference simply pointed nowhere, silently.

**Why it matters.** Notes are immutable, so a bad reference can never be
corrected in place; it stays in the corpus forever. Without detection you only
discover a typo by going to look for one, and the count can only grow.

### The four ways a reference can dangle

1. **Target never existed** — a typo, or a reference pasted from somewhere
   else. The uuid appears nowhere in the corpus. *Possible today.*
2. **Hash mismatch** — the uuid resolves but the content hash does not. Cannot
   happen while every block lives in an immutable note. *Becomes real in v1,
   when wiki pages are mutable.*
3. **Target file removed** — notes are immutable but a file can still be
   deleted from the repo. *Possible today.*
4. **Regeneration orphaned it** — a wiki page was rewritten and unchanged
   blocks were not given their old ids back. *v1; prevented by the
   id-preserving regeneration item above, and the reason it is not optional.*

### Options

- **`kg check`** — scan every note's references and report each dangling one
  with its kind, source note, and target. Render-time, so it works
  retroactively on the whole corpus. Report-only by default; an exit code for
  scripting. This is the cheap first move.
- **Show them while reading** — style dangling references distinctly in the
  HTML. Better than a separate command for the common case, because you notice
  without having to think to look. Both are worth having; they catch different
  moments.
- **Warn at submit** — check a note's references as it is canonized and print a
  warning. Must *not* block: notes are immutable, and refusing a submission
  over a typo would lose the writing. Warning only.
- **Resolve case 2 from history (v1)** — a hash that no longer matches the
  current block is not an error, it is a reference to an *earlier version*.
  Resolve it from git rather than reporting it broken. This is the annotation
  durability guarantee in
  `architecture/delta_ingestion_and_block_versioning.md` §4.6, and the reason
  references are pinned in the first place.

Case 2 is the one to keep in mind: once the wiki is mutable, the *majority* of
"dangling" references will be perfectly good references to superseded content.
A checker that cannot tell the difference will be noise, and noise gets muted.

---

## Open questions

Carried from `mvp-design.md` §13.

- [ ] **Q1** How does an agent know which wiki page a note affects?
      *Deferred as its own initiative — see v2+ semantic linking.*
- [ ] **Q2** What is the unit of regeneration — one page, a page and its index,
      a transitive neighbourhood? Interacts with Q1
- [ ] **Q3b** Lineage: reject at write, or flag at render?
- [x] **Q9** Where do agent replies live? *Resolved 2026-08-06: in conversations,
      which either party writes. The boundary moved from authorship to
      mutability.*
- [x] **Q10** Are chat logs citable sources? *Resolved 2026-08-06: yes,
      deliberately. Decided against the recommendation; reversible at render
      time because authorship is recorded, so no migration if it goes wrong.*
- [ ] **Q4** Is the paragraph the right block unit? Agreed as default, but
      prose sometimes packs several thoughts into one
- [ ] **Q5** Which model generates the wiki, and what caps the cost?
- [ ] **Q7** Link capture detail — assumed a source is a line inside a note,
      promotable to its own page
- [ ] **Q8** Where is this design over-engineered? *(never answered)*
- [x] **Q3** Reference syntax — resolved: `{#uuid:hash}`, always pinned
- [x] **Q6** Directory naming — resolved: `raw/`, `notes/`, `site/`

---

## Before v1: use v0.1 for a week

Write real notes, react to them, see whether the loop holds. Everything after
this point is expensive to change and cheap to postpone, and the corpus you
build now is what tells us whether generation should work the way we assumed.

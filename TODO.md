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

## v0.2 — small, all render-time or internal

- [ ] **Open todos view** — "what was I in the middle of". Block type is
      already recorded; render-time, so it works on existing notes
- [ ] `pytest` wiring and a runner for all three suites; no CI yet
- [ ] Persistent djot worker — `npx` spawns a Node process per parse
      (~100–300 ms). Fine now, wants fixing before bulk ingestion
- [ ] Remove `src/ingest/block_schema.py` (legacy; canonize does its own)
- [ ] Restore a copy-confirmation flash outside the repaint cycle
- [ ] Decide whether `+++` should be the *default* on headings, with a
      modifier for the single block ("rewrite this section" is likely commoner)

## v1 — wiki generation

The point where an LLM enters the system. Nothing below is deterministic.

- [ ] `wiki/` directory; agents write there, humans never do
- [ ] Explicit generation: assemble notes, hand to an agent, take the result
      back. No embeddings — a few hundred notes fit in context
- [ ] Record lineage on every generated block (`DERIVED_FROM` → note block)
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

## Open questions

Carried from `mvp-design.md` §13.

- [ ] **Q1** How does an agent know which wiki page a note affects?
      *Deferred as its own initiative — see v2+ semantic linking.*
- [ ] **Q2** What is the unit of regeneration — one page, a page and its index,
      a transitive neighbourhood? Interacts with Q1
- [ ] **Q3b** Lineage: reject at write, or flag at render?
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

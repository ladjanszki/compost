# CHANGELOG

This file overarches versions. Entries below the `v0` marker describe the
LadybugDB-centric architecture that `v0` closes out.

## v0.2 — 2026-08-06 — conversations, and an agent in the loop

The loop now runs with both parties in it. Either can write; neither can alter
what the other wrote.

**Changed — the shape of the system**

- **The split is mutability, not authorship.** `notes/` and `wiki/` enforced
  "humans write notes, agents write the wiki" with the filesystem. That boundary
  is gone: `conversations/` is append-only and `artifacts/` is rewritten in
  place, and either party writes either kind. What protected anything was never
  the directory but immutability, and that is kept — no block already written
  ever changes, whoever wrote it. Revises invariant 3 and §3 of `mvp-design.md`,
  which called a conversation a view rather than a storage type.
- **A conversation is one append-only file**, not a directory of turns. Turns
  get concatenated for reading anyway, and one file is one djot parse: at the
  measured ~1 s per `npx` spawn, a 70-turn imported session costs about a second
  this way against roughly two minutes as separate files.
- **Turns are fenced divs carrying their author** —
  `{#handle .turn author="claude"}`. One native djot construct provides the
  container, the authorship, and the nesting that folded tool traffic needs. No
  frontmatter, no sidecar, nothing outside the reference implementation.
- **Block ids are 8 hex characters, not UUIDv7.** A UUID cost 39 bytes per block
  on disk and 56 per reference — measured at 26.8% of the corpus, and unreadable
  inline. Handles cost 10.2%. Nothing needed a per-block timestamp; note ids stay
  UUIDv7 so dates and ordering still work. Rejected the shorter registry-backed
  handle: a handle-to-block file cannot be rebuilt from the `.dj` files, so
  losing it would break every reference at once.
- **The version pin is now optional.** `{#handle}` for immutable conversation
  blocks, whose handle already pins their content; `{#handle@ver}` for artifacts.
  Both forms are defined now so the syntax never has to change again.
- **The thread is inferred from citations.** You reply by clicking a block, so
  the conversation is implied; `-c` is only needed when a draft cites nothing or
  cites two threads.

**New**

- `kg artifact` — publish a markdown document as an artifact. On update,
  unchanged blocks **keep their handles**, matched by content hash rather than
  position so an insertion does not renumber everything after it. Without this,
  regenerating a document orphans every comment ever written about it, and those
  comments live in immutable turns where they can never be corrected. This is
  the delta algorithm from `architecture/delta_ingestion_and_block_versioning.md`,
  and it turned out to be about thirty lines.
- `kg import` — a closed Claude Code session becomes a conversation. The whole
  log is turned into one markdown document and canonized in a single pass,
  because pandoc carries fenced divs and their attributes through to djot.
  Nothing is filtered: tool traffic and thinking are wrapped in `.tool-call`
  divs that the renderer folds away, so the transcript is complete and every
  block of it addressable. Subagent branches become `claude:sidechain` turns.
- `site/blocks.json` — every block with its handle, hash, type, source,
  structure, citations and author. An agent can read a `.dj` with grep but
  cannot *cite* one, because the hash is SHA-256 over the parsed block; this
  closes that gap and doubles as whole-corpus context assembly.
- `kg check` — dangling references and handle collisions, as a set difference
  over `blocks.json`. A dangling reference cannot be repaired in place, because
  the turn holding it is immutable, so noticing is the only defence.
- `AGENTS.md` — everything an agent needs to read and write a base, without
  reading this repository.
- Rendering: per-turn author labels straight from the djot attribute via
  `attr()`, no JavaScript; `.tool-call` divs folded into `<details>`; whole
  turns subtree-copyable.

**Fixed — correctness**

- **The importer attributed the harness to the human.** A `user` line in a
  session log is not the same thing as "the person typed this": tool results
  come back as user messages because that is the API protocol, the harness
  injects its own context, and a slash command echoes both its name and its
  output. In one 18-"user"-turn session **only 1 turn was genuinely typed**, so
  a reader saw directory listings above the user's name. Tool results are now
  folded into the call that produced them, matched on `tool_use_id`; harness
  messages are attributed to `system`; injected system-reminders are lifted out
  of real typing and kept, folded, rather than discarded.
- **A conversation's date was decoded from a UUIDv4.** An imported session is
  named after its log, whose id is not a UUIDv7, so reading its first twelve hex
  digits as a millisecond timestamp dated one conversation to the year 4527.
  `_when()` now checks the version nibble, and imported turns carry their real
  timestamp as an attribute.
- **A div swallowed its children.** `inject_ids` recursed into a div and gave
  every child an id; `ast_walker` nested those children inside the div's
  `content` instead of emitting them. Two halves of one pipeline held opposite
  beliefs, so canonization wrote ids into the file for blocks the block list did
  not contain — clickable in HTML, resolving to nothing, absent from every view.
  Neither the verifier nor the roundtrip test could see it, because the blocks
  were missing from both sides of every comparison; `test_roundtrip` even had a
  `_flatten()` helper written to accommodate the nesting. This blocked folds
  entirely, and would have made every block of every imported turn
  unaddressable.

- **A reference inside code is not a citation.** Importing this project's own
  sessions took `kg check` from 6 dangling references to 48 — every one a shell
  command from a throwaway experiment or a documented example. A checker that
  reports those is noise, and noise gets muted, which would cost the only thing
  the check is for. Code blocks and code spans are now excluded, and the count
  went to zero.
- **The repo is its own knowledge base.** `.kg`, `conversations/`, `artifacts/`
  and `raw/` at the root; the docs are published with `kg artifact`. Moving the
  corpus in preserved all 3311 handles exactly, verified by comparing a hash of
  the whole handle set before and after.
- Index links show the document's own heading, the artifact's filename (so
  "where is the README?" has an answer), the real date, participants, and size.
  A conversation is titled by **what the human opened with** — its first heading
  is usually something the agent wrote, and its first block can be harness
  output, which titled one session "<local-command-caveat>Caveat: The...".

**Measured, because it drove decisions**

- Appending a turn directly after a heading section merges it into the
  *previous* paragraph — an already-referenced block's text silently grows and
  the new turn's id attaches to nothing. A list appended after a paragraph is
  absorbed as continuation text and loses its id. A single blank line prevents
  every case found; the turn fence then makes merging structurally impossible.
- `npx @djot/djot` costs ~1 s per spawn, and `kg render` parses each file twice.

**Migration**

`tools/migrate_to_handles.py` remapped the test base: 248 blocks, 27 references
rewritten, zero dangling, including a cross-file subtree reference. Old-to-new
is positional — re-canonizing an immutable draft yields the same block sequence
— so nothing was guessed, and the script refuses to write if the sequences do
not correspond.

## v0.1 — 2026-08-04 — the mechanical loop

The write → submit → canonize → read → reference → submit loop works end to
end, with no LLM anywhere in it. Wiki generation is still unbuilt.

**New**

- `kg` on PATH via `pip install -e .`, working from any directory. The base is
  found via `--root`, `$KG_HOME`, or a `.kg` marker in any parent.
- `kg init` creates a base anywhere, which defers the tool/data split to a
  runtime choice rather than an architectural commitment.
- `kg new` opens `$EDITOR` and submits on exit — never on save, so saving
  mid-thought stays free.
- Static site with click-to-copy. Click a block for `{#uuid:hash}`,
  shift-click for `{#uuid:hash+++}`. Holding Shift while hovering highlights
  the subtree, so what will be copied is visible before committing.
- Backlinks: a note referencing a block appears as "Referenced by" on the note
  containing it. Computed at render time, so it works retroactively.
- Reverse-chronological index, dated from the UUIDv7 timestamp.

**Fixed — correctness**

- `loosen()` moved into canonization. Djot drops a list item's id in HTML
  unless the list is loose, so every list item and todo was unaddressable.
  Since notes are immutable this could not have been repaired later: notes
  canonized before the fix would have been permanently degraded.
- Backlink scanning reads parsed block text rather than the raw file. Pandoc
  escapes references on disk as `\{#uuid:hash\}`, so scanning the file found
  nothing.

**Docs**

- `README.md` restored — the repo had no entry point since the cleanup.
- `DEVELOPMENT.md` added: architecture, the non-obvious pandoc and djot
  behaviours, the sabotage-verification practice, and where the next work is.

## 2026-08-03 — Architecture pivot and repository cleanup

**Tagged `v0-graph-architecture`.** Everything removed in this cleanup remains
reachable there (`git show v0-graph-architecture:<path>`).

The product changed shape after a workflow interview (`my-workflow.md`,
`mvp-interview.md`). The new design is in `mvp-design.md`:

- **`.dj` files in git are the source of truth.** LadybugDB is no longer
  canonical storage. Any graph that returns will be a derived, disposable cache.
- **Notes are immutable and human-written; wiki pages are agent-written.** The
  human never writes the wiki, agents never write notes.
- **Lineage replaces semantic extraction.** Every wiki block cites the note or
  source block it derives from. Recorded at generation time rather than
  extracted afterwards — free, exact, and it doubles as the anti-slop
  mechanism: a block with nothing to cite is invalid.
- **Deleted, not deferred:** Phase 05 (entity/relation extraction), Phase 07
  (LLM-to-Cypher), temporal quadruplets, `Annotation` nodes, the Parquet event
  log (git supersedes it), and HITL diff approval.
- **Retained:** `architecture/delta_ingestion_and_block_versioning.md`. Its
  content-hash and delta mechanisms carry over unchanged; the subject moves
  from human-edited notes to agent-regenerated wiki pages.

Removed 47 files across two commits (superseded docs, then the LadybugDB
ingestion path). ~360 LOC of parsing and rendering carried forward.

**Defects found during the carry-over audit**, both on the MVP critical path
and neither caught by the existing roundtrip test:

1. `ast_walker.py` silently drops `task_list` / `task_list_item`. Djot supports
   them natively (`checkbox: checked|unchecked`); the walker has no branch, so
   todos vanish with no error.
2. Nested list items are emitted *before* their parent, and nesting depth is
   discarded, so `- a` / `- b` (nested) yields `[b, a]` flattened to one level.

*Correction:* an earlier version of this entry claimed nested items were
embedded as raw markup in the parent block. That was wrong. The confusion came
from a probe written without blank lines — **djot requires a blank line before
a nested list**; without one djot itself (not the walker) parses the child as
lazy continuation text of the parent paragraph. That is spec behaviour and a
*canonization* concern, since hand-written notes rarely include those blank
lines. The walker defect is the ordering and depth loss described above.

`test_roundtrip.py` detects none of it: a dropped element is absent from both
sides of the comparison, and reordering survives re-parsing unchanged. The
Phase 03 claim of "no data loss, 31 block types" holds only for the properties
the test actually compares.

---

## Phase 02 & 03 — 2026-05-16

Implemented Phase 02: Rewrote ingestion to bypass Pandoc and use native `djot.js`. Dropped JSONL intermediate representation to write blocks directly into Parquet files, which are immediately loaded into LadybugDB during `ingest_page()`. Extended Block schema with `language` field and added `LINKS_TO` relationships for explicit cross-links. Re-wrote `inline_reconstruct.py` and `ast_walker.py` against the native AST.

Implemented Phase 03: Built Djot rendering via `blocks_to_djot.py` that formats structured Block dictionaries back into raw Djot text. Added a roundtrip validation harness (`test_roundtrip.py`) validating `Djot -> Blocks -> Djot` without data loss (whitespace-normalized, structural fidelity). Passed verification for 31 block types. Achieved ~4.6x token reduction compared to raw JSON block representation.

## 2026-05-10 — Kuzu to LadybugDB Migration
Replaced Kuzu with LadybugDB (community fork) as the embedded graph database, following
Apple's acquisition and archiving of the Kuzu repository. Renamed `kuzu_schema.py` →
`ladybug_schema.py`, `kuzu_loader.py` → `ladybug_loader.py`. Updated all design docs,
implementation plans, and workspace paths. Python package changed from `kuzu` to
`real-ladybug==0.15.3`. Import alias: `import real_ladybug as lb`.
LadybugDB now supports `OPTIONAL MATCH` — constraint removed from Phase 07 design and
implementation plans. Added defensive parsing guidance for `SHOW_TABLES()` output change.
No data migration was needed (no existing database on disk).

## Phase 01 — 2026-05-08

JSONL → LadybugDB graph index. Implemented `src/index/` module: `ladybug_schema.py`, `jsonl_to_parquet.py`, `ladybug_loader.py`, `build_index.py`. Loads blocks and pages from JSONL into LadybugDB via Parquet COPY FROM. Full rebuild on each run. Verified: 47 Block nodes, 7 Page nodes, 47 HAS_BLOCK edges from the test corpus.

Dependencies added: `ladybug`, `pyarrow`.

## Phase 00 — 2026-05-08

Djot → JSONL ingestion pipeline. Implemented `src/ingest/` module: pandoc-based parser, AST walker, inline reconstructor, block schema builder, JSONL writer. Ingests a Djot file into `blocks.jsonl` + `pages.jsonl`. Handles heading, paragraph, list_item (ordered + unordered). Verified: 9 blocks from test file, 47 blocks from full test corpus (7 files).

Dependencies: `python 3.12`, `uuid6`, `pandoc` (system).

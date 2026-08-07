# Development

Written for someone arriving cold. Read `README.md` first for what the system
does, then this to work on it. `mvp-design.md` is the product spec and is
authoritative where this document is silent.

---

## Mental model

Three ideas carry everything:

1. **`.dj` files in git are the source of truth.** HTML, `blocks.json`, any
   future graph — all derived and disposable. If you find yourself storing
   something that cannot be rebuilt from the `.dj` files, stop. The one
   exception proves the rule: *authorship* is asserted, not derivable, which is
   exactly why it lives in the `.dj` as a turn attribute rather than in
   `blocks.json`.
2. **Blocks are immutable; files are not.** A conversation file grows by
   appending turns, but no block already in it ever changes. That is what makes
   handles permanent and appending safe, and it is why conversations need none
   of the delta machinery artifacts will.
3. **The split is mutability, not authorship.** Either party writes either kind.
   `conversations/` is append-only, `artifacts/` is rewritten in place. What
   protects you is not that agents are locked out of a directory but that
   nothing already written can be altered.
4. **Blocks are the unit.** Every paragraph, heading, list item and todo has an
   8-hex handle. The whole product is that these are stable, copyable, and
   resolvable.

---

## The most important rule in this codebase

**Render-time changes are backward compatible. Canonization-time changes are
not.** Ask which side a change falls on *before* building it.

A **render-time** change reads the corpus and produces output. It applies to
every note ever written, for free, the next time you run `kg render`. Backlinks
were added after notes already existed and immediately worked on all of them.
Views, styling, click behaviour, new indexes — all free.

A **canonization-time** change alters what gets written into a `.dj`. Notes are
immutable, so notes canonized under the old behaviour keep it forever.
`loosen()` was this kind: without it, every list item and todo was unclickable,
and no amount of later rendering could recover it.

### Recovering from a canonization change

`raw/<uuid>.md` exists precisely so this is survivable. But re-canonizing is
not free, and the cost depends on what changed:

**Serialization-only** — whitespace, attribute placement, anything that does
not alter which blocks exist. Block ids and content are unchanged, so notes can
be migrated in place and every existing reference still resolves. `loosen()` is
in this class: re-running it over `notes/*.dj` would have been safe.

**Structural** — anything that changes block boundaries or what counts as a
block (splitting paragraphs differently, treating a construct as one block
instead of two). Re-canonizing `raw/` produces a *different set of blocks*, and
`canonize_text()` assigns fresh UUIDv7s. **Every existing `{#uuid:hash}`
reference breaks.** Recovering means writing an explicit migration that maps
old blocks to new ones and carries the ids across — possible because `raw/` is
kept, but real work, and impossible where blocks genuinely split or merged.

So: `raw/` makes canonization changes *recoverable*, not *cheap*. Treat any
change to block boundaries as a one-way door and get it right before the corpus
grows.

---

---

## Layout

The repo is also a knowledge base: `.kg`, `conversations/`, `artifacts/` and
`raw/` live at the root, so `kg` works anywhere in the tree without `KG_HOME`.
The docs are published into it with `kg artifact <file>.md`; the markdown is the
source and the `.dj` is its addressable form. **Republish after editing a doc**,
or the served copy drifts from the file.

```
src/
  cli.py              the `kg` entry point (argparse, one function per command)
  store.py            locating a base; conversations/ and artifacts/
  refs.py             THE handle and reference format, and what counts as a
                      citation — one source of truth
  artifact.py         documents: publish, and keep handles across a rewrite
  conversation.py     turns: wrap, append, verify; infer the thread from cites
  importer.py         a Claude Code session JSONL -> one markdown document
  canonize/
    __init__.py       canonize_text() + the verifier that can refuse output
    md_to_djot.py     pandoc wrapper; every flag prevents a silent rewrite
    inject_ids.py     --sourcepos parse, ids inserted as text, then loosen()
  ingest/
    djot_ast.py       runs djot.js, returns the native AST
    ast_walker.py     AST -> flat list of block dicts
    inline_reconstruct.py   inline nodes -> djot markup text
    block_schema.py   block records (legacy; canonize does its own)
  render/
    to_html.py        base -> static site, backlinks, click-to-copy, folds
    index.py          blocks.json + the check behind `kg check`
    blocks_to_djot.py blocks -> djot text (not on the canonize path; needed
                      when agents start generating artifacts)
tests/
  test_canonize/      markdown -> addressable turn
  test_conversation/  appending turns without disturbing them
  test_importer/      a session log -> a conversation
  test_render/        base -> clickable site, blocks.json, kg check
  test_03/            djot -> blocks -> djot roundtrip
tools/                scratch prototypes and one-off migrations
```

Run everything:

```bash
for t in tests/test_canonize/test_canonize.py \
         tests/test_conversation/test_conversation.py \
         tests/test_importer/test_importer.py \
         tests/test_render/test_site.py \
         tests/test_03/test_roundtrip.py; do
  conda run -n knowledge-graph python "$t" || echo "FAILED: $t"
done
```

There is no pytest wiring yet. Tests are standalone scripts that print
`PASS`/`FAIL` per check and exit non-zero on failure.

---

## The pipeline

```
raw/<conv>/<turn>.md
  → pandoc -f markdown-smart-auto_identifiers -t djot --wrap=preserve
  → restore checkbox markers        "☐ " → "[ ] ",  "☒ " → "[x] "
  → djot.js --to ast --sourcepos
  → insert {#handle} lines as text, bottom-up
  → loosen: blank line after each list item's id line
  → wrap in {#handle .turn author="..."} ::: ... :::
  → append to conversations/<conv>.dj, then verify nothing earlier moved
```

Notes are **authored in Markdown and stored as Djot**. Markdown allows lazy
list nesting; djot does not and would parse the child as continuation text.
Pandoc resolves that, so there is no hand-written normalizer and the author
never sees djot.

Ids are inserted **as text**, not round-tripped through the AST, so a canonized
file is exactly pandoc's output plus inserted id lines. The diff is additive
and reviewable — this is the only moment the system edits something a human
wrote, and it should stay that way.

`canonize_text()` verifies its own output and raises rather than emitting a
turn whose blocks are unaddressable. Trust that check; it has caught real bugs.

`append_turn()` verifies again after the append: every block already in the file
must still be there with the same handle, text, depth, level and containment.
Structure is compared because the seam failure changes no text — see
`conversation.py` for the measured cases.

---

## Non-obvious things, all found by testing

None of these are documented upstream. Changing code near them without knowing
them will silently break addressability.

**Pandoc**

- `-smart` off, or apostrophes become curly quotes (`don't` → `don't`).
- `--wrap=preserve`, or paragraphs are reflowed and the author's line breaks —
  which carry the rhythm of the writing — are destroyed.
- `-auto_identifiers` off, or pandoc leaves its own `{#a-heading}` slug in the
  file. Our uuid still wins semantically, so this is cleanliness, but slugs
  derive from heading text and invite referencing an id that moves.
- Pandoc's djot writer has **no task-list support**: `- [ ]` becomes a literal
  `☐`. No flag avoids it (`-task_lists` yields an equally inert `\[ \]`), so
  the marker is restored by regex. That substitution is the only custom text
  logic in the pipeline.

**Djot**

- A `{#id}` written before a heading attaches to the enclosing **`<section>`**,
  never the heading. The walker pushes it down onto the heading; the HTML
  renderer's script moves it back at load time and treats the section as the
  heading's subtree container.
- A list item's id is accepted **only on the item's first paragraph**
  (`- {#id}` / newline / `  text`). An id before the list attaches to the list
  container; the inline form `- {#id} text` is silently discarded.
- A list item's id is **dropped in HTML unless the list is loose** — djot
  unwraps the item's paragraph and the id goes with it. `loosen()` adds a blank
  line after each id line. Doing it *between* items misses single-item lists,
  which have no sibling to separate from.
- References survive on disk **escaped**, colon included: `\{#handle\}`.
  Parsing unescapes them, so scan parsed block text, never the raw file. Since
  a handle and an id attribute are now the same shape, **escaping is the only
  thing separating a reference the author typed from an id we assigned** —
  `refs.ID_ATTR` has a negative lookbehind for exactly this.
- A **div is a container**, and the walker must flatten its children into the
  block list. Nesting them inside `content` makes them invisible to everything
  downstream while `inject_ids` still writes ids for them — clickable in HTML,
  resolving to nothing. This was a real bug (see CHANGELOG v0.2) and neither the
  verifier nor the roundtrip test could see it, because the blocks were absent
  from both sides of every comparison.
- Pandoc carries fenced divs **and their key=value attributes** through to djot,
  which is why a whole imported session can be canonized in one pass instead of
  once per turn.
- Fence length matters. Tool output routinely contains `:::` and code fences, so
  the importer computes every fence to be longer than the longest run it must
  contain. A fixed fence gets closed early by its own payload.

---

## Testing

Every guarantee is **sabotage-verified**: re-introduce the defect and confirm
the suite fails. A test that has only ever passed proves nothing — two bugs in
this codebase were shipped past tests that looked green.

```bash
# Example: confirm the loosen guarantee is actually enforced
cp src/canonize/inject_ids.py /tmp/bak
# ...remove the loosen() call...
conda run -n knowledge-graph python tests/test_render/test_site.py   # must FAIL
cp /tmp/bak src/canonize/inject_ids.py
```

Two specific traps already hit:

- A coverage check that only fired when *zero* blocks were emitted passed
  happily while task lists were being dropped entirely.
- A roundtrip test comparing parse → render → reparse cannot see an element
  type dropped by the walker, because it is absent from **both** sides. Hence
  the AST-tag coverage check in `tests/test_03/test_roundtrip.py`.

When adding a check, assert against the **source AST**, not against the
pipeline's own output.

---

## Where the next work is

In rough order.

**1. Artifact generation (v1).** The big one. Conversations exist; nothing
generates an artifact from them yet. The shape agreed so far: generation is
explicitly invoked, an agent reads `blocks.json` directly (no embeddings — a
project corpus fits in context), and every emitted block cites the block it came
from. Note that the user has decided chat content **is** freely citable, so the
"a block with nothing to cite is invalid" rule is the anti-slop mechanism but
imported conversations are legitimate sources. See `mvp-design.md` §5.

**2. Regeneration must preserve handles.** When an agent rewrites an artifact,
unchanged blocks must keep their handles or every turn referring to them is
orphaned. This is the delta algorithm in
`architecture/delta_ingestion_and_block_versioning.md`. **Until it exists, no
agent should rewrite an artifact** — `AGENTS.md` says so explicitly.

**3. Deferred views.** Open todos across the corpus. Cheap: the block type is
already in `blocks.json`, and it is a render-time view so it works retroactively.

**4. Semantic linking (`mvp-design.md` §13 Q1).** Which artifact a turn affects,
beyond the blocks it explicitly cites. Needs embeddings or LLM reading, and is
its own initiative. Keep inferred edges in a distinct type from
reference/lineage edges: when a link is wrong, the first question is always
whether a machine guessed it or a human asserted it.

**5. Housekeeping.** No pytest/CI wiring. `npx` spawns a Node process per parse
(~1 s measured), which one-file-per-conversation keeps tolerable but which still
dominates `kg render`. `src/ingest/block_schema.py` is legacy.

---

## Conventions

- **Work on `main`; tag each version.** No feature branches. One developer, no
  remote, no CI, no review gate — a branch buys isolation from nothing and
  costs a stale trunk. This was learned the direct way: a `conversations`
  branch left `main` seventeen commits behind, still describing `notes/`,
  `wiki/` and UUID block ids, so anyone reading the default branch — or any
  agent following `AGENTS.md` — got confidently wrong instructions. That is the
  documentation drift this repo has been rescued from twice, in a new costume.
  Branch only for a change that is a genuine one-way door, and merge it fast.
- Commit per logical step; separate infrastructure/config changes from code.
- Update `CHANGELOG.md` when behaviour changes.
- **Fix documentation drift in the same session as the decision**, not the next
  one. This repo has been rescued from contradictory docs twice; both times the
  cause was a decision recorded in code but not in the design doc.

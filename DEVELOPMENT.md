# Development

Written for someone arriving cold. Read `README.md` first for what the system
does, then this to work on it. `mvp-design.md` is the product spec and is
authoritative where this document is silent.

---

## Mental model

Three ideas carry everything:

1. **`.dj` files in git are the source of truth.** HTML, indexes, any future
   graph — all derived and disposable. If you find yourself storing something
   that cannot be rebuilt from the `.dj` files, stop.
2. **Notes are immutable.** Submitting freezes a note. You never edit one; you
   write another note referring to it. This is what makes block ids permanent
   and provenance answerable.
3. **Blocks are the unit.** Every paragraph, heading, list item and todo has a
   UUIDv7. The whole product is that these ids are stable, copyable, and
   resolvable.

The consequence worth internalising: **anything computed at render time works
retroactively on old notes; anything written into a `.dj` at canonization time
does not.** Backlinks could be added later and immediately worked on existing
notes. `loosen()` could not — notes canonized without it are permanently
degraded. Ask which side a change is on before building it.

---

## Layout

```
src/
  cli.py              the `kg` entry point (argparse, one function per command)
  store.py            locating a base: --root, then $KG_HOME, then a .kg marker
  canonize/
    __init__.py       canonize_text() + the verifier that can refuse output
    md_to_djot.py     pandoc wrapper; every flag prevents a silent rewrite
    inject_ids.py     --sourcepos parse, ids inserted as text, then loosen()
  ingest/
    djot_ast.py       runs djot.js, returns the native AST
    ast_walker.py     AST -> flat list of block dicts
    inline_reconstruct.py   inline nodes -> djot markup text
    block_schema.py   block records (largely legacy; canonize does its own)
  render/
    to_html.py        base -> static site, backlinks, click-to-copy
    blocks_to_djot.py blocks -> djot text (not on the canonize path; needed
                      when agents start generating wiki pages)
tests/
  test_canonize/      markdown -> addressable note
  test_render/        base -> clickable site
  test_03/            djot -> blocks -> djot roundtrip
tools/                scratch prototypes, not part of the product
```

Run everything:

```bash
conda run -n knowledge-graph python tests/test_canonize/test_canonize.py
conda run -n knowledge-graph python tests/test_render/test_site.py
conda run -n knowledge-graph python tests/test_03/test_roundtrip.py
```

There is no pytest wiring yet. Tests are standalone scripts that print
`PASS`/`FAIL` per check and exit non-zero on failure.

---

## The pipeline

```
raw/<uuid>.md
  → pandoc -f markdown-smart-auto_identifiers -t djot --wrap=preserve
  → restore checkbox markers        "☐ " → "[ ] ",  "☒ " → "[x] "
  → djot.js --to ast --sourcepos
  → insert {#uuid} lines as text, bottom-up
  → loosen: blank line after each list item's id line
  → notes/<uuid>.dj                 frozen
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
note whose blocks are unaddressable. Trust that check; it has caught real bugs.

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
- References survive on disk **escaped**: `\{#uuid:hash\}`. Parsing unescapes
  them, so scan parsed block text, never the raw file.

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

**1. Wiki generation (v1).** The big one. Notes exist; nothing generates a wiki
yet. The shape agreed so far: generation is explicitly invoked, an agent reads
notes directly (no embeddings — a few hundred notes fit in context), and every
emitted block cites the note block it came from. That citation requirement is
also the anti-slop mechanism: a block with nothing to cite is invalid, so
general knowledge cannot leak in. See `mvp-design.md` §5.

**2. Regeneration must preserve ids.** When an agent rewrites a wiki page,
unchanged blocks must keep their ids or every note referring to them is
orphaned. This is the delta algorithm in
`architecture/delta_ingestion_and_block_versioning.md` — written for
human-edited files, but the algorithm is unchanged; only the subject moves.

**3. Deferred views.** Open todos across the corpus. Cheap: the block type is
already recorded, and it is a render-time view so it works retroactively.

**4. Semantic linking (`mvp-design.md` §13 Q1).** Which wiki page a note
affects, beyond the blocks it explicitly cites. Needs embeddings or LLM
reading, and is its own initiative. Keep inferred edges in a distinct type from
reference/lineage edges: when a link is wrong, the first question is always
whether a machine guessed it or a human asserted it.

**5. Housekeeping.** No pytest/CI wiring. `npx` spawns a Node process per parse
(~100–300 ms), which is fine at current scale but wants a persistent worker
before bulk ingestion. `src/ingest/block_schema.py` is largely legacy.

---

## Conventions

- Commit per logical step; separate infrastructure/config changes from code.
- Update `CHANGELOG.md` when behaviour changes.
- **Fix documentation drift in the same session as the decision**, not the next
  one. This repo has been rescued from contradictory docs twice; both times the
  cause was a decision recorded in code but not in the design doc.

# v0.2.17 — the list item is a container too

## Read this before running anything

**`.compost` is a symlink into the human's
private notes repository.** `compost digest`, `render`, `layer` and `draw` walk
*up* the tree looking for `.compost/`. Run any of them from inside this
repository — or anywhere beneath it — and you write into their personal base.
**`git checkout` cannot undo this.**

```bash
W=$(mktemp -d); cd "$W"; compost init . && compost digest --as=… && compost check
```

Reading is fine. Writing is not. Never copy base content into a tracked file.

## What you are building

The spec is **`docs/roadmap.md`, `## v0.2.17 — the list item is a container
too`**. Read it whole first, then **`CLAUDE.md`** (its rules override
everything here).

**This is the smallest release in the project's history and it is deliberately
mechanical.** v0.2.16 did exactly this for headings a day ago; you are doing it
one level down, with the same functions, the same tests and the same argument
already made and won.

## The shape already exists in the codebase — that is the whole trick

`_list_item` in `src/records.py` already collapses a **single** `Plain`/`Para`
into the `ListItem` itself: the text becomes the node's `content` and the
original block type becomes `params["wrap"]`. So one document holds both shapes
today:

```
- plain bullet        ListItem params={"wrap":"Plain"} content="plain bullet"
- parent bullet       ListItem                          <- no content
    - child one         ├─ Plain "parent bullet"        <- text as a SIBLING
                        └─ BulletList
```

**Make the second case match the first.** The `ListItem` carries the text and
`wrap` exactly as it already does, and the remaining blocks become its
children. **No new node type and no new param** — `wrap` already exists and
already means precisely this.

## Decisions already made — do not re-derive these

- **A non-identity `records_to_ast` is fine.** `hoist` and `unhoist` compose to
  the identity; that was argued and accepted in v0.2.16. Do not try to restore
  strict identity.
- **The rule is conservative: hoist only when the leading text is followed by
  nothing but lists.** `[Plain, Para]` stays as it is — two paragraphs in one
  bullet are siblings, and making the first contain the second asserts a
  relationship the source does not have. There is a GUARD for this.
- **`Figure` and `Table` captions are NOT hoisted.** A caption describes; it
  does not contain. The survey in the spec covers every other block type and
  `ListItem` is the only remaining instance — `DefinitionList` already does it
  right.

## The number that differs from v0.2.16, and it will surprise you

**Sections were node-neutral. This is not — it REMOVES a node per hoisted
item.** The separate `Plain`/`Para` child is absorbed into the `ListItem` that
already existed, so the corpus goes **19,538 → 19,400**, one fewer for each of
its 138 hoistable items.

The verify script asserts **exactly 19,400**, not merely "fewer". A count that
falls by the wrong amount means something else was absorbed too. *If the real
number is different, report it — do not adjust the assertion to match what you
built.* (The first draft of this spec said "adds no nodes", copied from v0.2.16
without re-deriving it. Writing the verify script is what caught that.)

## Verification

**`tests/verify-0.2.17.sh` was run at baseline: `pass 7   fail 3`.** Confirm
exactly that before changing anything. A `NEW` check that passes at baseline is
a **bug in the script** — report it, do not work around it. A `GUARD` failing
after your work is a regression whatever else passes.

**`./tests/run.sh` must stay green**, and read its **last line**: it must say
`corpus present, 520 documents`.

## The instruction that matters most

**Reporting a disagreement beats fixing it.** Three places most likely to be
wrong:

1. **The conservative rule may be too conservative.** Exactly one list item in
   the whole corpus is excluded by it: a `['Plain', 'CodeBlock']`. Whether a
   code block or a block quote under a bullet *should* be hoisted is a real
   question the spec deliberately did not decide. **Report what you think, do
   not quietly widen the rule.**
2. **`wrap` may not be sufficient to invert.** It records `Plain` vs `Para`. If
   something else is needed to reconstruct the original `ListItem` exactly, say
   what and why — that is the analogue of v0.2.16's moved identifier, which
   looked redundant and was not.
3. **`views.py` already calls `unhoist`** before handing blocks to pandoc, which
   is why v0.2.16's silent view bug should not recur. If list hoisting needs
   anything more from the view layer, that is a finding.

## Be suspicious of your own denominators

This project has been bitten **five times** by a number that did not move while
its denominator did. Report every measurement as `x of y`, never a bare
percentage. Use `find`, **not** `glob.glob("**/*.md")` — recursive glob silently
skips dot-directories and measures 518 of the 520 documents `run.sh` reports.

## Rules that will bite

- **Work on `main`. No branch. Do not commit, tag, or push.**
- **Add a test with a property, not a snapshot** — `tests/test_sabotage.py` is
  the pattern, and `tests/test_sections.py` is the closest worked example.
- **Do not repair pandoc's output.**
- **`READER` must stay defined exactly once in `src/`** — a suite greps for it.
- **A turn with more than one text block must keep raising**, naming
  `TODO-multiple-text-blocks.md`.

## Report back

1. **Each guarantee in the spec, and how you made it fail first.** Not "it
   passes" — what you broke, and what the failure said.
2. **The corpus node count before and after**, as `x of y`, measured through
   the real `ast_to_records`.
3. **Anything you disagreed with**, especially the three suspects above.
4. **What you did not do, and why.**
5. The final `./tests/verify-0.2.17.sh` line and `./tests/run.sh`'s last line,
   verbatim.

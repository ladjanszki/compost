# v0.2.14 — the recursion made explicit

## Read this before running anything

**`.compost` is a symlink into the human's
private notes repository.** `compost digest`, `render`, `layer` and `draw` all
walk *up* the directory tree looking for `.compost/`. Run any of them from
inside this repository — or anywhere beneath it — and you write into their
personal base. **`git checkout` cannot undo this.**

Every command that writes runs in a scratch directory:

```bash
W=$(mktemp -d); cd "$W"; compost init . && compost digest --as=… && compost check
```

Reading is fine. Writing is not.

## What you are building

The spec is **`docs/roadmap.md`, `## v0.2.14 — the recursion made explicit`**.
Read the whole section before writing code: seven build steps naming file and
function, then eleven guarantees each stated as a property.

Read also **`CLAUDE.md`** (its rules override everything here) and
**`DEVELOPMENT.md`** (module map and conventions).

`src/session.py` does not call the text digestor — it reimplements it. Two
`READER` constants holding one string, two functions turning markdown into
blocks, and a reach into `R._block`, a private function. This release makes the
delegation explicit and stores the delegated input like any other digestor
input.

## The one design decision, already made — do not re-derive it

The obvious shape is to hang the produced `document` under the turn. **It fails
`check()` by construction**: `document` is in `ROOT_TYPES`, and a root type with
a parent is a reported problem — one per fragment, against a release that must
report zero.

**The delegated document is a root that nobody contains.** The turn reaches it
by a new edge, `delegates_to`, in the `session` layer:

```
turn ──contains──> toolcall, thinking, contentblock…
  └──delegates_to──> document ──contains──> Para, BulletList…
                        └──derived_from──> blob(fragment)
                                              └──derived_from──> blob(transcript)
```

This is not novel: a subagent session is already a `session` root that nobody
contains, reached from a `toolcall` by `launched`. Same shape, same reasoning.
Verified at **0 check problems**. `ROOT_TYPES` is not to be changed and no new
node type is to be added.

## Borrowed names, and the discipline attached

`derived_from` is aligned with **`prov:wasDerivedFrom`** (W3C PROV-O), and the
fragment's location uses a **W3C Web Annotation** selector — `RFC 6901` JSON
Pointer, because the parent is a JSON line. A fragment has **no filename**, so
`original_name` is null and the selector says where inside the parent it came
from.

**Nothing may be claimed that `check` does not enforce.** Every `aligns_with` in
the schema must name both what is `enforced` and what is `not_enforced`, and
guarantee 7 tests exactly that. For `derived_from`: irreflexive and acyclic are
enforced (the twelfth `check()` assertion); PROV's ordering constraint is **not**
— `created_at` is audit metadata, not semantics, so there is no semantic clock.

## Verification

**`tests/verify-0.2.14.sh` has been run at baseline: `pass 5   fail 9`.** Nine
`NEW` checks fail, five `GUARD` checks pass. Confirm you see exactly that before
changing anything.

- A `NEW` check that passes at baseline is a **bug in the script**. Report it;
  do not work around it and do not treat the guarantee as met.
- A `GUARD` failing after your work is a regression whatever else passes.
- The script is not the whole acceptance test. **`./tests/run.sh` must stay
  green**, and read its **last line** — it says whether the corpus is present,
  and a green board on the smoke set alone has four guarantees switched off.

## The instruction that matters most

**Reporting a disagreement beats fixing it.** Something in the spec or the
verify script is probably wrong. Stop and say so with evidence rather than
patching around it. The v0.2.12 agent found the schema wrong about top-level
provenance and *said so* — the most valuable thing in that release.

Four places more likely than the rest to be wrong:

1. **`store.py`'s `where()`** prints "in `<file>`" by walking `contains` parents
   to a root and reading its `source`. After this release a prose block's parent
   is the delegated `document`, which has none, so it must follow `delegates_to`
   backwards. If that turns out to belong elsewhere, say so — this is the
   guarantee closest to the human's daily use of the tool.
2. **The selector convention.** A `.jsonl` blob is addressed as the JSON array
   of its lines, so `/3/message/content/2` means line 3. That convention is
   ours, not RFC 6901's. If it does not survive contact, report rather than
   invent a second one.
3. **`test_session_views` holds 22 guarantees** over a `turn → blocks` walk that
   becomes `turn → document → blocks`. If moving them changes what they assert
   rather than how they reach it, that is a finding.
4. **Guarantee 11** — the alignment prefix — was measured before the tree moved.
   **Re-measure it; do not assume it survived.** A lower number is a finding,
   not something to route around.

## Rules that will bite

- **Work on `main`.** No branch. Do not commit, tag, or push.
- **A turn with more than one text block must keep raising**, naming
  `TODO-multiple-text-blocks.md`. Do not make the totality test swallow it.
- **Add a test with a property, not a snapshot.** `tests/test_sabotage.py` is
  the pattern.
- **Do not repair pandoc's output**; three defects are documented in
  `docs/decisions.md` and sit outside the round-trip on purpose.
- **The round-trip property is the acceptance test.** If
  `records_to_ast(ast_to_records(ast)) == ast` fails on any fixture, the change
  is wrong regardless of what else passes.
- **Records are immutable.** No editing a line inside an existing file.

## Report back

1. **Each of the eleven guarantees, and how you made it fail first.** A vague
   answer here is the tell that it was never verified.
2. **The re-measured guarantee 11 number**, as a fraction of the **older** tree.
3. **Anything you disagreed with**, whether or not you acted on it.
4. **What you did not do**, and why.

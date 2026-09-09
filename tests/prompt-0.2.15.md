# v0.2.15 — AoTA: an artifact that grows

## Read this before running anything

**`.compost` is a symlink into the human's
private notes repository.** `compost digest`, `render`, `layer` and `draw` walk
*up* the tree looking for `.compost/`. Run any of them from inside this
repository — or anywhere beneath it — and you write into their personal base.
**`git checkout` cannot undo this.**

```bash
W=$(mktemp -d); cd "$W"; compost init . && compost digest --as=… && compost check
```

Reading is fine. Writing is not.

## What you are building

The spec is **`docs/roadmap.md`, `## v0.2.15 — AoTA: an artifact that grows`** —
seven build steps, eleven guarantees. Read it whole first. Then **`CLAUDE.md`**
(its rules override everything here) and **`docs/design-0.3.0.md` §1, §2, §6b**,
which is where the design was settled.

An append-only artifact keeps **one root, forever**. A later ingest of a longer
file adds `contains`/`next` edges to that root and mints nodes only for the tail.
No second root, no `revision_of`. Re-ingesting the corpus today re-mints **9,217
of 12,987 nodes for nothing — 71%** — and re-stores 369 of 546 fragment blobs.

## Decisions already made — do not re-derive these

- **`mutability` is `immutable` | `append-only` | `mutable`.** Required at
  creation, an error without it, and it **never changes** — `--mutability` on an
  `--updates` call is an error.
- **`--updates=guid` names the root**, for both append and revision. One flag;
  what it *means* depends on the target's mutability. `immutable` targets are
  refused. The user names it because *"which of fifty README.md files"* has no
  safe automatic answer.
- **One default is derivable:** a transcript is `<sessionId>.jsonl` and the root
  stores `session_id`. That covers 6 of 18 archived transcripts; the other 12 are
  `agent-<toolUseId>.jsonl` subagent files. **Both rules together cover 18/18.**
- **Omitting `--updates` mints a second root, silently.** Principle 10. Not a
  warning, not an error, not in this release.
- **Storage does not change.** A re-ingest stores the whole file as a second
  blob and the root gains a second `derived_from`. Measured and accepted —
  `TODO-storage-revamp.md`.

## The part that will surprise you

**Appending breaks `check()`'s eleventh assertion, and that is expected.**
`record_subtree_hash` folds a node's children; appending changes the root's fold
while the root record is untouched. Build the shape and `check` reports
*"record_subtree_hash does not recompute"* — I confirmed this before writing the
spec.

**The fix is to rewrite the root's record**, whole-file, which `CLAUDE.md` names
as the only honest form of change to immutable records. It is cheap because
**exactly one field on exactly one node moves**: the root's `record_hash` is
stable (its params do not change), and a turn's only ancestor is the session
root, since v0.2.14 made delegated documents roots that nobody contains.

Moving the fold to a rebuildable layer was considered and rejected — it makes the
only content-verifying assertion conditional. Do not revisit it.

## Verification

**`tests/verify-0.2.15.sh` was run at baseline: `pass 3   fail 8`.** Confirm you
see exactly that before changing anything. A `NEW` check that passes at baseline
is a **bug in the script** — report it, do not work around it. A `GUARD` failing
after your work is a regression whatever else passes.

The script expects two new functions by name — `records.refresh_fold(records,
root)` and `records.align(old_recs, old_root, new_recs, new_root) -> (prefix,
total)`. If those names are wrong for the design, **say so** rather than bending
the code to fit a test.

**`./tests/run.sh` must stay green**, and read its **last line** — a green board
on the smoke set alone has four guarantees switched off.

## The instruction that matters most

**Reporting a disagreement beats fixing it.** Four places most likely to be
wrong:

1. **The alignment walk must follow `delegates_to`.** A `contains`/`next` walk
   alone reaches **52.5%** of a digest and reports a tidy 100% of half the graph.
   v0.2.14 nearly shipped with that. Guarantee 8 asserts coverage for this
   reason.
2. **`check`'s contract assertions** (build step 5) need to know *when* a root
   was created to say "no edges added after". If the records cannot answer that,
   **that is a finding** — `created_at` is audit metadata, not semantics.
3. **`blob_of` returning several blobs** changes every caller. If a caller wants
   "the current bytes" rather than "all bytes", say which.
4. **Guarantee 4's node-count bound** (`n2 < n1*1.8`) is a proxy for "the head
   was not re-minted". If the real number makes it wrong, report the number.

## Rules that will bite

- **Work on `main`.** No branch. Do not commit, tag, or push.
- **A turn with more than one text block must keep raising**, naming
  `TODO-multiple-text-blocks.md`.
- **Records are immutable** — the root's fold refresh is a whole-file rewrite,
  not an in-place line edit.
- **Do not repair pandoc's output.** The round-trip property is the acceptance
  test; if `records_to_ast(ast_to_records(ast)) == ast` fails on any fixture the
  change is wrong regardless of what else passes.

## Report back

1. **Each of the eleven guarantees, and how you made it fail first.**
2. **The re-measured alignment number**, as a fraction of the **older** tree, and
   say how many nodes the walk covered out of how many exist.
3. **Anything you disagreed with**, whether or not you acted on it.
4. **What you did not do**, and why.

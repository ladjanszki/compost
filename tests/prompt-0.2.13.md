# v0.2.13 — the fold

## Read this paragraph before you run anything

**`.compost` is a symlink to the human's
private knowledge base.** `compost digest`, `render`, `layer` and `draw` all
walk *up* the directory tree looking for `.compost/`. Run any of them from
inside the repository — or from anywhere beneath it — and you write into their
personal data. **`git checkout` cannot undo this.** Every command that writes
runs in a scratch directory:

```bash
W=$(mktemp -d); cd "$W"; compost init . && compost digest --as=… && compost check
```

Reading the base is fine. Writing to it is not, and there is no recovery.

## What you are building

The spec is **`docs/roadmap.md`, section `## v0.2.13 — the fold`**. Read it
whole before writing any code: seven numbered build steps naming file and
function, then eight guarantees each stated as a property.

Read also, in this order: **`CLAUDE.md`** (the rules, and they override
everything here), **`design-total-mapping.md`** (why this release is shaped
this way — the reasoning is not repeated in the spec), and **`DEVELOPMENT.md`**
(the module map and the conventions).

## The two hashes, defined exactly — do not improvise these

Both are **top-level record fields**, beside `guid`, `created_at` and
`tool_version`. Neither goes in `params`: a hash stored inside `params` would be
inside its own input.

```python
def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")

record_hash        = sha256(_canon([type, params, content])).hexdigest()
record_subtree_hash = sha256(_canon([record_hash,
                                     [child.record_subtree_hash …]])).hexdigest()
```

Children in **`next` order**. The fold reads **`contains` and `next` only** — no
other edge type may move a fold. A leaf's fold is `H([record_hash, []])`.

`tests/verify-0.2.13.sh` hardcodes this definition. If your implementation
disagrees with it, one of the two is wrong and you must say which and why rather
than adjusting the script to match your code.

## Verification

**`tests/verify-0.2.13.sh` exists and has been run at baseline.** It reports
seven `NEW` checks — v0.2.13 guarantees, all currently failing — and two `GUARD`
checks — existing properties, both currently passing.

Run it before you change anything and confirm you see `pass 2   fail 7`. Then:

- A `NEW` check that passes before you start is a **bug in the script**. Say so.
  Do not work around it and do not treat it as done.
- A `GUARD` check that fails after your work is a regression, whatever else
  passes.
- The script is not the whole acceptance test. **`./tests/run.sh` must stay
  green**, and you must read its last line: it says `corpus ABSENT` or not, and
  a green board on the smoke set alone has four guarantees switched off.

## The instruction that matters most

**Reporting a disagreement beats fixing it.** If the spec, the design document
or the verify script is wrong — and at least one of them probably is — the most
valuable thing you can do is stop and say so, with the evidence. The previous
agent on this project found the schema was wrong about top-level provenance and
*said so* instead of patching it quietly, and that was the most useful thing
that happened in that release.

Specifically, three things in this spec are more likely than the rest to be
wrong, and I would rather hear about them than have them worked around:

1. **Build step 5** adds an eleventh assertion to `check()` — the first one that
   verifies content rather than structure. If that turns out to belong somewhere
   else, say so.
2. **Guarantee 5** claims the truncated-tree prefix is exactly 100.00%. It was
   measured on `session-04.jsonl` before the mapping fixes landed. Storing
   `signature` and `caller` changes what is hashed. **Re-measure it; do not
   assume it survived.** If it is no longer 100%, that is a finding, not a
   failure to route around.
3. **Build step 2's** list-shaped `tool_result.content` occurs twice in the
   whole corpus. If storing it whole breaks the transcript round-trip, the round
   trip wins and the mapping fix needs rethinking.

## Rules that will bite

- **Work on `main`.** No feature branch. Do not commit, do not tag, do not push.
  The human does all three.
- **Add a test with a property, not a snapshot.** Every suite in `tests/` states
  something that must be true and has been made to fail on purpose.
  `tests/test_sabotage.py` is the pattern.
- **Do not repair pandoc's output.** Three defects are documented in
  `docs/decisions.md` and sit outside the round-trip property on purpose.
- **The round-trip property is the acceptance test.** If
  `records_to_ast(ast_to_records(ast)) == ast` fails on any fixture, the change
  is wrong regardless of what else passes.
- **Do not edit records in place.** Records are immutable; a whole-file rewrite
  is the only honest form of change.
- **`docs/design-0.3.0.md` §8 is deleted, not amended.** Build step 7. It
  describes the per-type whitelist this release replaces.

## What to report when you are done

1. **Each of the eight guarantees, and how you made it fail first.** A vague
   answer here is the tell that it was never actually verified.
2. **The re-measured guarantee 5 number**, stated as a fraction of the *older*
   tree, not the newer one.
3. **Anything you disagreed with**, whether or not you acted on it.
4. **What you did not do**, and why.

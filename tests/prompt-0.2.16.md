# v0.2.16 — TA: revisions, and structure that means something

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

The spec is **`docs/roadmap.md`, `## v0.2.16 — TA: revisions, and structure
that means something`** — five build steps, eleven guarantees. Read it whole
first. Then **`CLAUDE.md`** (its rules override everything here),
**`TODO-section-container.md`** (the reasoning the spec compresses, including
two conclusions measurement overturned), and **`docs/design-0.3.0.md` §7, §9**.

Two things ship together because they are one question: a TA revision compares
trees by fold, and the unit worth comparing is a **section**.

## The frame — read this before you make any judgement call

From the human, and it decides every ambiguous case in this release:

> We are building a **knowledge graph**, not a representation as close to
> pandoc as possible. `contains` edges carry semantics — a heading is
> structural information. Several source types are unified under one node
> grammar, so the knowledge in each is exposed the same way.

**So the round-trip is a safety property, not the goal.** It proves nothing was
silently dropped. Where graph shape and pandoc shape pull apart, **the graph
wins**. This reverses the usual instinct and it is deliberate.

## Decisions already made — do not re-derive these

- **The container is the `Header`, not a `Div`.** `make_sections` produces a
  `Div` wrapping `[Header, ...rest]`; you **hoist** it — the `Div` is absorbed
  into its own `Header`, which becomes the parent of the rest. This was the
  human's call, and it was measured: hoisting adds **zero nodes** (14,153 →
  14,153) where the `Div` shape costs **+1,546**, one per heading.
- **A non-identity `records_to_ast` is accepted**, deliberately. The rule is
  that `hoist` and `unhoist` **compose** to the identity, tested as a property.
  Do not try to preserve strict identity; it was considered and rejected.
- **`make_sections` runs in the reader**, through a Lua filter, so the
  sectioning rule is *pandoc's* and not one we author and then defend against
  setext headings, level skips and headings in block quotes.
- **A TA revision re-mints the whole tree** (design-0.3.0 §9, Option A) and
  chains **roots only** with one `revision_of`. Never per-block revision edges.
- *Rejected: keeping sections in a separate layer.* It reintroduces the
  staleness hazard the roadmap declines to detect.

## Two facts that will cost you an hour if you find them yourself

Both measured on 2026-09-10:

1. **`make_sections` MOVES the identifier off the `Header` onto the `Div`.**
   The header's own attr becomes `['', [], [['number','1']]]` while the div
   carries `['chapter', ['section'], [['number','1']]]`. **Both must be kept**
   or `unhoist` is not an inverse. The emptied attr looks redundant and is not.
2. **`make_sections` absorbs author-written `::: section` divs.** A hand-written
   one containing a heading comes back with a generated id and a number,
   identical to any other section. There is therefore **no ambiguity to
   disambiguate** — the filter normalises first.

## Verification

**`tests/verify-0.2.16.sh` was run at baseline: `pass 4   fail 8`.** Confirm you
see exactly that before changing anything. A `NEW` check that passes at baseline
is a **bug in the script** — report it, do not work around it. A `GUARD` failing
after your work is a regression whatever else passes.

**`./tests/run.sh` must stay green**, and read its **last line** — a green board
on the smoke set alone has guarantees switched off. It should say `corpus
present, 520 documents`.

## The instruction that matters most

**Reporting a disagreement beats fixing it.** Four places most likely to be
wrong, named specifically because a blanket "tell me if something is off" gets
ignored:

1. **`markdown.ast_of_file` is a name this spec invented** so the verify script
   had something to call. If a different seam is better — one function taking
   text-or-path, the filter folded into `READER` itself — **say so** rather than
   bending the code to fit a test. A verify script dictating an API it made up
   is the failure mode most worth catching here.
2. **`params["section_attr"]` on `Header` is likewise the spec's name**, and it
   changes the schema. If the two attrs want a different shape, report it.
3. **Guarantee 3 asserts sectioning adds *zero* nodes.** That was measured on
   the corpus with a standalone hoist, not through `ast_to_records`. If the real
   implementation differs by even one node, **report the number** — do not
   adjust the guarantee to match what you built.
4. **Guarantee 6 — every markdown path sectioned identically.** There are
   currently two pandoc invocations (`markdown.py` on stdin, `routes.py` on a
   file). If collapsing them is harder than the spec assumes, that is a finding,
   not something to route around by applying the filter twice.

## Be suspicious of your own denominators

This project has been bitten **five times** by a number that "did not move"
while its denominator did — most recently in this very TODO, whose own deciding
measurement (25.1% of corpus documents have >1 heading) pointed the wrong way
because the corpus is 92% rust-book. Against the human's own documents it is
75.9%.

**Report every measurement as `x of y`, never as a bare percentage.** When a
number does not move, ask what its denominator did.

## Rules that will bite

- **Work on `main`.** No branch. **Do not commit, tag, or push.**
- **Add a test with a property, not a snapshot.** `tests/test_sabotage.py` is
  the pattern — every suite states something that must be true and has been made
  to fail on purpose.
- **A turn with more than one text block must keep raising**, naming
  `TODO-multiple-text-blocks.md`.
- **Records are immutable.** A whole-file rewrite is the only honest change.
- **Do not repair pandoc's output.** Three defects are known and documented in
  `docs/decisions.md`; they sit outside the round-trip on purpose.
- **`READER` must stay defined exactly once in `src/`** — a suite greps for it.

## Report back

1. **Each of the eleven guarantees, and how you made it fail first.** Not "it
   passes" — what you broke to prove the check is real, and what the failure
   said.
2. **The node count, flat versus sectioned**, as `x of y`, through the real
   `ast_to_records` rather than a standalone transform.
3. **Anything you disagreed with**, whether or not you acted on it — especially
   the four suspects above.
4. **What you did not do, and why.**
5. The final `./tests/verify-0.2.16.sh` line, and `./tests/run.sh`'s last line
   verbatim.

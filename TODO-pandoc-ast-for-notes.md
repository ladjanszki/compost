# TODO — one document digestor, and the pandoc AST as a stored artifact

**Postponed until after v0.3.0, by the human's own sequencing.** Two changes that
look separate and are not: storing the pandoc AST beside the text, and deleting
the `notes` route in favour of a document digestor that always produces AST.

---

## The observation

`notes` and `pandoc-ast` are almost the same route. One reads markdown and hands
pandoc's JSON to `ast_to_records`; the other is handed the JSON directly. The
only real difference is a `subprocess` call:

```
notes:       file → pandoc → AST → ast_to_records → records
pandoc-ast:  file →           AST → ast_to_records → records
```

`notes` is `pandoc-ast` with a conversion step in front. The human has wanted to
collapse them "for a long time": **one document digestor that always produces a
pandoc AST**, with the input format — markdown, LaTeX, HTML, a webpage —
becoming an argument to the conversion rather than a separate route.

## What would be stored

Both, and this is the part that matters:

- **the original text**, exactly as it arrived, which is what `storage/` holds
  today;
- **the pandoc AST it produced**, as its own stored artifact.

The AST is stored because it is *the deterministic function's output*, and
keeping it is what lets a later pass answer *"have we seen this semantically
distinct byte-stream before"* without re-running the conversion — and without
trusting that the conversion is still the same function it was. That is the
human's Skolemization argument, and it is the same reason `derived_from` is
asserted rather than recomputed.

## The factual correction this file exists to record

> *"Also lets save the pandoc ast — this is a jsonl file just as the claude code
> transcript so we can save each json one by one"*

**It is not.** `pandoc -t json` emits **one JSON object** with a `blocks` array,
not JSON Lines. There are no lines to slice.

This matters because the transcript plan and the document plan look parallel and
are not. Slicing a transcript means storing one JSON per line, which the file
already has. Slicing a document means **walking the `blocks` array** — which is
exactly what `ast_to_records` already does into the graph. So the question for
documents is not *"how do we slice it"* but *"is a stored AST anything more than
the graph already is?"*, and that has not been answered.

A defensible answer: the stored AST is the **input to the graph**, and the graph
is an interpretation that may improve — the same relationship `storage/` already
has with everything else. Under that reading it should be stored whole, one
artifact per conversion, not sliced at all.

## Why it waits

- **It is a storage change**, and `TODO-storage-revamp.md` argues storage waits
  until after v0.3.0 because its consumer is the semantic layer. Same reasoning,
  same slot.
- **It is entangled with route deletion.** Storing the AST for `notes` while
  `notes` still exists as a separate route builds the thing twice.
- **v0.2.15 is not the place.** Doing it inside the AoTA release would mean two
  structural changes measured against each other, which is how a regression
  hides.

## What would decide the shape

- **Does anything actually read a stored AST?** If the graph is always the
  answer, storing the AST is insurance rather than a feature — worth having, but
  it should be called that.
- **Measure the inflation.** 629 documents produced 19.2 MB of stored text. What
  do their ASTs weigh? A pandoc AST is typically several times its source. That
  number decides whether "store both" is cheap or doubles the base.
- **Which conversions are deterministic enough to be worth storing as
  functions?** The pandoc pin exists because they are not, quite:
  `environment.yml` pins `pandoc=3.11` exactly *because* a floor let the
  toolchain move under a measurement. A stored AST is only evidence if the
  version that produced it is recorded beside it.
- **What happens to `--as=notes` in the man page and every fixture?** The route
  names are in `tests/`, `docs/man-compost.md`, the schema's `route` params and
  every existing base. Deleting a route is a vocabulary change with a migration
  behind it.

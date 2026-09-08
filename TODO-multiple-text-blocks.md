# TODO — a turn with more than one delegated fragment

**Postponed in v0.2.14, with a loud error in its place.** Measured: this occurs
**0 times in 2,839 corpus turns**, so the error cannot fire on any material this
project has. When it does fire, that is the signal to build what is below.

---

## The context

v0.2.14 makes the digestion delegating: a turn's markdown prose is handed to the
markdown digestor, which produces a `document` root that the turn reaches by a
`delegates_to` edge, with the input stored as a blob.

That works cleanly when a turn has **exactly one** text block, because there is
one fragment, one blob, one document, one edge. Two facts make that the only
case that has ever occurred:

| across 2,839 corpus turns | count |
|---|---|
| turns mixing prose with non-prose children | **0** (0.0%) |
| turns carrying more than one text block | **0** (0.0%) |

## What is missing

The Claude Code transcript format permits `message.content` to hold several
`text` blocks, interleaved with `tool_use`, `thinking` and `tool_result`. A turn
like that has **several** delegated fragments, and v0.2.14 has no way to say
which produced blocks came from which input:

- several `delegates_to` edges from one turn, and nothing ordering them against
  the turn's other children;
- reconstruction — `records_to_session` is safe, since it reads
  `params["log"]`, but any view rebuilding a turn in reading order needs to
  interleave two delegated documents with the toolcalls between them;
- and the migration case: an existing base's turn with mixed children cannot be
  partitioned without re-parsing, which is the one thing the migration is
  designed to avoid.

## Why it was postponed

**v0.2.14 is already a detour.** It exists to stop `session.py` reimplementing
the text digestor; the tree-shape change is a consequence, not the goal. Adding
ordered multi-fragment delegation would roughly double it, to serve a case with
**no instances**.

The measurement is what makes this a defensible postponement rather than a
guess. Zero in 2,839 is not zero forever — the format allows it, and a future
harness version may well produce it — but building for it now would be
designing from imagination, which this project has decided against repeatedly.

## What is there instead

`src/session.py` raises immediately, naming this file, when it sees a turn with
more than one text block or with prose and non-prose children mixed. It does not
skip, warn, or guess: a silent partial import is the failure mode
`digest everything` exists to prevent, and a base built from a guess would be
wrong in a way nothing could detect afterwards.

**The cost of the guard is that `digest` refuses a transcript it would have
accepted before v0.2.14** — accepted by splicing every prose block flatly into
the turn, which is the very structure this release replaces. Refusing is the
honest option, and softening it to a warning is one line if the error turns out
to fire on real material.

## What would decide it

- The error firing. That is the whole point of it being an error.
- Or a count: re-run the two measurements above over a fresh corpus fetch and
  over the human's own base. If either number leaves zero, this stops being
  hypothetical.

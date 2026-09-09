# TODO — the storage revamp, and why it is not next

**Postponed after v0.3.0, deliberately, with a trigger that can pull it
forward.** Everything here was measured on 2026-09-09 against real material —
629 of the human's own documents and the seven-transcript corpus — so the next
person does not have to rediscover the size of the problem.

---

## The context

`storage/` holds every digestor input under a freshly minted `GUID.EXT`, and
never overwrites. That is principle 3 and it is not in question. What is in
question is **what counts as an input** when the same artifact is ingested more
than once.

**v0.2.15 is the release that makes re-ingestion routine.** Before it, a
re-ingest re-minted 71% of a transcript's nodes for nothing, which was
discouragement enough. Delta ingest removes that cost from the *graph* — and
removes the disincentive with it. Storage then grows by the whole file on every
ingest, while the graph grows only by the delta.

## What it costs, measured

| | |
|---|---|
| duplication already sitting in a 629-document base | **100 files, 1.76 MB of 19.2 MB — 9.1%** |
| whole documents that are byte-identical twins | 153 files in 54 groups |
| one re-ingest of the 7-transcript corpus | **+10.8 MB**, of which ~7.7 MB is bytes already on disk |
| ten re-ingests | +108 MB, graph growing only by the delta |

**9.1% is not an emergency and the transcript number is not correctness.**
Nothing is lost, nothing is wrong, and no answer the tool gives is affected. It
is disk.

## Why this one waits, when the mapping drops did not

The drops v0.2.13 found were **unrecoverable**: a field not read at import is
gone from every base built since, and no later pass can invent it. The citation
guids were the same shape — once a base is discarded, what its citations pointed
at cannot be reconstructed.

**Storage duplication is the opposite.** Every byte is still there, twice.
Collapsing duplicates later needs no information that is not on disk today, and
`blob.bytes_sha256` is already on every blob node, so the duplicates are
*findable* with a query rather than a migration. This is the most recoverable
kind of waste this project has.

And the design it serves does not exist yet. The slicing plan is explicitly
**preparation for Skolemization** — for being able to say *"we have seen this
semantically distinct byte-stream before"* — and the machinery that would use
that answer is the semantic layer, which ships in v0.3.0. Designing the servant
before the master is how a wrong criterion gets baked in. Every release in the
v0.2.13–v0.2.14 window redrew the one after it; specifying storage three
releases early would be designing from imagination, which this project has
decided against repeatedly.

## The trigger that pulls it forward

Do not wait for a slot; watch a number. The duplication is measurable from any
base with the standard library alone, because every blob carries its own hash:

```python
# duplicate bytes as a fraction of storage
import json, glob, collections
h = collections.Counter()
for f in glob.glob("BASE/graph/*.jsonl"):
    for l in open(f):
        r = json.loads(l)
        if r.get("type") == "blob":
            h[r["params"]["bytes_sha256"]] += 1
```

**Bring it forward when duplicate bytes pass a quarter of `storage/`**, or when
a single artifact has been re-ingested enough times that its blobs dominate. Ten
re-ingests of the current transcripts would do it. Until then the cost is disk
and the knowledge is written down here.

## What the design would be, as far as it is settled

Recorded so it is not re-derived from nothing:

- **Use format knowledge rather than pretending to have none.** The rule *filter
  only when disk or compute requires it* has the escape clause, and disk is what
  requires it. A digestor author knows their format; Claude Code publishes a
  JSON Schema for the transcript. **Get that schema before writing this.**
- **Slice a `.jsonl` transcript into one stored JSON per line.** The graph
  already knows the original filename, the order and the metadata, so the file
  is reconstructible. A re-ingest then stores only the lines it has not seen.
- **Measure the inflation first.** A 1,196-line transcript becomes 1,196 files.
  Whether that is better than one 10 MB blob is an empirical question about the
  filesystem, not an obvious win, and it has not been measured.
- **A pandoc AST is not JSONL.** `pandoc -t json` emits **one** JSON object with
  a `blocks` array. There are no lines to slice, so the transcript approach does
  not transfer to documents — slicing a document means walking `blocks`, which
  is what `ast_to_records` already does into the graph.
- **Content-addressed lookup does not conflict with minted names.**
  `docs/decisions.md` rejected deriving a *filename* from content. Using
  `bytes_sha256` as an *index* to find what is already stored leaves names
  minted and is compatible as written.

## The questions a digestor author should have to answer

The human's framing, worth keeping because it generalises past this problem:
*"it can be expected that if somebody wants to import a new format they know
enough about it to answer some structural questions."* Collecting those
questions is itself a deliverable, and the list so far — drawn from what the
three existing routes had to decide, usually late and under pressure:

1. **What is one input?** A file, a line, an object inside a line? The transcript
   answered "a line" only in v0.2.14, when delegation forced it.
2. **What is the unit of change?** Whole-file replacement, an append at the tail,
   or an edit anywhere. This is `mutability`, and v0.2.15 makes it explicit.
3. **Can two ingests of this format be recognised as the same artifact, and
   how?** A transcript can — `<sessionId>.jsonl` plus the `agent-` rule covers
   18 of 18. A markdown file cannot, which is why `--updates` is a flag.
4. **Which fields are per-instance rather than per-value?** `signature`, `id`,
   `tool_use_id`, `uuid`, `timestamp`. Getting this wrong is what made 491 empty
   `thinking` blocks hash identically for four minor versions.
5. **What does the format's own spec guarantee?** Claude Code publishes a JSON
   Schema for the transcript. **Get it before writing this release** — real-world
   knowledge is not a violation of *digest everything*, it is what makes the
   filtering decision an informed one rather than a guess.
6. **What is deterministic, and can its output be stored as evidence?** See
   `TODO-pandoc-ast-for-notes.md`: a stored artifact is only evidence if the
   version of the function that produced it is recorded beside it, which is why
   `environment.yml` pins `pandoc` exactly.

## Also parked, and where

- **`TODO-pandoc-ast-for-notes.md`** — storing the AST beside the text, and
  collapsing `notes` into a single document digestor. Same slot, same reasoning,
  and it carries one correction this file depends on: **a pandoc AST is not
  JSONL**, so the transcript slicing plan does not transfer to documents.
- **`records.blob_of()` returns one blob** and an AoTA root will have several.
  That one is *not* postponed — v0.2.15 has to answer it, because the append
  creates it.

## One thing this must not break

`tools/export_citations.py` reads a base **with the standard library alone** — no
compost, nothing imported from `src/` — and that is a deliberate proof that a
base outlives the tool that wrote it. Any storage change has to keep that true.
If the revamp makes a base unreadable without the program that wrote it, the
revamp is wrong, however much disk it saves. Frozen bases in the notes repository
are the test: `base-v0.2.13-2026-09-08/` must stay readable forever.

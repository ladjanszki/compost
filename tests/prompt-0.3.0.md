# v0.3.0 — the talks-about layer

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

**This release has a second hazard the previous six did not: it spends money
and it handles a credential.** See "The key" below before you make a call.

## What you are building

The spec is **`docs/roadmap.md`, `## v0.3.0 — the talks-about layer`**. Read it
whole first, then **`CLAUDE.md`** (its rules override everything here).

A concept map the human writes, an LLM pass that links blocks to the concepts
they are about, and a generated page per concept collecting what landed there.
Nine build steps, fourteen guarantees.

**This is the largest release since v0.2.9 and the first that calls a model.**
Three things in this project have never existed before today: a network call in
`src/`, a record the graph cannot recompute from bytes, and a builder that
takes an argument.

## The key, and the budget

**`.env` in the repo root holds `OPENROUTER_API_KEY`.** It is gitignored
(`.gitignore:39`) and **must stay that way** — there is a GUARD in the verify
script that greps tracked files for the key prefix, and it must never fire.

- **$10 limit, and it expires 2026-09-16T07:55Z.** After that the key is dead
  and a real run is impossible until the human mints another.
- **`GET https://openrouter.ai/api/v1/key` with the bearer token returns
  `usage` and `limit_remaining` and costs nothing.** Check it before and after
  any real run and report both numbers.
- **Never print the key, never write it to a file, never put it in a record or
  in `storage/`.** Read it from the environment at the point of use.

The measured full-corpus pass is **cents**, so $10 is not a constraint — but
only if you batch. One block per call spends 98.7% of the budget re-sending the
map.

## Decisions already made — do not re-derive these

- **The record shapes are decided and written down** in `docs/roadmap.md`, "The
  records this mints". Node `concept_run` (its guid *is* the run id) and
  `abstention`, both `UNCONTAINED`. Edge `talks_about` with props `primary` and
  `run`. Edge `used` for run → map and run → prompt. Layer `concept-map`.
  **All five are schema changes** — `tools/record-schema-1.json` is closed
  (`additionalProperties: false`, enums on node type, edge type and layer), so
  an invented name fails `test_grammar` rather than quietly working.
- **The per-block size cap is 8,000 characters**, measured. Do not re-pick it;
  the reasoning and the distribution are in the spec.
- **Stage 2 is a view, not a layer.** `render_collection` in `src/views.py`,
  beside `render_djot`, `render_md` and `render_html`. Generated from records
  and nothing else, so it cannot drift from the classification.
- **Line format over JSON in the prompt** was a *guess*, explicitly. See "three
  suspects" below — this is the one you are most invited to overturn, with
  measurement.
- **OpenRouter over Claude Code, stdlib over `requests`.** `pyproject.toml`'s
  `dependencies = []` stays true and a GUARD checks it.
- **A failed run writes nothing.** Not a partial graph file. Refusal is the
  project default.

## What the previous agent changed in the spec, and why it matters to you

The spec was reviewed on 2026-09-15 before you were launched. Three things were
found, and they are the reason your baseline numbers differ from the ones in
older parts of the document:

1. **The cost table's prose and its numbers disagreed.** It defined a
   classifiable block as including `CodeBlock` and `BlockQuote`, but the
   published 12,296 blocks / ~514,343 tokens reproduces *only without*
   `CodeBlock`. The difference is exactly 2,002, the corpus's code-block count.
   **`CLASSIFIABLE` is now `Para`, `Plain`, `ListItem`, `Header`** — one named
   constant, one line to change.
2. **`BlockQuote` was a no-op either way** — it carries its own text **0 of
   159** times, because its prose lives in child `Para`s that are already
   counted.
3. **Guarantee 8 had no record shape behind it and no build step.** It is now
   build step 8, the fifteenth `check` assertion.

## Verification

**`tests/verify-0.3.0.sh` was run at baseline: `pass 13   fail 10`.** Confirm
exactly that before changing anything — all ten NEW fail, all thirteen GUARD
pass. A `NEW` check that passes at baseline is a **bug in the script**; report
it, do not work around it. A `GUARD` failing after your work is a regression
whatever else passes.

Four bugs were already found and fixed in that script while baselining it, so
it is not above suspicion:

- a NEW check matched `from collections import Counter` and passed at baseline;
- a GUARD forbade `urlopen` in suites, which `test_serve` legitimately uses
  against 127.0.0.1, and so failed at baseline;
- two checks built a graph by hand with no `next` chain, so `Graph.children()`
  raised before `check()` was ever reached — they failed for the wrong reason;
- **backticks inside the heredocs are command substitution**, because the
  heredocs are unquoted so `$ROOT` expands. Do not put backticks in a check
  body.

**`./tests/run.sh` must stay green**, and read its **last line**: it must say
`corpus present, 520 documents`.

## Fixtures exist — use them, do not invent more

`tests/fixtures/concept-map/` was created for this release and every one is
named by a guarantee:

| file | for |
|---|---|
| `map.md` | three labels, four sublabels, grounding prose under each. Verified: `concept_map` arrives as a typed `MetaBool`, the round-trip holds, the tree is label → prose → sublabel |
| `no-frontmatter.md` | the same body, frontmatter stripped — guarantee 3 |
| `over-cap.md` | one synthetic 12,199-character block, and `concept_map: false` so it also covers a *false* key. The corpus maxes at **2,120** and cannot exercise the cap |
| `response-good.txt` | a five-fragment answer in the prompt's line format |
| `response-bad-short.txt`, `response-bad-label.txt`, `response-bad-id.txt` | one per check in guarantee 5 |

The canned responses are what let guarantees 5, 6, 9, 11 and 12 be tested with
the caller injected and **the network untouched**. They use `none of these` as
the abstain label; if you change that, change them with it.

## The instruction that matters most

**Reporting a disagreement beats fixing it.** Four places most likely to be
wrong:

1. **The answer format.** The line format was chosen over JSON on the argument
   that a cheap model follows it more reliably. *That is a guess, not a
   measurement*, and it is written down as a guess. You have a real key and a
   $10 budget: **measure it.** If the count-and-label checks fail often, change
   the prompt — `prompts/concept-map.md` has a `version` field for exactly
   this. Report the failure rate either way.
2. **`CLASSIFIABLE` excluding `CodeBlock`.** Decided on the argument that a code
   block has no prose *about* a topic, so classifying one invites exactly the
   false positive the human rules against. It is a query-time filter, so it is
   reversible for free. **If a real run suggests otherwise, say so** — the cost
   table moves to 14,298 / ~602,629.
3. **Two limits may not be enough.** A hundred blocks at 8,000 characters is
   800,000 characters in one batch. That cannot happen on any measured
   material, but nothing prevents it. A third limit — close the batch on total
   characters — is the obvious guard. It was deliberately *not* specified.
   Report whether you think it is needed; do not add it silently.
4. **The abstention rate is ambiguous and the spec says so.** It is meant to
   signal *the map is wrong*. But **14.1%** of blocks in the notes base are
   both short and have no ancestor path — mostly vendored plugin docs — where a
   high rate means *the material is unclassifiable* instead. The two are
   indistinguishable from outside. **Do not report an abstention rate without
   saying which material it was measured on.**

## Be suspicious of your own denominators

This project has been bitten **six times** by a number that did not move while
its denominator did, and the seventh was found on 2026-09-15 while preparing
this brief: the cost table's 12,296 was a different set from the one its own
prose named.

Report every measurement as `x of y`, never a bare percentage. Use `find`,
**not** `glob.glob("**/*.md")` — recursive glob silently skips dot-directories
and measures 518 of the 520 documents `run.sh` reports.

**The corpus pin is intact**: 520 documents, 19,400 nodes, largest block 2,120
characters. If any of those moves, something else is wrong.

## Rules that will bite

- **Work on `main`. No branch. Do not commit, tag, or push.**
- **Add a test with a property, not a snapshot** — `tests/test_sabotage.py` is
  the pattern.
- **The suites never make a network call.** The injectable caller is the shape
  (`tools/loop.py`'s `ask=`). A suite that needs a model response reads a
  canned fixture.
- **Never scan raw file text for citations**, and by the same reasoning never
  scan raw text to find a concept map. Frontmatter is a **guard** on a root you
  were pointed at, never a discovery mechanism.
- **Digest everything; filter at query time.** `CLASSIFIABLE` is a query-time
  filter and is allowed. Dropping something at import is not.
- **Do not repair pandoc's output.**
- **`READER` must stay defined exactly once in `src/`** — a suite greps for it,
  and `ENDPOINT`/`MODEL` in `llm.py` now get the same treatment.
- **A view of a broken graph is worse than no view** — `render` refuses when
  `check` fails, and your new view is inside that refusal.

## Report back

1. **Each guarantee in the spec, and how you made it fail first.** Not "it
   passes" — what you broke, and what the failure said.
2. **What a real run actually cost**, as `limit_remaining` before and after,
   with the model id, the batch size and the call count.
3. **The three response checks' real failure rate** against the model you used,
   and whether the line format survived contact.
4. **The abstention rate, and on which material** — never the bare number.
5. **Anything you disagreed with**, especially the four suspects above.
6. **What you did not do, and why.**
7. The final `./tests/verify-0.3.0.sh` line and `./tests/run.sh`'s last line,
   verbatim.

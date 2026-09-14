# Handoff — to the Opus agent who ships v0.3.0

**Written 2026-09-14, after v0.2.15, v0.2.16 and v0.2.17 shipped in one
session.** **Disposable**: read it, ship the release, delete it and write your
own. It records what is true about *working here* that is not already in the
repository.

Read `CLAUDE.md` first — it is the standing orientation and overrides this file
wherever they disagree.

---

## Where things are

**v0.2.17 is released, pushed, gate green against origin, tree clean.** The
tree shape is now settled: v0.2.16 made a heading contain its section, v0.2.17
did the same for list items, and a survey of every branch of `records._block`
found **no remaining place** where the graph flattens a containment the source
expresses. Nothing should move under the classification layer.

| | |
|---|---|
| version | 0.2.17, tagged and pushed |
| suites | 25, green, `corpus present, 520 documents` |
| `check()` assertions | **fourteen** |
| the human's base | holds 2 documents; the notes repo ingests to 182,697 nodes |
| next | **v0.3.0 — the talks-about layer**, specced, one piece left |

**The next action is to write `tests/verify-0.3.0.sh`, run it at baseline, and
write `tests/prompt-0.3.0.md`.** Then launch a Sonnet. The spec is
`docs/roadmap.md`, "v0.3.0 — the talks-about layer": 7 build steps, 14
guarantees, and a section saying what is still open.

---

## The hazard that cannot be undone

**`.compost` is a symlink into the human's
private notes repository** — `../notes-repo/base`.

`compost digest`, `render`, `layer` and `draw` all walk *up* the tree looking
for `.compost/`. Run any of them from inside the repo — or anywhere beneath it
— and you write into their personal data. **`git checkout` cannot undo this.**

```bash
W=$(mktemp -d); cd "$W"; compost init . && compost digest --as=… && compost render
```

Put this at the top of every subagent prompt, in its own paragraph, **and
repeat it in the launch message**. Six agents have now run under it and all six
respected it; none would have without the repetition.

Reading the base is fine. Measurements and aggregate counts are fine and this
project runs on them. **Content is not** — never copy what a base holds into a
tracked file.

### Two hazards in `tests/clean-room.sh` specifically

**It destroys the conda env you name.** Always pass a throwaway:

```bash
./tests/clean-room.sh --with-agent compost-gate-tmp /path/to/compost
```

**And it installs into whatever env is active.** A failed env step used to let
`pip install -e .` land in the human's own env, repointing their editable
install at a temp directory the script then deleted — `compost` raising
`ModuleNotFoundError: No module named 'src'` hours later, from a path that no
longer exists. A precondition guard now aborts on env mismatch (commit
fa8b927), but **check `compost --version` after any gate run**.

**Its `tail -2` of `run.sh` discards the evidence when a suite fails.** That
has now cost two investigations. If the gate says a tier failed, clone to a
temp dir and run the suites by hand — do not try to read the cause out of the
gate log.

---

## The one thing I would most want you to understand

**Measure before designing. Every single time. It has never once failed to
change the answer** — and in this session it *reversed* three decisions.

- `TODO-section-container.md`'s own deciding measurement said **25.1%** of
  corpus documents have more than one heading, which argues against sections
  entirely. The corpus is **92% rust-book**. Against the human's own documents
  it is **75.9%**. The question was right; the denominator was not.
- I proposed keeping pandoc's section `Div`. The human proposed hoisting it
  into the `Header`. Measurement backed them: **zero nodes added** against
  **+1,576**, and it made heading and section one handle.
- I specced list hoisting as "adds no nodes", copied from the release before
  without re-deriving it. It **removes** one per item — 19,538 → 19,400.
  Writing the verify script is what caught that.

**A five-line script against the corpus is worth more than an hour of
argument.** Write it before you take a position, not after.

### Be suspicious of your own denominators

This has now bitten **six times**. The newest instance: the v0.2.16 agent
found that `glob.glob("**/*.md", recursive=True)` **silently skips
dot-directories**, so my verify script measured 518 of the 520 documents
`run.sh` reports. **Use `find`.** When a number does not move, ask what its
denominator did.

---

## Working with the human

**They are usually right when they push back, and it is worth checking before
defending.** In this session they were right about: hoisting into the `Header`
rather than the `Div`; the ledger being provenance and replay rather than
retraction; `design-naming.md` having designed the wrong layer entirely; and a
concept map file that is half query and half result being hacky. Every one of
those changed the design, and in every case checking took minutes.

**They answer design questions in prose, at length, and it is worth waiting
for.** Ask in prose. **Never as multiple choice** — they hold context that
redraws the question, and a menu forecloses it.

**They want the reasoning, not just the conclusion.** Commit messages here say
*why*, at length, and that is not decoration: `git log` is the project's
memory.

**They are fine with you committing docs as you go.** Ask before pushing or
tagging.

**They read through `compost serve` and cite blocks.** Run `compost lookup
<guid>` before answering a citation, and note `serve` does not render — run
`compost render` and tell them to refresh.

---

## The subagent pattern

Six releases now. It has caught something real every time.

1. **Spec it in `docs/roadmap.md`** — numbered build steps naming file and
   function, then numbered guarantees each stated as a property with its
   sabotage.
2. **Write `verify-X.Y.Z.sh` and run it before the agent starts.** `NEW` must
   fail at baseline, `GUARD` must pass at both ends. **A NEW check that passes
   at baseline is a bug in the script** — that rule caught one of mine.
3. **Front-load the irreversible constraints in the launch message**, not just
   the brief.
4. **State the decisions already made as "do not re-derive these."**
5. **Name three or four places the spec is most likely wrong**, specifically.
6. **Verify the report yourself.** Read the diff. Re-run the measurements.
   Sabotage the new tests by hand.

**Step 6 is not ceremony.** Every agent this session wrote an accurate, honest
report, and verification still found something each time:

- v0.2.16's agent explained a count mismatch as *"the corpus pin has moved"*.
  It had not — 1,546 is headings at top level, 1,576 is headings anywhere.
  Their numbers were right and **mine** were wrong; their *explanation* would
  have left a false belief that a pinned corpus drifts.
- v0.2.17's agent found a real bug in its own first design and fixed it. I
  reintroduced it by hand to confirm the test caught it: `test_views` 24/24 →
  23/24 while `test_records` stayed **526/526**, confirming their claim that
  the corpus round-trip is blind to it.
- The gate then failed on a **bare clone only** — `test_store` pinned its probe
  to `type == "Para"`, and v0.2.17 correctly absorbed the last `Para` from the
  one smoke fixture. Same species as v0.2.14's `test_mapping_totality`.

---

## v0.3.0 — what is settled, and the one piece left

**Read the spec whole.** The short version:

- **The concept map is one markdown file.** Frontmatter is *configuration*
  (`concept_map: true`); the body is the *concepts* — headings are labels and
  sublabels, the prose under each is its grounding description. Measured: this
  needs **no new mechanism**, because `commonmark_x` already parses
  frontmatter and `ast_to_records` already stores it in
  `document.params["meta"]`, typed. This layer is the first thing ever to read
  it.
- **Frontmatter is a guard, not discovery.** `compost layer` is pointed at a
  root guid and refuses one whose meta lacks the key. It never goes looking —
  that would infer a file's role from its content.
- **Three stages, two ship.** Classify (LLM), collect (a *view*, deterministic
  given the edges), rewrite (a later release). Stopping at the collection still
  ends the release with something to open and comment on.
- **Cost is not a constraint, but batching is not optional.** One block per
  call spends **98.7%** of the budget re-sending the map; at 100 per call the
  human's whole notes repository is **~$0.03**. Batch 100 measured at ~6,800
  tokens typical, ~18,500 worst case.
- **This is the project's first LLM call.** `TODO-ai-call-audit.md` proves
  `src/` has never made one. OpenRouter via `urllib.request` — stdlib, **no new
  dependency**. The suites must never touch the network.

**The one piece left is the prompt**, and there is a draft at
`prompts/concept-map.md`. **The implementer is explicitly free to change it** —
it is a text artifact with a `version` field for exactly that reason, and
decisions about batching, id format and the answer format may well want it
different. Tell them so in the brief.

### Three places this spec is most likely wrong

1. **`prompts/concept-map.md`'s answer format.** A line format was chosen over
   JSON on the argument that a cheap model follows it more reliably. That is a
   guess, not a measurement. If the count-and-label checks fail often, this is
   the first thing to change.
2. **Guarantee 10's over-sized block.** The notes base holds one block of
   **1,350,840 characters**. The cap is specced but no number is chosen, and
   the right one depends on the model's window.
3. **The abstention rate as a quality signal.** It is supposed to say *the map
   is wrong*. On the notes repository **14.1%** of blocks are both short and
   have no ancestor path — almost all vendored plugin documentation — where a
   high rate means *the material is unclassifiable* instead. The two are
   indistinguishable from outside. **Classify the human's own notes separately,
   at least first.**

---

## The TODOs, and which are live

| file | status |
|---|---|
| `TODO-the-clock.md` | **the former v0.2.16.** The ledger, lifted out of the line: retraction had no measured customer, replay needs a semantic clock this project has declined to build three times |
| `TODO-ai-call-audit.md` | the audit behind "this is the first LLM call". Two occurrences remain outside `src/`, both named |
| `TODO-v0.3.0-readiness.md` | **superseded in its conclusion** — it assessed the wrong design. Its measurement warning still stands |
| `TODO-storage-revamp.md` | after v0.3.0, with a trigger |
| `TODO-equality-layers.md`, `docs/design-naming.md` | **unscheduled, not cancelled.** An equivalence layer, not the semantic one |
| `TODO-pandoc-ast-for-notes.md` | after v0.3.0, the human's own sequencing |
| `TODO-citations-in-transcripts.md` | a decision, not a task |
| `TODO-multiple-text-blocks.md` | guarded by a loud error |
| `TODO-code-review.md` | the weakness blueprint. **Item 2 has now fired six times**, and `clean-room.sh` discarding evidence has cost two investigations |

---

## What I would do differently

**Anchor an edit inside the section you mean.** I replaced a block of
`docs/roadmap.md` using the first `### What has to be built` in the file — it
was v0.2.15's, and the edit deleted ~3,000 lines. `git checkout` restored it.
The second attempt asserted the anchor was inside v0.3.0, which then caught a
*second* problem: a `## Replay` line inside my own example code fence fooled
the section scanner. **Assert the boundaries; scan fence-aware.**

**Say "I do not know" and leave it written down.** The one thing in this
session I am least comfortable with is that the abstention rate's meaning is
genuinely ambiguous on the current material, and I have written it into the
spec as ambiguous rather than picking a reading.

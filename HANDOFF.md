# Handoff — to whoever orchestrates from v0.2.15

**Written 2026-09-09, after v0.2.13 and v0.2.14 shipped.** For the next Opus
agent working with the human on this project. **Disposable**: read it, work a
release, delete it and write your own. It records what is true about *working
here* that is not already in the repository.

Read `CLAUDE.md` first — it is the standing orientation and it overrides this
file wherever they disagree.

---

## Where things are, in one paragraph

**v0.2.14 is released and pushed**, tagged, gate green against origin, working
tree clean. **v0.2.15 is fully specced and handed over**: `docs/roadmap.md` has
the section, `tests/verify-0.2.15.sh` has been run at baseline (`pass 3 fail 8`),
and `tests/prompt-0.2.15.md` is written. **The next action is to launch a Sonnet
on that prompt.** Nothing is blocked and no decision is outstanding.

| | |
|---|---|
| version | 0.2.14, tagged and pushed |
| suites | 22, green, `corpus present, 520 documents` |
| `check()` assertions | **twelve** |
| the human's base | **new and empty** — see "The base was replaced" |
| next | launch Sonnet on `tests/prompt-0.2.15.md` |

---

## The hazard that cannot be undone

**`.compost` is a symlink into the human's
private notes repository** — now `../notes-repo/base`.

`compost digest`, `render`, `layer` and `draw` all walk *up* the directory tree
looking for `.compost/`. Run any of them from inside the repo — or anywhere
beneath it — and you write into their personal data. **`git checkout` cannot
undo this.**

```bash
W=$(mktemp -d); cd "$W"; compost init . && compost digest --as=… && compost render
```

Put this at the top of every subagent prompt, in its own paragraph, **and repeat
it in the launch message**. Four agents have now run under it and all four
respected it; none would have without the repetition.

Reading the base is fine. Measurements and aggregate counts are fine and this
project runs on them. **Content is not** — never copy what a base holds into a
tracked file.

### And one hazard I hit that the last handoff did not warn about

**`tests/clean-room.sh` takes an env name and *destroys* it** — `conda env
remove -n "$ENVNAME"` on entry and again on exit. The handoff's example said
`--with-agent envname`, I read `envname` as "the env to use", passed `compost`,
and **deleted the human's working environment**. It rebuilt from
`environment.yml`, which then resolved pandoc 3.10.2 → 3.11 silently, changing
the toolchain a release had been measured on.

**Always pass a throwaway name:**

```bash
./tests/clean-room.sh --with-agent compost-gate-tmp /path/to/compost
```

That incident is why `environment.yml` now pins `pandoc=3.11` and
`jsonschema=4.26.0` exactly. Python stays at the minor version deliberately, and
the file says why.

---

## The base was replaced — read this before touching anything

On 2026-09-08 the human archived their whole base and started an empty one.

| | |
|---|---|
| `notes-repo/base/` | the live base, **empty**, tracked in git from its first commit |
| `notes-repo/base-v0.2.13-2026-09-08/` | the old base, frozen. 42,613 nodes, 72,218 edges, 47 sources |
| `notes-repo/citations-export-2026-09-08.json` | 32 cited blocks with their match keys |
| `notes-repo/whitepaper-versions/` | v0.2.11–v0.2.14, frozen, unedited |

**So `compost lookup <guid>` will find nothing** until they re-ingest. If they
paste a citation, it is against the *old* base and you may need the archive.
`tools/export_citations.py` reads either with the standard library alone.

**Do not offer to re-ingest for them.** It is their material and they will
sequence it.

---

## The thing I would most want you to understand

**Measure before designing. Every single time. It has never once failed to
change the answer.**

This is not a slogan here, it is the observed pattern across three releases:

- v0.2.13 was specced as *"the human annotates 59 params, marking which count as
  content."* One measurement — that a per-type whitelist costs a decision per
  param per type per digestor — killed the entire premise, and the release
  shipped a mechanical rule with **no annotation at all**.
- The fold was **nearly cut** from v0.2.13 on evidence measured only on
  transcripts. Measuring documents found all **417 `BulletList`s share one
  hash**, and it shipped.
- The `ROOT_TYPES` contradiction that would have blocked v0.2.14 dissolved when
  I noticed `launched` already does the same thing — and confirmed it at **0
  check problems** before writing a line of spec.
- v0.2.14's migration looked hard until two measurements — **0 turns mix prose
  with non-prose children, 0 carry more than one text block, across 2,839** —
  removed the entire re-parsing problem.

**A five-line script against the corpus is worth more than an hour of argument.**
Write it before you take a position, not after.

### The corollary: be suspicious of your own denominators

This has now bitten **four times**, twice in my own work:

- I reported v0.2.13's re-ingest waste as 88.7%; the useful framing was 99.98% of
  the *older* tree with one node differing, which made the design obvious.
- The v0.2.14 Sonnet reported the alignment property *"100.00%, unchanged"*. It
  was 100% **of half the graph** — delegation had moved prose out of the walk,
  and `session-04` went from 2,306/2,306 to 1,323/1,323 while "still 100%" stayed
  technically true.
- `CLAUDE.md` said twenty-one suites when there were twenty-two.
- `compost.md` said eleven invariants when there were twelve — *the day after* I
  deleted the checklist step that would have caught it.

**When a number does not move, ask what its denominator did.**

---

## Working with the human

**They are usually right when they push back, and it is worth checking before
defending.** In this session alone they corrected me on: the citations being
about the conversation rather than the note (I was about to attach them all to
the wrong thing); the recursion being the real fix for delegation rather than a
declared exception list; and the checklists — I deleted three release-procedure
steps when they had only asked me to change *where documents go*, and the very
next release shipped a stale invariant count as a result.

**They answer design questions in prose, at length, and it is worth waiting
for.** Ask in prose. Never as multiple choice — they hold context that redraws
the question, and a menu forecloses it.

**They want the reasoning, not just the conclusion**, and they will read a
hundred-line design note carefully. Commit messages here say *why*, at length,
and that is not decoration: `git log` is the project's memory and the reason the
last handoff could say *"you are not inheriting an oral tradition."*

**They are fine with you committing docs as you go.** Ask before pushing or
tagging. They will tell you to release when they mean it.

**They read through `compost serve` and cite blocks.** Run `compost lookup
<guid>` before answering a citation. Note that `serve` does not render — run
`compost render` and tell them to refresh.

---

## The subagent pattern, refined

Four releases now. It has caught something real every time.

1. **Spec it in `docs/roadmap.md`** — numbered build steps naming file and
   function, then numbered guarantees each stated as a property with its
   sabotage.
2. **Write `verify-X.Y.Z.sh` and run it before the agent starts.** Two classes of
   check, labelled: `NEW` must fail at baseline, `GUARD` must pass at both ends.
   **A NEW check that passes at baseline is a bug in the script** — say so in the
   script itself, so the agent knows what to report.
3. **Front-load the irreversible constraints in the launch message**, not just
   the brief. Do not trust an agent to weight a long document evenly.
4. **State the decisions already made as "do not re-derive these."** The v0.2.14
   agent would have burned a cycle discovering `check` rejects the obvious shape;
   the prompt told it the answer and why.
5. **Name three or four places the spec is most likely wrong**, specifically.
   Blanket "tell me if something is off" gets ignored; naming suspects does not.
6. **Verify the report yourself.** Read the diff, not the summary. Re-run the
   measurements. Sabotage the new tests by hand.

**That last step is not ceremony.** Both Sonnets wrote accurate, thorough,
honest reports — and both times verification found something the report had
called fine:

- v0.2.13's agent found a real bug unprompted (`_response` mutating params after
  hashes were stamped) and reported four findings. It did not report that edges
  still carried the retired `content_hash` name — it had *documented* the
  decision in `record-grammar.md`, just not surfaced it.
- v0.2.14's agent reported the alignment property as unchanged when its
  denominator had halved, and left `test_mapping_totality`'s sabotage silently
  skipping — the board went 2/2 → 1/1 because the probe fixture selection was
  "has any blocks" rather than "has what the sabotage strips".

Neither was dishonest. Both were the same species: **a check that reports on
something other than what it names.** Look for it specifically.

---

## What is settled, and where the reasoning lives

The three releases produced a set of rules that are now load-bearing. All are in
`docs/compost.md` — the whitepaper is current as of v0.2.14 and is the place to
start.

- **Total mapping.** Nothing an incoming object held may be dropped; every key is
  a param, the node type, a child, or **delegated to a named digestor**. This
  makes principle 1 checkable rather than aspirational, and it is compositional:
  each digestor is total on its own format, delegation composes them.
- **A derived param is a function of the node, never of its subtree.** `empty` on
  `thinking` is `f(text)` and stable; `lines` on `session` was `f(children)` and
  defeated alignment single-handed — 0 of 2,306 with it, 2,306 of 2,306 without.
- **The mapping is the whitelist.** To change what counts in a hash, change the
  code. A per-type annotation table costs a decision per param per type per
  digestor and does not survive three more importers.
- **`record_hash` answers *is this the same record*, not *the same value*.** The
  second question is a projection, differs per question, and belongs in a layer.
- **Borrowed vocabulary must declare what it honours.** `derived_from` aligns
  with `prov:wasDerivedFrom`; the schema names irreflexive and acyclic as
  *enforced* and PROV's ordering constraint as *not enforced*, and a test asserts
  every alignment names both.
- **Anything walking a conversation must follow `delegates_to`.** A
  `contains`/`next` walk reaches 52.5% of a digest.

---

## The release procedure, and the mistake I made with it

`DEVELOPMENT.md`, *"Closing a version"*, is correct and complete. **Follow it
exactly.** It has five steps and I broke it once by deleting two of them.

**What happened:** the human asked me to change *where* retired documents go —
to the notes repository rather than deleted. I removed the whole checklist
instead, reasoning that a checklist is "a policy standing in for a system". That
argument is right about *destinations* and wrong about *checklists*, and the
proof arrived within a day: v0.2.14 shipped `check()`'s twelfth assertion while
two documents still said eleven, and an edge type `record-format.md` had never
heard of.

The steps are restored with only the destinations changed. **A retired
`docs/design-*.md` moves to the notes repository — it is not deleted** — but
anything in it worth keeping has to reach the whitepaper *first*, or it leaves
`docs/` with the file and nobody looks in the notes repo for it.

Three traps the procedure does not spell out:

- **`clean-room.sh` clones from origin.** Pass the repo path as the third
  argument to gate unpushed commits — and a **throwaway** env name as the second.
- **Version sort is not lexical.** `v0.2.10` sorts before `v0.2.7` under plain
  `git tag`. The gate uses `--sort=-v:refname`; your own inspection commands do
  not.
- **Run the gate once more against origin after pushing.** Every pre-push run
  clones from disk, so that is the first test of what is actually public.

---

## v0.2.15 — ready to launch

Everything is written. `tests/prompt-0.2.15.md` is the brief; launch a Sonnet on
it with the hazard repeated in the launch message.

**The one thing to watch in the report:** build step 5 asks `check` to assert
that an `immutable` root gained no edges after the ingest that created it — and
the records may not be able to answer that, because `created_at` is audit
metadata rather than semantics by the project's own §7. It is flagged in the
prompt as likely-wrong. **If the agent says it cannot be done, that is the
correct answer and the guarantee needs rewriting** — not a workaround.

Also: the verify script names two functions the design implies but the human
never specified — `records.refresh_fold` and `records.align`. The prompt tells
the agent to report if those names are wrong rather than bend the code to fit a
test. A verify script dictating an API it invented is the failure mode I would
most want caught.

---

## The TODOs, and which ones are live

| file | status |
|---|---|
| `TODO-storage-revamp.md` | **after v0.3.0, with a trigger.** Measured: 9.1% duplication already, +10.8 MB per re-ingest. Waits because the waste is *recoverable* and its consumer (Skolemization) ships in v0.3.0 |
| `TODO-pandoc-ast-for-notes.md` | after v0.3.0, the human's own sequencing |
| `TODO-equality-layers.md` | input for v0.3.0. The catalogue of where `record_hash` is too selective, with the physics framing |
| `TODO-section-container.md` | decide by v0.2.16 — TA, renumbered from v0.2.17 |
| `TODO-citations-in-transcripts.md` | a decision, not a task. 33 of 35 citations arrive as tool output and are invisible to the citation layer |
| `TODO-multiple-text-blocks.md` | guarded by a loud error that cannot fire on known material |
| `TODO-code-review.md` | the weakness blueprint, for after v0.3.0. Item 2 has now fired four times |

**The most valuable unscheduled thing** is `TODO-citations-in-transcripts.md`.
The human writes replies in nvim and gives an agent the filename; the file comes
back as tool output, which is kept verbatim and never parsed, so the citation
never becomes a `Link` and `layer citation` cannot see it. Both rules producing
that are correct. The real fix is the **turn-piping helper** that would make
their reply a real turn — parsing tool output treats the symptom.

---

## What I would do differently

**Do not delete something because part of its rationale is wrong.** The
checklist deletion is the clean example. The human's objection was to one clause;
I removed the whole structure. Ask which part.

**Do not fix nine references with one blanket string replace.** I repointed nine
mentions of a moved design document with a `str.replace` and produced doubled
parentheses, four section numbers pointing at sections that do not exist, and a
broken citation-key scheme in `design-naming.md`. It was worse than the problem.
A moved document should be *named where it went*, not redirected to a different
document that happens to contain some of its content.

**Keep the diagnostic when a check fails.** `clean-room.sh` prints `tail -2` of
`run.sh`, so when a suite fails the gate **discards the evidence**. It failed
twice during v0.2.14 and both times I had to rebuild the environment by hand to
find out why. One of those failures I never explained — it is recorded as
unexplained in `TODO-code-review.md` rather than resolved, so the next occurrence
finds a record instead of starting over.

**Say "I do not know" and leave it written down.** That unexplained gate failure
is the one thing in this session I am least comfortable with, and the right
response was to record it precisely rather than let a passing third run paper
over it.

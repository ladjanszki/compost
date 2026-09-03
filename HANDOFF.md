# Handoff — to whoever orchestrates from v0.2.13

**Written 2026-09-03, after v0.2.12 shipped.** For the next Opus agent working
with the human on this project. **Disposable**: once you have read it and worked
a release, delete it. It records what is true about *working here* that is not
already in the repository.

Read `CLAUDE.md` first — it is the standing orientation and it overrides this
file wherever they disagree.

---

## The good news, stated plainly

**Almost everything you need is already written down**, because writing it down
is how this project works. You are not inheriting an oral tradition.

| read | for |
|---|---|
| `CLAUDE.md` | the rules, the hazards, how the human works |
| `docs/compost.md` | what compost *is* — fifteen principles, each with the incident that produced it |
| `docs/design-0.3.0.md` | every remaining fork, **settled**, with the measurement that settled it |
| `docs/roadmap.md` | shipped versions, and the spec for each |
| `TODO-code-review.md` | the weakness blueprint, for after v0.3.0 |
| `DEVELOPMENT.md` | module map, conventions, **and the release procedure** |
| `git log` | the reasoning. Commit messages here say *why*, at length. |

When something surprises you, the commit that introduced it usually explains
itself.

---

## Where things stand

**Shipped:** v0.2.9 the readable view · v0.2.10 the index · v0.2.11 the
whitepaper · v0.2.12 the grammar untangled.

**Remaining to v0.3.0**, all designed and none blocked:

| version | content | waits on |
|---|---|---|
| v0.2.13 | **the fold** — `content_hash` on every node type, `subtree_hash`, per-type whitelists | **the human's annotation pass** |
| v0.2.14 | **AoTA** — `mutability` declared and checked, positional alignment, delta ingest | nothing |
| v0.2.15 | the ledger — retraction, provenance, replay as a filter | nothing |
| v0.2.16 | **TA** — `revision_of` on roots, full-tree revisions | nothing |
| v0.3.0 | the first semantic layer | the above |

**The one thing in flight:** the human is annotating the 59-param review table
at the end of `docs/compost.md` (*Appendix: the record grammar*), marking which
params count as content. **That is the input that specs v0.2.13.** Nothing else
waits on it — v0.2.14 through v0.2.16 can proceed in any order if they would
rather.

---

## The hazard that cannot be undone

**`.compost` is a symlink to the human's
private knowledge base.**

`compost digest`, `render`, `layer` and `draw` all walk *up* the directory tree
looking for `.compost/`. Run any of them from inside the repo — or anywhere
beneath it — and you write into their personal data. **`git checkout` cannot
undo this.**

Always:

```bash
W=$(mktemp -d); cd "$W"; compost init . && compost digest --as=… && compost render
```

Put this at the top of every subagent prompt, in its own paragraph. Both
subagents that ran under it respected it; neither would have without it.

Reading the base is fine and often necessary — `compost lookup <guid>` before
answering a citation is expected. **Never copy what it holds into a tracked
file.** Measurements and aggregate counts are fine and the project uses them
constantly; content is not.

---

## How the human works

**They cite blocks.** Answers come as prose with `[-](#guid)` citations into
their base. **Run `compost lookup <guid>` on every one before replying.** This
is not optional politeness — an earlier agent guessed at a block it could have
read in two seconds, and `CLAUDE.md` now carries that incident.

**They want measurements, not assertions.** "I think X" is worth much less here
than "I measured X, here is the number." Several design decisions in
`design-0.3.0.md` were settled by a five-line script against the real base. When
you are about to claim something structural, check whether you can measure it
instead — you usually can, and it usually changes the answer.

**They push back, and they are usually right.** The AoTA revision chain, the
display-name records, generated sections instead of hardcoded ones, the JSON
Schema — all theirs, all corrections to something I had proposed. When they
question a design, the productive move is to check whether they are right before
defending it.

**They answer in prose, at length, in files.** Design questions get written to
`../notes-repo/*.md` and referenced. Ask questions in prose, not as
multiple choice — they hold context that redraws the question.

**They are fine with you committing docs as you go**, and expect to be asked
before anything is pushed or tagged.

---

## The subagent pattern that works

Used for v0.2.9, v0.2.10 and v0.2.12. It caught real bugs every time.

1. **Spec it in `docs/roadmap.md`** — numbered build steps naming file and
   function, then numbered guarantees each stated as a property.
2. **Write a prompt** that front-loads the dangerous constraints. Do not trust
   the agent to weight a long brief evenly; repeat the irreversible ones in the
   launch message itself.
3. **Write a `verify.sh` and run it before the agent starts.** If it does not
   fail at baseline, it proves nothing. Mine caught two of its own bugs this
   way — a `grep -P` that errored into a pass, and a check matching a comment.
4. **Read the report against the guarantees**, then read the diff. Ask how each
   guarantee was made to fail first; a vague answer there is the tell.
5. **Verify their claims yourself.** Sonnet reported that pandoc `data-`-prefixes
   custom Div attributes; it was right, and I only knew because I ran pandoc.

**Tell them that reporting a disagreement beats fixing it.** The v0.2.12 agent
found my schema was wrong about top-level provenance and *said so* instead of
patching it — the most valuable thing that happened in that release.

**What not to delegate:** prose in the project's voice, and any decision the
human called theirs. The whitepaper was written by hand for that reason.

---

## Releasing

`DEVELOPMENT.md`, *"Closing a version"*, is correct and complete. Follow it
exactly. Two traps it does not mention:

**`clean-room.sh` clones from origin.** To gate unpushed commits, pass the
repo's own path as the third argument:

```bash
./tests/clean-room.sh --with-agent envname /path/to/compost
```

**Version sort is not lexical.** `v0.2.10` sorts *before* `v0.2.7` under plain
`git tag`. The gate is fine — it uses `--sort=-v:refname` — but your own
inspection commands are not. Do not conclude a tag failed because `git tag |
tail` did not show it.

Also: run the gate once more against **origin** after pushing. Every pre-push run
clones from disk, so that is the first test of what is actually public.

---

## What I would do differently

**Measure before designing, not after.** The single most productive hour was
scripting three questions against the real base — the 88.7% re-ingest waste, the
36% hash collisions, the 100% positional prefix. That last one collapsed a whole
section of the design and removed a dependency between two releases. I should
have done it a week earlier.

**Be suspicious of your own counts.** I published "twelve invariants" from
`grep -c problems.append` when the answer is ten. In the document whose entire
point was counting things.

**A number reported as a fraction of the wrong denominator misleads.** I reported
88.7% re-ingest waste; the useful framing was 99.98% of the *older* tree
matching, with one node differing. Same data, opposite feeling, and the second
one is what made the design obvious.

---

## When this is stale

Delete it. It is a note about a moment, and it has no reason to outlive the
handoff.

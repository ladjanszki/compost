# TODO — tool output through compost, instead of into the context

**Not scheduled. An idea from the human, 2026-09-14, with the argument for it,
the conflict I think it contains, and a proposed split that resolves the
conflict.** Written because the idea is good and the failure mode is subtle
enough to be worth recording before anyone builds it.

---

## Where it came from

Late in a long session I noted my own context usage: **197k of 578k tokens —
about a fifth of everything — was Bash tool output**, and the harness's own
advice was *"pipe output through head, tail, or grep to reduce result size."*

The human's observation:

> The problem is most of the time you write one liners where you have to decide
> beforehand what the argument for tail and/or head should be in the bash
> command. Of course you can't do this too optimally. If the tool use is not
> directly injected into your context but into compost first then with a cheap
> and stupid model we would be able to check where is the relevant part which
> you can review. Of course because the tool output is there you can come back
> for more context later.

---

## Why this is the project's own rule, applied one level up

**It is exactly principle 1, and I was breaking it all session.**

> **Digest everything the file holds; filter at query time, never at import.**
> Deciding a field is noise while reading it is a decision made once, silently,
> and unrecoverably.

Writing `| tail -3` is *filtering at import*. I have to guess what matters
**before seeing the output**, the discarded part is gone, and nobody — me
included — knows what was in it. That is the same decision the project forbids
a digestor from making, made a hundred times a session by the agent that wrote
the rule.

It cost something twice in one session, both recorded:

- `clean-room.sh`'s own `tail -2` of `run.sh` **discarded the suite line naming
  a failure**, twice, and both times the cause had to be rediscovered by
  cloning to a temp directory and running the suites by hand.
- My first gate run went through `| tail -30`, which threw away the env-setup
  lines. When the human's `compost` command broke hours later, the evidence
  that would have explained it immediately had already been dropped.

**And the records are already shaped for this.** `toolcall` and `tooloutput`
are first-class node types with `tool_use_id`, `name`, `input`, `text` and
`is_error`; the man page already says tool output is *"stored whole, because it
is terminal text"*. A transcript digest is already lossless by property. The
store does not need inventing — only a different producer.

---

## The conflict I think it contains

**A cheap model choosing what I see is a filter whose mistakes are invisible.**
If it drops the one line that mattered, I do not get a worse answer with a
warning — I get a confident answer built on a gap I cannot detect, because I
never saw what was removed. That is precisely the defect this project keeps
finding under a different name: **a check reporting on something other than
what it names**, which surfaced six times in one session.

It is worse than a human filtering, because at least `tail -3` is *honest about
being arbitrary*. A summary reads as complete.

**The human's own sentence contains the mitigation**, and it is the right one:
*"because the tool output is there you can come back for more context later."*
That converts an unrecoverable filter into a recoverable one, which is the
project's actual criterion — *filtering later is free and reversible; filtering
at import is neither.*

**But recoverable is only worth something if the reader knows to go back.** An
agent handed a confident summary has no signal that it is missing anything.
So the design has to make the gap *visible*, not merely *reachable*. Minimum:
the summary states what it left out, by size and shape — *"showed 12 of 340
lines; 328 lines matching `PASS` omitted"* — so absence is a fact in the
context rather than a silence.

**A second, smaller conflict:** the summariser cannot know what I am looking
for. Summarising `git diff` is not a well-posed task; *"which files changed
outside `src/`"* is. So the **query has to travel with the call** — this is not
"summarise this output", it is "answer this from this output, and say what you
did not use". A generic summariser will underperform a well-chosen `grep`.

---

## The split I would propose, and why this half first

**The idea is two ideas, and only the second one needs a model.**

### Stage 1 — store it, hand back a handle. No LLM at all.

Every tool call's output goes to compost. The agent receives a mechanical,
honest slice — first N and last N lines, plus the total — and **a handle**.
Anything else it wants, it queries: `compost lookup`, `grep`, a `--range`.

This alone fixes most of what the human observed:

- no guess before seeing the output
- nothing discarded — the full text is in `storage/` and the graph
- what was omitted is *stated*, not hidden
- **no extra model call, no latency, no cost, no new trust boundary**
- and it makes an agent's session **auditable after the fact** — the tool
  output is in a base, addressable, citable, queryable, which is what this
  project exists for

### Stage 2 — a cheap model pre-selects, carrying the query.

Only worth building **if stage 1 is measured and the agent still cannot find
things**. It adds a model call per tool use, a new writer to the base, and the
invisible-filter problem above.

**This ordering is the project's standing one**: ship the reversible half,
measure, and let evidence decide whether the ambitious half is needed. It is
the same shape as *code first, record the scheme name from day one*, and as
*require the flag first and relax later*.

---

## What would have to be decided

1. **Whose base?** An agent's tool output is voluminous and mostly disposable;
   the human's base is their reading material. Almost certainly a **separate
   base per session**, which raises the first real question of *many small bases
   rather than one*.
2. **Who writes it?** Nothing in `src/` is currently invoked by a harness on
   every tool call. `digest --as=…` per call is likely too slow; this may want
   an append-only writer, which v0.2.15 now supports.
3. **What does the agent get back by default?** Head+tail+count is the obvious
   start. The exact numbers should come from measuring real sessions.
4. **How is the omission made visible?** The single most important detail, per
   the conflict above.
5. **Is this compost, or a tool that uses compost?** `tools/loop.py` is the
   precedent for the second, and `pyproject.toml` deliberately does not ship
   `tools/`.
6. **Does it need an LLM at all?** Stage 1 says no. That should be *tested*
   before stage 2 is designed.

---

## The measurement to take first

**Against a real transcript, already digestible today, with no new code:**
of an agent session's total context, what fraction is tool output; what the
distribution of output sizes is; and — the one that decides everything — **how
often the agent later needed something it had already truncated away.** The
last is answerable by looking for repeated calls that widen a previous
`head`/`tail`, which is a mechanical pattern in the transcript.

This project has never once regretted measuring first, and has reversed three
designs in a single session by doing it.

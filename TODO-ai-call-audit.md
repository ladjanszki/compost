# TODO — every AI call in this project, audited

**Written 2026-09-11, at the human's request, before v0.3.0 adds the first
deliberate one.** Their standing position: LLM API calls were declined on more
than one occasion, and an unplanned one added for convenience is exactly the
kind of thing that stops this tool being minimal. This file is the audit so
that the v0.3.0 call is *the first*, by decision rather than by accident, and
so the rest can be deleted or kept on purpose.

---

## The headline: `src/` makes no AI calls at all

**Every `subprocess.run` in `src/` is pandoc or graphviz. There are four, and
that is the complete list:**

| file | call |
|---|---|
| `src/markdown.py:56` | pandoc, the reader |
| `src/views.py:347` | pandoc, the writer |
| `src/draw.py:163` | graphviz `-V` |
| `src/draw.py:228` | graphviz `-Tsvg` |

No network call, no API key, no model name, nowhere in the tool. **The ten
subcommands cannot reach an LLM.** `compost digest`, `check`, `layer`,
`render`, `lookup`, `serve`, `draw`, `ls`, `init` and `version` are all pandoc,
graphviz and the standard library.

## The three places AI appears anyway

### 1. `tools/loop.py` — a real `claude --print` call

```python
r = subprocess.run(["claude", "--print", "--output-format", "json"], ...)   # :107
```

**What it is.** One round of the `nvim → compost → claude → compost` loop,
turned into an importable function. Its own docstring is explicit that it is
*"Not a subcommand and will not become one"*.

**How exposed it is.** `run_round(st, note_text, ask=_ask_claude, …)` takes the
call as an **injectable parameter**, and `tests/test_loop.py` supplies a canned
envelope instead — *"digesting a round should not cost an API call every run"*.
So the suites never call it, and a caller can substitute anything.

**Status: not part of `compost`.** It is in `tools/`, which
`pyproject.toml` deliberately excludes from the package — *"tools/ stays out of
this list on purpose; it is dev material, reachable from a checkout, and never
shipped"*. It cannot be invoked through the CLI: `loop` is not in `src/cli.py`.

**Decision needed:** keep as dev material, or delete. It is the closest thing
to a precedent for the v0.3.0 seam and the injectable shape is worth copying —
but it hardcodes `claude`, which is precisely what v0.3.0 must not do.

### 2. `tests/clean-room.sh` — asks a fresh Claude what it can work out

```bash
step "a fresh Claude, given only CLAUDE.md"                  # :221
if ! command -v claude >/dev/null; then …                    # :223
```

**What it is.** The gate's last step gives a clean clone to a fresh Claude with
only `CLAUDE.md` and checks whether the document alone explains how to fetch
the corpus and read the tier line. Its comment: *"the one failure this script
cannot otherwise catch"* — documentation drift that every local reader is
immune to because they already know.

**How exposed it is.** Opt-in behind `--with-agent`, skipped when `claude` is
not on PATH, and it **tests the documentation, not the tool**. It writes
nothing into any base.

**Status: a test of prose, not a feature.** Recommend keeping, and it is worth
noting it is the only AI call in the project with a stated reason nothing else
can serve.

### 3. `src/routes.py` — `claude-code-response` **reads** output, never calls

`grep subprocess src/routes.py` finds **one comment and no call.** The route
ingests a `{responds_to, follows?, envelope}` wrapper around what `claude
--print --output-format json` produced *somewhere else*, by someone else, into
a file. That is ingestion of an artifact, the same as digesting a transcript.

**Status: not an AI call.** It parses bytes. Listed here only because grepping
for "claude" finds it and a future audit should not have to re-derive that.

## What this means for v0.3.0

**The claim "this is the first LLM API call in compost" is true**, and now
checkable: `src/` contains none, and the two that exist are a dev script
outside the package and a documentation test. Nothing in the shipped tool has
ever called a model.

So v0.3.0 is genuinely the first, and the constraints the human set apply
cleanly:

- **Not Claude Code.** A layer that only builds inside Claude Code means the
  base can only be built by someone with Claude Code, and the result cannot be
  reproduced or audited later. `tools/loop.py`'s hardcoded `claude` is the
  anti-pattern, in the repo, to point at.
- **One seam**, the way `src/markdown.py` is the one pandoc seam and `READER`
  is defined exactly once. A test should assert the model name and endpoint are
  defined once, the same way `test_extras` greps for `READER`.
- **The suites must never make a network call.** `tools/loop.py`'s injectable
  `ask=` is the shape that already works here.
- **No API key in the graph, in `storage/`, or in git.**

## The deeper reason this matters, beyond minimalism

**An LLM judgement is the first input to this graph that cannot be recomputed
from bytes.** Everything until now is deterministic: the round-trip is an
acceptance test *because* `records_to_ast(ast_to_records(ast))` can be re-run
and compared. Run a classifier twice and it may produce different edges.

That is the third instance of one shape this project keeps meeting — a fact the
records cannot recompute — after the missing semantic clock
(`TODO-the-clock.md`) and `design-naming.md`'s `scheme`. The answer that worked
both times applies again: **if it cannot be recomputed, the record must carry
enough to explain it.** Model id, prompt version, the concept-map revision it
ran against, and the run itself as a node.

That is not bureaucracy — it is what makes *aerating the compost* possible:
open it, read it, point at the exact place, ask for a fix.

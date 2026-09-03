# TODO — a code review, after v0.3.0

**Not scheduled inside the current window.** After v0.3.0 ships, run one or more
Opus agents over this codebase looking for weaknesses of the kind recorded
below. This file is the **blueprint**: not a list of bugs, but a worked example
of the *class* of mistake to hunt for.

---

## The incident this exists to generalise

**Found 2026-09-03.** `docs/record-grammar.md` — a **markdown document** — is the
source of truth for what a valid record is. `tests/test_grammar.py` discovers
that grammar by **scraping prose with regexes**:

```python
body = text.split("## 3. Node types", 1)[1].split("\n## 4.", 1)[0]
for line in body.splitlines():
    if not line.startswith("|"): continue
    ...re.findall(r"`([^`]+)`", cells[1])
```

It splits on a **literal heading string**, parses **markdown table pipes**, and
extracts field names from **backtick spans**.

### Why it is bad

**The records are JSON.** There is a standard, mature way to define and validate
a JSON document's shape, and this invented a worse one — a hand-rolled parser
over a prose format that was never designed to be parsed. *This would earn an F
in a first software-engineering course, and it shipped here because each step
looked reasonable on its own.*

**It fails silently, in the most dangerous direction.** Rename `## 3. Node
types` and the test does not error — it finds fewer types and quietly asserts
less. A test that weakens without failing is worse than no test, because the
board stays green.

**It was about to be broken by unrelated work.** The v0.2.11 docs revamp
restructures `docs/`. Renaming that heading is exactly what a revamp does.

**The gap was invisible from both ends.** The document looked authoritative
because a test checked it. The test looked rigorous because it checked a
document. Neither was wrong on its own.

### Why it survived so long

Because the *other* half was genuinely good. The suite checks coverage **in both
directions** — the grammar may not name a type the base never produces, and the
base may not produce one the grammar does not name. That is a real and unusual
property, and it made the whole suite look sound. **A strong idea can carry a
weak implementation past review.**

### The fix, scheduled as v0.2.12

A JSON Schema becomes the source of truth for record shape; `check()` keeps the
graph-level invariants no schema can express; the coverage tests survive and
read structured data instead of scraping tables; the prose keeps the reasons.

---

## The blueprint: what to hunt for

Each of these is generalised from the incident above.

1. **Where is a standard solved problem solved by hand?** Parsing, validating,
   serialising, diffing, hashing, sorting. Ask of every hand-rolled parser: what
   is the format, and does it have a standard tool?

2. **Which tests can weaken without failing?** Anything that discovers what to
   assert by searching, globbing, splitting on a literal, or matching a regex
   over content it does not own. A test whose assertion count is derived from
   data can quietly assert nothing. **Ask every test: what makes it fail if it
   stops testing anything?**

3. **Which documents are load-bearing for code?** A prose file a program parses
   is a schema without a schema's guarantees. Find every `open(...md)` and every
   split on a heading.

4. **Where is a good idea protecting a bad implementation?** The two-direction
   coverage check hid the scraping for months. Look for genuinely clever
   properties and check the machinery underneath them separately.

5. **Which invariants are enforced by attention rather than by a program?**
   `docs/compost.md` lists fifteen principles and ten invariants — only the ten
   are checked. For each of the fifteen, ask whether it *could* be checked
   cheaply, and why it is not.

6. **What is asserted by a comment?** Claims in docstrings and comments that no
   test holds. Several have already been found false: `views.py` claiming
   handles were 8 characters, `CLAUDE.md` claiming the repo has no `.compost/`,
   the roadmap claiming human turns had a coloured border when the selector
   matched nothing.

7. **Which numbers in documentation were measured, and when?** This project
   labels measurements. Re-run them. The `roadmap.md` note that three claims
   *"had already been wrong because they were argued from constructed samples"*
   is the standing warning.

8. **Where does a silent failure look like a success?** A dead CSS selector, a
   grep that matches a comment, a `--sort` that is lexical when it should be
   version-ordered, an empty result treated as a clean result.

## How to run it

Independent agents that know nothing of each other's findings, so agreement
between them means something. Triage into three buckets: **fix now**, **record
as a known cost**, **wrong, and here is why**. The third bucket matters most —
a review that is never wrong was not looking hard enough.

## When this is done

Delete this file, or replace it with what the review found.

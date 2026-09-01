# TODO — revamp `docs/`

**Not scheduled, and deliberately not in `docs/roadmap.md`.** That file holds
work with a version number and a settled design; this has neither yet. It is not
in `TODO.md` either, because that is the running list of gaps in the *tool* and
this is a question about the repository.

**Do this after v0.3.0 ships, not before.** The folder is being actively written
into right now — `design-0.3.0.md` and `design-0.2.10.md` are both live working
documents — and tidying a shelf while still stacking it is how things get filed
twice.

---

## The trigger: a contradiction already in `CLAUDE.md`

Its *What is authoritative* table says:

> `docs/` — **what is true now.** Rewritten as understanding improves.

That has stopped being true. Twelve files sit in `docs/` and they are at least
**four different kinds of thing**:

| kind | files |
|---|---|
| what is true now | `decisions.md`, `record-format.md`, `record-grammar.md`, `man-compost.md`, `queries.md` |
| superseded drafts, kept for intent | `spec.md`, `design-answers.md`, `spec-review.md` |
| describes material not in this repo | `migration.md` |
| working design for unreleased work | `roadmap.md`, `design-0.3.0.md`, `design-0.2.10.md` |

One rule covering four categories means the rule describes none of them. A
reader who takes the table literally will believe `spec.md` is current — and
`CLAUDE.md` separately says it is *"historical, superseded by `decisions.md`"*,
so the file already contradicts itself about its own directory.

## The two questions

**Where does each file live** — `docs/`, the private notes folder, or nowhere?

**Should it be published at all?** This is the one that needs a person. It is a
judgement about what this repository is *for*, not a filing decision, and it is
the question that prompted this task: on 2026-09-01 `design-answers.md` was
moved out to the notes folder and then moved back, because the answer was not
obvious.

## What is already known, so it is not re-derived

While `design-answers.md` was out, the cost of erasing a `docs/` file from
history was measured:

- it entered in a **single commit**, `e9f189c` (2026-08-18), and was never
  modified afterwards
- removing it retroactively would rewrite **115 commits**
- and require recreating **ten tags**, `v0.2` through `v0.2.9` — which
  `tests/clean-room.sh` then checks against every `CHANGELOG.md` heading, so
  getting one wrong breaks the release gate
- on a public remote, a force-push **does not reliably erase anything**:
  orphaned commits stay reachable by SHA, and anything already cloned or cached
  stays cloned and cached

**So history rewriting is not the tool for tidying.** It is the tool for
material that should never have been committed — the standard the **v0.1
corpus** met, and a design draft does not. For everything in this task, `git rm`
plus a commit is the honest operation: the file stops being in the repository,
and history keeps saying it was there, which is true.

## Whatever is decided

`CLAUDE.md`'s authoritative table has to stop claiming one status for the whole
directory. Either the categories get named there, or the directory stops holding
four kinds of thing — but the current table cannot survive either way.

## When this is done

Delete this file. It is a note about a job, and it has no reason to outlive it.

# compost — conversations to an addressable wiki

A local-first knowledge base for people who run many projects at once and need
to get back into one cheaply after weeks away.

You write in your editor and submit. Every paragraph, list item and todo gets a
permanent handle. You read it as a static site, click any block to copy a
reference to it, and write your next turn *about* that block. An agent reads the
same base, answers into the same conversation, and its answer is addressable
too. Closed Claude Code sessions can be imported whole, so past chats stop being
stranded.

**Status: v0.1.4.** The loop runs with a human and an agent in it. Artifact
generation — an agent writing a README or TODO from the conversations — is not
built yet.

---

## Install

Requires `conda`, plus `node` 18+ on your PATH for the djot reference parser.

```bash
conda env create -f environment.yml
conda activate knowledge-graph
pip install -e .
```

Verify: `compost --help`, `pandoc --version` (3.x), `npx @djot/djot --version`.

## Quickstart

```bash
compost init ~/my-project/kb        # a base per project
export KG_HOME=~/my-project/kb

compost new                         # opens $EDITOR; submits when you close it
compost serve                       # build the site and serve it on :8000
```

Open <http://localhost:8000>, click a block, and the reference lands on your
clipboard:

```
{#a3f9c2d1}
```

**Shift-click** a heading, a parent list item or a whole turn to copy its
subtree instead — hold Shift while hovering and the subtree highlights:

```
{#a3f9c2d1+++}
```

Paste it into your next turn. `compost` works out which conversation you are
replying to from the blocks you cite, so there is nothing else to copy. The
target grows a **Referenced by** section. That is the loop.

## Bringing an agent in

```bash
compost import ~/.claude/projects/<slug>/<session>.jsonl   # a past session
compost last                                               # hand a turn to an agent
```

Point the agent at `AGENTS.md` and the base. It reads `site/blocks.json` — the
whole corpus in one file, with the hashes it cannot compute itself. It never
needs this repository.

**An agent with its own interface answers there rather than submitting a turn.**
You import the round, and its answer becomes addressable that way. Two output
channels for one answer is worse than one, and the import is where the handles
come from regardless. `compost submit --author <who>` stays for you, and for an
agent that has nowhere else to write.

## Commands

| | |
|---|---|
| `compost init [dir]` | create a knowledge base |
| `compost new` | write a turn in `$EDITOR`; submits on exit |
| `compost submit <file>` | append an existing markdown file as a turn |
| `compost import <log>` | import a closed Claude Code session |
| `compost render` | build the static site and `blocks.json` |
| `compost check` | report dangling references and handle collisions |
| `compost serve [-p PORT]` | render, then serve on localhost |

`--author` records who wrote a turn; `-c` names the conversation when it cannot
be inferred. The base is found via `--root`, then `$KG_HOME`, then a `.kg`
marker in the current directory or any parent.

## What's on disk

```
raw/<conv>/<turn>.md      drafts exactly as written, frozen
raw/<conv>/<session>.jsonl  an imported session log, exactly as ingested
conversations/<conv>.dj   turns, appended; no block in one ever changes
artifacts/<name>.dj       documents, rewritten in place
site/                     generated HTML + blocks.json (disposable, gitignored)
.kg                       marker identifying the base root
```

The split is by **mutability, not authorship**. Either you or an agent can write
either kind. What protects you is that a conversation is append-only: nothing
already written can be altered, whoever wrote it. Authorship is recorded on each
turn as a djot attribute, so it lives in the file and therefore in git.

Keep your base in git. The `.dj` files are the source of truth; everything else
is derived and can be deleted.

## This repo is its own knowledge base

`compost` is developed inside the base it built. `conversations/`, `artifacts/` and
`raw/` sit at the repo root next to `src/`, and a `.kg` marker there means `compost`
resolves the base from anywhere in the tree with no `KG_HOME` set.

The documents you are reading are published into it:

```bash
compost artifact README.md      # republish after editing
compost render && compost serve      # read and comment on them at localhost:8000
```

**The `.md` file is the source; `artifacts/<name>.dj` is its canonized,
addressable form** — the same relationship `raw/` has to a conversation turn.
Edit the markdown, republish, and unchanged blocks keep their handles, so
comments written about them survive.

## Design

- [CLAUDE.md](CLAUDE.md) — what an agent loads first; the routing table
- [AGENTS.md](AGENTS.md) — how to read and write the base; an agent needs this
  and the base, not this repo
- `artifacts/state-of-play.dj` — **where the work actually stands.** Read it in
  the served site, or from `site/blocks.json`
- [DEVELOPMENT.md](DEVELOPMENT.md) — the code, the non-obvious parts, and where
  the next work is
- [TODO.md](TODO.md) — what is next
- [CHANGELOG.md](CHANGELOG.md) — history
- [archive/](archive/) — the v0.1 spec and the interviews that produced it.
  **Historical. Superseded. Do not follow it.**

The reasoning behind every decision is in `conversations/`, not in a spec.
A spec drifts; an immutable conversation cannot.

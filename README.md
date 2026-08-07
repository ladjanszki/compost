# kg — conversations to an addressable wiki

A local-first knowledge base for people who run many projects at once and need
to get back into one cheaply after weeks away.

You write in your editor and submit. Every paragraph, list item and todo gets a
permanent handle. You read it as a static site, click any block to copy a
reference to it, and write your next turn *about* that block. An agent reads the
same base, answers into the same conversation, and its answer is addressable
too. Closed Claude Code sessions can be imported whole, so past chats stop being
stranded.

**Status: v0.2.** The loop runs with a human and an agent in it. Artifact
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

Verify: `kg --help`, `pandoc --version` (3.x), `npx @djot/djot --version`.

## Quickstart

```bash
kg init ~/my-project/kb        # a base per project
export KG_HOME=~/my-project/kb

kg new                         # opens $EDITOR; submits when you close it
kg serve                       # build the site and serve it on :8000
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

Paste it into your next turn. `kg` works out which conversation you are
replying to from the blocks you cite, so there is nothing else to copy. The
target grows a **Referenced by** section. That is the loop.

## Bringing an agent in

```bash
kg import ~/.claude/projects/<slug>/<session>.jsonl   # a past session
kg submit reply.md --author claude                    # an agent's turn
```

Point the agent at `AGENTS.md` and the base. It reads `site/blocks.json` — the
whole corpus in one file, with the hashes it cannot compute itself — and submits
turns back. It never needs this repository.

## Commands

| | |
|---|---|
| `kg init [dir]` | create a knowledge base |
| `kg new` | write a turn in `$EDITOR`; submits on exit |
| `kg submit <file>` | append an existing markdown file as a turn |
| `kg import <log>` | import a closed Claude Code session |
| `kg render` | build the static site and `blocks.json` |
| `kg check` | report dangling references and handle collisions |
| `kg serve [-p PORT]` | render, then serve on localhost |

`--author` records who wrote a turn; `-c` names the conversation when it cannot
be inferred. The base is found via `--root`, then `$KG_HOME`, then a `.kg`
marker in the current directory or any parent.

## What's on disk

```
raw/<conv>/<turn>.md      drafts exactly as written, frozen
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

`kg` is developed inside the base it built. `conversations/`, `artifacts/` and
`raw/` sit at the repo root next to `src/`, and a `.kg` marker there means `kg`
resolves the base from anywhere in the tree with no `KG_HOME` set.

The documents you are reading are published into it:

```bash
kg artifact README.md      # republish after editing
kg render && kg serve      # read and comment on them at localhost:8000
```

**The `.md` file is the source; `artifacts/<name>.dj` is its canonized,
addressable form** — the same relationship `raw/` has to a conversation turn.
Edit the markdown, republish, and unchanged blocks keep their handles, so
comments written about them survive.

## Design

- [AGENTS.md](AGENTS.md) — hand this to an agent; it needs nothing else
- [mvp-design.md](mvp-design.md) — what this is and why
- [DEVELOPMENT.md](DEVELOPMENT.md) — the code, the non-obvious parts, and where
  the next work is
- [TODO.md](TODO.md) — what is next, by version
- [CHANGELOG.md](CHANGELOG.md) — history, including the architectures this
  replaced

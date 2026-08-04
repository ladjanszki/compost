# kg — notes to an addressable wiki

A local-first knowledge store for people who run many projects at once and need
to get back into one cheaply after weeks away.

You write notes in your editor and submit them. Every paragraph, list item and
todo gets a permanent id. You read them as a static site, click any block to
copy a reference to it, and write your next note *about* that block. Over time
an agent generates a wiki from those notes, and every line it writes cites the
note it came from.

**Status: v0.1.** The mechanical loop works end to end and involves no LLM.
Wiki generation is not built yet — see [mvp-design.md](mvp-design.md) §8.1.

---

## Install

Requires `conda`, plus `node` 18+ on your PATH for the djot reference parser.

```bash
conda env create -f environment.yml
conda activate knowledge-graph
pip install -e .
```

Verify:

```bash
kg --help
pandoc --version      # 3.x, installed into the env
npx @djot/djot --version
```

## Quickstart

```bash
kg init ~/knowledge          # create a knowledge base
export KG_HOME=~/knowledge   # so kg works from any directory

kg new                       # opens $EDITOR; submits when you close it
kg serve                     # build the site and serve it on :8000
```

Open <http://localhost:8000>, click a block, and the reference lands on your
clipboard:

```
{#019fcc46-f469-7475-bc04-abd9f0070e8a:fa6ee1f1c297ee10}
```

**Shift-click** a heading or a parent list item to copy its whole subtree
instead — hold Shift while hovering and the subtree highlights so you can see
what you'll get:

```
{#019fcc46-f469-7475-bc04-abd9f0070e8a:fa6ee1f1c297ee10+++}
```

Paste that into your next note. When you submit it, the note it refers to grows
a **Referenced by** section linking back. That is the loop.

## Commands

| | |
|---|---|
| `kg init [dir]` | create a knowledge base (default: current directory) |
| `kg new` | write a note in `$EDITOR`; submits on exit |
| `kg submit <file>` | canonize an existing markdown file into the base |
| `kg render` | build the static site |
| `kg serve [-p PORT]` | render, then serve on localhost |

The base is located via `--root`, then `$KG_HOME`, then a `.kg` marker in the
current directory or any parent — so `kg` works from anywhere.

## What's on disk

```
raw/<uuid>.md      the draft exactly as you wrote it, frozen
notes/<uuid>.dj    canonized and addressable, frozen
site/              generated HTML (disposable, gitignored)
.kg                marker identifying the base root
```

Both files share a uuid, so "what did I actually write" is a filename lookup.
Notes are **immutable**: submitting freezes them. You react to a note by
writing another note, never by editing it.

Keep your knowledge base in git. The `.dj` files are the source of truth;
everything else is derived and can be deleted.

## Design

- [mvp-design.md](mvp-design.md) — what this is and why, including what is
  deliberately deferred (§12) and what is still open (§13)
- [DEVELOPMENT.md](DEVELOPMENT.md) — the code, the non-obvious parts, and where
  the next work is
- [CHANGELOG.md](CHANGELOG.md) — history, including the v0 architecture this
  replaced

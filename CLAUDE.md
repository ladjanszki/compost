# kg — start here

This repo is a tool **and its own knowledge base**. Both matter, and the
knowledge base is where the reasoning lives.

## Do this first

```bash
kg render          # rebuilds site/ and site/blocks.json
kg check           # must report 0 dangling, 0 collisions
```

Then read, in this order:

1. **`site/blocks.json`** — the whole corpus, one record per block: handle, hash,
   type, source, author, text, citations. This is how you read *and cite* the
   base; the hash is not in the `.dj` files, so nothing else lets you build a
   reference.
2. **`artifacts/state-of-play.dj`** — where the work actually stands, written
   for you. Start here for "what should I do next".
3. **`AGENTS.md`** — how to read and write the base. Short. Read it before
   submitting anything.

## What is authoritative

| Source | Status |
|---|---|
| `conversations/` | **why** every decision was made. Immutable, so it cannot drift. |
| `artifacts/` | **what is true now.** Rewritten as understanding improves. |
| `README.md`, `DEVELOPMENT.md`, `TODO.md`, `CHANGELOG.md` | the markdown sources for four of those artifacts. Edit these, then `kg artifact <file>.md`. |
| `archive/` | **historical. Not current. Do not follow it.** |

Code comments cite `mvp-design.md` section numbers. That document is archived —
the citations are historical and its content is superseded.

## The rules that bite

- **Work on `main`, tag each version.** No feature branches; see
  `DEVELOPMENT.md` Conventions for why this was learned the hard way.
- **Scan parsed blocks, never raw file text.** References are escaped on disk,
  handles inside code blocks are not citations, and this corpus *quotes its own
  syntax* in its own content. This rule has been violated three times and cost
  something every time.
- **Render-time changes are free; canonization-time changes are one-way.**
  Ask which a change is before building it. `DEVELOPMENT.md` explains the
  difference and it decides urgency more than anything else.
- **Republish after editing a doc** (`kg artifact README.md`), or the served
  copy drifts from the file.
- **Never rewrite a conversation.** They are append-only.

## Working with the human

They write in nvim, click blocks in the served HTML to copy handles, and reply
by citing them. When they paste a `{#handle}`, resolve it from `blocks.json`
before answering. Reply as a turn:

```bash
kg submit reply.md --author claude
```

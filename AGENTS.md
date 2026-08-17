# Using a kgb knowledge base

You are working with a project knowledge base built by `kgb`. This file is all
you need — do not read the tool's source to use it.

**Read the base, not the repo's markdown.** `site/blocks.json` is the corpus;
`artifacts/state-of-play.dj` is where the work stands; `conversations/` holds
why every decision was made. Markdown files at the repo root are *sources* for
four of the artifacts, so reading both is reading the same thing twice. Anything
under `archive/` is historical and must not be followed.

A base is a directory containing `.kg`, `conversations/`, `artifacts/`, `raw/`
and `site/`. Find it with `--root <dir>` or `$KG_HOME`, or by running `kgb` from
inside it.

---

## The one thing to understand

Every block — paragraph, heading, list item, todo — has an **8-hex handle**.
References look like this:

```
{#a3f9c2d1}        that block
{#a3f9c2d1+++}     that block and everything under it
{#a3f9c2d1@7f2e}   that block at a specific version (artifacts only)
```

Handles are permanent. A block, once written, never changes, so a reference
written today resolves forever.

---

## Reading

**Start with `site/blocks.json`.** It is the whole corpus in one file, written
by `kgb render`, one record per block:

```json
{"handle": "43942d3c", "hash": "ce617538c3b715e2", "type": "list_item",
 "source": "019fd7b7-....dj", "kind": "conversation", "author": "human",
 "text": "T1 — the scope reframe...", "cites": ["443feb1e"]}
```

- resolve a handle → find the record whose `handle` matches
- what cites this block → records whose `cites` contains it
- who wrote it → `author`
- the whole thread → every record with the same `source`, in order

At a few hundred blocks, reading `blocks.json` *is* context assembly. There is
no retrieval layer and none is wanted yet.

You can also read `conversations/*.dj` directly — they are plain text with
`{#handle}` on the line above each block — but the **hash is not in the file**.
It is SHA-256 over the parsed block, so `blocks.json` is the only place to get
one without running the tool.

## Writing

**If you are an agent with your own interface — a Claude Code session or
similar — answer there. Do not submit your reply as a turn.** The human imports
the round afterwards, which makes your answer addressable anyway. Submitting as
well produces two copies of one answer in two places, and it is the human who
has to read both.

What does not change: resolve every handle before you answer, and cite handles
in your answer. The import turns those into real citations, which is where the
value was all along.

Submit a turn only when you are asked to, or when you have no interface of your
own. You never write `.dj` files by hand.

```bash
kgb submit reply.md --author claude          # thread inferred from citations
kgb submit reply.md --author claude -c <id>  # or name the conversation
```

The conversation is inferred from the blocks your draft cites, because a reply
is normally *about* something. Cite blocks from two different conversations and
it will refuse rather than guess.

Then `kgb render` to rebuild the site and `blocks.json`.

### Rules

1. **Cite real handles.** Copy them from `blocks.json`; never invent one. A note
   is immutable, so a wrong reference can never be corrected in place — it stays
   in the corpus forever. `kgb check` reports them, but the point is not to
   create them.
2. **One idea per block.** Whatever should be referenceable on its own gets its
   own paragraph or list item. This is the single biggest thing you can do to
   make a note useful later.
3. **Never edit a conversation file.** They are append-only. React by submitting
   a new turn.
4. **Say `--author`** on any turn you do submit. Turns record who wrote them.
   Never submit as `human`.

## Commands

| | |
|---|---|
| `kgb render` | rebuild `site/` and `site/blocks.json` |
| `kgb check` | dangling references and handle collisions; non-zero on failure |
| `kgb submit <file> --author <who>` | append a turn |
| `kgb import <session.jsonl>` | import a closed Claude Code session |
| `kgb serve` | render, then serve on localhost |

## The two content types

**Conversations** (`conversations/<uuid>.dj`) are append-only. Turns are fenced
divs carrying their author:

```
{#8e3dc827 .turn author="human" turn="019fd7b7-..."}
:::
{#bf8c7af8}
# What to do with this note?
:::
```

Either party writes them. Nothing already written ever changes.

**Artifacts** (`artifacts/<name>.dj`) are documents — a README, a TODO, a
design — rewritten in place as understanding improves. **Regenerating one must
preserve the handles of unchanged blocks**, or every reference into it is
orphaned. That machinery does not exist yet, so do not rewrite an artifact
unless you have been asked to and know how the handles will be carried across.

## What not to do

- Do not put a block's authorship, or anything else you want kept, in
  `blocks.json`. It is regenerated on every render. Durable data lives in the
  `.dj` files, which are the source of truth and are in git.
- Do not use `kgb new` — it opens an editor.
- Do not reformat or "tidy" existing files.

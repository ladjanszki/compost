# Migrating the v0.1 corpus

*Status: for discussion. Nothing here is built.*

v0.2 replaced the tool. The corpus it was built for is still on disk and
v0.2 cannot read it. This document is about closing that gap: what the old base
holds, what constrains how it can be moved, and the routes available. The
numbers are measured, not estimated.

## Why it matters more than it looks

The tool being thrown away was the easy half. The corpus is 6,741 blocks with
159 of them cited by handle, and the reasoning behind every decision in v0.2
lives in it. Without a migration, v0.2 is a nicer program that knows nothing,
and every handle in `CLAUDE.md`, in `docs/`, in commit messages and in the
conversations themselves points at nothing.

## What exists

*The corpus described here was removed from this repository's history — it was
personal notes. It is kept privately, and every count below was measured while
it was still present. The paths are how it was laid out then, and how a
migration would expect to find it.*

| | count | notes |
|---|---|---|
| `conversations/*.dj` | 9 | canonized transcripts, handles assigned |
| `raw/<id>/*.jsonl` | 7 | the session logs behind them — **two conversations have none** |
| `artifacts/*.dj` | 14 | project documents, handles assigned |
| `raw/artifacts/*.md` | 7 | markdown sources for 7 of the 14 |
| `raw/<id>/*.md` | 19 | the human's submitted drafts |

**`graph.dj` has no markdown source anywhere** — it exists only as a canonized
`.dj`.

**The two conversations without a JSONL are not missing one.** Their ids are
UUIDv7 (`019fe816…`, `019ff180…` — version nibble `7`), minted by compost's own
`uuid6` dependency; all seven real session logs are UUIDv4. Their `raw/`
directories hold only submitted `.md` files, each with its own v7 id. Searching
`~/.claude` finds no log for either, and Claude Code only ever writes v4 ids.

So these are conversations compost *built* from submitted files, back when the
file channel and the session transcript were both in use for the same purpose.
Nothing was lost, and no route can give them session structure they never had.

The backup is verified: 49/49 files byte-identical in
`corpus-removed-before-v0_2/`, and `compost-full-history.bundle` restores 95
commits and 8 tags in a clean clone.

## The four measurements that decide this

**1. The `.dj` files bind handle to block with certainty.** Pandoc's djot reader
recovers **5,860 distinct ids** from them, because `{#xxxxxxxx}` on its own line
*is* djot attribute syntax. No parsing heuristic, no matching, no guessing.

**2. Re-deriving handles from `raw/` does not work.** Text-matching old handles
onto a fresh ingest of the same markdown recovers **103 of 217** on the
artifacts. Zero were matched *wrongly* — half simply do not match, because the
old canonization normalised text on the way to `.dj`. So the old `.dj` text and
a fresh ingest of its source are no longer the same string, and this route is
closed.

**3. Positional alignment does not work either.** The artifacts carry 236
top-level handles where a fresh ingest produces 549 citable nodes, and **0 of 7
documents match on count.** The old canonizer assigned handles to fewer things
than v0.2 makes nodes for.

**4. But the conversations carry an alignment key.** Every turn in a `.dj` is
`{#handle .turn author="human" turn="<uuid>"}`, and **1,449 of 1,455** of those
uuids exist as lines in the matching JSONL. Structure recovered from the `.dj`
by the djot reader: 1,460 `turn` Divs and 935 `tool-call` Divs.

### The fork, and 529 duplicated turns

`9bc18568` was forked from `a7d175f9`. All **529** of the parent's lines appear
in the fork with byte-identical content — 67% of the fork — and they carry the
**same line uuids** in both logs.

Importing both as they stand duplicates that entire prefix: 529 turns of
content as two sets of nodes with matching `content_hash` values and different
guids. That is the deferred re-import identity question arriving in the
migration rather than after it.

It also suggests its own answer. The log line `uuid` is already stored on every
turn as `params.uuid`, and it is stable across both logs, so an importer that
looked a turn up by it would make the fork and its parent *share* their common
prefix instead of copying it. That is the first concrete identity key this
corpus has offered, it costs one lookup, and it is worth deciding before the
migration rather than as a consequence of it.

### Four logs that were never imported

The project directory holds 11 session logs; `raw/` has 7. The unimported ones
are `155721f1` (75 lines), `d54085ed` (47), `8b6a710f` (633) and `44564a21`
(1807, and still being written — it is the session this document was drafted
in). Whether the migration is also the moment to take them in is a separate
choice from how the existing corpus moves.

## Route A — ingest the `.dj` files

Feed `conversations/*.dj` and `artifacts/*.dj` to the importer. Pandoc's djot
reader attaches every `{#handle}` as a block id, so handles arrive as data
rather than as a matching problem. `Div .turn` becomes a `turn` node,
`Div .tool-call` becomes a `toolcall`, and the block tree underneath is
whatever v0.2 makes of it.

- uniform: one path for all 9 conversations and all 14 artifacts
- handles are exact, with nothing to verify beyond a count
- the two file-only conversations survive, which matters because no other
  route can reconstruct what they never had
- `graph.dj` survives, which no other route manages

What it gives up: the `.dj` text is the *old* rendering, with the em dashes
already turned into `---` and handles already escaped as `\{#…\}`. And the
session facts that never reached the `.dj` — `tool_use_id` pairing, `replies_to`,
tool output as its own node, session metadata — are not recoverable from it.

## Route B — ingest the JSONL, align handles by turn uuid

Import the 7 available session logs with the v0.2 importer, giving full session
structure. Then, for each turn, find the same turn in the `.dj` by uuid and
transfer the old handles onto the corresponding blocks. Alignment within a
single turn is a small ordered set rather than a whole document, which is why
this is plausible where measurement 3 failed.

- full session fidelity for the 7 conversations that have logs
- the corpus arrives through exactly the path new conversations use

What it gives up: the two file-only conversations, which have no log to import
and must fall back to Route A — which means two of nine conversations have a different shape from the
rest, permanently. All 14 artifacts still need Route A regardless. And the
within-turn matching rule is a new thing that can be subtly wrong, where Route A
has nothing to get wrong.

## Route C — hybrid

Route B where a log exists, Route A everywhere else. Best fidelity, most code,
and a corpus with two shapes in it.

## What I would choose, and the reasoning to argue with

**Route A, for everything.**

The old corpus does not need to be a first-class session graph. It needs to be
**citable** — 159 live references have to keep resolving, and the reasoning has
to stay readable next to the decisions it produced. Route A delivers that with
no heuristic anywhere.

The session structure Route B recovers is *new capability applied backwards*.
The v0.2 importer already handles new conversations properly, and `raw/` stays
in `storage/` for the day someone wants to re-derive more from the logs. Doing
that archaeology now buys fidelity in exactly the nine conversations least
likely to need it, at the cost of a matching rule that could silently
mis-assign a handle in an immutable corpus.

The lossy text is a real cost and it should be stated plainly: those em dashes
are already gone, and Route A makes that permanent. But the alternative is not
"recover them" — it is "recover them and lose the handles", because measurement
2 closes the door on having both.

**Mark migrated nodes.** A `migrated: true` param, or a separate layer, so that
a conversation missing `replies_to` and `tooloutput` reads as *"this came from
v0.1"* rather than as an importer bug. Whatever we choose, the absence should be
explicable from the record itself.

## The handle dictionary

Built **first**, before anything is rewritten, because the `.dj` files are the
only evidence the old handles ever existed.

Old 8-hex handle → new UUIDv4. No prose, so it can be committed and outlive any
single backup folder. Under Route A it is a by-product: the importer knows both
ids as it assigns them.

Its purpose is not runtime resolution — that is the point of rewriting the
citations. It is so the *archived* copies can later be updated to stay
internally consistent, and so any handle quoted outside the base can be traced.

## Rewriting citations, in the same pass

A line that is exactly `{#xxxxxxxx}` is an **assignment** and becomes the
block's id. Every other occurrence is a **citation** and becomes
`[-](#<new-uuid>)`.

Doing both in one pass is what avoids a permanent side table: afterwards the
corpus resolves on its own. Roughly 2,071 inline citation occurrences are
affected; the old base reports 0 dangling, so every one has a known target.

This is the point where conversation text changes. The append-only rule survives
in the place it now lives: the pristine bytes are in the bundle and the backup,
and the migration is a *translation into a new store* rather than an edit of the
record.

## Verification

1. Every handle resolvable before the migration resolves after — the count is
   known, so this is exact rather than approximate.
2. `compost check` reports 0 problems.
3. Citation edge count matches the number of rewritten references.
4. Spot-compare rendered views: the migrated `default-djot` of a conversation
   against its old `.dj`, allowing for the syntax change.
5. Re-running the migration on the same input produces the same *structure* —
   guids differ, `content_hash` values do not.

## Deliberately not attempted

- **No recovery of the pre-canonization text.** Measurement 2 makes it a choice
  between the original prose and the handles, and the handles win.
- **No unification of `file` and `document` nodes** for paths that appear as
  both.
- **No re-derivation of session structure for the old conversations** beyond
  what the `.dj` carries — under Route A that means turns and tool calls, and
  not much else.

## Open questions

1. **Route A, B or C?** The recommendation above is Route A; the case against it
   is the lossy text and the missing session structure.
2. **What node type is a migrated conversation?** A `session` with `turn`
   children keeps it consistent with new imports. A plain `document` is simpler
   and admits that it is not really a session record any more.
3. **Do the archived copies get rewritten** to the new citation form, or stay as
   the record of what was originally written? The bundle preserves the pristine
   bytes either way.
4. **What happens to handles cited outside the base** — in `CLAUDE.md`, `docs/`,
   commit messages? They become stale text pointing at nothing. Rewrite them
   from the dictionary, or accept them as historical.
5. **Does the migration run once and get deleted, or stay as a command?** Once is
   honest; a command is testable.
6. **Does the fork share its parent's turns or duplicate them?** Keying turn
   identity on the log line uuid makes them share, and answers re-import
   identity for transcripts at the same time.
7. **Do the four unimported logs come in with the migration** or separately?

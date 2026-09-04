# Total mapping

**Status: being decided.** Written 2026-09-04, out of the v0.2.13 hash design.
If it survives review it stops being a design document and becomes part of the
whitepaper — either as a sixteenth principle or as the enforcement half of
principle 4 — and this file is deleted.

---

## 1. The question that turned out to be wrong

v0.2.13 was blocked on a table: 59 params, one column, *is this content?* The
answer would decide what goes into `content_hash`, per node type, forever.

The table cannot be filled in. Not because the judgements are hard — some are,
most are not — but because there will be another table. cstlib will bring
dozens of node types. So will a graphviz importer, and a filesystem importer,
and whatever comes after those. A design that needs one discretionary decision
per param per type per importer does not have a fixed cost; it has a cost that
grows with every graph the tool learns to hold, and each of those decisions is
made once, silently, by whoever happened to be writing that importer.

The way out was to notice that **the mapping already answers it**. When
`session.py` reads a `tool_use` block and writes

```python
b.node("toolcall", {"name": …, "tool_use_id": …, "input": …})
```

it has already decided what that thing is made of. That decision is in code,
it was reviewed, it is under test. Asking a second time — in a table, in a
schema annotation — is asking the same question in a worse place.

So: **the code is the whitelist.** The hash covers the record. To change what
counts, change the mapping, and the hash changes because you are genuinely
storing something different.

## 2. The hole in that, and what closes it

The rule has a hole, and it is the reason this document exists.

*"Hash the record"* and *"hash the incoming object"* are only the same statement
if the record holds everything the incoming object held. Where the mapping
drops a key, they diverge — and the divergence is invisible, because the
dropped key is not in the record to be missed.

We found three, measured across the corpus and fixtures:

| type | dropped key | occurrences |
|---|---|---|
| `thinking` | `signature` | 492 |
| `toolcall` | `caller` | 902 |
| `tooloutput` | keys inside a list-shaped `content` | 2 |

The first one had a visible consequence: every empty `thinking` node in the base
hashed identically, 491 into 1, because the only thing distinguishing them was
the field the mapping threw away. Nobody noticed for four minor versions. It
surfaced by accident, while measuring something else.

**The fix is not a better hash.** It is a mapping that does not drop things.

> **Total mapping.** For every object an importer reads, everything that object
> held is recoverable from what the importer wrote.

If that holds, hashing the record *is* hashing the source, by construction. The
fork closes. There is nothing left to decide per param.

## 3. Why this is the right question to ask an importer author

Compare the two questions a new importer's author can be asked.

**"Is this param content?"** is a judgement. It needs context the author may not
have, it can be answered wrongly in a way that looks fine, and when it is
answered wrongly the failure is a *false positive* — two different things
declared the same. That is silent, it merges, and anything downstream that acted
on it cannot be un-acted.

**"Where did this key go?"** is bookkeeping. It has exactly one correct answer,
the author is holding the object when they answer it, and a machine can check
it. When it is answered wrongly the failure is a test failure, at the moment the
mistake is made, naming the importer and the key.

That is the whole trade, and it is why this scales to cstlib and graphviz and
the filesystem while the table does not. **The thought still goes into designing
the mapping** — it just goes in as structure rather than as annotation, and it
is checked rather than trusted.

## 4. What "recoverable" has to mean, and where the boundary really is

The weak reading of totality is *every key was read*. That reading is useless: a
mapping that writes `params["everything"] = str(obj)` reads every key and tells
you nothing.

The strong reading is *the object can be rebuilt from the node*. That is a round
trip, and it is the shape this project already uses twice —
`records_to_ast(ast_to_records(ast)) == ast` and
`records_to_session(session_to_records(lines)) == lines`.

But some digestors do not map an object to a node. They **parse** it. A `text`
block's markdown becomes a tree of `Para`, `BulletList` and `CodeBlock` nodes,
and that cannot round-trip: re-serialising markdown from a pandoc AST is not
byte-exact, and `docs/decisions.md` records three defects that make it
deliberately not so.

**The first version of this document called that a second kind of mapping** —
"interpretive" — and proposed that importers declare which kind each of theirs
was. That was wrong, and it was wrong in a way worth recording: it turned a
structural problem into a list of exceptions, and an exception list is a table
restated beside the code, which is the thing §1 exists to remove.

### The digestion is recursive, and it should say so

A digestor that meets content it does not own **delegates to the digestor that
does**, explicitly, and the delegated input is **stored as a blob** exactly like
any other digestor input. Then there is one rule and no kinds:

> Every digestor's input is stored as a blob. Every key of that input is a
> param, the node type, a child, or delegated to a named digestor — whose input
> is itself a blob.

Totality is then **compositional**: each digestor is total on its own format,
delegation composes them, and the pipeline is total by induction. Nothing
declares a kind, because there is only one.

**The irreversibility does not vanish — it is relocated to a named boundary,
with the input preserved beside it.** Markdown text to pandoc AST is still
lossy. What changes is that the bytes are in `storage/`, addressed by a
`derived_from` edge, which is the edge that already exists for exactly this
purpose. Delegation gets the same representation as top-level ingestion rather
than a parallel one.

### What this costs, measured

**549 delegated markdown inputs across the seven corpus sessions, 376 KB against
10.8 MB of transcript — 3.5%.** Median input 158 bytes. One blob node and one
`derived_from` edge each.

### And it names a defect that already exists

`session.py` does not call the text digestor. It reimplements it:

| | `src/routes.py` | `src/session.py` |
|---|---|---|
| reader flags | `READER`, line 39 | `READER`, line 67 — the same string, a second copy |
| text to blocks | `_ast_of_text`, line 58 | `_md_blocks`, line 73 |
| blocks to records | `R.ast_to_records` | `R._block` — a private function |

Two constants holding one meaning, in a codebase where `docs/decisions.md`
records that every one of those flags is load-bearing and measured. Change the
notes reader and the transcript reader diverges silently.

### One consequence to state out loud

`storage/` stops meaning *"the files the human imported"* and starts meaning
*"every digestor input"*. That is a clarification rather than a change —
`CLAUDE.md`'s *"sources are immutable, and storage is a blob store"* already
reads that way — but it should be said deliberately rather than discovered.

## 5. What total mapping makes true

1. **`record_hash` and a source hash are the same number.** The v0.2.13 fork
   disappears, and the hash can be defined over the record — which is the only
   definition that also works for nodes with no incoming object at all
   (`session`, `blob`, `alias`, anything a layer mints).
2. **`check` can verify hashes.** Recomputing `H([type, params, content])` from
   records on disk needs no source file and no importer version. A hash over the
   incoming object would need both.
3. **Digest-everything gets enforced at the node.** Today it is asserted at the
   *file* — `records_to_session(...) == lines` passes even with `signature`
   dropped, because `log` carries it. The file is reconstructible while the node
   is impoverished, and only the first is currently tested.
4. **New importers need no judgement.** cstlib's author is never asked whether a
   CST node's byte offset is content.

## 6. What it does not claim

- **Not that the interpretation is good.** Totality says nothing was lost. It
  says nothing about whether `toolcall` is the right shape, or `author` the
  right name. Those stay design questions.
- **Not that `record_hash` is a value hash.** It answers *is this the same
  record*. Two genuinely identical empty thinking blocks will hash differently
  once `signature` is stored — correctly, under that reading. *Is this the same
  value* is a query-time projection and belongs in a layer.
- **Not a constraint on synthesized nodes.** `session`, `blob`, `file`,
  `display_name` are minted from several inputs or from none. Totality is
  vacuous for them, which is the right answer rather than a gap.
- **Not a bar on derived params** — but there is a separate rule they need,
  and it is not part of totality. A param the importer computed was never in
  the source, so totality has no opinion on it. It still has to obey:

  > A derived param may be a function of the node itself. It may never be a
  > function of the node's subtree.

  `empty` on `thinking` is `f(text)`: stable forever. `lines` on `session` is
  `f(children)`: it moves every time the tree grows, and it is exactly why a
  re-ingested transcript's root failed to match itself. Measured on
  `session-04.jsonl`, truncated to 70% and re-read — **with `lines`, the
  identical prefix is 0 of 2,306 nodes; without it, 2,306 of 2,306, 100.00%.**
  A derived param that reads the subtree defeats alignment by construction,
  because alignment is the thing that walks the subtree.

  `lines` is also redundant: the session's children *are* the lines. It is
  denormalised state duplicating a fact the graph already holds, and it is
  deleted in v0.2.13.

## 7. What it costs

Params get bigger. `caller` will be stored on 902 `toolcall` nodes in this
corpus and every one of them says `{"type": "direct"}`. That is the
digest-everything rule taking its stated price, and the stated answer applies:
volume is not the objection, this is not the main way the base is read, and a
field that distinguishes nothing today is exactly the field that will
distinguish something the first time a call is not direct.

Storing `signature` also makes every empty `thinking` node distinct. Whether
that is right depends on whether a signature is content — and under
`record_hash` the question does not arise, because `record_hash` is not
claiming they are different *values*.

## 8. How it is tested

A property, in the `tests/test_sabotage.py` idiom, made to fail on purpose
before it is trusted:

> For every object a digestor reads, every key is accounted for — promoted to a
> param, consumed as the node type, descended into as children, or delegated to
> a named digestor whose input is stored. A key that is none of these fails the
> test, naming the digestor, the object type and the key.

Sabotage: delete `"signature"` from the `thinking` mapping and the suite must go
red. It currently stays green, which is the whole point.

**All three known violations are structural** — `signature`, `caller` and the
list-shaped `tool_result.content` are every one of them a straight key-drop. So
the test catches all three before delegation exists, which is why v0.2.13 can
take the hashes and v0.2.14 the recursion, with no rework between them.

## 9. Open

Three of the four questions this document originally asked were about how a
mapping declares its kind. Delegation removed the kinds, so it removed the
questions. What is left:

1. **Is this a new principle, or the enforcement of principle 4?** Principle 4
   is *views may filter, importers may not*. This is what makes that checkable
   rather than aspirational. Either framing works; the whitepaper should pick
   one deliberately.
2. **What does a delegated blob's `original_name` say?** A fragment lifted out
   of a transcript never had a filename. Null, or something synthesised from the
   turn it came from. Small, but it is a param on every one of the 549.
3. **Does `tooloutput`'s list-shaped `content` delegate, or is it structural?**
   `_result_text` flattens a list of dicts to joined text. Two occurrences in
   the whole corpus. Under delegation it is probably structural — the list is
   stored whole and nothing parses it — which would retire the question.

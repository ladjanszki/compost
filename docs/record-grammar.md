# The record grammar — schema 1

**What a record is allowed to be**, exhaustively, as the program actually
writes and validates it today. This is the normative companion to
`docs/record-format.md`: that document argues *why* the node and edge design is
shaped this way, this one states *what is legal*. Where they disagree, this one
is wrong and should be corrected against the code — every table below was
derived from `src/` and from digesting `tests/fixtures/`, not from memory.

Everything here describes **schema 1**, which is the schema compost has always
written. Schema 1 is not new behaviour; it is the first version *number* given
to behaviour that already existed.

---

## 1. `schema_version`

> **Status: specified here, not yet written.** No code emits this field today.
> It lands in v0.2.4 (`docs/plan-v0.2.4.md`, step 1). Everything else in this
> document describes records the program writes right now; this section alone
> describes one it is about to. The "absent means 1" rule below is what makes
> that gap harmless.

### The field

```json
{"record": "node", "schema_version": 1, "guid": "…", "type": "Para", …}
```

**On every record**, not on a file and not on the base. Three reasons, in order
of weight:

1. **Files carry no meaning.** Graph filenames are minted uuids and load order
   cannot change the result (`CLAUDE.md`). A per-file header would put meaning
   into how records are grouped into files, which is exactly the property this
   base refuses to have.
2. **It survives regrouping.** `Store.load()` concatenates and deduplicates by
   canonical bytes (`src/store.py:159`), so records move between files freely.
   A field on the record moves with it; a header does not.
3. **It makes migration granular.** Schema 2 records can sit beside schema 1
   records in one base, and a migration rewrites only the records whose shape
   actually changed. A base-wide version forces an all-or-nothing rewrite.

**Measured cost: 4.4%.** Over the 767 records the fixtures produce (349,244
bytes, mean 455 B/record), `"schema_version":1,` adds 20 bytes each — 15,340
bytes. This is the cheapest of the three options and the least clever.

### Absent means 1

**Reading:** a record without `schema_version` is schema 1. Every record ever
written by compost conforms to the grammar below, so this is a definition
rather than a guess, and no existing base needs rewriting.

**Writing:** the field is required. New records carry it.

That asymmetry is the whole migration: there isn't one.

### When the number bumps

**Bump** when a record that was valid becomes invalid, or when a key that
existed changes meaning or type:

- a key is added to, removed from, or renamed on a record form
- an existing key's type or interpretation changes
- an existing node or edge type's required params change

**Do not bump** for additions that leave every existing record valid:

- a new node type, a new edge type, a new layer
- a new *optional* key on an existing form

By that rule the planned v0.2.4 work — the `layer` and `handle` node types, the
`by` field on generated edges, the `alias` and `citation` layers — is **all
additive, and schema stays 1.** A version that increments every release carries
no information; this one is meant to be readable years later.

---

## 2. The record

Every line of every `.compost/graph/**/*.jsonl` file is one JSON object with a
`record` key that is either `"node"` or `"edge"`. There is no other form, no
header line, and no envelope.

```
record   ::= node | edge

node     ::= { "record": "node"
             , "schema_version": 1
             , "guid":   GUID
             , "type":   NODE_TYPE
             , "params": OBJECT        ; optional, omitted when empty
             , "content": ARRAY        ; optional, pandoc inlines
             , "content_hash": SHA256  ; present iff required — see §5.9
             }

edge     ::= { "record": "edge"
             , "schema_version": 1
             , "guid":   GUID
             , "layer":  LAYER
             , "type":   EDGE_TYPE
             , "source": GUID
             , "destination": GUID
             }

GUID     ::= [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}
```

`GUID` is a UUIDv4 in every case. Nothing derives a guid from content, and
nothing derives one guid from another — including the two names one source
carries: a document's guid and its blob's storage name are minted separately
and **must not** be derivable from each other.

A **handle** is the whole guid: `HANDLE_LEN = 36` (`src/records.py:42`). A
prefix of a guid is not a handle and resolves to nothing.

`content` holds pandoc **inline** elements verbatim, as read. Inlines are never
decomposed into records — the addressable unit is the block.

`params` is an **open object**. Its keys per node type are catalogued in §3, but
the grammar does not close it: a route may store anything the source said, and
"digest everything, filter at query time" depends on that openness.

---

## 3. Node types

### 3.1 Pandoc block constructors

One node per block, from `src/records.py:_block` and its helpers. `content`
means pandoc inlines are carried on the record; `children` means the node's
content is other nodes, reached by `contains`.

| type | params | body |
|---|---|---|
| `Plain` | — | content |
| `Para` | — | content |
| `LineBlock` | — | content |
| `Header` | `level`, `attr` | content |
| `CodeBlock` | `attr`, `text` | — (text is in params) |
| `RawBlock` | `format`, `text` | — (text is in params) |
| `HorizontalRule` | — | — |
| `BlockQuote` | — | children |
| `Div` | `attr` | children |
| `Figure` | `attr` | children: `Caption`, then blocks |
| `BulletList` | — | children: `ListItem` |
| `OrderedList` | `list_attributes` | children: `ListItem` |
| `ListItem` | `wrap` *(collapsed form only)* | content **or** children |
| `DefinitionList` | — | children: `DefinitionTerm` |
| `DefinitionTerm` | — | content (the term), children: `DefinitionItem` |
| `DefinitionItem` | — | children |
| `Table` | `attr`, `colspecs` | children: `Caption`, `TableHead`, `TableBody`…, `TableFoot` |
| `Caption` | `short` *(when non-null)* | children |
| `TableHead` | `attr` | children: `Row` |
| `TableBody` | `attr`, `row_head_columns`, `intermediate_rows` | children: `Row` |
| `TableFoot` | `attr` | children: `Row` |
| `Row` | `attr` | children: `Cell` |
| `Cell` | `attr`, `align`, `rowspan`, `colspan` | children |

**`ListItem` has two forms.** An item holding exactly one `Plain` or `Para`
collapses into the `ListItem` itself and carries `wrap` naming which one it was
— 89% of items do. `wrap` is not decoration: `Plain`-versus-`Para` is precisely
how pandoc encodes list tightness, so dropping it would turn every tight list
loose. The other form has no params and holds children.

**An unmapped block constructor raises.** `_block` ends in
`NotImplementedError`, deliberately: three separate data-loss bugs in this
project's history were all a missing branch failing *silently*.

### 3.2 Transcript types

From `src/session.py`. These are compost's own inventions; no pandoc equivalent
exists, which is the recorded reason views of them are format-bound
(`TODO.md`, *Output portability*).

| type | params | body |
|---|---|---|
| `session` | `source`, `session_id`, `version`, `lines`, `route`, `agent`? | children: `turn`, `logline` |
| `turn` | `author`, `timestamp`, `uuid`, `log` | children: blocks, `thinking`, `toolcall`, `tooloutput`, `contentblock` |
| `logline` | `line_type`, `uuid`, `timestamp`, `log` | — |
| `thinking` | `text`, `empty` | — |
| `toolcall` | `name`, `input`, `tool_use_id` | children: `tooloutput` |
| `tooloutput` | `text`, `is_error`, `tool_use_id` | — |
| `contentblock` | `block_type`, `block` | — |

Four things this table is load-bearing about:

- **`params["log"]` is the whole original line**, on `turn` and `logline` alike.
  It is what makes `records_to_session(session_to_records(lines)) == lines`
  exact. A message's text is therefore held twice — raw in `log`, parsed as
  blocks — and that duplication is accepted on purpose: raw is the source,
  parsed is the derivation.
- **`logline` means kept but not understood.** A line type with no reading still
  becomes a node carrying everything it said. *Kept* and *understood* are
  different claims and the grammar keeps them apart.
- **`contentblock` is the same idea one level down**, for a message block whose
  type this importer has no branch for. It is *shown* in views, because the
  point of storing it is to notice it.
- **`author` is `human`, `assistant` or `envelope`.** A `user` line carrying only
  tool results is the transcript's envelope, not something a person typed. This
  is a statement about authorship and never about whether to keep the line.

### 3.3 Roots

| type | params |
|---|---|
| `document` | `meta`, `pandoc_api_version`, `source`, `route` |
| `session` | see §3.2 |

`ROOT_TYPES = {"document", "session"}` (`src/records.py:29`). A root has **no**
`contains` parent. `route` is recorded here because it is the only node that
knows: every block below looks identical whether it arrived via `notes` or
`pandoc-ast`.

### 3.4 Entities

Nodes that belong to no containment tree at all —
`UNCONTAINED = {"file", "blob"}` (`src/records.py:34`). They are pointed at;
they are inside nothing.

| type | params |
|---|---|
| `file` | `path` — a path a session touched |
| `blob` | `original_name`, `stored_as`, `bytes_sha256`, `imported_at`, `route` |

**`file` and `blob` are not the same thing and are not to be merged.** A `file`
is a path some session mentioned; a `blob` is bytes that live in
`.compost/storage/`. When one path is both, a `represents` edge is the intended
join — nothing mints one yet.

**`stored_as` is the only way to reach a source's bytes.** It is
`GUID.EXT` with a *freshly minted* guid, unrelated to any other guid in the
record. Reconstructing a storage path from `params["source"]` is guessing, and
will guess wrong; `records.blob_of()` is the supported route.

---

## 4. Edge types, by layer

`layer` says which *kind of statement* an edge is making. Six exist, five of
them written by `digest`.

| layer | type | source → destination | written by |
|---|---|---|---|
| `pandoc-ast` | `contains` | container block → block | `records.ast_to_records` |
| `pandoc-ast` | `next` | block → next sibling block | " |
| `session` | `contains` | `session`/`turn`/`toolcall` → child | `session.py` |
| `session` | `next` | line → next line, **log order** | " |
| `session` | `touches` | `toolcall` → `file` | " |
| `claude-code` | `replies_to` | `turn` → `turn`, **reply order** | " |
| `ingestion` | `derived_from` | root → `blob` | `store._digest` |
| `agent` | `launched` | `toolcall` → `session` | `store._link_agents` |
| `citation` | `cites` | any node → any node | `records.citation_edges` |

**`next` and `replies_to` are both stored, deliberately.** `next` is log order
and is what regenerates the file; `replies_to` is the conversational truth. The
two diverge the moment a session has a sidechain, and storing only one means
guessing the other. Which of them a *view* should follow is still undecided
(`docs/decisions.md:136`).

**`cites` is defined and not yet minted.** `citation_edges()` exists and is
tested; nothing in `src/` calls it. See `docs/roadmap.md`, v0.2.4.

**A citation is a `Link` node in `content`, never text.** A code block holds
text with no inlines, so it contains no links and *cannot* contribute a
citation however often it quotes the syntax. That is a property of the format,
not a rule anyone has to remember — and the rule it replaces was broken three
times.

---

## 5. Invariants

The nine assertions `records.check()` makes over a whole loaded graph. **A view
of a graph that fails any of them is refused, not rendered.**

1. **No guid carries two different records.** Byte-identical duplicates are
   agreement and collapse silently in `load()`; a guid with two different bodies
   is a hard error and is never resolved by picking a winner.
2. **Every edge endpoint resolves** to a node present in the graph.
3. **Parent count.** A node in `UNCONTAINED` has zero `contains` parents; a node
   in `ROOT_TYPES` has zero; every other node has **exactly one**.
4. **A `session` is `launched` by at most one `toolcall`.**
5. **No cycle through `contains` ∪ `launched`.** Both are containment as far as
   rendering is concerned, and a cycle across the pair would loop a view.
6. **No cycle in `contains`** alone.
7. **The `next` chain over a node's children is a total order**: exactly one
   head, no cycle, no edge leaving the parent, and full coverage of the
   children.
8. **No two nodes share a handle.** Vacuous while `HANDLE_LEN == 36`, since a
   handle is the guid; it exists so that shortening handles cannot silently
   introduce collisions.
9. **`content_hash` is present exactly when required** — when the node has
   `content`, or its type is in `TEXT_IN_PARAMS` (`CodeBlock`, `RawBlock`).

`content_hash` is `sha256(canonical([type, params, content]))`, where
`canonical` is JSON with sorted keys, no spaces, and `ensure_ascii=False`.

---

## 6. Closed vocabularies

Three lists are closed in schema 1. Everything else is open.

**Layers** (§4): `pandoc-ast`, `session`, `claude-code`, `ingestion`, `agent`,
`citation`.

**Routes** — the named ways material enters a base: `notes`,
`claude-code-transcript`, `pandoc-ast`. **Nothing is inferred from a file
extension.** The suffix survives into `storage/` as a decoration for whoever
pulls the bytes back out, and nothing reads it.

**Authors** on a `turn`: `human`, `assistant`, `envelope`.

---

## 7. What the grammar deliberately does not say

- **What `params` may contain.** Open by design. A route stores everything its
  source said; deciding a field is noise at read time is a decision made once,
  silently, and unrecoverably.
- **What order records appear in.** None. Files are minted uuids, load order
  cannot change the result, and any tool that reads a filename to decide what a
  record means is repeating the suffix-routing mistake.
- **Which records are true.** The grammar constrains shape, not content. Two
  records may describe the same thing twice; the base records that both exist
  and, later, that they are related. Merging is a judgement, and a judgement made
  at import is made once and silently.
- **How anything renders.** `records_to_ast` must stay exactly reversible;
  handles, collapsing and decoration belong in `src/views.py`.

---

## 8. This document is verified, not remembered

**`tests/test_grammar.py` holds every table above against a real digest of
`tests/fixtures/`**, in both directions and on every run of `./tests/run.sh`.
The ground truth is a base the program actually wrote — a type the code *can*
emit but no fixture ever reaches has never been seen written, and a table entry
for it would be a guess.

Seven guarantees, each sabotage-verified:

1. Every node type in the base is documented here.
2. Every node type documented here is exercised by a fixture.
3. No node carries a param this document does not name.
4. Every `(layer, type)` edge pair in the base is documented here.
5. Every documented edge pair is exercised, except those on an explicit
   *not yet minted* list.
6. That list is still accurate — minting `cites` fails this check until §4 is
   updated to say so.
7. The assembled base passes `records.check()`.

Current coverage: **33 node types, 8 edge pairs, 372 nodes.** The one documented
edge pair not exercised is `citation` / `cites`, which nothing in `src/` mints
yet (`docs/roadmap.md`, v0.2.4).

Two fixtures exist for this and nothing else. Before them the fixtures reached
28 of the 33 types, and `CodeBlock`, `RawBlock`, `BlockQuote`, `Div` and
`contentblock` were documented from the code alone:

- **`tests/fixtures/grammar/all-constructors.md`** — one instance of every block
  constructor the `notes` reader emits. It is also swept by `test_records.py`,
  so it must stay a fixed point through pandoc as well.
- **`tests/fixtures/grammar/contentblock.jsonl`** — a transcript carrying a
  message block of an unknown type and a bare string where a block was expected,
  the two ways `contentblock` is reached. Its exact session round-trip is
  asserted here.

Four constructors are unreachable through any reader this project uses and
arrive as a hand-built AST via `--as=pandoc-ast`: `LineBlock`, `Figure`, `Table`
and `DefinitionList`, in `tests/fixtures/ast/unreachable-constructors.json`.

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

**Measured cost.** Over the 972 records the fixtures currently produce (401,357
bytes, mean 412 B), `"schema_version":1,` adds 20 bytes each — **+5.1%**. This is
the cheapest of the three options and the least clever.

That figure covers this field **alone**. The whole v0.2.4 record change —
`schema_version` everywhere plus `created_at`, `tool_version` and `content_hash`
on edges — costs **+27.1% overall and +78.8% on edges**, because three fields land
on a record whose mean size is 213 B. An earlier draft published the 5% and not
the 27%, which is the flattering half of a number in a project that measures
`-smart` to the percentage point.

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

By that rule the v0.2.4 work — the `alias` and `unresolved_citation` node
types, the `names` edge, and the `by`, `created_at`, `tool_version` and
`content_hash` fields on edges — is **all additive, and schema stays 1.** A
version that increments every release carries no information; this one is meant to
be readable years later.

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
             , "schema_version": 1     ; present, same as on a node
             , "guid":   GUID
             , "layer":  LAYER
             , "type":   EDGE_TYPE
             , "source": GUID
             , "destination": GUID
             , "by":     STRING        ; optional — which scheme wrote this
                                        ; edge; absent on structural edges
                                        ; (contains, next, derived_from,
                                        ; launched, touches, replies_to,
                                        ; responds_to), present on
                                        ; citation-layer edges
             , "created_at": TIMESTAMP ; present, ISO 8601 UTC
             , "tool_version": STRING  ; present, the writer's own version
             , "content_hash": SHA256  ; present — see §5, the edge form
             }

GUID     ::= [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}
```

`GUID` is a UUIDv4 in every case. Nothing derives a guid from content, and
nothing derives one guid from another — including the two names one source
carries: a document's guid and its blob's storage name are minted separately
and **must not** be derivable from each other.

A **handle** is the whole guid: `HANDLE_LEN = 36` (`src/records.py:51`). A
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
| `document` | `is_error`, `duration_api_ms`, `num_turns`, `stop_reason`, `session_id`, `total_cost_usd`, `usage`, `modelUsage`, `permission_denials`, `terminal_reason`, `fast_mode_state`, `fast_mode_disabled_reason`, `subtype`, `api_error_status`, `result`, `ttft_ms`, `ttft_stream_ms`, `time_to_request_ms`, `type`, `duration_ms`, `uuid` |

`ROOT_TYPES = {"document", "session"}` (`src/records.py:38`). A root has **no**
`contains` parent. `route` is recorded here because it is the only node that
knows: every block below looks identical whether it arrived via `notes` or
`pandoc-ast`.

**The third row is `--as=claude-code-response` (`src/routes._response`),
merged rather than replacing the first.** A `document` minted from a
`claude --print --output-format json` envelope carries every one of the
envelope's own keys in `params`, verbatim and unrenamed, *beside* the usual
`meta`/`pandoc_api_version`/`source`/`route` — CLAUDE.md's digest-everything
rule, applied to a source that happens to be JSON instead of a JSON-in-Markdown
file. `result` is kept twice on purpose: verbatim here as the source of truth,
and separately parsed into the document's own `contains` children exactly the
way a `notes` document's blocks are, so the answer is addressable the same way
any other paragraph is. Nothing is removed to make room for the second row —
open `params` (§2) is exactly what lets one node type answer to two shapes of
input.

**`params["uuid"]` is the envelope's own uuid, not this record's `guid`.**
Verbatim copying means one word names two different things on the same
record — looks like a bug, is not one. Renaming it on the way in would stop
this route being a faithful copy of what claude printed; leaving it means a
reader has to know which of the two it is asking for. `params["session_id"]`
is promoted the same way, verbatim, and is the join to a `claude-code-transcript`
digest of the same conversation, should a `duplicates` layer ever join them
(`docs/roadmap.md`, *Beyond this window*) — not built here.

### 3.4 Entities

Nodes that belong to no containment tree at all —
`UNCONTAINED = {"file", "blob", "alias", "unresolved_citation"}`
(`src/records.py:43`). They are pointed at; they are inside nothing.

| type | params |
|---|---|
| `file` | `path` — a path a session touched |
| `blob` | `original_name`, `stored_as`, `bytes_sha256`, `imported_at`, `route` |
| `alias` | `value`, `scheme` — a name that leads to another node |
| `unresolved_citation` | — (no params) |

**`file` and `blob` are not the same thing and are not to be merged.** A `file`
is a path some session mentioned; a `blob` is bytes that live in
`.compost/storage/`. When one path is both, a `represents` edge is the intended
join — nothing mints one yet.

**`stored_as` is the only way to reach a source's bytes.** It is
`GUID.EXT` with a *freshly minted* guid, unrelated to any other guid in the
record. Reconstructing a storage path from `params["source"]` is guessing, and
will guess wrong; `records.blob_of()` is the supported route.

**`alias` and `unresolved_citation` are the citation layer's naming
machinery** (`compost layer citation`, `src/layers.py`). A citation whose
target is not in the base cannot become an edge — a dangling endpoint fails
`check` and would take the whole graph down — so the layer mints an
`unresolved_citation` placeholder and an `alias` naming it, and points the
`cites` edge at the placeholder instead:

```json
{"type": "alias", "created_at": "…", "tool_version": "0.2.4",
 "params": {"value": "deadbeef-1111-…", "scheme": "uuid-link"}}

{"type": "unresolved_citation", "created_at": "…", "tool_version": "0.2.4"}
```

**Provenance is top-level on both, exactly as on an edge — never inside
`params`.** Neither type carries a `content_hash` (§5.9), so putting
`created_at`/`tool_version` in `params` would have worked for these two, but
it would set a precedent that breaks the first time a *hashed* node type
needs provenance, since node hashing is positional over
`[type, params, content]` and blind to anything else the record carries.
This is decided once, here; it does not apply to any other node type, whose
shape (§2, §3.1–3.3) is unchanged by this release.

**One alias and one placeholder per distinct unresolved value, per build.**
Two citations of the same missing handle in one run of `compost layer
citation` mint one placeholder and two `cites` edges into it. Running the
builder again mints a *second*, independent alias/placeholder pair — nothing
is deduplicated or reused across builds.

**Why the value lives on the alias, not on the placeholder.** `lookup`
resolves a guid, else an alias, and nothing else; putting a lookup-worthy
string on `unresolved_citation` itself would force `lookup` to know what that
type is, a type-specific exception in a mechanism that has none. An alias is
*any* name that leads to a node, and a placeholder is an ordinary thing to
name.

---

## 4. Edge types, by layer

`layer` says which *kind of statement* an edge is making. Nine exist, six of
them written by `digest`; `citation` is written by `compost layer citation`
(`src/layers.py`). Those two are the writers *this tool* ships — **not the only
things that may write records.** Any script or agent emitting valid JSONL under
`graph/` is an equal writer; `check` is the gate, not authorship. See
`docs/decisions.md`, "Anything may write records".

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
| `citation` | `cites` | any node → any node, or → `unresolved_citation` | `layers._citation` |
| `citation` | `names` | `alias` → the node it names | `layers._citation` |
| `conversation` | `responds_to` | response `document` → the `document`/`session` it answers | `routes._response` |
| `conversation` | `next` | a round → what follows it, note before its response and response before the next note | " |
| `conversation` | `next` | answered root → response `document`, **reading order** | `routes._response` |

**`conversation` is its own layer, not `citation`.** "This response answered
that note" is a different kind of fact from a link found in parsed text, and
keeping it apart is what lets either be reasoned about without the other. Both
edges are minted **structural**, at digest time, by the one route that knows
both guids — never by `layer`, and never carrying `by` (see §2): a citation may
legitimately dangle and gets a placeholder, but a `responds_to`/`next` endpoint
that resolves to nothing is a bug in whatever wrote the wrapper file, and
`store._digest` refuses the whole batch rather than writing it (§5, and
`docs/roadmap.md`, "the conversation loop").

**Neither edge is `contains`, and there is no container node joining the two
roots.** `check`'s parent count (§5.3) is counted from `contains` alone, so a
note and its response are two independent roots, each keeping its own page —
joining them with any other edge type needed no new machinery. A container
would have failed outright: `ROOT_TYPES` roots must have zero `contains`
parents, so a node holding both would be rejected by the very rule that makes
a root a root.

**`next` here reuses the type-name `next` from `pandoc-ast` and `session`,
deliberately, and is safe for the same reason both other uses already are:
`Graph._next` (`src/records.py:302`) keys the chain by *source* alone, with no
layer discriminator, and a root is never the source of a block-level or
line-level `next` edge — roots have no siblings in either of those chains. See
`docs/roadmap.md`'s *Risks accepted without mitigation*, "`Graph._next` is
layer-blind", which named `conversation` as the third user of this edge type
before it existed.**

**`next` and `replies_to` are both stored, deliberately.** `next` is log order
and is what regenerates the file; `replies_to` is the conversational truth. The
two diverge the moment a session has a sidechain, and storing only one means
guessing the other. Which of them a *view* should follow is still undecided
(`docs/decisions.md:136`).

**`names` is how an alias resolves.** Exactly one `names` edge leaves each
`alias` node, pointing at the node the alias's `params["value"]` stands for —
today always an `unresolved_citation`, since `uuid-link` is the only scheme
and it never mints an alias for a value that already resolves.

**A citation is a `Link` node in `content`, never text.** A code block holds
text with no inlines, so it contains no links and *cannot* contribute a
citation however often it quotes the syntax. That is a property of the format,
not a rule anyone has to remember — and the rule it replaces was broken three
times.

---

## 5. Invariants

The ten assertions `records.check()` makes over a whole loaded graph. **A view
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
9. **`content_hash` is present exactly when required** — this assertion is about
   **nodes only**: present when the node has `content`, or its type is in
   `TEXT_IN_PARAMS` (`CodeBlock`, `RawBlock`); absent otherwise. Edges are not
   inspected by it.
10. **`schema_version`, when present, is not greater than the one this tool
    writes.** Absent means 1 by definition, so this can never fire on an
    existing base; it fires the first time a newer tool's records are loaded
    by an older one — the only reason the field is read as well as written.

### The two `content_hash` functions

They share a field name and are **not comparable**. A query grouping by
`content_hash` across record kinds is comparing nothing.

| | node | edge |
|---|---|---|
| input | `[type, params, content]` | the record minus a skip list |
| shape | a positional **array** | an **object** |
| excludes | `record`, `guid` — by not being in the array | `record`, `guid`, `schema_version`, `content_hash`, `created_at`, `tool_version` |
| present | only when the node has content | always |

Both are `sha256(canonical(…))`, where `canonical` is JSON with sorted keys, no
spaces, and `ensure_ascii=False`.

The edge form excludes identity **and provenance** deliberately: a hash must say
what the edge *claims*, never when or by what it was written, or the same fact
rebuilt tomorrow would not match the one written today — which is the only thing
the hash is for. See `docs/decisions.md`.

**Neither reaches everything.** Transcript node types, `alias` and
`unresolved_citation` carry no hash at all; and an edge pointing at a placeholder
hashes differently on every build, because the placeholder's guid is fresh each
time. `content_hash` is evidence for a future dedup design, not a mechanism
anything acts on.

---

## 6. Closed vocabularies

Four lists are closed in schema 1. Everything else is open.

**Layers** (§4): `pandoc-ast`, `session`, `claude-code`, `ingestion`, `agent`,
`citation`, `conversation`.

**Routes** — the named ways material enters a base: `notes`,
`claude-code-transcript`, `pandoc-ast`, `claude-code-response`. **Nothing is
inferred from a file extension.** The suffix survives into `storage/` as a
decoration for whoever pulls the bytes back out, and nothing reads it.

**Authors** on a `turn`: `human`, `assistant`, `envelope`.

**Schemes** — the `by` field on a citation-layer edge and an alias's own
`params["scheme"]`, naming which resolver produced it: `uuid-link`, the only
one `compost layer citation` knows (`BUILDERS["citation"]`, `src/layers.py`).

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

Current coverage: **35 node types, 12 edge pairs, 380 nodes.** `citation` /
`cites` and `citation` / `names` are exercised by a document written *inside
the test itself* — `tests/test_grammar.py`'s `build()` digests the fixtures,
reads a real block guid out of the base, writes a temporary document citing
that guid and a fabricated one, digests it, and runs `compost layer citation`
over the whole thing, so both branches of the layer (a resolved edge, and an
`alias`/`unresolved_citation` pair for the one that does not resolve) are
exercised without a committed fixture that would have to hard-code a guid
that could never actually resolve in a fresh base. `conversation` / `responds_to`
and `conversation` / `next` are exercised the same way, one `claude-code-response`
wrapper answering a *root* already in the base — not a block, since a block is
already the source of its own pandoc-ast `next` edge and `Graph._next` keys the
whole chain by source alone (`src/records.py:302`); pointing the wrapper at one
was tried while writing this fixture and broke `check` immediately, which is
exactly the accepted risk `docs/roadmap.md` names as *"`Graph._next` is
layer-blind"*, confirmed rather than merely asserted. The *not yet minted* list
(§8, item 6) is empty as of v0.2.4 — it held `("citation", "cites")` while
`citation_edges()` was defined and tested but called by nothing in `src/`.

Two fixtures exist for the base-constructor coverage below and nothing else.
Before them the fixtures reached 28 of the 33 pre-v0.2.4 types, and
`CodeBlock`, `RawBlock`, `BlockQuote`, `Div` and `contentblock` were documented
from the code alone:

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

# Implementation plan — v0.2.4

**Scope:** `schema_version`, edge provenance and hashing, the `alias` and
`unresolved_citation` node types, the `names` edge, `compost layer citation`, and
`lookup` reporting citations. Nothing else.

`docs/roadmap.md` has the reasoning. This file has the steps. Where they
disagree, the roadmap is right — stop and ask rather than guessing.

**Delete this file when v0.2.4 is tagged.** It is a working document.

---

## 0. Before you start

```bash
conda activate compost      # pandoc 3.10 — the base env has 3.8 and won't say so
pip install -e .
./tests/run.sh
```

The last line of `run.sh` says `corpus present` or `corpus ABSENT`. **Read it
every time.** With the corpus absent, `test_records` sweeps 6 documents; with it
present, 526. A green board on 6 documents is not a green board — run
`./tests/fetch-corpus.sh` first if it says ABSENT.

Suites are run as `python3 -m tests.test_NAME` from the repo root. Use that form
throughout, matching `tests/run.sh`.

### Rules that are not negotiable

- **Work on `main`.** No feature branch. Do not tag.
- **Never scan raw file text for citations.** A citation is a `Link` node inside
  parsed `content`. `records._links()` (`src/records.py:603`) is the pattern and
  the existing `citation_edges()` already does this correctly — do not rewrite it.
- **Every guid is a fresh `uuid4()`.** Never derive a guid from content, from
  another guid, or from a hash. If you find yourself wanting a deterministic guid,
  you have misread the plan.
- **Add a property, not a snapshot**, and make each one fail on purpose before
  believing it. `tests/test_sabotage.py` is the model.
- **Do not "fix" duplicates.** Running the builder twice is *supposed* to produce
  two full sets of records. That is the design, and step 6 has a test asserting it.
- Commit per numbered step unless a step says otherwise.

### What this release deliberately does NOT contain

Do not add any of these, even if they seem obviously missing:

- no `drop` subcommand
- no `layer` node type, no declarations, no registry written into the graph
- no staleness detection of any kind
- no dependency ordering or "rebuild what's needed" logic
- no deduplication, at write time or read time
- no new `check` assertions

---

## Step 1 — `schema_version` on every record

**Files:** `src/records.py`.

Add near the other module constants (after line 26):

```python
# The grammar version a record conforms to. See docs/record-grammar.md.
# Absent means 1 by definition: schema 1 is what compost has always written, so
# every record ever produced already conforms and nothing needs rewriting.
# Optional on read, required on write.
SCHEMA_VERSION = 1
```

In `Builder.node()` (line 71) and `Builder.edge()` (line 83), add
`"schema_version": SCHEMA_VERSION` immediately after `"record"`.

**`content_hash` must not change.** It is
`sha256(canonical([type_, params or {}, content]))` — it never included `record`
or `guid`, and `schema_version` must not enter it either. The existing call site
already passes only those three values, so leave that line completely alone.

Add **one** `check` assertion, at the end of `records.check()`:

```python
for r in records:
    v = r.get("schema_version")
    if v is not None and v > SCHEMA_VERSION:
        problems.append(f"{r['guid']} is schema {v}; this tool writes "
                        f"{SCHEMA_VERSION}")
```

It cannot fire on any existing base — absent means 1 — and it fires loudly the
first time a newer tool's records are loaded by an older one, which is the only
reason the field exists. **Do not** assert that the field is *present*: every
record written before this release lacks it and `check` must keep passing on
them.

Also bump `src/__init__.py` to `0.2.4` in this step, so `tool_version` on every
record written during this work is honest.

**Verify:**

```bash
python3 -m tests.test_records     # count unchanged (526 with corpus, 6 without)
./tests/run.sh                    # all suites green
```

---

## Step 2 — provenance and hashing on edges

**Files:** `src/records.py`.

### 2a. A timestamp helper

`src/store.py:51` already has `_now()`. Move it to `records.py` so `Builder` can
use it without importing `store` — that import direction does not exist today and
must not be created. Update `store.py`'s call sites to use the `records` one.

**`records.py` does not currently import `datetime`** (see its import block at
lines 21–24). Add it. `store.py` may then drop its own import if nothing else
uses it — check before deleting.

### 2b. `Builder.edge()` gains three fields

```python
def edge(self, type_, src, dst, layer: str = LAYER, **props):
    e = {"record": "edge", "schema_version": SCHEMA_VERSION,
         "guid": self._mint(), "layer": layer, "type": type_,
         "source": src, "destination": dst}
    e.update(props)                       # `by`, and anything a builder adds
    e["created_at"] = _now()
    e["tool_version"] = __version__
    e["content_hash"] = edge_hash(e)
    self.records.append(e)
```

`__version__` comes from `from . import __version__` at the top of the module —
**not** `import src`, which does not work from inside the package.

Every edge in the base gets these, ingest-time and built alike. Storage is not
being optimised for.

### 2c. `edge_hash`

```python
# Provenance and identity are excluded on purpose. An edge's hash must say what
# it *claims* — type, layer, by, source, destination — and never when or by what
# it was written, or the same fact rebuilt tomorrow would not match the one
# written today, which is the entire use of the hash.
EDGE_HASH_SKIP = {"record", "guid", "schema_version", "content_hash",
                  "created_at", "tool_version"}


def edge_hash(e: dict) -> str:
    return hashlib.sha256(canonical(
        {k: v for k, v in e.items() if k not in EDGE_HASH_SKIP})).hexdigest()
```

**Verify:** `./tests/run.sh` green. The round-trip suites compare **ASTs and log
lines**, not records, so extra fields on edges do not affect them. If a suite goes
red here it is comparing records directly — fix the test to compare
`content_hash` or to drop the keys in `EDGE_HASH_SKIP`, not to remove the fields.

---

## Step 3 — two new node types

**Files:** `src/records.py`.

Add `"alias"` and `"unresolved_citation"` to `UNCONTAINED` (line 34):

```python
UNCONTAINED = {"file", "blob", "alias", "unresolved_citation"}
```

Both are entities — pointed at, inside nothing. Without this, `check` reports
*alias &lt;guid&gt; has 0 parents, expected 1* and the whole board goes red.

**Neither type may carry a `content_hash`.** `check`'s ninth assertion
(`src/records.py:543`) requires `content_hash` to be *absent* unless the node has
`content` or its type is in `TEXT_IN_PARAMS`. `Builder.node()` already gets this
right as long as you pass `params=` and no `content=`. Do not add one.

No other change to `records.py` in this step. **No new `check` assertions.**

---

## Step 4 — `src/layers.py`

**File:** new. Match the docstring style of `src/routes.py`.

This module owns `compost layer`. Do not put layer logic in `store.py`.

**Imports this file needs**, none of which exist yet — write them first:

```python
import uuid
from pathlib import Path

from . import __version__          # NOT `import src`; that fails inside the package
from . import records as R
from . import store as S
```

**Write the sections below in the order 4a → 4b → 4c → 4d, but place the
registry (4a) *after* the builder (4b) in the file.** A module-level dict that
names a function defined below it raises `NameError` at import time, and the
module will not load at all.

### 4a. The registry

```python
# name -> {by -> builder}. Named the way routes are named, and for the same
# reason: what produced a record is written down, never inferred.
# Defined AFTER _citation — see the note above.
BUILDERS = {
    "citation": {"uuid-link": _citation},
}
```

### 4b. The citation builder

`records.citation_edges(records)` already exists (`src/records.py:621`), is
tested, and returns `(edges, unresolved)`. **Do not rewrite its link-reading
logic** — that logic is what makes "handles inside code are not citations" true by
construction. Its `mint` parameter takes no arguments and cannot help you here;
ignore it and let it mint normally.

```python
def _citation(recs, name, by):
    """Citation edges, plus a placeholder for every target that is not here.

    An unresolved target cannot become an edge — a dangling endpoint fails
    `check` and takes the whole graph down. Before this it had nowhere to live
    at all: not in the text, not in the graph, only in terminal output. Now the
    absence is a record.
    """
    b = R.Builder()
    edges, unresolved = R.citation_edges(recs)
    for e in edges:
        # schema_version is NOT optional here. citation_edges builds raw dict
        # literals rather than going through Builder.edge(), so nothing has
        # added it — and "required on write" would be violated by the very
        # release that introduces it.
        e["schema_version"] = R.SCHEMA_VERSION
        e["layer"], e["by"] = name, by
        e["created_at"], e["tool_version"] = R._now(), __version__
        e["content_hash"] = R.edge_hash(e)

    # One alias and one placeholder per *distinct* value in this build. Two
    # citations of the same missing handle share one placeholder.
    seen = {}
    for value, source in unresolved:
        if value not in seen:
            ph = b.node("unresolved_citation")
            al = b.node("alias", {"value": value, "scheme": by})
            b.edge("names", al, ph, name, by=by)
            seen[value] = ph
        b.edge("cites", source, seen[value], name, by=by)
    return {"cites": len(edges) + sum(1 for _ in unresolved),
            "placeholders": len(seen),
            "records": edges + b.records,
            "unresolved": sorted(seen)}
```

**Provenance goes top-level, not in `params`** — on the two node types this
release adds, and **only** those two. Do **not** change `Builder.node()`'s
general behaviour; every other node type stays as it is. Set `created_at` and
`tool_version` as top-level keys where `layers.py` mints an `alias` or an
`unresolved_citation`, exactly as `Builder.edge()` does for edges.

Putting them in `params` would work for these two (neither carries a
`content_hash`) but sets a precedent that breaks the moment a hashed type needs
provenance, since node hashing is `canonical([type, params, content])`.

*An earlier draft of this paragraph said "on every node", which contradicted the
storage measurement published beside it — that figure was computed with
provenance on edges only. Whether to widen it later is `TODO.md`, deferred until
after v0.2.8.*

**`citation_edges` currently returns `unresolved` as a list of bare handle
strings, not `(value, source)` pairs.** You need the citing node's guid to build
the edge, so change `unresolved.append(handle)` (`src/records.py:652`) to
`unresolved.append((handle, n["guid"]))`, change the signature's return
annotation from `tuple[list, list[str]]` to `tuple[list, list[tuple[str, str]]]`,
and update `tests/test_citations.py`'s existing assertions to match. That is the
only change to `citation_edges` — leave everything else in it alone.

### 4c. `build`

```python
def build(st, name: str, by: str) -> dict:
    """Generate a layer. Reads the base; writes one new file. Nothing else.

    This does NOT look at what a previous run wrote. Running it twice produces
    two complete sets of records and removes neither. That is deliberate: see
    docs/roadmap.md, "the tool does not hold your hand".
    """
    recs, _ = st.load()
    r = BUILDERS[name][by](recs, name, by)
    st.write(f"{uuid.uuid4()}.jsonl", r["records"])
    return r
```

The builder returns a dict rather than a count because `records` holds four
kinds of thing — `cites` edges, `alias` nodes, `unresolved_citation` nodes and
`names` edges. Reporting `len(records)` as "cites edges" inflates the headline
number by roughly 3× the count of distinct unresolved values.

### 4d. `main(argv)`

Mirror `src/views.py:main` — `S.Store.find()`, catch `S.NotABase`, return an int.
**`views.main` is called as `views.main(argv[1:])`, so its `argv[0]` is the
subcommand name.** Wire `layer` the same way and parse from `argv[1:]` inside.

```
compost layer                        list what can be built
compost layer NAME [--by SCHEME]     build it
```

- Bare `compost layer` prints the `BUILDERS` registry. This is **static help**,
  not a report about the base — it does not read the graph.
- `--by` defaults to the single key in `BUILDERS[NAME]` when there is exactly
  one, and is required when there is more than one.
- Unknown NAME or `--by` prints what is available and returns 2, the way
  `digest --as` does.
- Print the outcome:

```
  1,204 cites edges  |  3 unresolved -> 3 placeholders
    deadbeef-0000-0000-0000-000000000000
    7f0e91a2-…
```

Print at most ten unresolved values, then `… and N more`.

### 4e. Wire it into `src/cli.py`

**This is a step in its own right and is easy to miss.** `src/cli.py:62` has the
dispatch chain; without a branch there, `compost layer` prints *unknown command*
and `tests/test_manpage.py` goes red for a reason that does not point here.

```python
if cmd == "layer":
    from . import layers
    return layers.main(argv[1:])
```

Add it beside the `render` and `serve` branches. The `USAGE` string and module
docstring are step 10.

---

## Step 5 — `Graph.linked` keeps `by`

**Files:** `src/records.py`, and any caller.

`Graph.__init__` (`src/records.py:284`) indexes non-`contains`, non-`next` edges
by **type alone** and stores only destination guids, so `by` is discarded:

```python
self._rel.setdefault(r["type"], {}).setdefault(r["source"], []).append(r["destination"])
```

Store the **edge record** instead of the destination guid, and have `linked()`
take an optional filter:

```python
def linked(self, guid, type_, by=None):
    """Edges of `type_` leaving `guid`, in record order."""
    out = self._rel.get(type_, {}).get(guid, [])
    return [e for e in out if by is None or e.get("by") == by]
```

**Also update `_rel`'s type annotation** at `src/records.py:275` — it currently
reads `dict[str, dict[str, list[str]]]` and becomes `dict[str, dict[str, list[dict]]]` —
and the `linked()` docstring at `:288`, which promises "destinations".

**There is exactly one caller today: `src/views.py:133`,** which does
`for sub in g.linked(guid, "launched")` and expects guids. Update it to read
`e["destination"]`. Confirm the count with `grep -rn "\.linked(" src/ tests/`
before and after — if there is more than one, the plan is out of date and you
should say so rather than guess.

**Verify:** `./tests/run.sh`. `test_session_views` exercises the `launched` path
and will catch a mistake here.

---

## Step 6 — `tests/test_layer.py`

**File:** new. Add `test_layer` to the list in `tests/run.sh` (lines 11–13).

Harness: a `tempfile.TemporaryDirectory`, `S.Store.init`, `S._digest` wrapped in
`contextlib.redirect_stdout(io.StringIO())` to keep the board quiet — copy the
shape from `tests/test_views.py`.

Any fixture you hand-write into `graph/` lives **inside that temp directory**, per
`tests/test_sabotage.py`'s precedent. Never in a real base.

**Use two separate bases.** Properties 1–3 need a base with **no** unresolved
citations; properties 4–6 need one with them. Mixing them makes property 2 false,
because a placeholder gets a fresh guid every build, so two builds' `cites` edges
into placeholders have different `destination` and therefore different
`content_hash`. Build the two bases in two helpers and say which is which.

Eight properties:

*Base A — every citation resolves:*

1. **Building twice produces two full sets.** Build, count `cites` edges, build
   again, count again — the second count is exactly double. *This asserts the
   accumulation is intended and stops a later reader "fixing" it.*
2. **The two sets pair up by `content_hash`** and have different guids.
3. **`content_hash` ignores `created_at` and `tool_version`.** Take one edge,
   copy it, change both fields, and confirm `edge_hash` returns the same value.
   *This property caught a real contradiction during design; it must exist.*

*Base B — some citations do not resolve:*

4. **An unresolved citation mints exactly one `alias` and one
   `unresolved_citation` per distinct value**, and the `cites` edge's destination
   is the placeholder. Cite the same missing handle twice in one document and
   confirm two edges into one placeholder.
5. **`check` is clean after a build containing unresolved citations.** Nothing
   dangles.
6. **`lookup` by an alias value returns the placeholder** and names the scheme.

*Either base:*

7. **`Graph.linked` preserves `by`** — build, then confirm the returned records
   carry it.
8. **Every record in the base carries `schema_version`.** Sweep the whole loaded
   base, not just the layer's output — this is the property that catches
   `citation_edges`' raw dict literals, which no other test would.

**Sabotage each before believing it.** In particular: remove `"alias"` from
`UNCONTAINED` and confirm the board goes red; add `created_at` back into
`EDGE_HASH_SKIP`'s complement and confirm property 3 fails; make the builder
reuse a placeholder across builds and confirm property 1 fails.

---

## Step 7 — the cross-document citation test

**File:** `tests/test_citations.py`.

Its seven existing properties are unit-level, against hand-built records. Add the
one only the real pipeline can exercise:

- Digest document A into a temp base. Read the guid of one of its blocks out of
  the graph. Write document B containing `[-](#<that guid>)`. Digest B. Run
  `layers.build(st, "citation", "uuid-link")`. Assert a `cites` edge runs from a
  block of B to that block of A.

This is the case `_digest`'s batch isolation could never resolve, and the reason
the layer exists.

Also update this file's existing assertions for the `unresolved` shape change
from step 4b.

---

## Step 8 — `lookup`

**Files:** `src/store.py` (the `lookup` branch of `main`, line 427),
`tests/test_lookup.py`, `CLAUDE.md`.

Three additions:

1. **Resolve aliases.** If the argument is not a guid present in the graph, find
   every `alias` node whose `params["value"]` matches, follow its `names` edge,
   and print the target. Say which scheme resolved it.
2. **Return all matches.** Several aliases may share a value — that is expected
   and is not an error. Print how many, and print each. **Never pick one
   silently.**
3. **Report incoming citations** — every `cites` edge whose `destination` is the
   node, with the citing block's type and a truncated `R.plain_text()`.
4. **Also report citations that reached a placeholder naming this guid.** Without
   this, `lookup <guid>` says *nothing cites this* for a block that **is** cited,
   because the citing edge points at an `unresolved_citation` minted before the
   target existed and never retracted. The reverse path is: find `alias` nodes
   whose `value` equals the guid → follow `names` → collect `cites` edges into
   those placeholders. Label them differently from direct citers, e.g.
   *cited before this block was in the base*.

`CLAUDE.md` currently says `lookup` "does not say what cites it — there is no
citation layer yet". Fix that sentence in this commit.

**Do not add a staleness warning.** On a base where the layer has not been
rebuilt, `lookup` will under-report, and that is an accepted risk recorded in the
roadmap. Silence there is deliberate — but point 4 above is *not* staleness, it is
a citation that was recorded and is simply one hop away.

**`tests/test_lookup.py:97` currently asserts the opposite of this step.** Its
property *"lookup names the node asked for and no other"* checks
`set(re.findall(HANDLE_RE, out)) == {guid}`, with a comment explaining that a
second node "would mean deriving the citation layer on every query". It stays
green today only because the temp base has no citations — so the suite would
silently stop testing anything. Rewrite the property as **"lookup names the node
asked for, plus its citers, and nothing else"**, extend the harness to include a
citation, and replace the module docstring's second paragraph, which states the
old design as fact.

New properties: a cited handle reports its citer; an uncited handle says so and
still exits 0; an alias value resolves; two aliases with one value both appear; a
guid cited only through a placeholder still reports that citer.

---

## Step 9 — the grammar

**Files:** `docs/record-grammar.md`, `tests/test_grammar.py`.

`tests/test_grammar.py` carries `NOT_YET_MINTED = {("citation", "cites")}` and
checks the grammar's tables against a real digest, in both directions.

**It will stay green through step 8**, because no fixture contains a citation
link — verified: `grep -rn '\[-\](#' tests/fixtures/` finds nothing, and
`build()` only digests fixtures. **This step is what makes it red**, by teaching
`build()` to run the layer. Expect green until here; if the board goes red
earlier, that is a real failure, not this one.

**It will go red for three reasons, not one.** `NOT_YET_MINTED` is the obvious
one. The other two come from this step's own documentation edits: once `alias`,
`unresolved_citation` and `citation`/`names` are documented, the suite's
*"every documented node type is exercised"* (`tests/test_grammar.py:146`) and
*"every documented edge pair is exercised"* (`:162`) fail unless a fixture
actually produces them. Their messages name the missing types and do not point at
the cause.

1. Extend `test_grammar.build()` to digest a citing document and then call
   `layers.build(st, "citation", "uuid-link")`. **Generate that document inside
   the test** — a committed fixture with a hard-coded guid would never resolve in
   a fresh base. It needs a two-phase digest: digest the fixtures, read a real
   block guid out of the graph, write a temp `.md`, digest it, then build.
   **That document must contain two citations** — one to the real guid and one to
   a fabricated one such as `deadbeef-0000-0000-0000-000000000000` — so the layer
   mints both branches and all three node types and both edge types appear.
2. Delete the `NOT_YET_MINTED` entry.
3. Update `docs/record-grammar.md`:
   - **§2** — add `schema_version` (present), `by`, `created_at`, `tool_version`
     and `content_hash` to the edge form. **Leave the "GUID is a UUIDv4 in every
     case / nothing derives a guid from content" sentence exactly as it is** — it
     is still true, and it also carries the unrelated storage/graph name
     separation invariant.
   - **§3.4** — add `alias` (`value`, `scheme`) and `unresolved_citation` (no
     params). Note that provenance is top-level on both, not in `params`.
   - **§4** — `citation`/`cites` loses its "not yet minted" note; add
     `citation`/`names`.
   - **§5** — assertion 9 is about **nodes** only. State the **two hash
     functions** side by side and that they are not comparable: a node's is
     `sha256(canonical([type, params, content]))`, positional over an array with
     no exclusions; an edge's is `sha256(canonical(record − EDGE_HASH_SKIP))`,
     an object with a six-key skip list. Same field name, different inputs — a
     query grouping by `content_hash` across record kinds is comparing nothing.
     Add the new `schema_version` assertion.
   - **§1** — the field is now written; delete the status banner. Also delete the
     stale sentence in *When the number bumps* that names "the `layer` and
     `handle` node types" as the planned v0.2.4 work — there is no `layer` node
     type and the type is called `alias`.
   - **§6** — add `uuid-link` to the closed vocabularies.
   - **§8** — refresh the coverage numbers from the suite's own output.
   - **Storage figures** — replace the 4.4% claim with the measured totals; see
     step 10.

---

## Step 10 — documentation

One commit, at the end.

- **`CLAUDE.md`** — the `compost layer` line in the command list; the `lookup`
  sentence (step 8); and **line 31's "the eight subcommands"**, which nothing
  tests and which will otherwise go stale.
- **`docs/man-compost.md`** — a ninth subcommand: a `## SYNOPSIS` line and a
  `### layer …` section. It also spells the count in prose — *"The eight
  subcommands below"* becomes *"nine"*, and `tests/test_manpage.py:106` checks
  that word.
- **`src/cli.py`** — the `USAGE` string (keep the two-space-then-name format that
  `usage_names()` matches) *and* the module docstring's list, which is a second
  copy of the same information.
- **`docs/decisions.md`** — the home CLAUDE.md names for every non-obvious
  decision. Four to **add**: guids stay UUIDv4 and why UUIDv5 was rejected; the
  `EDGE_HASH_SKIP` exclusion list and the contradiction it resolves; the two
  governing constraints (no dependency handling, no consistency guarantee) and
  the four unescapable states they removed; and that `content_hash` is evidence
  for a future dedup design rather than a mechanism anything acts on.
  **And one to fix:** its `## Citations` section still says a reference is
  written `{@a1b2c3d4}` and that the migration rewrites `{#x}` → `{@x}`. Both are
  false — the syntax is `[-](#guid)` and v0.2.5 rejects the rewrite. Appending
  four entries above a section that contradicts them is worse than not appending.
- **`docs/record-format.md`** — **missing from the previous draft of this list,
  and `CLAUDE.md:35` ranks it third in the reading order.** Its `## Edge` block
  shows the six-key edge form, which gains five keys; and `## Defining
  content_hash` defines the field for nodes only, ending *"A node with no content
  gets no `content_hash`"* — still true of nodes, now misleading about edges. Its
  note that an `identity_hash` "has to wait until the hash input is pinned down"
  is answered by `EDGE_HASH_SKIP` and should say so.
- **`DEVELOPMENT.md`** — `layers.py` in the module map.
- **`README.md`** — the pipeline.
- **`CHANGELOG.md`** — append. Do not edit an existing entry.
- **`docs/roadmap.md`** — nothing.

**Re-measure the storage cost and publish it.** The roadmap and
`record-grammar.md` §1 currently quote 4.4%, which measured `schema_version`
alone on a fixture set that has since grown. Re-run the measurement after the
implementation and write down the real totals — the estimate is +27% overall and
+79% on edges, and a project that measures `-smart` to the percentage point
should not ship the flattering half of a number.

---

## Definition of done

```bash
./tests/run.sh          # fourteen suites, all green, `corpus present`
```

Then, by hand, in a scratch base. **The order matters: `b.md` cannot cite a guid
until `a.md` has been digested and that guid exists.**

```bash
compost init .
echo "The block that gets cited."      > a.md
compost digest --as=notes a.md
compost render
grep -o 'id="[0-9a-f-]\{36\}"' .compost/views/default-html/a.html | head -2
#   ^ take the guid of a real block; call it G

printf 'Answering [-](#G) here.\nAnd [-](#deadbeef-0000-0000-0000-000000000000) which is absent.\n' > b.md
#   substitute the real G above

compost digest --as=notes b.md
compost layer                        # lists: citation (uuid-link)
compost layer citation               # 2 cites edges | 1 unresolved -> 1 placeholder
compost check                        # 0 problems
compost render
compost layer citation               # runs again, same counts
compost check                        # STILL 0 problems — duplicates are legal
compost lookup G                     # the block AND its citer, listed twice
compost lookup deadbeef-0000-0000-0000-000000000000
                                     # resolves via alias to the placeholder
```

Three lines are the point of the release: `layer citation` reports **one
unresolved and one placeholder** (the absence became a record), `check` reports
**0 problems after a second build** (duplicates are not an error), and `lookup G`
shows the citer **twice** (nothing dedups). If any of the three surprises you, the
implementation is wrong, not the plan.

**Do not tag.** Report back when the board is green and that sequence behaves.

---

## Things that will bite

- **`check` does NOT run inside `Store.load()`.** Its only three call sites are
  `store.py:181`, `store.py:466` and `views.py:380` — so `digest` and `lookup` are
  ungated. A wrong assertion breaks `check` and `render`, not everything.
- **`store._digest` writes `pandoc-ast` and `ingestion` records into one file**
  (`src/store.py:334`). Any code assuming one file is one layer is wrong. Nothing
  in this release should care, because nothing removes files.
- **`Store.load()` deduplicates byte-identical records** (`store.py:159`). With
  `created_at` on every edge, two builds are never byte-identical, so nothing
  collapses. That is intended — do not add a timestamp-stripping "fix".
- **`tests/test_manpage.py` checks a spelled-out number in prose.** Adding a
  subcommand without updating that word fails the board with a message that does
  not obviously point at the man page.
- **`src/__init__.py` still says `0.2.3`.** Bump it in step 1 so
  `tool_version` on every record written during this work is honest. Note
  `docs/man-compost.md` also hard-codes *"Version 0.2.3"* and nothing tests that
  string.
- **`compost layer` is not gated by `check`,** and neither is `Store.load()`. So
  building a layer onto a broken graph is allowed. That follows the `lookup`
  precedent and is intended — do not "fix" it by adding a gate.
- **`plain_text()` folds `params["text"]` in at `src/records.py:598-599`**, not at
  `:47` — that line is only the `TEXT_IN_PARAMS` constant. This matters if you go
  looking for why the citation reader must walk `content` rather than flatten.
- **The corpus tier.** `run.sh`'s last line is the only thing that says whether 6
  or 526 documents were exercised.
- **Every line number in this document was correct when it was written and rots
  within a release.** If one does not match, trust the code and say so rather than
  editing around it.

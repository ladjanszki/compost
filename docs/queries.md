# Querying a base with SQL

`compost` has no `query` subcommand and this document is not asking for one —
see `docs/roadmap.md`, "v0.2.8 — a query layer", for why that decision waits.
What exists instead is a **read-only SQL view** over a base's records, built
on [duckdb](https://duckdb.org)'s `read_json`, and a small set of queries
that answer the questions this project has actually had.

Nothing here is installed and nothing here is a subcommand. `tools/` is
development material, reachable from a checkout and never shipped
(`DEVELOPMENT.md`).

## Running one

From a checkout, with `duckdb` importable (`conda env update -f
environment.yml` if it is not):

```python
from pathlib import Path
from tools import graph_sql as GS

con = GS.connect(Path(".compost/graph"))
GS.run_file(con, Path("tools/queries/node_count.sql"))
```

`connect()` does the one thing every query here depends on: it points a view
named `records` at `graph/*.jsonl` and never writes a file — no `.duckdb` on
disk, ever. A `.sql` file assumes only that `records` exists, so the same
file also runs unmodified from the `duckdb` CLI once you `CREATE VIEW
records AS SELECT DISTINCT * FROM read_json('.compost/graph/*.jsonl',
map_inference_threshold=0);` yourself.

**Read `tools/graph_sql.py`'s module docstring before writing a new one.**
Everything below was measured against this project's own bases, not assumed:
`params` infers as a lossless `MAP(VARCHAR, JSON)` only when duckdb reads the
whole glob at once and `map_inference_threshold=0`; `content` is the field
that actually varies in shape between bases, not `params`; `->>` raises
inside a `WHERE` that also filters on `record`, so a predicate into `params`
needs `json_extract_string` instead; and `guid`, `source` and `destination`
infer as `UUID` while `created_at` infers as `TIMESTAMP`, so a caller
comparing either to a Python string casts one side or duckdb refuses to run
the query at all.

**The SQL lives in `tools/queries/*.sql`, this document does not repeat it.**
Embedding a query in prose is literate programming done by hand — the copy
that runs and the copy that is read drift the moment one changes without the
other. Two guards keep that from happening silently: `tests/test_query.py`
reads these exact files and runs them, so a query under test cannot rot
unnoticed; and the same suite checks that every file here is *mentioned*
below, so nothing can go undocumented. Neither guard pins the prose to the
SQL word for word, which is the point — the prose says why, the file says
how.

## The dedup bridge

`Store.load()` drops a record it has already seen, comparing the *whole
record* (`docs/decisions.md`, "load() deduplicates byte-identical records").
Raw SQL over the glob does not, so `records` here is defined as `SELECT
DISTINCT * FROM raw_records` — every query below reads `records`, never
`raw_records`, unless it is specifically about the divergence between them.

**`count(DISTINCT guid)` was considered and rejected as this bridge, in
writing.** It reconciles a byte-identical duplicate file the same way
`SELECT DISTINCT` does — but it *also* collapses a genuine guid conflict the
same way, and cannot tell the two apart: measured, a base holding a
duplicated file and a base holding two different records under one guid
report the identical `count(DISTINCT guid)`. `records`'s row-level `SELECT
DISTINCT` can tell them apart — the harmless duplicate collapses to one row,
the conflict leaves two — which is exactly what `check_duplicate_guids.sql`
(below) is built on. `tests/test_query.py` measures this on both bases side
by side rather than asserting it from one.

## Starting queries

| file | answers |
|---|---|
| `node_count.sql` | how many nodes are in the base |
| `edge_count.sql` | how many edges are in the base |
| `unresolved_citations.sql` | how many distinct citation targets are missing — one placeholder per handle, not per citation |
| `nodes_with_alias.sql` | how many nodes are named by at least one `alias` |

## The `check` assertions, mirrored

Each file below is the SQL half of one branch of `src/records.py`'s
`check()`. `tests/test_query.py` is the twin-assertion test: it sabotages a
small base one way per branch and requires the same guid(s) back from both
sides, not merely the same count.

| file | mirrors |
|---|---|
| `check_duplicate_guids.sql` | "guid `{g}` carries two different records" |
| `check_dangling_edges.sql` | "edge `{g}` has a dangling source/destination" |
| `check_parent_counts.sql` | all three parent-count branches at once: an `UNCONTAINED` node contained by something, a root node with a parent, and anything else without exactly one |
| `check_launched_multiple.sql` | "session `{g}` is launched by N tool calls" |
| `check_content_hash.sql` | "`content_hash` should be present/absent" |
| `check_schema_version.sql` | "`{g}` is schema N; this tool writes 1" |

`check_parent_counts.sql` and `check_content_hash.sql` hand-copy `UNCONTAINED`,
`ROOT_TYPES` and `TEXT_IN_PARAMS` from `src/records.py` as literal SQL lists,
and `check_schema_version.sql` hand-copies `SCHEMA_VERSION`. None of the four
is a shared source with the Python original — if one changes there and not
here, `tests/test_query.py` is what notices, on whichever fixture base
exercises the branch that moved.

### Not mirrored, on purpose

Three of `check()`'s branches have no SQL twin here, and the gap is
deliberate rather than an oversight:

- **"handle shared by two nodes"** cannot fire under the current format.
  `HANDLE_LEN` is 36 — the full length of a guid — so `g[:36]` is `g`, and
  two distinct dict keys (which is what `nodes` is keyed by) can never
  collide after being sliced to their own full length. A SQL query that
  always returns nothing would test that the query returns nothing, not that
  the check means anything, so it was left out rather than written to look
  busy.
- **`Graph.children`'s ordering check** — that a multi-child parent's `next`
  edges form exactly one chain, with one head, no cycle, and full coverage —
  and **the two containment-cycle checks** are graph-path problems, not
  aggregate ones. A faithful SQL mirror needs a recursive CTE walking each
  multi-child parent's chain and would be a meaningfully larger piece of work
  than every other branch in this document combined; shipping one without the
  same measurement discipline the rest of this file was held to would be
  worse than leaving the gap named. `docs/roadmap.md`'s "Risks accepted
  without mitigation" already notes these are safe today "by accident" for
  unrelated reasons (`_next` being layer-blind) — worth revisiting together
  with that note, not separately.

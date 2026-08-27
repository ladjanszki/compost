#!/usr/bin/env python3
"""
graph_sql.py — the read-only SQL view over a base's graph/, via duckdb.

Nothing here materialises anything: `connect()` opens an in-memory duckdb
connection and points a view at `graph/*.jsonl` directly. Closing the
connection, or letting it fall out of scope, leaves no file behind — there is
no duckdb database file, ever (docs/roadmap.md, "v0.2.8 — a query layer",
"DuckDB, reading .compost/graph/*.jsonl in place"). `layer` writes derived
*records* into the graph; this writes nothing at all, and nobody should later
"improve" it into a materialised store.

**The read shape, measured against this project's own bases.** `read_json`
over the *glob*, not file by file, with `map_inference_threshold=0`:
reading one file at a time infers `params` as a STRUCT built from that one
file's own keys, silently dropping any key only some other file has — no
warning, just an absent column. Reading the whole glob together gives every
writer's keys a chance to be seen before duckdb commits to a shape, and it
settles on `MAP(VARCHAR, JSON)` instead: lossless, no column list to
maintain. `content` is the unstable field here, not `params` — it infers
differently between a `notes` base and one holding transcripts too, which is
one more reason nothing in `tools/queries/` reads inside it.

Two more findings that shape every query file:

- **`->>` raises** inside a `WHERE` that also filters on `record`, because
  `params` is a MAP on one row and absent on another (an edge has no
  `params` at all) — duckdb cannot resolve the cast. `json_extract_string`
  does not have this problem and is what a query should reach for instead.
- **`guid`, `source` and `destination` infer as `UUID`; `created_at` infers
  as `TIMESTAMP`.** Comparing either against a plain Python string needs a
  cast on one side, or duckdb raises rather than silently stringifying.

**The dedup bridge is `SELECT DISTINCT` over the whole row**, not
`count(DISTINCT guid)` — mirroring `Store.load()`, which deduplicates on
`R.canonical(rec)` (the whole record) and leaves a genuine guid conflict as
two rows for `check` to find. `count(DISTINCT guid)` would hide exactly the
conflict `check` exists to catch (docs/decisions.md, "load() deduplicates
byte-identical records"). `records` below is the deduped view every query
should read from; `raw_records` is the ungrouped glob, kept only for a query
that wants to look at the divergence itself.
"""
from pathlib import Path

try:
    import duckdb
    HAVE_DUCKDB = True
except ImportError:                 # pragma: no cover — exercised by test skip
    duckdb = None
    HAVE_DUCKDB = False

# What a skipped guarantee says, mirroring tests/tier.py's WHY and
# tests/test_draw.py's GV_WHY: a bare environment should say why a guarantee
# is missing rather than leave a silent gap in the board.
WHY = "duckdb not installed (conda env update -f environment.yml)"

QUERIES = Path(__file__).parent / "queries"


def connect(graph_dir: Path):
    """An in-memory duckdb connection with `records` reading `graph_dir`.

    `graph_dir` is a base's `.compost/graph/` — flat by rule since v0.2.8
    (`src/store.py`, "graph/ is flat"), so one glob reaches every record and
    nothing under a subdirectory is silently missed or silently included.
    """
    con = duckdb.connect()
    # Single-quote escaping, not a bound parameter: duckdb's binder rejects a
    # prepared parameter inside CREATE VIEW ("this type of statement can't be
    # prepared"), so the glob is interpolated as a SQL string literal — safe
    # here because it is built from this repo's own path, never from
    # untrusted input.
    glob = str(Path(graph_dir) / "*.jsonl").replace("'", "''")
    con.execute(
        f"CREATE VIEW raw_records AS "
        f"SELECT * FROM read_json('{glob}', map_inference_threshold=0)")
    con.execute("CREATE VIEW records AS SELECT DISTINCT * FROM raw_records")
    return con


def run_file(con, sql_path: Path) -> list[tuple]:
    """Execute one `tools/queries/*.sql` file exactly as written on disk.

    No templating and no substitution: every file assumes only that
    `records` (and, rarely, `raw_records`) already exists, which is what
    `connect()` sets up. That is what lets the twin-assertion test read the
    very file a person would run by hand from the duckdb CLI, rather than a
    second copy of the query kept in sync by hand.
    """
    return con.execute(Path(sql_path).read_text()).fetchall()


def sql_files() -> list[Path]:
    return sorted(QUERIES.glob("*.sql"))

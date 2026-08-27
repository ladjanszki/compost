#!/usr/bin/env python3
"""
test_query.py — the twin-assertion test: `check()`'s guarantees, expressed
twice, required to agree.

This is the point of v0.2.8 (docs/roadmap.md, "v0.2.8 — a query layer"). Every
`tools/queries/check_*.sql` file mirrors one branch of `src/records.py`'s
`check()`, reading `graph/*.jsonl` through `tools/graph_sql.py` rather than
`Store.load()`. Each case here sabotages a small hand-built base one way,
asks both sides what is wrong, and requires the same guids back — not just
the same problem *count*, which two implementations could agree on by
accident.

**Scoped deliberately, and said here rather than left implicit.** Three of
`check()`'s branches are NOT mirrored:

- the "handle shared by two nodes" check is dead code today — `HANDLE_LEN`
  is 36, the full length of a guid, so `g[:36]` is `g` and two distinct dict
  keys can never collide after slicing to their own full length. Mirroring a
  branch that cannot fire would test nothing; see `docs/queries.md`.
- `Graph.children`'s ordering check (one head, no cycle, full coverage of a
  multi-child parent's `next` chain) and the two containment-cycle checks
  are graph-path problems, not aggregate ones. A correct general mirror
  needs a recursive CTE walking each multi-child parent's chain, which is a
  different scale of engineering than every other branch here — untested,
  it would be worse than an honest gap. Left for later, and `docs/queries.md`
  says so.

`tests/tier.py`'s pattern governs absence: duckdb is a conda-forge package,
not a Python stdlib module, so a bare environment (or one that skipped
`conda env update`) must still show a full board and say why every case here
was skipped, exactly like `test_draw.py` does for graphviz.
"""
import re
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R      # noqa: E402
from src import routes as RT      # noqa: E402
from src import store as S        # noqa: E402
from tools import graph_sql as GS  # noqa: E402

QUERIES_DIR = Path(__file__).parent.parent / "tools" / "queries"
QUERIES_MD = Path(__file__).parent.parent / "docs" / "queries.md"


# --------------------------------------------------------------------------
# base building — one small base per case, sabotaged one way each
# --------------------------------------------------------------------------

def _base(tmp: Path, name: str, extra: list | None = None) -> S.Store:
    """A one-file base: two paragraphs and a code block, plus `extra` records
    written to a second file — the shape every sabotage case starts from."""
    st = S.Store.init(tmp / name)
    p = tmp / f"{name}.md"
    p.write_text("A paragraph.\n\nAnother one.\n\n```\na code block\n```\n")
    recs, root = R.ast_to_records(RT._ast_of(p), source=p.name, route="notes")
    st.write("a.jsonl", recs)
    if extra:
        st.write("b.jsonl", extra)
    return st


def sabotage_dup_guid(recs):
    node = next(r for r in recs if r["record"] == "node" and r["type"] == "Para")
    return [dict(node, content=[{"t": "Str", "c": "different"}])]


def sabotage_dangling(recs):
    return [{"record": "edge", "guid": str(uuid.uuid4()), "layer": R.LAYER,
             "type": "contains", "source": str(uuid.uuid4()),
             "destination": str(uuid.uuid4())}]


def sabotage_two_parents(recs):
    contains = [r for r in recs if r["record"] == "edge" and r["type"] == "contains"]
    return [dict(contains[-1], guid=str(uuid.uuid4()), source=contains[0]["source"])]


def sabotage_uncontained(recs):
    para = next(r for r in recs if r["record"] == "node" and r["type"] == "Para")
    blob = {"record": "node", "guid": str(uuid.uuid4()), "layer": R.LAYER,
            "type": "blob", "params": {}}
    e = {"record": "edge", "guid": str(uuid.uuid4()), "layer": R.LAYER,
         "type": "contains", "source": para["guid"], "destination": blob["guid"]}
    return [blob, e]


def sabotage_root_has_parent(recs):
    doc = next(r for r in recs if r["record"] == "node" and r["type"] == "document")
    para = next(r for r in recs if r["record"] == "node" and r["type"] == "Para")
    e = {"record": "edge", "guid": str(uuid.uuid4()), "layer": R.LAYER,
         "type": "contains", "source": para["guid"], "destination": doc["guid"]}
    return [e]


def sabotage_launched_multiple(recs):
    doc = next(r for r in recs if r["record"] == "node" and r["type"] == "document")
    session = dict(doc, guid=str(uuid.uuid4()), type="session")
    session.pop("content", None)
    call1, call2 = str(uuid.uuid4()), str(uuid.uuid4())
    n1 = dict(doc, guid=call1, type="toolcall")
    n1.pop("content", None)
    n2 = dict(doc, guid=call2, type="toolcall")
    n2.pop("content", None)
    e1 = {"record": "edge", "guid": str(uuid.uuid4()), "layer": S.AGENT_LAYER,
          "type": "launched", "source": call1, "destination": session["guid"]}
    e2 = {"record": "edge", "guid": str(uuid.uuid4()), "layer": S.AGENT_LAYER,
          "type": "launched", "source": call2, "destination": session["guid"]}
    return [session, n1, n2, e1, e2]


def sabotage_hash_present_wrongly(recs):
    doc = next(r for r in recs if r["record"] == "node" and r["type"] == "document")
    return [dict(doc, guid=str(uuid.uuid4()), content_hash="0" * 64)]


def sabotage_hash_missing(recs):
    para = next(r for r in recs if r["record"] == "node" and r["type"] == "Para")
    twisted = dict(para, guid=str(uuid.uuid4()))
    del twisted["content_hash"]
    return [twisted]


def sabotage_schema_version(recs):
    n = next(r for r in recs if r["record"] == "node")
    return [dict(n, guid=str(uuid.uuid4()), schema_version=99)]


# --------------------------------------------------------------------------
# comparison — pull the guid(s) each side names, out of two different shapes
# --------------------------------------------------------------------------

def _py_guids(problems: list[str], pattern: str) -> set:
    out = set()
    for p in problems:
        m = re.search(pattern, p)
        if m:
            out.add(m.groups() if len(m.groups()) > 1 else m.group(1))
    return out


def _sql_guids(rows: list[tuple], cols: tuple[int, ...] = (0,)) -> set:
    out = set()
    for row in rows:
        vals = tuple(str(row[c]) for c in cols)
        out.add(vals if len(cols) > 1 else vals[0])
    return out


CASES = [
    # (sabotage fn, sql file, python-message pattern, sql-row columns to pull)
    ("a duplicate guid, conflicting content",
     sabotage_dup_guid, "check_duplicate_guids.sql",
     r"guid (\S+) carries two different records", (0,)),
    ("a dangling edge endpoint",
     sabotage_dangling, "check_dangling_edges.sql",
     r"edge (\S+) has a dangling (\w+)", (0, 1)),
    ("a node with two parents",
     sabotage_two_parents, "check_parent_counts.sql",
     r"^\S+ (\S+) has \d+ parents, expected 1", (0,)),
    ("an UNCONTAINED node contained by something",
     sabotage_uncontained, "check_parent_counts.sql",
     r"^\S+ (\S+) is contained by something", (0,)),
    ("a root node with a parent",
     sabotage_root_has_parent, "check_parent_counts.sql",
     r"^\S+ (\S+) has a parent$", (0,)),
    ("a session launched by two tool calls",
     sabotage_launched_multiple, "check_launched_multiple.sql",
     r"session (\S+) is launched by \d+ tool calls", (0,)),
    ("content_hash present when it should be absent",
     sabotage_hash_present_wrongly, "check_content_hash.sql",
     r"^\S+ (\S+): content_hash should be absent", (0,)),
    ("content_hash absent when it should be present",
     sabotage_hash_missing, "check_content_hash.sql",
     r"^\S+ (\S+): content_hash should be present", (0,)),
    ("a schema_version this tool did not write",
     sabotage_schema_version, "check_schema_version.sql",
     r"^(\S+) is schema \d+", (0,)),
]


def main():
    results = []

    def case(name, ok, detail):
        results.append((ok, name, detail))

    if not GS.HAVE_DUCKDB:
        for name, *_ in CASES:
            case(f"twin: {name}", None, GS.WHY)
        case("every .sql file is mentioned in docs/queries.md", None, GS.WHY)
        case("SELECT DISTINCT reproduces Store.load()'s dedup", None, GS.WHY)
        case("count(DISTINCT guid) can't tell a conflict from a duplicate; "
             "the bridge can", None, GS.WHY)
    else:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)

            # -- a clean base: check() and every check_*.sql agree on nothing
            st = _base(tmp, "clean")
            recs, _ = st.load()
            py_problems = R.check(recs)
            con = GS.connect(st.graph)
            all_empty = not py_problems
            for f in GS.sql_files():
                if f.name.startswith("check_"):
                    all_empty = all_empty and not GS.run_file(con, f)
            case("a clean base: check() and every check_*.sql agree (both empty)",
                 all_empty,
                 f"{len(py_problems)} python problems, sql files checked "
                 f"{sum(1 for f in GS.sql_files() if f.name.startswith('check_'))}")

            # -- one sabotage per branch, agreeing on the exact guid(s) named
            for name, sabotage_fn, sql_name, pattern, cols in CASES:
                st = _base(tmp, name.replace(" ", "_")[:24] + uuid.uuid4().hex[:6])
                recs, _ = st.load()
                extra = sabotage_fn(recs)
                st.write("sabotage.jsonl", extra)
                recs2, _ = st.load()
                py_problems = R.check(recs2)
                con = GS.connect(st.graph)
                rows = GS.run_file(con, QUERIES_DIR / sql_name)
                py_set = _py_guids(py_problems, pattern)
                sql_set = _sql_guids(rows, cols)
                ok = bool(py_set) and py_set == sql_set
                case(f"twin: {name}", ok,
                     f"python {py_set or py_problems} | sql {sql_set or rows}")

        # -- every .sql file is mentioned in docs/queries.md
        text = QUERIES_MD.read_text() if QUERIES_MD.exists() else ""
        missing = [f.name for f in GS.sql_files() if f.name not in text]
        case("every .sql file is mentioned in docs/queries.md",
             not missing, f"missing: {missing}" if missing else
             f"{len(GS.sql_files())} files, all mentioned")

        # -- the dedup bridge: SELECT DISTINCT matches Store.load(), and
        # count(DISTINCT guid) would have hidden the guid conflict case above
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            st = _base(tmp, "dedup")
            victim = st.files()[0]
            st.write("copy-of-a.jsonl", R.from_jsonl(victim.read_text()))
            recs, _ = st.load()
            con = GS.connect(st.graph)
            sql_count = GS.run_file(con, QUERIES_DIR / "node_count.sql")[0][0] \
                + GS.run_file(con, QUERIES_DIR / "edge_count.sql")[0][0]
            case("SELECT DISTINCT reproduces Store.load()'s dedup",
                 sql_count == len(recs),
                 f"Store.load() {len(recs)} records, sql (nodes+edges) {sql_count}")

            # A second, separate base: same starting content, but the second
            # file holds the SAME guid with DIFFERENT content — a genuine
            # conflict, not a harmless duplicate. `docs/decisions.md`,
            # "Reject count(DISTINCT guid) as the bridge, in writing":
            # count(DISTINCT guid) cannot tell these two bases apart — a
            # byte-identical copy and a same-guid conflict both collapse to
            # the same reading — while `records`'s row-level SELECT DISTINCT
            # can, and check_duplicate_guids.sql is built on that.
            st2 = _base(tmp, "conflict")
            con_dup = GS.connect(st.graph)   # the healthy "dedup" base above
            dg_dup = con_dup.execute(
                "SELECT COUNT(DISTINCT guid) FROM records "
                "WHERE record='node'").fetchone()[0]

            recs_c, _ = st2.load()
            match = next(r for r in recs_c if r["record"] == "node"
                        and r["type"] == "Para")
            st2.write("conflicting.jsonl",
                     [dict(match, content=[{"t": "Str", "c": "different"}])])
            con2 = GS.connect(st2.graph)
            dg_conflict = con2.execute(
                "SELECT COUNT(DISTINCT guid) FROM records "
                "WHERE record='node'").fetchone()[0]
            row_count_conflict = con2.execute(
                "SELECT COUNT(*) FROM records "
                "WHERE record='node'").fetchone()[0]
            dup_rows = GS.run_file(con2, QUERIES_DIR / "check_duplicate_guids.sql")

            # The blind spot: the SAME node count from count(DISTINCT guid)
            # on a healthy dup-file base and on a genuinely conflicted one —
            # it cannot distinguish them. The row-level bridge can: its own
            # row count exceeds the guid count on the conflicted base, and
            # check_duplicate_guids.sql names the guid outright.
            blind = dg_dup == dg_conflict
            visible = row_count_conflict > dg_conflict and bool(dup_rows)
            case("count(DISTINCT guid) can't tell a conflict from a duplicate; "
                 "the bridge can",
                 blind and visible,
                 f"count(DISTINCT guid): {dg_dup} (dup file) == {dg_conflict} "
                 f"(conflict) | records row count on conflict base "
                 f"{row_count_conflict} > {dg_conflict}, "
                 f"check_duplicate_guids.sql -> {dup_rows}")

    for ok, name, detail in results:
        mark = "skip" if ok is None else ("pass" if ok else "FAIL")
        print(f"  {mark}  {name:<62} {detail}")
    skipped = sum(1 for ok, _, _ in results if ok is None)
    ran = len(results) - skipped
    bad = sum(1 for ok, _, _ in results if ok is False)
    tail = f"   ({skipped} skipped: {GS.WHY})" if skipped else ""
    print(f"\n{ran - bad}/{ran} query guarantees hold{tail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

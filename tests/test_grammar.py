#!/usr/bin/env python3
"""
test_grammar.py — the record grammar cannot drift from the records.

`docs/record-grammar.md` claims to state exhaustively what a record is allowed
to be. That claim was written by reading `src/`, which is how every stale
document in this repository started, so it is held here against a real digest
instead.

The ground truth is a **base built from the fixtures**, not the code: a type the
program can emit but no fixture reaches is a type nobody has ever seen written,
and a table entry for it is a guess. That is why this suite ships with the
fixtures that close the gap — before them the fixtures exercised 28 of the 33
documented node types, and `CodeBlock`, `RawBlock`, `BlockQuote`, `Div` and
`contentblock` were documented from the code alone.

Checked in **both directions**, like `test_manpage.py`: the grammar may not name
a type the base never produces, and the base may not produce one the grammar
does not name. The same for edge `(layer, type)` pairs, and for the params of
every node type — an undocumented param is exactly the drift this exists to
catch.
"""
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R    # noqa: E402
from src import session as SESS  # noqa: E402
from src import store as S      # noqa: E402

HERE = Path(__file__).parent
GRAMMAR = HERE.parent / "docs/record-grammar.md"
FIX = HERE / "fixtures"

# Written down rather than discovered, because "the program cannot produce this
# yet" is a claim about intent that no probe can make. `cites` is defined in
# `records.citation_edges` and called by nothing in `src/`; the grammar says so
# out loud, and this list is what keeps the two statements in step. Wiring the
# citation layer means deleting an entry here, which is the point.
NOT_YET_MINTED = {("citation", "cites")}


def documented_nodes(text: str) -> dict:
    """Node type -> the params the grammar names for it.

    Every table row in §3 whose first cell is a single backticked identifier.
    Params are the backticked tokens of the second cell; `—` means none and a
    trailing `?` marks optional, which this does not distinguish because the
    check is "no param appears that is undocumented", not "every documented
    param appears" — a fixture is not obliged to exercise an optional key.
    """
    body = text.split("## 3. Node types", 1)[1].split("\n## 4.", 1)[0]
    out = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or not (cells[0].startswith("`")
                                  and cells[0].endswith("`")):
            continue
        name = cells[0].strip("`")
        if " " in name:            # a prose cell, not a type
            continue
        # Merged, not assigned: `session` is described in §3.2 and named again
        # in §3.3 as a root, and the second row must not erase the first.
        out.setdefault(name, set()).update(
            m.rstrip("?") for m in re.findall(r"`([^`]+)`", cells[1]))
    return out


def documented_edges(text: str) -> set:
    """The `(layer, type)` pairs the grammar's §4 table names."""
    body = text.split("## 4. Edge types", 1)[1].split("\n## 5.", 1)[0]
    out = set()
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        pair = [re.findall(r"`([^`]+)`", c) for c in cells[:2]]
        if all(len(c) == 1 for c in pair):
            out.add((pair[0][0], pair[1][0]))
    return out


def build() -> list:
    """Digest every fixture through its real route, and load the base back.

    Through `store._digest` rather than `routes.read`, because `blob`,
    `derived_from` and `launched` are minted by the store and a route-level
    sweep would report them missing when they are merely elsewhere. That is the
    measurement error this suite exists to not repeat.
    """
    with tempfile.TemporaryDirectory() as d:
        st = S.Store.init(Path(d))
        batches = [
            ("notes", sorted(str(p) for p in (FIX / "notes").glob("*.md"))
             + [str(FIX / "edge-cases/nested-lists.md"),
                str(FIX / "grammar/all-constructors.md")]),
            ("pandoc-ast", [str(FIX / "ast/unreachable-constructors.json")]),
            ("claude-code-transcript",
             [str(FIX / "sessions/session-smoke.jsonl"),
              str(FIX / "sessions/sidechain-parent.jsonl"),
              str(FIX / "grammar/contentblock.jsonl")]),
        ]
        import contextlib
        import io
        for route, args in batches:
            with contextlib.redirect_stdout(io.StringIO()):
                if S._digest(st, route, args, "compost"):
                    raise RuntimeError(f"digest failed for {route}")
        recs, _ = st.load()
        return recs


def main():
    text = GRAMMAR.read_text()
    doc_nodes = documented_nodes(text)
    doc_edges = documented_edges(text)
    recs = build()

    seen_nodes = Counter(r["type"] for r in recs if r["record"] == "node")
    seen_edges = {(r["layer"], r["type"]) for r in recs
                  if r["record"] == "edge"}
    seen_params = defaultdict(set)
    for r in recs:
        if r["record"] == "node":
            seen_params[r["type"]] |= set((r.get("params") or {}).keys())

    problems = []

    def check(name, ok, detail=""):
        print(f"  {'ok   ' if ok else 'FAIL '} {name:<48} {detail}")
        if not ok:
            problems.append(name)

    undocumented = sorted(set(seen_nodes) - set(doc_nodes))
    check("every node type in the base is documented",
          not undocumented, ", ".join(undocumented))

    unexercised = sorted(set(doc_nodes) - set(seen_nodes))
    check("every documented node type is exercised",
          not unexercised, ", ".join(unexercised))

    bad_params = []
    for t, params in sorted(seen_params.items()):
        extra = params - doc_nodes.get(t, set())
        if extra:
            bad_params.append(f"{t}: {', '.join(sorted(extra))}")
    check("no node carries an undocumented param",
          not bad_params, "; ".join(bad_params))

    e_undoc = sorted(seen_edges - doc_edges)
    check("every (layer, type) in the base is documented",
          not e_undoc, ", ".join(map(str, e_undoc)))

    e_unex = sorted(doc_edges - seen_edges - NOT_YET_MINTED)
    check("every documented edge pair is exercised",
          not e_unex, ", ".join(map(str, e_unex)))

    still_absent = sorted(p for p in NOT_YET_MINTED if p in seen_edges)
    check("the not-yet-minted list is still accurate",
          not still_absent,
          f"{still_absent} is minted now — update the grammar"
          if still_absent else "")

    # The two fixtures this suite added carry the guarantees of their own
    # routes, or they would be documenting a shape the tool cannot read back.
    src = FIX / "grammar/contentblock.jsonl"
    lines = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    srecs, sroot = SESS.session_to_records(src)
    check("the contentblock fixture round-trips exactly",
          SESS.records_to_session(srecs, sroot) == lines)

    check("the assembled base passes check", not R.check(recs))

    total = 7
    print(f"\n{total - len(problems)}/{total} grammar guarantees hold  |  "
          f"{len(seen_nodes)} node types, {len(seen_edges)} edge pairs, "
          f"{sum(seen_nodes.values())} nodes")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

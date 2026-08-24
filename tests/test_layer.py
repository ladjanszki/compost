#!/usr/bin/env python3
"""
test_layer.py — what `compost layer citation` promises.

Two separate bases, because mixing them breaks property 2: a placeholder gets
a fresh guid every build, so two builds' `cites` edges into a placeholder have
different `destination` and therefore different `content_hash` — the pairing
property only holds when every citation in the base actually resolves.

**Base A** — every citation resolves. Properties 1-3.
**Base B** — some citations do not resolve. Properties 4-6.
**Either base** — properties 7-8.

Running the builder twice is supposed to produce two full sets of records,
neither removed — that is the design (docs/roadmap.md, "the tool does not
hold your hand"), and property 1 is what stops a later reader "fixing" it.
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import layers as L      # noqa: E402
from src import records as R     # noqa: E402
from src import routes as RT     # noqa: E402
from src import store as S       # noqa: E402

FAKE = "deadbeef-0000-0000-0000-000000000000"


def _digest_text(st, tmp, name, text):
    """Write `text` to `tmp/name`, read it as `notes`, and commit it to `st`.

    Goes through the real markdown reader rather than hand-built records, so
    a `[-](#guid)` in the text becomes a genuine `Link` node — the whole point
    of `citation_edges` is that it never regexes text.
    """
    p = tmp / name
    p.write_text(text)
    recs, root = R.ast_to_records(RT._ast_of(p), source=name, route="notes")
    st.write(f"{name}.jsonl", recs)
    return recs, root


def _cites(recs):
    return [r for r in recs if r["record"] == "edge" and r["type"] == "cites"]


def _nodes_of_type(recs, t):
    return [r for r in recs if r["record"] == "node" and r["type"] == t]


def build_base_a(tmp: Path):
    """Every citation resolves: one target paragraph, one citing paragraph."""
    st = S.Store.init(tmp / "a")
    target_recs, _ = _digest_text(st, tmp, "target.md", "A target paragraph.\n")
    target = next(r for r in target_recs
                  if r["record"] == "node" and r["type"] == "Para")
    _digest_text(st, tmp, "citing.md",
                 f"Citing [-](#{target['guid']}) here.\n")
    citing_recs, _ = st.load()
    citer = next(r for r in citing_recs if r["record"] == "node"
                 and r["type"] == "Para"
                 and R._links(r) and R._links(r)[0] == f"#{target['guid']}")
    return st, target["guid"], citer["guid"]


def build_base_b(tmp: Path):
    """Some citations do not resolve: one fabricated handle, cited twice."""
    st = S.Store.init(tmp / "b")
    _, root = _digest_text(
        st, tmp, "citing.md",
        f"Citing [-](#{FAKE}) and again [-](#{FAKE}) here.\n")
    recs, _ = st.load()
    citer = next(r for r in recs if r["record"] == "node"
                 and r["type"] == "Para")
    return st, citer["guid"]


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        # -- Base A: every citation resolves ---------------------------------
        st_a, target_guid, citer_guid = build_base_a(tmp)

        def builds_twice():
            with contextlib.redirect_stdout(io.StringIO()):
                L.build(st_a, "citation", "uuid-link")
                recs1, _ = st_a.load()
                c1 = len(_cites(recs1))
                L.build(st_a, "citation", "uuid-link")
                recs2, _ = st_a.load()
                c2 = len(_cites(recs2))
            return c1 == 1 and c2 == 2 * c1, f"{c1} then {c2} cites edges"
        case("building twice produces two full sets", builds_twice)

        def pair_by_hash():
            recs, _ = st_a.load()
            cites = _cites(recs)
            hashes = [e["content_hash"] for e in cites]
            guids = {e["guid"] for e in cites}
            return (len(cites) == 2 and hashes[0] == hashes[1]
                    and len(guids) == 2,
                    f"{len(cites)} edges, {len(set(hashes))} distinct hash(es)")
        case("the two sets pair up by content_hash, distinct guids",
             pair_by_hash)

        def hash_ignores_provenance():
            recs, _ = st_a.load()
            e = _cites(recs)[0]
            other = dict(e, created_at="1970-01-01T00:00:00Z",
                        tool_version="0.0.0")
            return (R.edge_hash(other) == e["content_hash"],
                    "content_hash unchanged by created_at/tool_version")
        case("content_hash ignores created_at and tool_version",
             hash_ignores_provenance)

        # -- Base B: some citations do not resolve ---------------------------
        st_b, citer_b = build_base_b(tmp)
        with contextlib.redirect_stdout(io.StringIO()):
            L.build(st_b, "citation", "uuid-link")
        recs_b, _ = st_b.load()

        def one_alias_one_placeholder():
            aliases = _nodes_of_type(recs_b, "alias")
            placeholders = _nodes_of_type(recs_b, "unresolved_citation")
            cites = _cites(recs_b)
            dests = {e["destination"] for e in cites}
            return (len(aliases) == 1 and len(placeholders) == 1
                    and len(cites) == 2 and dests == {placeholders[0]["guid"]},
                    f"{len(aliases)} alias, {len(placeholders)} placeholder, "
                    f"{len(cites)} cites edges into it")
        case("one alias and one placeholder per distinct value",
             one_alias_one_placeholder)

        def check_is_clean():
            problems = R.check(recs_b)
            return not problems, f"{len(problems)} problems"
        case("check is clean after a build with unresolved citations",
             check_is_clean)

        def lookup_by_alias():
            # Mirrors the reverse path step 8 wires into `compost lookup`:
            # find an alias node by value, follow its `names` edge.
            aliases = [r for r in _nodes_of_type(recs_b, "alias")
                      if r["params"]["value"] == FAKE]
            names = {e["source"]: e["destination"] for e in recs_b
                    if e["record"] == "edge" and e["type"] == "names"}
            placeholders = _nodes_of_type(recs_b, "unresolved_citation")
            targets = {names[a["guid"]] for a in aliases}
            return (len(aliases) == 1 and aliases[0]["params"]["scheme"] == "uuid-link"
                    and targets == {placeholders[0]["guid"]},
                    f"alias -> {targets}, scheme {aliases[0]['params']['scheme'] if aliases else '?'}")
        case("lookup by alias value returns the placeholder, names the scheme",
             lookup_by_alias)

        # -- Either base -------------------------------------------------------
        def linked_keeps_by():
            g = R.Graph(recs_b)
            edges = g.linked(citer_b, "cites")
            return (len(edges) == 2 and all(e.get("by") == "uuid-link" for e in edges),
                    f"{len(edges)} edges, by={[e.get('by') for e in edges]}")
        case("Graph.linked preserves by", linked_keeps_by)

        def every_record_has_schema_version():
            missing = [r for r in recs_b if r.get("schema_version") is None]
            return (not missing,
                    f"{len(missing)} of {len(recs_b)} records lack schema_version")
        case("every record in the base carries schema_version",
             every_record_has_schema_version)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} layer guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

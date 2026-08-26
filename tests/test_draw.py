#!/usr/bin/env python3
"""
test_draw.py — what `compost draw` promises.

`docs/roadmap.md` ("v0.2.7 — a graph view") is the spec, and its central
claim is the one property this suite protects hardest: **the DOT is always
written, and SVG is never a precondition for it** — that is what keeps the
graphviz binary optional at all. Everything else here follows the same shape
as `test_layer.py`: build a small base once, then state and sabotage-verify
one property per case.

Graphviz itself is optional at *test* time too, the same way the corpus is —
`HAVE_GV` gates any guarantee that needs the binary, and the summary line
says how many were skipped and why, mirroring `tests/tier.py`'s pattern for
the corpus rather than reusing that module, since this is about a system
binary, not fetched test material.
"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import draw as D        # noqa: E402
from src import layers as L      # noqa: E402
from src import records as R     # noqa: E402
from src import store as S       # noqa: E402

HERE = Path(__file__).parent
NOTE1 = HERE / "fixtures/notes/note-01.md"
SESSION = HERE / "fixtures/sessions/session-smoke.jsonl"

ENGINE = D.DEFAULT_ENGINE
HAVE_GV = shutil.which(ENGINE) is not None
GV_WHY = ("graphviz not on PATH — "
          "conda install -n compost -c conda-forge graphviz=14.1.2")


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def build_base(tmp: Path):
    """One base, several layers: `pandoc-ast` and `ingestion` from two notes
    documents, `citation` from a link between them, and `session`/`claude-code`
    from a transcript — enough distinct record layers that "edge class ==
    record layer" is actually exercised, not merely true by there being only
    one layer to get right.
    """
    st = S.Store.init(tmp / "base")
    _quiet(S._digest, st, "notes", [str(NOTE1)], "compost")
    recs, _ = st.load()
    target = next(r for r in recs if r["record"] == "node" and r["type"] == "Para")

    citing = tmp / "citing.md"
    citing.write_text(f"Citing [-](#{target['guid']}) here.\n")
    _quiet(S._digest, st, "notes", [str(citing)], "compost")
    _quiet(S._digest, st, "claude-code-transcript", [str(SESSION)], "compost")
    _quiet(L.build, st, "citation", "uuid-link")

    recs, _ = st.load()
    docs = [r for r in recs if r["record"] == "node" and r["type"] == "document"]
    target_doc = next(d for d in docs
                       if R._p(d, "source") == "note-01.md")
    citing_doc = next(d for d in docs if R._p(d, "source") == "citing.md")
    return st, target_doc["guid"], citing_doc["guid"]


def build_broken_base(tmp: Path):
    """A base `check` rejects: one real document, plus a hand-written `cites`
    edge into a guid nothing minted — a dangling destination, same shape
    `tests/test_sabotage.py` and `docs/decisions.md`'s "anything may write
    records" both use.
    """
    st = S.Store.init(tmp / "broken")
    _quiet(S._digest, st, "notes", [str(NOTE1)], "compost")
    recs, _ = st.load()
    real_guid = next(r["guid"] for r in recs if r["record"] == "node")
    b = R.Builder()
    b.edge("cites", real_guid, "deadbeef-0000-0000-0000-000000000000",
          "citation", by="uuid-link")
    st.write("dangling.jsonl", b.records)
    return st


def _dot_edges(text: str) -> dict:
    """`edge guid -> class` for every edge line, read back with a regex.

    Legitimate here in a way it would not be for graphviz's own SVG output:
    this is plain ASCII this module just wrote in the same process, with a
    fixed quoting scheme this test knows exactly — not bytes graphviz has
    re-escaped on the way out. See `node_ids_survive_the_svg` below for the
    case that genuinely needs an XML parser.
    """
    return {m.group(1): m.group(2) for m in re.finditer(
        r'-> "[^"]+" \[id="([^"]+)", class="([^"]+)"', text)}


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
        st, target_root, citing_root = build_base(tmp)

        # -- the property that earns the dependency --------------------------

        def dot_always_written_sabotaged():
            # SABOTAGE. A `draw` that only writes the DOT once the SVG has
            # already succeeded — exactly the bug docs/roadmap.md forbids
            # ("never make SVG a precondition for writing DOT"). Wholesale
            # function replacement, same technique test_response.py uses on
            # `_structural_gaps`.
            real_draw = D.draw

            def broken(st_, root_, engine_):
                recs_, _ = st_.load()
                dot_text, n = D.build_dot(recs_, root_, engine_)
                dd = st_.graphviz
                dd.mkdir(parents=True, exist_ok=True)
                svg_text = D.render_svg(dot_text, engine_)
                written = set()
                if svg_text is not None:            # <- the bug
                    dp = dd / "graph.dot"
                    dp.write_text(dot_text)
                    written.add(dp)
                    sp = dd / "graph.svg"
                    sp.write_text(svg_text)
                    written.add(sp)
                for f in dd.iterdir():
                    if f.is_file() and f not in written:
                        f.unlink()
                return {"dot": dd / "graph.dot",
                        "svg": (dd / "graph.svg") if svg_text else None,
                        "nodes": n, "engine": engine_, "removed": []}

            real_which = D.shutil.which
            D.shutil.which = lambda name: None      # force "no engine"
            D.draw = broken
            try:
                r = D.draw(st, None, ENGINE)
                sabotage_missing = not r["dot"].exists()
            finally:
                D.draw = real_draw
                D.shutil.which = real_which

            # Same forced-absent engine, real code: the DOT must still land.
            D.shutil.which = lambda name: None
            try:
                r2 = D.draw(st, None, ENGINE)
            finally:
                D.shutil.which = real_which
            real_ok = r2["dot"].exists() and r2["dot"].stat().st_size > 0 \
                and r2["svg"] is None

            return sabotage_missing and real_ok, (
                f"sabotaged (dot conditional on svg): dot missing = "
                f"{sabotage_missing}  |  real code, engine forced absent: "
                f"dot written, svg skipped = {real_ok}")
        case("the DOT is written whether or not an engine is present "
             "(sabotaged)", dot_always_written_sabotaged)

        def svg_present_iff_engine_present():
            if not HAVE_GV:
                return None, GV_WHY
            r = D.draw(st, None, ENGINE)
            with_engine = r["svg"] is not None and r["svg"].exists()
            real_which = D.shutil.which
            D.shutil.which = lambda name: None
            try:
                r2 = D.draw(st, None, ENGINE)
            finally:
                D.shutil.which = real_which
            without_engine = r2["svg"] is None \
                and not (st.graphviz / "graph.svg").exists()
            return with_engine and without_engine, (
                f"engine present -> svg written: {with_engine}; "
                f"engine forced absent -> svg skipped and removed: "
                f"{without_engine}")
        case("SVG tracks engine presence exactly", svg_present_iff_engine_present)

        # -- what downstream (a future HTML view, a future two-phase layout)
        #    needs from every record ---------------------------------------

        def edge_class_is_record_layer_sabotaged():
            recs, _ = st.load()
            edge_layer = {r["guid"]: r["layer"] for r in recs
                          if r["record"] == "edge"}
            dot_text, _ = D.build_dot(recs, None, ENGINE)
            found = _dot_edges(dot_text)
            layers_seen = len(set(edge_layer.values()))
            real_ok = (len(found) == len(edge_layer) and layers_seen >= 3
                       and all(found[g] == edge_layer[g] for g in found))

            # SABOTAGE. `class` carries the edge's own *type* instead of its
            # *layer* — the exact confusion the roadmap calls out as the
            # reason to have a class at all: a two-phase layout needs to pull
            # `citation` out of a flat DOT, and `type` cannot answer that.
            real_fn = D._edge_line

            def broken(e):
                return real_fn(e).replace(f'class="{e["layer"]}"',
                                          f'class="{e["type"]}"')
            D._edge_line = broken
            try:
                bad_text, _ = D.build_dot(recs, None, ENGINE)
                bad_found = _dot_edges(bad_text)
                sabotage_wrong = any(bad_found[g] != edge_layer[g]
                                     for g in bad_found)
            finally:
                D._edge_line = real_fn

            return real_ok and sabotage_wrong, (
                f"{len(found)} edges across {layers_seen} distinct layers, "
                f"class matches layer; sabotage (class=type) caught: "
                f"{sabotage_wrong}")
        case("every DOT edge's class is its record layer (sabotaged)",
             edge_class_is_record_layer_sabotaged)

        def node_ids_survive_the_svg_sabotaged():
            if not HAVE_GV:
                return None, GV_WHY
            recs, _ = st.load()
            node_guids = {r["guid"] for r in recs if r["record"] == "node"}

            def parsed_ids(dot_text):
                svg = D.render_svg(dot_text, ENGINE)
                el = ET.fromstring(svg)
                return {e.get("id") for e in el.iter() if e.get("id")}

            dot_text, _ = D.build_dot(recs, None, ENGINE)
            real_ids = parsed_ids(dot_text)
            real_ok = node_guids <= real_ids

            # A substring/grep check would say this feature is broken: some
            # guid gets its hyphens escaped to `&#45;` on the way into the
            # SVG (graphviz's own writer, not this module's), so raw text
            # containment on at least one guid must fail even though the
            # XML-parsed id matches exactly. docs/roadmap.md, "the guid is
            # not in the SVG bytes".
            raw_svg = D.render_svg(dot_text, ENGINE)
            probe = next(iter(node_guids))
            grep_would_say = probe in raw_svg
            xml_says = probe in real_ids

            # SABOTAGE. Nodes with no `id=` at all.
            real_fn = D._node_line

            def broken(n):
                return f'  "{n["guid"]}" [label="x"];'
            D._node_line = broken
            try:
                bad_text, _ = D.build_dot(recs, None, ENGINE)
                bad_ids = parsed_ids(bad_text)
                sabotage_missing = len(node_guids & bad_ids) == 0
            finally:
                D._node_line = real_fn

            return real_ok and sabotage_missing, (
                f"{len(node_guids)} node guids all present in the "
                f"XML-parsed SVG; substring match on one guid: "
                f"{grep_would_say}, XML-parsed: {xml_says} "
                f"(false negative avoided); sabotage (no id=) caught: "
                f"{sabotage_missing}")
        case("every node's id= guid survives into the SVG, "
             "asserted through an XML parser (sabotaged)",
             node_ids_survive_the_svg_sabotaged)

        def no_clusters_sabotaged():
            recs, _ = st.load()
            dot_text, _ = D.build_dot(recs, None, ENGINE)
            real_ok = "subgraph cluster" not in dot_text

            # SABOTAGE. `twopi` — the default engine — ignores clusters
            # entirely (measured: 0 cluster elements against 4 from `dot` on
            # the same file), so one sneaking back in would be invisible
            # work rather than a loud failure. docs/roadmap.md, "Not
            # `subgraph cluster_` per root."
            real_fn = D.build_dot

            def broken(recs_, root_, engine_):
                text, n = real_fn(recs_, root_, engine_)
                text = text.replace(
                    "digraph compost {",
                    "digraph compost {\n  subgraph cluster_bug { }")
                return text, n
            D.build_dot = broken
            try:
                bad_text, _ = D.build_dot(recs, None, ENGINE)
                sabotage_caught = "subgraph cluster" in bad_text
            finally:
                D.build_dot = real_fn

            return real_ok and sabotage_caught, (
                f"no cluster in real output; injected one caught: "
                f"{sabotage_caught}")
        case("no subgraph cluster_, ever (sabotaged)", no_clusters_sabotaged)

        # -- the graph view is still a view: refuses a broken base ----------

        def refuses_when_check_fails_sabotaged():
            st_bad = build_broken_base(tmp)
            real_problems = R.check(st_bad.load()[0])

            refused = False
            try:
                D.draw(st_bad, None, ENGINE)
            except RuntimeError:
                refused = True

            # SABOTAGE. Disable the guard `draw` calls, the same way
            # test_response.py disables `_structural_gaps` to show its
            # refusal is load-bearing.
            real_check = D.R.check
            D.R.check = lambda recs: []
            try:
                drew_anyway = False
                try:
                    D.draw(st_bad, None, ENGINE)
                    drew_anyway = True
                except RuntimeError:
                    drew_anyway = False
            finally:
                D.R.check = real_check

            return bool(real_problems) and refused and drew_anyway, (
                f"{len(real_problems)} real problems, refused: {refused}; "
                f"guard disabled (sabotaged): drew anyway = {drew_anyway}")
        case("draw refuses when check fails, like render (sabotaged)",
             refuses_when_check_fails_sabotaged)

        # -- the synthetic root is DOT-local, never a record -----------------

        def synthetic_root_never_a_record():
            before, _ = st.load()
            r = D.draw(st, None, ENGINE)
            after, _ = st.load()
            guids_after = {rec["guid"] for rec in after}
            dot_text = r["dot"].read_text()
            return (D.SYNTH_ROOT in dot_text
                    and D.SYNTH_ROOT not in guids_after
                    and len(after) == len(before)
                    and not R.check(after)), (
                f"'{D.SYNTH_ROOT}' appears in the DOT, not among "
                f"{len(after)} records; check still clean")
        case("the synthetic root is DOT-local, never a record",
             synthetic_root_never_a_record)

        # -- ROOT draws exactly that root's subgraph, no more ----------------

        def root_scoping():
            recs, _ = st.load()
            dot_text, n = D.build_dot(recs, target_root, ENGINE)
            reach = D._tree_reach(recs, target_root)
            drawn = set(re.findall(r'^  "([0-9a-f-]{36})" \[id=', dot_text,
                                   re.M))
            # The citing document's own paragraph never appears — it is a
            # different root's subtree — and neither does the `cites` edge
            # into this one, since only one endpoint would be inside.
            citing_recs, _ = st.load()
            citing_only = D._tree_reach(citing_recs, citing_root) - reach
            leaked = citing_only & drawn
            return (n == len(reach) and drawn == reach and not leaked
                    and 'class="citation"' not in dot_text), (
                f"{n} nodes, exactly the {len(reach)} under this root; "
                f"nothing leaked from the citing document")
        case("ROOT draws exactly that root's subgraph", root_scoping)

        # -- never refuses on size, only warns --------------------------------

        def warns_but_never_refuses():
            # `D.main` finds its base via `Store.find()` from the cwd, the
            # same as every other subcommand's `main` — so this one needs to
            # actually run from inside the base, like test_layer.py's
            # `default_is_still_uuid_link` does for `layers.main`.
            here = Path.cwd()
            os.chdir(st.root)
            try:
                real_warn = D.WARN_NODES
                D.WARN_NODES = 0          # force the branch on a tiny base
                try:
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        rc_over = D.main(["draw"])
                    over_text = out.getvalue()
                finally:
                    D.WARN_NODES = real_warn
                out2 = io.StringIO()
                with contextlib.redirect_stdout(out2):
                    rc_under = D.main(["draw"])
                under_text = out2.getvalue()
            finally:
                os.chdir(here)
            return (rc_over == 0 and "warning" in over_text
                    and rc_under == 0 and "warning" not in under_text), (
                f"threshold forced below base size: warns, rc={rc_over}; "
                f"default threshold: no warning, rc={rc_under}")
        case("past the node-count threshold it warns; it never refuses",
             warns_but_never_refuses)

        # -- draw owns its whole directory ------------------------------------

        def stale_sweep_sabotaged():
            # A run that leaves an extra file behind, planted directly —
            # the state a broken sweep (one that only removes filenames it
            # is about to overwrite, rather than everything it did not just
            # write) would leave. "draw owns its stale sweep" exists to
            # prevent exactly this, the same way `render_all` sweeps
            # `views/`. docs/roadmap.md, "v0.2.7 — a graph view".
            D.draw(st, None, ENGINE)
            stray = st.graphviz / "leftover-from-a-deleted-document.dot"
            stray.write_text("digraph stale {}\n")
            sabotage_visible = stray.exists()

            D.draw(st, target_root, ENGINE)
            real_ok = not stray.exists()
            after = sorted(f.name for f in st.graphviz.iterdir())

            return sabotage_visible and real_ok, (
                f"a planted stray file existed before the next run; "
                f"real sweep removed it, leaving only {after}")
        case("a run leaves only its own output behind (sabotaged)",
             stale_sweep_sabotaged)

    for ok, name, detail in results:
        mark = "skip" if ok is None else ("pass" if ok else "FAIL")
        print(f"  {mark}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if ok is False)
    skipped = sum(1 for ok, _, _ in results if ok is None)
    ran = len(results) - skipped
    tail = f"   ({skipped} skipped: {GV_WHY})" if skipped else ""
    print(f"\n{ran - bad}/{ran} draw guarantees hold{tail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

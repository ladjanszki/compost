#!/usr/bin/env python3
"""
test_views.py — what the three default views promise.

Views are generated and disposable, so the tests here are about what a reader
gets, not about bytes: every citable block reachable in a document shows its
handle, the markdown view stays clean enough to commit as README.md, and each
view is valid in its own format.
"""
import contextlib
import io
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R    # noqa: E402
from src import routes as RT    # noqa: E402
from tests import tier as T  # noqa: E402
from src import store as S      # noqa: E402
from src import views as V      # noqa: E402

HERE = Path(__file__).parent
SAMPLE = (T.markdown("edge-cases")
          + sorted((HERE / "fixtures/notes").glob("note-0[1-3].md")))
HANDLE = re.compile(r"\{#[0-9a-f]{8}\}")


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    with tempfile.TemporaryDirectory() as d:
        st = S.Store.init(Path(d))
        # Built through the real ingestion path rather than by hand, so the
        # base under test has the shape `compost digest` actually produces —
        # blob nodes, `derived_from` edges and all. A view test that builds
        # its own records can only ever check the views against itself.
        with contextlib.redirect_stdout(io.StringIO()):
            S._digest(st, "notes", [str(f) for f in SAMPLE], "compost")
        V.render_all(st)
        recs, _ = st.load()
        g = R.Graph(recs)
        docs = [n for n in g.nodes.values() if n["type"] == "document"]

        def citable(doc):
            def walk(guid):
                for k in g.children(guid):
                    n = g.nodes[k]
                    if n["type"] in V.CITABLE:
                        yield n
                    yield from walk(k)
            return list(walk(doc["guid"]))

        # Not recomputed here: a view test that derives its own filenames
        # cannot notice the day two documents start sharing one.
        NAMES = V.view_names(docs)

        def name_of(doc):
            return NAMES[doc["guid"]]

        def every_block_shows_a_handle():
            missing = 0
            for doc in docs:
                txt = (st.views / "default-djot" / f"{name_of(doc)}.dj").read_text()
                parent = {e["destination"]: e["source"] for e in recs
                          if e["record"] == "edge" and e["type"] == "contains"}
                for n in citable(doc):
                    if V.handle(n["guid"]) in txt:
                        continue
                    # A list item's own first paragraph shares the item's
                    # handle on purpose; anything else is a real gap.
                    p = g.nodes.get(parent.get(n["guid"], ""), {}).get("type")
                    if not (p == "ListItem" and n["type"] in ("Plain", "Para")):
                        missing += 1
            return missing == 0, f"{missing} citable blocks without a handle"
        case("every citable block shows its handle (djot)",
             every_block_shows_a_handle)

        def html_ids():
            missing = 0
            for doc in docs:
                txt = (st.views / "default-html" / f"{name_of(doc)}.html").read_text()
                for n in citable(doc):
                    if f'id="{V.handle(n["guid"])}"' not in txt:
                        missing += 1
            return missing == 0, f"{missing} blocks without an html id"
        case("every citable block is an html anchor", html_ids)

        def md_is_clean():
            injected = 0
            for doc in docs:
                view = (st.views / "default-md" / f"{name_of(doc)}.md").read_text()
                blob = R.blob_of(recs, doc["guid"])
                src = (st.storage / R._p(blob, "stored_as")).read_text()
                if len(HANDLE.findall(view)) != len(HANDLE.findall(src)):
                    injected += 1
            return injected == 0, "markdown carries only the handles the source had"
        case("the markdown view injects no handles", md_is_clean)

        def no_document_is_overwritten():
            # SAMPLE deliberately contains two different files both named
            # nested-lists.md. Before view names were disambiguated, one of
            # them silently overwrote the other's pages and `render` reported
            # writing files that held the wrong document.
            stems = [name_of(d) for d in docs]
            pages = list((st.views / "default-html").glob("*.html"))
            return len(set(stems)) == len(docs) and len(pages) == len(docs) + 1, \
                f"{len(docs)} documents, {len(set(stems))} distinct names"
        case("every document gets its own view file", no_document_is_overwritten)

        def views_parse():
            bad = []
            for doc in docs:
                for sub, ext, fmt in (("default-djot", ".dj", "djot"),
                                      ("default-md", ".md", "commonmark_x"),
                                      ("default-html", ".html", "html")):
                    f = st.views / sub / f"{name_of(doc)}{ext}"
                    r = subprocess.run(["pandoc", "-f", fmt, "-t", "json", str(f)],
                                       capture_output=True, text=True)
                    if r.returncode:
                        bad.append(f.name)
            return not bad, f"{len(docs) * 3} view files all parse"
        case("every view is valid in its own format", views_parse)

        def handles_unique():
            return not [p for p in R.check(recs) if "shared by two nodes" in p], \
                f"{len(g.nodes)} nodes, no 8-character handle collision"
        case("short handles do not collide", handles_unique)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<46} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} view guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

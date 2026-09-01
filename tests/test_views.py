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

    # -- v0.2.9: page furniture -----------------------------------------
    # These are properties of the CSS/JS strings and of a *document* root,
    # not of a session — the slash-command guarantees that need a transcript
    # are in test_session_views.py instead.
    with tempfile.TemporaryDirectory() as d2:
        st2 = S.Store.init(Path(d2))
        note = Path(d2) / "note-with-a-literal-tag.md"
        note.write_text(
            "<command-name>/exit</command-name> is not a real command here, "
            "just prose that happens to open with one of the three "
            "harness-reserved tags.\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            S._digest(st2, "notes", [str(note)], "compost")
        V.render_all(st2)
        html_pages = [f for f in (st2.views / "default-html").glob("*.html")
                      if f.name != "index.html"]
        doc_html = html_pages[0].read_text()

        def document_root_untouched_by_slash_handling():
            # `_session_children` — where the caveat is suppressed and the
            # command rewritten — is reached only when the AST root is a
            # `session` (`_ast`, src/views.py). A `document` root never
            # passes through it, so its own literal <command-name> survives
            # verbatim rather than being rewritten to a bare "/exit" line.
            # Sabotage: routing every root through `_session_children`
            # (dropping the `n["type"] == "session"` guard) rewrites this
            # paragraph the same way a transcript's would be, and the raw
            # tag disappears from the page.
            return ("<command-name>/exit</command-name>" in doc_html
                    and 'class="block"' in doc_html), \
                "a document's own <command-name>-leading paragraph is unchanged"
        case("a document root is untouched by slash-command handling",
             document_root_untouched_by_slash_handling)

        def no_before_content_is_a_guid():
            # The v0.2.9 regression, stated as a property: `.block::before`
            # used to print `attr(id)`, and the id is a 36-character guid —
            # a monospace string sized for the 8-character handle v0.2 no
            # longer has. Sabotage: putting `attr(id)` back in the `content`
            # declaration reproduces the unreadable page.
            return "attr(id)" not in V.CSS, \
                "no ::before rule's content is the block's id"
        case("no CSS ::before content is the block's guid",
             no_before_content_is_a_guid)

        def click_handler_has_no_geometry_gate():
            # The regression: `onHandle` computed from cursor position, and a
            # `window.innerWidth > 992` escape hatch that happened to cover
            # the human's own window size. Sabotage: reintroducing either
            # check makes clicking the body of a block (off the old gutter,
            # on a wide window) silently do nothing again.
            return ("innerWidth" not in V.JS
                    and "getBoundingClientRect" not in V.JS), \
                "the click handler has no width comparison and no geometry test"
        case("the click handler contains no window-width comparison",
             click_handler_has_no_geometry_gate)

        def author_selectors_name_only_real_authors():
            # Guarantee 14, added while verifying v0.2.9. Every value a
            # `[data-author...]` selector names must be in the closed
            # vocabulary of docs/record-grammar.md §6 — `human`, `assistant`,
            # `envelope`. v0.1's authors were different, and porting its
            # `^="claude"` / `^="agent"` rules verbatim left two selectors
            # matching nothing on every page, so assistant turns kept the
            # default grey rule and "you can tell who is speaking" was only
            # half delivered. A dead selector is silent, which is why this is
            # a property and not a review note.
            # Sabotage: rename one selector's value to "claude" and this fires.
            AUTHORS = {"human", "assistant", "envelope"}
            named = set(re.findall(r'\[data-author[\^$*]?="([^"]+)"\]', V.CSS))
            unknown = named - AUTHORS
            return not unknown and {"human", "assistant"} <= named, \
                f"author selectors name {sorted(named)}, unknown {sorted(unknown)}"
        case("every author selector names a real author value",
             author_selectors_name_only_real_authors)

        def shift_does_not_reach_the_clipboard():
            # v0.1's shift-click copied `{#id+++}`, a citation syntax v0.2
            # does not resolve. Asserted on the source rather than by
            # simulating a keypress, because this is the one behaviour a
            # future reader is most likely to "restore" from v0.1 without
            # noticing the syntax it produced is dead. Sabotage: making the
            # click handler read `e.shiftKey` and append '+++' reproduces it.
            m = re.search(r"addEventListener\('click',.*?\n\}\);", V.JS, re.S)
            click_block = m.group(0) if m else ""
            return (bool(click_block)
                    and "shift" not in click_block.lower()
                    and "+++" not in click_block
                    and "'[-](#' + el.id + ')'" in click_block), \
                "the click handler builds '[-](#guid)' without reading Shift"
        case("the copied string is byte-identical with and without Shift, "
             "and has no +", shift_does_not_reach_the_clipboard)

        def hl_and_hl_sub_share_one_background():
            # One highlight, one meaning. A single declaration for both
            # selectors makes two different values impossible by
            # construction; sabotage is splitting them into two rules that
            # could then drift apart, e.g. restoring v0.1's amber `.hl-sub`.
            m = re.search(r"\.hl,\s*\.hl-sub\s*\{([^}]*)\}", V.CSS)
            return m is not None and "background" in m.group(1), \
                ".hl and .hl-sub are one declaration, so one background value"
        case(".hl and .hl-sub resolve to the same background",
             hl_and_hl_sub_share_one_background)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<46} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} view guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

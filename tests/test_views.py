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

    # -- v0.2.10: the index page, and display names --------------------
    # Guarantee 11 needs no base at all — it is a property of the CSS string.
    def no_dark_media_block():
        # Sabotage: putting `@media (prefers-color-scheme: dark)` back (the
        # v0.2.9 shape) reproduces the page rendering dark on a dark-set
        # machine, which is not the forced-light look this release chose.
        return ("prefers-color-scheme" not in V.CSS
                and "--bg:#fff" in V.CSS), \
            "no dark media query, and --bg is the light token"
    case("the CSS defines no prefers-color-scheme block, and --bg is light",
         no_dark_media_block)

    def _rows(html):
        return re.findall(r'<a href="([^"]+)">([^<]*)</a>', html)

    def _row_for(html, href):
        m = re.search(r'<tr><td><a href="' + re.escape(href)
                      + r'"[^>]*>.*?</tr>', html, re.S)
        return m.group(0) if m else ""

    with tempfile.TemporaryDirectory() as d3:
        st3 = S.Store.init(Path(d3))
        # Three documents, digested one `R._now` value apart so their blobs'
        # `imported_at` are distinct and the sort-order guarantee has a real
        # order to check rather than a same-second tie. `_digest` is the only
        # caller of `R._now()` on the ingest path (`store.py`'s blob node), so
        # patching the module-level function reaches it without touching
        # `_digest` itself.
        orig_now = R._now
        docs_order = [("note-01.md", "2026-01-01T00:00:00Z"),
                      ("note-02.md", "2026-01-02T00:00:00Z"),
                      ("note-03.md", "2026-01-03T00:00:00Z")]
        try:
            for fname, ts in docs_order:
                R._now = lambda ts=ts: ts
                with contextlib.redirect_stdout(io.StringIO()):
                    S._digest(st3, "notes",
                              [str(HERE / "fixtures/notes" / fname)], "compost")
        finally:
            R._now = orig_now

        with contextlib.redirect_stdout(io.StringIO()):
            # session-smoke, digested twice: the duplicate-row guarantee, and
            # exactly the design doc's own real example — one thing ingested
            # more than once, each ingest minting fresh guids, nothing collapsed.
            S._digest(st3, "claude-code-transcript",
                      [str(HERE / "fixtures/sessions/session-smoke.jsonl")],
                      "compost")
            S._digest(st3, "claude-code-transcript",
                      [str(HERE / "fixtures/sessions/session-smoke.jsonl")],
                      "compost")
            # A second, distinct session — its turns run in 2026, session-smoke's
            # in 2003 — so the sort-order guarantee has a genuine, known order
            # to check rather than only a tied pair.
            S._digest(st3, "claude-code-transcript",
                      [str(HERE / "fixtures/sessions/session-slash.jsonl")],
                      "compost")

        recs3, _ = st3.load()
        nodes3 = {r["guid"]: r for r in recs3 if r["record"] == "node"}
        doc_by_source = {R._p(n, "source"): n["guid"] for n in nodes3.values()
                         if n["type"] == "document"}
        note01 = doc_by_source["note-01.md"]
        note02 = doc_by_source["note-02.md"]
        note03 = doc_by_source["note-03.md"]
        session_roots = [n["guid"] for n in nodes3.values()
                         if n["type"] == "session"]
        smoke_roots = [g for g in session_roots
                      if R._p(nodes3[g], "source") == "session-smoke.jsonl"]
        slash_root = next(g for g in session_roots
                          if R._p(nodes3[g], "source") == "session-slash.jsonl")

        def _render3():
            V.render_all(st3)
            recs, _ = st3.load()
            g = R.Graph(recs)
            idx = (st3.views / "default-html" / "index.html").read_text()
            docs = [n for n in g.nodes.values() if n["type"] in R.ROOT_TYPES]
            names = V.view_names(docs)
            return recs, g, idx, names

        recs3, g3, idx3, names3 = _render3()

        def unnamed_roots_show_their_stem():
            rows = dict(_rows(idx3))
            return (rows.get(names3[note02] + ".html") == "note-02"
                    and rows.get(names3[note03] + ".html") == "note-03"), \
                "a root with no display_name shows its filename stem"
        case("a root with no display_name shows its filename stem",
             unnamed_roots_show_their_stem)

        # Written by hand, straight into graph/ — the supported path CLAUDE.md
        # blesses ("anything may write records; check is the gate") and the
        # one `compost-name` itself uses under the hood.
        b1 = R.Builder()
        dn1 = b1.node(V.DISPLAY_NAME_TYPE, {"value": "The Curated Title"})
        b1.edge("names", dn1, note01, V.DISPLAY_LAYER)
        R.stamp_hashes(b1.records)   # a leaf, same fold `compost-name` runs
        st3.write("display-1.jsonl", b1.records)
        pages_before = {f.name for f in (st3.views / "default-html").glob("*.html")}
        recs3, g3, idx3, names3 = _render3()

        def named_root_shows_name_and_keeps_its_file():
            rows = dict(_rows(idx3))
            href = names3[note01] + ".html"
            pages_after = {f.name for f in (st3.views / "default-html").glob("*.html")}
            return (rows.get(href) == "The Curated Title"
                    and pages_after == pages_before), \
                (f"row text {rows.get(href)!r}, "
                 f"page filenames unchanged: {pages_after == pages_before}")
        case("a root with a display_name shows the name; the page filename "
             "is unchanged", named_root_shows_name_and_keeps_its_file)

        # A second display name for the same root, with controlled
        # `created_at` values (via `R._now`) so "the newer wins" is checked
        # against a known timestamp instead of racing the wall clock — the
        # first display name above was written with the real one, which is
        # between these two.
        try:
            R._now = lambda: "2020-01-01T00:00:00Z"
            b_old = R.Builder()
            dn_old = b_old.node(V.DISPLAY_NAME_TYPE, {"value": "An Older Name"})
            b_old.edge("names", dn_old, note01, V.DISPLAY_LAYER)
            R.stamp_hashes(b_old.records)
            st3.write("display-old.jsonl", b_old.records)

            R._now = lambda: "2030-01-01T00:00:00Z"
            b_new = R.Builder()
            dn_new = b_new.node(V.DISPLAY_NAME_TYPE, {"value": "A Newer Name"})
            b_new.edge("names", dn_new, note01, V.DISPLAY_LAYER)
            R.stamp_hashes(b_new.records)
            st3.write("display-new.jsonl", b_new.records)
        finally:
            R._now = orig_now

        recs3, g3, idx3, names3 = _render3()
        win1 = dict(_rows(idx3)).get(names3[note01] + ".html")
        recs3, g3, idx3b, names3b = _render3()
        win2 = dict(_rows(idx3b)).get(names3b[note01] + ".html")

        def newest_display_name_wins_stably():
            # Sabotage: picking the first `names` edge found, or the oldest,
            # instead of comparing `created_at`, shows "The Curated Title" or
            # "An Older Name" here instead.
            return win1 == "A Newer Name" == win2, \
                f"first render: {win1!r}, second render: {win2!r}"
        case("with two display_name nodes, the newer created_at wins, "
             "stably across renders", newest_display_name_wins_stably)

        def display_name_node_passes_check_via_uncontained():
            b4 = R.Builder()
            dn4 = b4.node(V.DISPLAY_NAME_TYPE, {"value": "Check Target"})
            b4.edge("names", dn4, note01, V.DISPLAY_LAYER)
            R.stamp_hashes(b4.records)
            test_recs = recs3 + b4.records
            clean = [p for p in R.check(test_recs) if dn4 in p]
            original = R.UNCONTAINED
            try:
                # Sabotage: without "display_name" in UNCONTAINED, `check`
                # demands exactly one `contains` parent and reports 0.
                R.UNCONTAINED = original - {"display_name"}
                sabotaged = R.check(test_recs)
            finally:
                R.UNCONTAINED = original
            reported = any(dn4 in p and "0 parents" in p for p in sabotaged)
            return not clean and reported, \
                f"clean problems: {clean}, sabotaged catches it: {reported}"
        case("a display_name node passes check via UNCONTAINED, and fails "
             "without it", display_name_node_passes_check_via_uncontained)

        def index_has_one_section_per_root_type():
            sections = re.findall(r"<h2>(.*?)</h2>", idx3)
            base_ok = len(sections) == len(R.ROOT_TYPES)
            docs3 = [n for n in g3.nodes.values() if n["type"] in R.ROOT_TYPES]
            original = R.ROOT_TYPES
            try:
                # Sabotage: a hardcoded ["Sessions", "Documents"] pair would
                # still show two sections here, never three.
                R.ROOT_TYPES = original | {"conversation"}
                grown = V.render_index(g3, recs3, docs3, V.view_names(docs3))
            finally:
                R.ROOT_TYPES = original
            grown_sections = re.findall(r"<h2>(.*?)</h2>", grown)
            grew = (len(grown_sections) == len(sections) + 1
                    and "no conversations yet" in grown)
            return base_ok and grew, \
                (f"{len(sections)} sections for {len(R.ROOT_TYPES)} root "
                 f"types; a third type grows the page to {len(grown_sections)}")
        def dates_are_scannable():
            # Guarantee 16, added in review. The roadmap asked for date
            # columns and never said what a date looks like, so the raw
            # record value shipped: `2003-08-05T16:30:57.370Z` in a table
            # column. `_when` trims to minutes for display only; the record
            # keeps every digit. Sabotage: return `ts` unchanged from
            # `_when` and the T, the seconds and the Z come back.
            bad = re.findall(r"<td>[^<]*T\d\d:\d\d:\d\d[^<]*</td>", idx3)
            return not bad, f"{len(bad)} raw ISO timestamps in table cells"
        case("date columns are trimmed to minutes, not raw ISO",
             dates_are_scannable)

        case("the index has exactly len(ROOT_TYPES) sections, and adding a "
             "root type grows the page by one",
             index_has_one_section_per_root_type)

        def every_row_links_to_a_real_file():
            rows = _rows(idx3)
            missing = [href for href, _ in rows
                      if not (st3.views / "default-html" / href).exists()]
            return bool(rows) and not missing, \
                f"{len(rows)} rows, {len(missing)} linking to a missing file"
        case("every row links to a file that exists", every_row_links_to_a_real_file)

        def session_row_first_last_are_turn_min_max():
            # Computed independently here, not read back off the view: every
            # turn carries its own timestamp, and this recomputes min/max from
            # the graph rather than trusting what render_index already wrote.
            mismatches = []
            for root in session_roots:
                turns = [g3.nodes[k] for k in g3.children(root)
                        if g3.nodes[k]["type"] == "turn"]
                times = sorted(R._p(t, "timestamp") for t in turns
                              if R._p(t, "timestamp"))
                row = _row_for(idx3, names3[root] + ".html")
                # min/max still computed from the graph here; only the
                # display trim is shared with the code under test, and
                # guarantee 16 pins that separately.
                if not (row and V._when(times[0]) in row
                        and V._when(times[-1]) in row):
                    mismatches.append(root)
            return bool(session_roots) and not mismatches, \
                f"{len(session_roots)} sessions, {len(mismatches)} mismatched"
        case("a session row's first/last are the min/max of its turns' "
             "timestamps", session_row_first_last_are_turn_min_max)

        def document_row_imported_from_blob_not_filename():
            ok = True
            for root in (note01, note02, note03):
                blob = R.blob_of(recs3, root)
                imported = R._p(blob, "imported_at")
                row = _row_for(idx3, names3[root] + ".html")
                if not (imported and row and V._when(imported) in row):
                    ok = False
            return ok, "each document's imported cell matches its blob's imported_at"
        case("a document row's imported time comes from its blob via "
             "derived_from, not any filename",
             document_row_imported_from_blob_not_filename)

        def sections_sorted_descending():
            doc_section = idx3.split("<h2>Documents</h2>", 1)[1] \
                              .split("<h2>", 1)[0]
            sess_section = idx3.split("<h2>Sessions</h2>", 1)[1]
            doc_hrefs = [h for h, _ in _rows(doc_section)]
            sess_hrefs = [h for h, _ in _rows(sess_section)]
            # Constructed so the true order is known: note-03's blob is the
            # newest import, note-01's the oldest; session-slash's turns run
            # in 2026, session-smoke's (both copies) in 2003.
            expect_docs = [names3[note03] + ".html", names3[note02] + ".html",
                          names3[note01] + ".html"]
            slash_href = names3[slash_root] + ".html"
            return (doc_hrefs == expect_docs
                    and sess_hrefs[0] == slash_href
                    and set(sess_hrefs[1:]) == {names3[g] + ".html"
                                                for g in smoke_roots}), \
                f"documents: {doc_hrefs}; sessions: {sess_hrefs}"
        case("each section is sorted descending on its stated key",
             sections_sorted_descending)

        def duplicate_session_gets_two_rows():
            sess_section = idx3.split("<h2>Sessions</h2>", 1)[1]
            rows = _rows(sess_section)
            smoke_hrefs = {names3[g] + ".html" for g in smoke_roots}
            present = [h for h, _ in rows if h in smoke_hrefs]
            return len(smoke_roots) == 2 and len(present) == 2, \
                f"{len(smoke_roots)} smoke session roots, {len(present)} rows"
        case("a session digested twice gets two rows, not one",
             duplicate_session_gets_two_rows)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<46} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} view guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

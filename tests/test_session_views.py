#!/usr/bin/env python3
"""
test_session_views.py — rendering a transcript.

The djot view shows everything, because djot has no collapse and because an
agent that cannot see the output cannot reason about it. The html view collapses
tool output into <details>, because a human is scrolling. Same graph, two
readings — which is the point of generating views from records rather than
from a document.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli              # noqa: E402
from src import records as R    # noqa: E402
from tests import tier as T  # noqa: E402
from src import session as SESS  # noqa: E402
from src import store as S      # noqa: E402
from src import store as ST
from src import views as V      # noqa: E402

HERE = Path(__file__).parent
# The sidechain pair is excluded here and digested separately below: it is
# five lines, and letting it into this slice would silently push a substantial
# corpus session out of the sample.
SESSIONS = [f for f in T.sessions() if f.name != "sidechain-parent.jsonl"][:3]
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


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
        roots = {}
        for f in SESSIONS:
            recs, root = SESS.session_to_records(f)
            st.write(f"{f.stem}.jsonl", recs)
            roots[f.stem] = root
        # The sidechain pair goes in through `digest`, because the subagent
        # view depends on a `launched` edge and only ingestion mints one.
        with contextlib.redirect_stdout(io.StringIO()):
            ST._digest(st, "claude-code-transcript",
                       [str(HERE / "fixtures/sessions/sidechain-parent.jsonl")],
                       "compost")
        V.render_all(st)
        recs, _ = st.load()
        g = R.Graph(recs)
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        kids = {}
        for r in recs:
            if r["record"] == "edge" and r["type"] == "contains":
                kids.setdefault(r["source"], []).append(r["destination"])
        # Read what was rendered, not what was expected to be. Keying off
        # `roots` meant the cases below silently ignored any page the renderer
        # produced from a source this suite did not write itself — which is
        # every subagent's parent, once digest started pulling extra files in.
        djot = {f.stem: f.read_text()
                for f in (st.views / "default-djot").glob("*.dj")}
        html = {f.stem: f.read_text()
                for f in (st.views / "default-html").glob("*.html")
                if f.name != "index.html"}

        def every_session_rendered():
            # Every session *except* one that something launched: a subagent
            # is rendered inside the call that ran it, so a page of its own
            # would be the same transcript twice.
            launched = {r["destination"] for r in recs
                        if r["record"] == "edge" and r["type"] == "launched"}
            entry = [n for n in nodes.values() if n["type"] == "session"
                     and n["guid"] not in launched]
            return len(djot) == len(entry) and all(djot.values()), \
                f"{len(entry)} entry-point sessions, {len(djot)} rendered"
        case("a session gets a view at all", every_session_rendered)

        def shown(n):
            """Nodes a view is expected to render.

            Several things are stored and deliberately not rendered, and every
            exclusion is a decision recorded in `views.py` rather than an
            accident: a `thinking` node with no text, and a slash command's
            `<local-command-caveat>` paragraph (v0.2.9 — an instruction to the
            model, not something the human said). A `turn` is shown exactly
            when at least one of its children is (v0.2.9's general rule,
            `views.py`'s `_render_session`, replacing the older special case
            for an envelope turn specifically — that case is now just one way
            for every child to be unshown, not a rule of its own). Being in
            the graph and being on the page are different things.
            """
            if n["type"] == "thinking" and n["params"].get("empty"):
                return False
            if n["type"] == "Para" and V._lead_tag(n) == V.SLASH_CAVEAT:
                return False
            if n["type"] == "turn":
                kk = kids.get(n["guid"], [])
                return bool(kk) and any(shown(nodes[k]) for k in kk)
            return True

        def turns_appear():
            turns = [n for n in nodes.values()
                     if n["type"] == "turn" and shown(n)]
            text = "\n".join(djot.values())
            missing = [t for t in turns if t["guid"] not in text]
            return turns and not missing, \
                f"{len(turns)} turns with content, {len(missing)} missing"
        case("every turn appears with its handle", turns_appear)

        def envelopes_are_stored_but_not_shown():
            # The importer used to skip these lines outright, losing the uuid,
            # timestamp, parentUuid and toolUseResult that came with them. They
            # are nodes now. That must not put 140 blank frames on the page.
            env = [n for n in nodes.values() if n["type"] == "turn"
                   and n["params"].get("author") == "envelope"
                   and not kids.get(n["guid"])]
            text = "\n".join(djot.values())
            leaked = [n for n in env if n["guid"] in text]
            whole = [n for n in env if n["params"].get("log")]
            return env and not leaked and len(whole) == len(env), \
                f"{len(env)} envelope turns, all carrying their log, none rendered"
        case("envelope turns are kept in the graph and stay off the page",
             envelopes_are_stored_but_not_shown)

        def authors_carried():
            text = "\n".join(djot.values())
            return ('author="human"' in text
                    and 'author="assistant"' in text), \
                "author survives onto the rendered turn"
        case("attribution reaches the view", authors_carried)

        def output_is_whole_in_djot():
            outs = [n for n in nodes.values() if n["type"] == "tooloutput"
                    and n["params"].get("text")]
            text = "\n".join(djot.values())
            dropped = 0
            for o in outs:
                raw = o["params"]["text"]
                # List-shaped content (v0.2.13, total mapping: a list-shaped
                # `tool_result.content` is stored whole rather than flattened)
                # is rendered as pretty JSON, same as the view does.
                rendered = (json.dumps(raw, indent=1, ensure_ascii=False)
                           if isinstance(raw, list) else raw)
                first = rendered.strip().split("\n")[0][:40]
                if first and first not in text:
                    dropped += 1
            return outs and not dropped, \
                f"{len(outs)} outputs, {dropped} with content missing"
        case("djot shows tool output in full", output_is_whole_in_djot)

        def html_collapses():
            # Tool output collapses, and so does a subagent transcript — it is
            # the output of its `Agent` call, arriving in another file. A tool
            # call's own input collapses too (v0.2.9), and so does a slash
            # command's stdout (same `tooloutput` pattern, v0.2.9) — same
            # reasoning throughout: a human is scrolling. One folding mechanism
            # for all four, which is why the count is a sum.
            n_details = sum(t.count("<details>") for t in html.values())
            outs = sum(1 for n in nodes.values() if n["type"] == "tooloutput")
            calls = sum(1 for n in nodes.values() if n["type"] == "toolcall")
            subs = sum(1 for r in recs if r["record"] == "edge"
                       and r["type"] == "launched")

            def nonempty_stdout(n):
                if n["type"] != "Para" or V._lead_tag(n) != V.SLASH_STDOUT:
                    return False
                return bool(V._ANSI_RE.sub("", R.plain_text(n)).strip())
            stdouts = sum(1 for n in nodes.values() if nonempty_stdout(n))

            return n_details == outs + calls + subs + stdouts, \
                f"{n_details} <details> for {outs} outputs + " \
                f"{calls} tool-call inputs + {subs} subagents + " \
                f"{stdouts} slash-command stdouts"
        case("html collapses tool output and subagents", html_collapses)

        def djot_has_no_raw_html():
            leaked = sum(t.count("<details>") for t in djot.values())
            return leaked == 0, "no html leaks into the djot view"
        case("the collapse is html-only", djot_has_no_raw_html)

        def empty_thinking_hidden():
            th = [n for n in nodes.values() if n["type"] == "thinking"]
            empty = [t for t in th if t["params"]["empty"]]
            text = "\n".join(djot.values())
            shown = [t for t in empty if t["guid"] in text]
            return empty and not shown, \
                f"{len(empty)} empty thinking nodes, none rendered"
        case("empty thinking nodes are not invented into the view",
             empty_thinking_hidden)

        def handles_are_uuids():
            # Scanning for short handles would be wrong: the bleached prose
            # carries 8-character citations of its own, which are content.
            # The question is only whether *injected* handles are full guids.
            text = "\n".join(djot.values())
            citable = [n for n in nodes.values()
                       if n["type"] in V.CITABLE | V.SELF_LABELLING
                       and shown(n) and n["type"] != "session"]
            missing = [n for n in citable if n["guid"] not in text]
            full = re.findall(r"\{#(" + UUID + r")\}", text)
            return citable and not missing and full, \
                f"{len(citable)} citable nodes all present, " \
                f"{len(full)} full-uuid handle markers"
        case("every citable node carries a full-uuid handle",
             handles_are_uuids)

        def djot_reparses():
            bad = []
            for name, text in djot.items():
                r = subprocess.run(["pandoc", "-f", "djot", "-t", "json"],
                                   input=text, capture_output=True, text=True)
                if r.returncode:
                    bad.append(name)
            return not bad, f"{len(djot)} djot views all parse"
        case("the djot view is valid djot", djot_reparses)

        def toolcalls_named():
            calls = [n for n in nodes.values() if n["type"] == "toolcall"]
            text = "\n".join(djot.values())
            named = sum(1 for c in calls
                        if f'name="{c["params"]["name"]}"' in text)
            return calls and named == len(calls), \
                f"{named}/{len(calls)} tool calls carry their name"
        case("a tool call says which tool it was", toolcalls_named)

        def subagents_render_inside_their_call():
            # Six unreadable `agent-<hex>` pages for one conversation is what
            # this replaced. A launched transcript gets no page of its own; it
            # appears where it was launched.
            launched = {r["destination"] for r in recs
                        if r["record"] == "edge" and r["type"] == "launched"}
            if not launched:
                return False, "no launched edge in the fixture base"
            pages = {f.stem for f in (st.views / "default-html").glob("*.html")}
            orphaned = [x for x in launched
                        if Path(R._p(nodes[x], "source", "")).stem in pages]
            page = (st.views / "default-html" / "sidechain-parent.html").read_text()
            return not orphaned and "Hello from the subagent" in page, \
                f"{len(launched)} launched, none with a page, prose inlined"
        case("a subagent renders inside the call that launched it",
             subagents_render_inside_their_call)

        def render_removes_stale_pages():
            # `render` only ever wrote, which was invisible until a transcript
            # could stop having a page of its own. A stale page stays in the
            # browser showing a document the graph no longer presents that way.
            ghost = st.views / "default-html" / "ghost.html"
            ghost.write_text("<p>from no record at all</p>")
            V.render_all(st)
            return not ghost.exists(), \
                "a view file no render produced is removed"
        case("render leaves only what it wrote", render_removes_stale_pages)

    # -- v0.2.9: slash commands, recognised structurally --------------------
    # tests/fixtures/sessions/session-slash.jsonl carries the three measured
    # originals verbatim (docs/roadmap.md, v0.2.9) plus an ANSI-bearing one,
    # each its own turn, alongside two ordinary human/assistant turns so the
    # suppression is shown against real content rather than an all-slash file.
    with tempfile.TemporaryDirectory() as d2:
        st2 = S.Store.init(Path(d2))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ST._digest(st2, "claude-code-transcript",
                       [str(HERE / "fixtures/sessions/session-slash.jsonl")],
                       "compost")
        digest_output = buf.getvalue()
        V.render_all(st2)
        recs2, _ = st2.load()
        nodes2 = {r["guid"]: r for r in recs2 if r["record"] == "node"}
        kids2: dict[str, list[str]] = {}
        for r in recs2:
            if r["record"] == "edge" and r["type"] == "contains":
                kids2.setdefault(r["source"], []).append(r["destination"])
        djot2 = {f.stem: f.read_text()
                 for f in (st2.views / "default-djot").glob("*.dj")}
        html2 = {f.stem: f.read_text()
                 for f in (st2.views / "default-html").glob("*.html")
                 if f.name != "index.html"}
        djot_text = "\n".join(djot2.values())
        html_text = "\n".join(html2.values())

        def _para_with_tag(tag, contains=None):
            for n in nodes2.values():
                if n["type"] == "Para" and V._lead_tag(n) == tag:
                    if contains is None or contains in R.plain_text(n):
                        return n
            raise AssertionError(f"no Para with lead tag {tag!r} found")

        def _turn_of(child_guid):
            src = next(s for s, ds in kids2.items() if child_guid in ds)
            return nodes2[src]

        caveat = _para_with_tag(V.SLASH_CAVEAT)
        caveat_turn = _turn_of(caveat["guid"])
        command = _para_with_tag(V.SLASH_COMMAND)
        stdout_plain = _para_with_tag(V.SLASH_STDOUT, "See ya")
        stdout_ansi = _para_with_tag(V.SLASH_STDOUT, "Opus 5")
        ansi_turn = _turn_of(stdout_ansi["guid"])

        def caveat_turn_produces_nothing():
            # Sabotage: making `_render_slash` return a block for the caveat
            # (treating it like the other two tags) puts both the paragraph
            # and the empty turn frame around it back on the page.
            leaked = (caveat["guid"] in djot_text or caveat["guid"] in html_text
                      or caveat_turn["guid"] in djot_text
                      or caveat_turn["guid"] in html_text)
            return not leaked, \
                "neither the caveat paragraph nor its turn's frame is on the page"
        case("a turn whose only child is a caveat produces no output at all",
             caveat_turn_produces_nothing)

        def caveat_still_in_the_graph():
            # The property this guards: rendering is not where filtering
            # happens. Sabotage: dropping the line at import time, rather than
            # suppressing it at render time, would pass every case above too.
            n = nodes2.get(caveat["guid"])
            has_text = n is not None and "Caveat" in R.plain_text(n)
            here = Path.cwd()
            os.chdir(d2)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = cli.main(["compost", "lookup", caveat["guid"]])
            finally:
                os.chdir(here)
            return (has_text and code == 0
                    and "Caveat" in out.getvalue()), \
                "the caveat's node is unchanged in the graph, and " \
                "`compost lookup` still resolves it"
        case("the caveat's node is still in the graph after rendering",
             caveat_still_in_the_graph)

        def command_line_has_a_handle():
            # Sabotage: emitting the command's Para without routing it through
            # `g.wrap` (e.g. returning it straight from the elif branch)
            # drops the handle and the block stops being citable.
            return (command["guid"] in djot_text
                    and f'id="{command["guid"]}"' in html_text), \
                "the command paragraph carries its guid as a citable handle, " \
                "in both views"
        case("the command paragraph renders with its guid as the block id",
             command_line_has_a_handle)

        def command_line_has_no_angle_bracket():
            # Sabotage: building the line from the node's raw djot/markdown
            # text instead of `R.plain_text` leaves the three tag pairs — or
            # their escaped form — sitting in the rendered line.
            m = re.search(re.escape(command["guid"]) + r'\}\n(.*?)\n', djot_text)
            djot_line = m.group(1) if m else None
            m = re.search(r'id="' + re.escape(command["guid"])
                          + r'"[^>]*>\s*<p>(.*?)</p>', html_text, re.S)
            html_line = m.group(1) if m else None
            ok = (djot_line is not None and "<" not in djot_line
                  and html_line is not None and "<" not in html_line)
            return ok, f"djot: {djot_line!r}, html: {html_line!r}"
        case("the rendered command line has no < character",
             command_line_has_no_angle_bracket)

        def stdout_folds_in_html_bare_in_djot():
            djot_block = re.search(
                r'\{#' + re.escape(stdout_plain["guid"]) + r'\}\n(.*?)\n\n',
                djot_text, re.S)
            html_block = re.search(
                r'id="' + re.escape(stdout_plain["guid"]) + r'"[^>]*>(.*?)</div>',
                html_text, re.S)
            in_djot_ok = (djot_block is not None
                          and "<details>" not in djot_block.group(1)
                          and "See ya!" in djot_block.group(1))
            in_html_ok = (html_block is not None
                          and "<details>" in html_block.group(1)
                          and "See ya!" in html_block.group(1))
            return in_djot_ok and in_html_ok, \
                "stdout is a bare code block in djot, a <details> in html"
        case("stdout with text folds in html and stays bare in djot",
             stdout_folds_in_html_bare_in_djot)

        def empty_stdout_renders_nothing():
            # Unit-level, not through digest: a synthetic Para whose only
            # inline is the stdout tag, no text after it.
            node = {"type": "Para", "guid": str(id(object())),
                    "content": [{"t": "RawInline",
                                 "c": ["html", V.SLASH_STDOUT]}]}
            return (V._render_slash(None, node, "html") is None
                    and V._render_slash(None, node, "djot") is None), \
                "an empty stdout renders nothing in either view"
        case("empty stdout renders nothing in either view",
             empty_stdout_renders_nothing)

        def ansi_stripped_in_view_present_in_record():
            # Both halves in one test: the SGR sequence must still be in the
            # record the view was built from (nothing about rendering may
            # touch ingestion), and must not be in either rendered view.
            # The raw log line, not a re-serialisation of it: `json.dumps`
            # escapes a control character back into readable text, which would
            # make this pass even if the importer had never kept the byte.
            log_content = (ansi_turn["params"].get("log", {})
                           .get("message", {}).get("content", ""))
            in_record = "\x1b[1m" in log_content
            in_djot = "\x1b" in djot_text or "[1m" in djot_text
            in_html = "\x1b" in html_text or "[1m" in html_text
            return in_record and not in_djot and not in_html, \
                f"ANSI in record: {in_record}, leaked into djot: {in_djot}, " \
                f"leaked into html: {in_html}"
        case("ANSI escapes are stripped in the view, kept in the record",
             ansi_stripped_in_view_present_in_record)

        def every_turn_says_who_is_speaking():
            return ('data-author="human"' in html_text
                    and 'data-author="assistant"' in html_text
                    and "[data-author]" in V.CSS
                    and "::before" in V.CSS), \
                "every turn div carries a data-author attribute, and the " \
                "CSS keys a rule off it"
        case("every turn div says who is speaking", every_turn_says_who_is_speaking)

        def digest_prints_whole_guid_lookup_accepts_it():
            m = re.search(r"root ([0-9a-f-]+), blob ([0-9a-f-]+)",
                          digest_output)
            if not m:
                return False, f"no 'root <guid>, blob <guid>' in: {digest_output!r}"
            root_guid, blob_guid = m.group(1), m.group(2)
            here = Path.cwd()
            os.chdir(d2)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = cli.main(["compost", "lookup", root_guid])
            finally:
                os.chdir(here)
            return (len(root_guid) == 36 and len(blob_guid) == 36
                    and code == 0 and root_guid in out.getvalue()), \
                f"digest printed a {len(root_guid)}-char root guid, " \
                f"lookup exit {code}"
        case("digest prints the whole root guid, and lookup accepts it",
             digest_prints_whole_guid_lookup_accepts_it)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<52} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} session-view guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

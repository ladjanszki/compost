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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
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

            Two types are stored and deliberately not rendered, and both
            exclusions are decisions recorded in `views.py` rather than
            accidents: a `thinking` node with no text, and an envelope turn
            whose only content was a tool result that got folded into the call
            that produced it. Being in the graph and being on the page are
            different things.
            """
            if n["type"] == "thinking" and n["params"].get("empty"):
                return False
            if n["type"] == "turn" and n["params"].get("author") == "envelope" \
                    and not kids.get(n["guid"]):
                return False
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
                first = o["params"]["text"].strip().split("\n")[0][:40]
                if first and first not in text:
                    dropped += 1
            return outs and not dropped, \
                f"{len(outs)} outputs, {dropped} with content missing"
        case("djot shows tool output in full", output_is_whole_in_djot)

        def html_collapses():
            # Tool output collapses, and so does a subagent transcript — it is
            # the output of its `Agent` call, arriving in another file. One
            # folding mechanism for both, which is why the count is a sum.
            n_details = sum(t.count("<details>") for t in html.values())
            outs = sum(1 for n in nodes.values() if n["type"] == "tooloutput")
            subs = sum(1 for r in recs if r["record"] == "edge"
                       and r["type"] == "launched")
            return n_details == outs + subs, \
                f"{n_details} <details> for {outs} outputs + {subs} subagents"
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

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<52} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} session-view guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

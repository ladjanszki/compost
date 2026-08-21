#!/usr/bin/env python3
"""
test_session_views.py — rendering a transcript.

The djot view shows everything, because djot has no collapse and because an
agent that cannot see the output cannot reason about it. The html view collapses
tool output into <details>, because a human is scrolling. Same graph, two
readings — which is the point of generating views from records rather than
from a document.
"""
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
from src import views as V      # noqa: E402

HERE = Path(__file__).parent
SESSIONS = T.sessions()[:3]
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
        V.render_all(st)
        recs, _ = st.load()
        g = R.Graph(recs)
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        kids = {}
        for r in recs:
            if r["record"] == "edge" and r["type"] == "contains":
                kids.setdefault(r["source"], []).append(r["destination"])
        djot = {n: (st.views / "default-djot" / f"{n}.dj").read_text()
                for n in roots}
        html = {n: (st.views / "default-html" / f"{n}.html").read_text()
                for n in roots}

        def every_session_rendered():
            return len(djot) == len(SESSIONS) and all(djot.values()), \
                f"{len(djot)} sessions rendered to all three views"
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
            n_details = sum(t.count("<details>") for t in html.values())
            outs = sum(1 for n in nodes.values() if n["type"] == "tooloutput")
            return n_details == outs, \
                f"{n_details} <details> for {outs} tool outputs"
        case("html collapses every tool output", html_collapses)

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

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<52} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} session-view guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

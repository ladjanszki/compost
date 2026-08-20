#!/usr/bin/env python3
"""
test_session.py — what the session importer promises.

The two that matter most are opposites: prose must be *parsed* so a paragraph
of an answer is citable, and tool output must *not* be, so a `ls` listing does
not acquire headings it never had.
"""
import glob
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R    # noqa: E402
from tests import tier as T  # noqa: E402
from src import session as S    # noqa: E402

HERE = Path(__file__).parent
FIXTURES = T.sessions()


def main():
    results = []

    def case(name, fn):
        # `fn` returning None means "not applicable here" — a guarantee that
        # needs the fetched corpus, asked for on a bare clone. It is reported,
        # never counted as passing: a suite that goes quiet on 8% of its
        # material is worse than one that fails.
        try:
            got = fn()
            ok, detail = (None, T.WHY) if got is None else got
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    # Every property is checked against all seven sessions at once. Running
    # them against one fixture let "0 tool outputs, none split into blocks"
    # pass as a guarantee, which is how a suite starts lying.
    recs, per_session = [], []
    for f in FIXTURES:
        r, root = S.session_to_records(f)
        recs += r
        per_session.append((f, r))
    g = R.Graph(recs)
    by_type = Counter(r["type"] for r in recs if r["record"] == "node")
    nodes = {r["guid"]: r for r in recs if r["record"] == "node"}

    def graph_is_sound():
        p = []
        for f, r in per_session:
            p += R.check(r)
        return not p, f"{len(nodes)} nodes over {len(FIXTURES)} sessions, " \
                      f"{p[:1] or 'no problems'}"
    case("the imported session checks clean", graph_is_sound)

    def prose_is_parsed():
        if not T.have_corpus():
            return None
        # a session with answers in it must produce real block nodes
        blocks = sum(by_type[t] for t in ("Para", "Plain", "Header", "ListItem",
                                          "CodeBlock", "BulletList", "Table"))
        return blocks > 1000, f"{blocks} prose blocks parsed out of the turns"
    case("assistant prose becomes real blocks", prose_is_parsed)

    def output_is_verbatim():
        # tool output is one node holding text, never split into paragraphs
        outs = [n for n in nodes.values() if n["type"] == "tooloutput"]
        parsed = [o for o in outs if g.children(o["guid"])]
        return outs and not parsed, \
            f"{len(outs)} tool outputs, none split into blocks"
    case("tool output is kept whole", output_is_verbatim)

    def results_are_folded():
        outs = [n for n in nodes.values() if n["type"] == "tooloutput"]
        parent = {e["destination"]: e["source"] for e in recs
                  if e["record"] == "edge" and e["type"] == "contains"}
        misfiled = [o for o in outs
                    if nodes.get(parent.get(o["guid"], ""), {}).get("type")
                    != "toolcall"]
        return outs and not misfiled, \
            f"{len(outs)} results, all under their toolcall"
    case("a tool result folds into its call", results_are_folded)

    def ids_match():
        pairs = 0
        parent = {e["destination"]: e["source"] for e in recs
                  if e["record"] == "edge" and e["type"] == "contains"}
        for n in nodes.values():
            if n["type"] != "tooloutput":
                continue
            call = nodes.get(parent.get(n["guid"], ""), {})
            if call.get("params", {}).get("tool_use_id") == \
                    n["params"]["tool_use_id"]:
                pairs += 1
        outs = by_type["tooloutput"]
        return outs and pairs == outs, f"{pairs}/{outs} matched on tool_use_id"
    case("call and result are matched by id, not order", ids_match)

    def attribution():
        authors = Counter(n["params"]["author"] for n in nodes.values()
                          if n["type"] == "turn")
        # every human turn must carry real prose, never only tool results
        bad = 0
        for n in nodes.values():
            if n["type"] != "turn" or n["params"]["author"] != "human":
                continue
            kids = [nodes[k]["type"] for k in g.children(n["guid"])]
            if all(k in ("toolcall", "tooloutput") for k in kids):
                bad += 1
        return bad == 0, f"{dict(authors)}, {bad} misattributed"
    case("only typed turns are attributed to the human", attribution)

    def files_dedupe():
        paths = [n["params"]["path"] for n in nodes.values()
                 if n["type"] == "file"]
        # deduped per session, so compare within each
        dupes = 0
        for f, r in per_session:
            ps = [n["params"]["path"] for n in r
                  if n["record"] == "node" and n["type"] == "file"]
            dupes += len(ps) - len(set(ps))
        return paths and not dupes, \
            f"{len(paths)} file nodes across sessions, {dupes} duplicated within one"
    case("a file touched twice is one node", files_dedupe)

    def thinking_kept():
        if not T.have_corpus():
            return None
        th = [n for n in nodes.values() if n["type"] == "thinking"]
        empty = sum(1 for n in th if n["params"]["empty"])
        return len(th) > 100, \
            f"{len(th)} thinking nodes ({empty} with no text in the log)"
    case("thinking blocks are kept as nodes", thinking_kept)

    def all_fixtures():
        if not T.have_corpus():
            return None
        n = sum(1 for x in recs if x["record"] == "node")
        return n > 5000, f"{len(FIXTURES)} sessions, {n} nodes, {len(recs)-n} edges"
    case("every fixture session imports cleanly", all_fixtures)

    for ok, name, detail in results:
        mark = "skip" if ok is None else ("pass" if ok else "FAIL")
        print(f"  {mark}  {name:<48} {detail}")
    bad = sum(1 for ok, _, _ in results if ok is False)
    skipped = sum(1 for ok, _, _ in results if ok is None)
    ran = len(results) - skipped
    tail = f"   ({skipped} skipped: {T.WHY})" if skipped else ""
    print(f"\n{ran - bad}/{ran} session-import guarantees hold{tail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

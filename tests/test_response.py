#!/usr/bin/env python3
"""
test_response.py — what `compost digest --as=claude-code-response` promises.

`docs/roadmap.md`, v0.2.6, "the conversation loop": a `claude --print
--output-format json` envelope, wrapped with the guid of the note it answers,
becomes a `document` root like any other — every envelope key kept verbatim in
`params`, `result` additionally parsed so its paragraphs are citable, and two
new edges (`responds_to`, `next`) joining it to the note's root without either
root containing the other.

`ENVELOPE` is transcribed from a real captured example (`docs/roadmap.md`,
"The envelope, measured") — 21 top-level keys, a nested dict (`usage`), and a
JSON `null` (`api_error_status`) — so property 1 is checked against the actual
shape rather than a guess at it.

Base A builds one note and one response answering it, and most properties
read that base. Base B is the refusal case: a wrapper naming a guid nobody
minted, which `_digest` must refuse whole rather than write a dangling edge.
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R     # noqa: E402
from src import routes as RT     # noqa: E402
from src import store as S       # noqa: E402
from src import views as V       # noqa: E402

FAKE_ROOT = "deadbeef-0000-0000-0000-000000000000"

ENVELOPE = {
    "is_error": False,
    "duration_api_ms": 2697,
    "num_turns": 1,
    "stop_reason": "end_turn",
    "session_id": "2de219da-97ce-485c-a8f6-6d3dd37477b3",
    "total_cost_usd": 0.0630105,
    "usage": {"input_tokens": 2, "output_tokens": 4,
              "cache_read_input_tokens": 8113},
    "modelUsage": {"claude-opus-5": {"inputTokens": 2, "outputTokens": 4,
                                     "costUSD": 0.0624265}},
    "permission_denials": [],
    "terminal_reason": "completed",
    "fast_mode_state": "off",
    "fast_mode_disabled_reason": "sdk_opt_in_required",
    "subtype": "success",
    "api_error_status": None,
    "result": "A first paragraph.\n\nA second paragraph.\n",
    "ttft_ms": 1788,
    "ttft_stream_ms": 1263,
    "time_to_request_ms": 47,
    "type": "result",
    "duration_ms": 1818,
    "uuid": "4d9add9f-2e6e-4efc-a97a-b78d3b86d7f8",
}


def run(*args, cwd=None):
    from src import cli
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(["compost", *args])
    return code, out.getvalue()


def _digest_notes(st: S.Store, tmp: Path, name: str, text: str):
    """A note, through the real `notes` route via `store._digest`, so `blob`
    and `derived_from` are minted the way an actual digest produces them."""
    p = tmp / name
    p.write_text(text)
    with contextlib.redirect_stdout(io.StringIO()):
        if S._digest(st, "notes", [str(p)], "compost"):
            raise RuntimeError(f"digest failed for {name}")
    recs, _ = st.load()
    root = next(r for r in recs if r["record"] == "node"
                and r["type"] in R.ROOT_TYPES
                and R._p(r, "source") == name)
    return root["guid"]


def _digest_response(st: S.Store, tmp: Path, name: str, wrapper: dict):
    p = tmp / name
    p.write_text(json.dumps(wrapper))
    with contextlib.redirect_stdout(io.StringIO()):
        code = S._digest(st, "claude-code-response", [str(p)], "compost")
    return code


def build_base_a(tmp: Path):
    """One note, one response answering it — the ordinary round."""
    st = S.Store.init(tmp / "a")
    note_root = _digest_notes(st, tmp, "note.md", "The note's own text.\n")
    code = _digest_response(st, tmp, "round.json",
                            {"responds_to": note_root, "envelope": ENVELOPE})
    assert code == 0, "seeding base A failed"
    recs, _ = st.load()
    resp_root = next(r for r in recs if r["record"] == "node"
                     and r["type"] in R.ROOT_TYPES
                     and R._p(r, "source") == "round.json")
    return st, note_root, resp_root["guid"]


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

        # -- Base A: an ordinary round ---------------------------------------
        st_a, note_root, resp_root = build_base_a(tmp)
        recs_a, _ = st_a.load()
        nodes_a = {r["guid"]: r for r in recs_a if r["record"] == "node"}
        resp_node = nodes_a[resp_root]
        resp_params = resp_node.get("params", {})

        def envelope_survives_verbatim():
            missing = [k for k in ENVELOPE if resp_params.get(k) != ENVELOPE[k]]
            nested_ok = resp_params.get("usage") == ENVELOPE["usage"]
            null_ok = "api_error_status" in resp_params \
                and resp_params["api_error_status"] is None
            return (not missing and nested_ok and null_ok,
                    f"{len(ENVELOPE)} keys checked, "
                    f"{len(ENVELOPE) - len(missing)} match, "
                    f"nested dict survives: {nested_ok}, null survives: {null_ok}")
        case("every envelope key survives in params, verbatim",
             envelope_survives_verbatim)

        def envelope_merge_is_load_bearing():
            # SABOTAGE. Without the merge, params carries none of the
            # envelope's own keys — proves property 1 is not vacuously true
            # (e.g. from some other field named "usage" already in params).
            #
            # Patching `RT._response` alone would not reach this: `ROUTES`
            # (`src/routes.py`) stores the function *object*, bound once at
            # module load, and `RT.read()` calls that stored reference
            # directly rather than looking the name up again — so the
            # dispatch table entry itself has to be swapped, not the name.
            real_entry = RT.ROUTES["claude-code-response"]

            def broken(path, mint, route):
                wrapper = json.loads(path.read_text(encoding="utf-8"))
                recs, root = R.ast_to_records(
                    RT._ast_of_text(wrapper["envelope"].get("result", "")),
                    mint=mint, source=path.name, route=route)
                b = R.Builder(mint)
                b.edge("responds_to", root, wrapper["responds_to"],
                      RT.CONVERSATION_LAYER)
                return recs + b.records, root   # params.update(...) removed
            RT.ROUTES["claude-code-response"] = \
                (broken, real_entry[1], real_entry[2])
            try:
                with tempfile.TemporaryDirectory() as d2:
                    tmp2 = Path(d2)
                    st2 = S.Store.init(tmp2 / "sab")
                    root2 = _digest_notes(st2, tmp2, "n.md", "text\n")
                    code = _digest_response(st2, tmp2, "r.json",
                                            {"responds_to": root2,
                                             "envelope": ENVELOPE})
                    recs2, _ = st2.load()
                    resp2 = next(r for r in recs2 if r["record"] == "node"
                                and r["type"] in R.ROOT_TYPES
                                and R._p(r, "source") == "r.json")
                    sabotaged = "usage" not in resp2.get("params", {})
            finally:
                RT.ROUTES["claude-code-response"] = real_entry
            return (code == 0 and sabotaged,
                    "without the merge, an envelope key that should survive "
                    "does not — the real route is what makes it survive")
        case("the envelope merge is load-bearing (sabotaged)",
             envelope_merge_is_load_bearing)

        def uuid_is_the_envelopes_own():
            return (resp_params.get("uuid") == ENVELOPE["uuid"]
                    and resp_params["uuid"] != resp_root,
                    f"params['uuid']={resp_params.get('uuid')!r}, "
                    f"record guid={resp_root!r}")
        case("params['uuid'] is the envelope's own uuid, not the record's guid",
             uuid_is_the_envelopes_own)

        def session_id_is_top_level():
            return (resp_params.get("session_id") == ENVELOPE["session_id"],
                    f"params['session_id']={resp_params.get('session_id')!r}")
        case("session_id is a top-level param", session_id_is_top_level)

        def result_is_parsed_into_blocks():
            g = R.Graph(recs_a)
            kids = g.children(resp_root)
            texts = [R.plain_text(nodes_a[k]) for k in kids]
            return (len(kids) == 2 and texts == ["A first paragraph.",
                                                 "A second paragraph."],
                    f"{len(kids)} children, texts {texts}")
        case("result is parsed into addressable child blocks",
             result_is_parsed_into_blocks)

        def parsing_result_is_load_bearing():
            # SABOTAGE. Stub the reader to emit no blocks at all — if the
            # route stopped calling it, the previous property would still
            # (wrongly) pass on whatever blocks happened to be left from a
            # prior call, so this proves the parse step is what puts them
            # there rather than some other mechanism.
            real = RT._ast_of_text
            RT._ast_of_text = lambda text: {
                "pandoc-api-version": [1, 23, 1], "meta": {}, "blocks": []}
            try:
                with tempfile.TemporaryDirectory() as d2:
                    tmp2 = Path(d2)
                    st2 = S.Store.init(tmp2 / "sab2")
                    root2 = _digest_notes(st2, tmp2, "n.md", "text\n")
                    code = _digest_response(st2, tmp2, "r.json",
                                            {"responds_to": root2,
                                             "envelope": ENVELOPE})
                    recs2, _ = st2.load()
                    resp2 = next(r for r in recs2 if r["record"] == "node"
                                and r["type"] in R.ROOT_TYPES
                                and R._p(r, "source") == "r.json")
                    g2 = R.Graph(recs2)
                    empty = g2.children(resp2["guid"]) == []
            finally:
                RT._ast_of_text = real
            return (code == 0 and empty,
                    "with the reader stubbed to emit nothing, the response "
                    "root has zero children — the real reader is what "
                    "populates them")
        case("parsing `result` is load-bearing (sabotaged)",
             parsing_result_is_load_bearing)

        def responds_to_edge():
            e = next((e for e in recs_a if e["record"] == "edge"
                     and e["type"] == "responds_to"), None)
            return (e is not None and e["source"] == resp_root
                    and e["destination"] == note_root
                    and e["layer"] == "conversation" and "by" not in e,
                    f"responds_to: {e}")
        case("a responds_to edge joins the response to the note",
             responds_to_edge)

        def next_edge():
            e = next((e for e in recs_a if e["record"] == "edge"
                     and e["type"] == "next" and e["layer"] == "conversation"),
                     None)
            return (e is not None and e["source"] == note_root
                    and e["destination"] == resp_root and "by" not in e,
                    f"next: {e}")
        case("a next edge gives the pair reading order", next_edge)

        def check_is_clean():
            problems = R.check(recs_a)
            return not problems, f"{len(problems)} problems"
        case("the graph checks clean end to end", check_is_clean)

        def both_roots_get_a_page():
            here = st_a.root
            with contextlib.redirect_stdout(io.StringIO()):
                written, ndocs, _, _ = V.render_all(st_a)
            stems = {p.stem for p in written}
            note_stem = Path(R._p(nodes_a[note_root], "source")).stem
            resp_stem = Path(R._p(resp_node, "source")).stem
            return (ndocs >= 2 and note_stem in stems and resp_stem in stems,
                    f"{ndocs} documents rendered, both stems present: "
                    f"{note_stem in stems and resp_stem in stems}")
        case("neither root contains the other; both keep their own page",
             both_roots_get_a_page)

        # -- Base B: the refusal --------------------------------------------
        def refuses_a_missing_structural_guid():
            st_b = S.Store.init(tmp / "b")
            before_g = len(list(st_b.graph.glob("*.jsonl")))
            before_s = len(list(st_b.storage.iterdir()))
            code = _digest_response(st_b, tmp, "bad.json",
                                    {"responds_to": FAKE_ROOT,
                                     "envelope": ENVELOPE})
            after_g = len(list(st_b.graph.glob("*.jsonl")))
            after_s = len(list(st_b.storage.iterdir()))
            return (code == 1 and before_g == after_g and before_s == after_s,
                    "a responds_to guid nobody minted refuses the file, "
                    "writes nothing")
        case("digest refuses a responds_to guid absent from batch and base",
             refuses_a_missing_structural_guid)

        def the_refusal_is_load_bearing():
            # SABOTAGE. Disable the guard `_digest` calls and show what it
            # was preventing: the same bad file now digests "successfully"
            # and leaves a dangling edge that fails `check` for the whole
            # base — the exact failure the guard exists to stop before it
            # is ever written (docs/roadmap.md, "the conversation loop").
            real = S._structural_gaps
            S._structural_gaps = lambda plans, known: []
            try:
                st_c = S.Store.init(tmp / "c")
                code = _digest_response(st_c, tmp, "bad2.json",
                                        {"responds_to": FAKE_ROOT,
                                         "envelope": ENVELOPE})
                recs_c, _ = st_c.load()
                problems = R.check(recs_c)
            finally:
                S._structural_gaps = real
            wrote_something = code == 0
            return (wrote_something and any("dangling" in p for p in problems),
                    f"disabled guard: digest returned {code}, "
                    f"check reports {len(problems)} problem(s)")
        case("the refusal is load-bearing (sabotaged)",
             the_refusal_is_load_bearing)

        def ordinary_citations_are_unaffected():
            # A dangling `[-](#guid)` link in an ordinary note is not a
            # structural edge — `notes` mints no `cites` edge at digest time
            # at all, only `compost layer citation` does, later, as a
            # placeholder. The new guard must not touch that path.
            st_d = S.Store.init(tmp / "d")
            p = tmp / "citing.md"
            p.write_text(f"Citing [-](#{FAKE_ROOT}) here.\n")
            with contextlib.redirect_stdout(io.StringIO()):
                code = S._digest(st_d, "notes", [str(p)], "compost")
            return code == 0, "a dangling citation link still digests fine"
        case("an ordinary dangling citation is untouched by the new guard",
             ordinary_citations_are_unaffected)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} response guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

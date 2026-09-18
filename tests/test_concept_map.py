#!/usr/bin/env python3
"""
test_concept_map.py — the talks-about layer (v0.3.0), one case per guarantee.

`docs/roadmap.md`, "v0.3.0 — the talks-about layer" names fourteen
guarantees; this file is their permanent home, the way `test_sabotage.py` is
for the record format's own invariants. `tests/verify-0.3.0.sh` covered the
same ground during the build and says so in its own header: it is deleted
when the version ships, so whatever it checked has to survive here or
nowhere.

Every case builds its own throwaway base under `tempfile.TemporaryDirectory`
— never `.compost` in this checkout, which is a symlink into the human's
private notes repository (CLAUDE.md) — and every case that needs a model
response injects a fake `ask=` rather than calling `src.llm.ask`. Nothing
here reaches the network; guarantee 2 is that property holding for the whole
suite, not one case in particular.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import layers as L      # noqa: E402
from src import llm as LLM       # noqa: E402
from src import markdown as MD   # noqa: E402
from src import records as R     # noqa: E402
from src import store as S       # noqa: E402
from src import views as V       # noqa: E402

HERE = Path(__file__).parent
FIX = HERE / "fixtures" / "concept-map"
PROMPT_FILE = HERE.parent / "prompts" / "concept-map.md"

ROOT_RE = re.compile(r"root ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}"
                     r"-[0-9a-f]{12})")

NOTES_TEXT = (
    "# Storage notes\n\n"
    "Some prose about immutability and never overwriting a stored blob.\n\n"
    "- A bullet about addressing bytes from a document.\n"
    "- Another bullet, unrelated to anything on the map.\n\n"
    "# Random topic\n\n"
    "Nothing to do with the concept map at all.\n\n"
    "# Counting\n\n"
    "Measuring corpus sizes before deciding anything.\n")

# The map fixture, minus its "Measurement" section — guarantee 11.
MAP_V2_TEXT = (
    "---\nconcept_map: true\n---\n\n"
    "# Storage\n\n"
    "How bytes are kept, addressed and never overwritten.\n\n"
    "## Immutability\n\nWhy a source is written once and never edited.\n\n"
    "## Addressing\n\nGetting from a document to its bytes.\n\n"
    "# Time\n\nClocks, ordering, replay.\n\n"
    "## Replay\n\nReconstructing a past state from records.\n")


def _digest(st, path, mutability=None, updates=None):
    """`store._digest`, quiet, returning the root guid it printed."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = S._digest(st, "notes", [str(path)], "test",
                       mutability=mutability, updates=updates)
    out = buf.getvalue()
    if rc:
        raise RuntimeError(f"digest of {path} failed: {out}")
    m = ROOT_RE.search(out)
    if not m:
        raise RuntimeError(f"no root guid in digest output: {out}")
    return m.group(1)


def build_base(tmp: Path):
    """A base with the map fixture, the real prompt, and a small notes
    document with a controlled, known set of classifiable fragments."""
    st = S.Store.init(tmp / "base")
    map_root = _digest(st, FIX / "map.md", mutability="mutable")
    prompt_root = _digest(st, PROMPT_FILE, mutability="mutable")
    notes = tmp / "notes.md"
    notes.write_text(NOTES_TEXT)
    notes_root = _digest(st, notes, mutability="immutable")
    return st, map_root, prompt_root, notes_root


def rule(text: str) -> str:
    """A deterministic stand-in for a model's judgement, keyed on the
    fixture text above — not on fragment id, so it is indifferent to
    whatever order batching assigns them."""
    t = text.lower()
    if "immutability" in t:
        return "Storage > Immutability"
    if "addressing" in t:
        return "Storage > Addressing"
    if "storage notes" in t:
        return "Storage"
    if "enormous block" in t:
        return "Storage"
    if "short block after it" in t:
        return "Time"
    if "measuring corpus sizes" in t:
        return "Measurement"
    return L.ABSTAIN_LABEL


def fake_ask(system: str, user: str, model: str) -> str:
    out = []
    for m in re.finditer(r"^\[(\d+)\]\s+(.+)$", user, re.M):
        out.append(f"[{m.group(1)}] {rule(m.group(2))}")
    return "\n".join(out)


def fake_ask_no_measurement(system: str, user: str, model: str) -> str:
    """Same as `fake_ask`, but abstains on anything `rule` would have called
    Measurement -- guarantee 11's second run, against a map that dropped it."""
    out = []
    for m in re.finditer(r"^\[(\d+)\]\s+(.+)$", user, re.M):
        label = rule(m.group(2))
        out.append(f"[{m.group(1)}] "
                   f"{L.ABSTAIN_LABEL if label == 'Measurement' else label}")
    return "\n".join(out)


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    # -- guarantee 1 ---------------------------------------------------
    def g1_no_network():
        import urllib.request
        orig = urllib.request.urlopen

        def boom(*a, **k):
            raise AssertionError("--cost-calculation reached the network")
        urllib.request.urlopen = boom
        try:
            with tempfile.TemporaryDirectory() as d:
                st, map_root, prompt_root, _ = build_base(Path(d))
                out = L.cost_calculation(st, map_root, prompt_root=prompt_root,
                                         model="openai/gpt-4o-mini")
            return "estimate" in out.lower(), out.splitlines()[-1]
        finally:
            urllib.request.urlopen = orig
    case("[1] --cost-calculation makes no network call, with --model",
         g1_no_network)

    # -- guarantee 2 -----------------------------------------------------
    def g2_suite_never_calls_llm():
        orig = LLM.ask

        def boom(*a, **k):
            raise AssertionError("something called llm.ask directly")
        LLM.ask = boom
        try:
            with tempfile.TemporaryDirectory() as d:
                st, map_root, prompt_root, _ = build_base(Path(d))
                L.cost_calculation(st, map_root, prompt_root=prompt_root)
                result = L.build_concept_map(st, map_root, prompt_root,
                                             ask=fake_ask, model="m",
                                             batch_size=100)
            return True, f"classified {result['classified']} with no call " \
                        f"to llm.ask"
        finally:
            LLM.ask = orig
    case("[2] the suite never makes a network call — inject a raising "
         "llm.ask", g2_suite_never_calls_llm)

    # -- guarantee 3 -------------------------------------------------------
    def g3_refuses_without_flag():
        with tempfile.TemporaryDirectory() as d:
            st = S.Store.init(Path(d) / "base")
            root = _digest(st, FIX / "no-frontmatter.md", mutability="immutable")
            try:
                L.cost_calculation(st, root)
                return False, "did not refuse"
            except L.ConceptMapError as e:
                return "concept_map" in str(e), str(e)
    case("[3] a root without concept_map: true is refused, names the key",
         g3_refuses_without_flag)

    # -- guarantee 4 ---------------------------------------------------
    def g4_labelling():
        with tempfile.TemporaryDirectory() as d:
            st, map_root, prompt_root, _ = build_base(Path(d))
            out = L.cost_calculation(st, map_root, prompt_root=prompt_root)
        lines = out.splitlines()
        exact = [l for l in lines if "characters" in l or "calls at batch" in l
                or "classifiable blocks would be sent" in l]
        est = [l for l in lines if "input tokens" in l]
        ok = (bool(exact) and bool(est)
              and all("estimate" not in l.lower() for l in exact)
              and all("estimate" in l.lower() for l in est))
        return ok, out
    case("[4] exact numbers say so, estimated ones are labelled", g4_labelling)

    # -- guarantee 5 -------------------------------------------------------
    def g5_bad_responses():
        recs, root = R.ast_to_records(MD.ast_of_file(FIX / "map.md"))
        concepts = L._concept_map_tree(recs, root)
        label_index = L._label_index(concepts)
        sent = [1, 2, 3, 4, 5]
        problems = []

        good = (FIX / "response-good.txt").read_text()
        try:
            parsed = L._parse_response(good, sent, label_index)
            if len(parsed) != 5:
                problems.append(f"response-good: parsed {len(parsed)}")
        except L.ConceptMapError as e:
            problems.append(f"response-good wrongly refused: {e}")

        for fname, must_say in (
            ("response-bad-short.txt", "expected"),
            ("response-bad-label.txt", "not in the concept map"),
            ("response-bad-id.txt", "not sent"),
        ):
            text = (FIX / fname).read_text()
            try:
                L._parse_response(text, sent, label_index)
                problems.append(f"{fname}: was accepted, should refuse")
            except L.ConceptMapError as e:
                if must_say not in str(e):
                    problems.append(f"{fname}: wrong reason: {e}")
        return not problems, "; ".join(problems)
    case("[5] short count / unknown label / unsent id each fail loudly",
         g5_bad_responses)

    # -- guarantee 6 ---------------------------------------------------
    def g6_failed_run_writes_nothing():
        with tempfile.TemporaryDirectory() as d:
            st, map_root, prompt_root, _ = build_base(Path(d))
            before, _ = st.load()
            plan = L.plan_concept_map(st, map_root, prompt_root, batch_size=1)
            n_batches = len(plan["batches"])
            if n_batches < 2:
                return False, f"only {n_batches} batch(es); test needs >=2"
            fail_at = 2   # not the first call, so something was already
                          # "classified" in memory before the failure
            calls = {"n": 0}

            def flaky_ask(system, user, model):
                calls["n"] += 1
                if calls["n"] == fail_at:
                    raise RuntimeError("simulated call failure")
                return fake_ask(system, user, model)

            try:
                L.build_concept_map(st, map_root, prompt_root, ask=flaky_ask,
                                    model="m", batch_size=1)
                return False, "did not raise"
            except RuntimeError:
                pass
            after, _ = st.load()
            return before == after, f"{n_batches} batches, failed at call " \
                                    f"{fail_at}; {len(before)} vs " \
                                    f"{len(after)} records"
    case("[6] a failed run writes nothing — not a partial graph file",
         g6_failed_run_writes_nothing)

    # -- guarantee 7 -----------------------------------------------------
    def g7_one_run_deletable_whole():
        with tempfile.TemporaryDirectory() as d:
            st, map_root, prompt_root, _ = build_base(Path(d))
            r1 = L.build_concept_map(st, map_root, prompt_root, ask=fake_ask,
                                     model="m1", batch_size=100)
            st.write(f"{r1['run']}.jsonl", r1["records"])
            r2 = L.build_concept_map(st, map_root, prompt_root, ask=fake_ask,
                                     model="m2", batch_size=100)
            st.write(f"{r2['run']}.jsonl", r2["records"])
            recs, files = st.load()
            if R.check(recs):
                return False, f"base unsound before deletion: {R.check(recs)}"
            f1 = next(f for f in files if f.name == f"{r1['run']}.jsonl")
            f1.unlink()
            recs2, _ = st.load()
            problems = R.check(recs2)
            run1_gone = not any(r.get("guid") == r1["run"] for r in recs2)
            run2_edges = sum(1 for r in recs2 if r.get("record") == "edge"
                             and r["type"] == "talks_about"
                             and r.get("run") == r2["run"])
            r2_edges_before = sum(1 for r in r2["records"]
                                  if r["record"] == "edge"
                                  and r["type"] == "talks_about")
            ok = (not problems and run1_gone
                  and run2_edges == r2_edges_before and run2_edges > 0)
            return ok, f"problems={problems}, run1_gone={run1_gone}, " \
                      f"run2 edges {run2_edges}/{r2_edges_before}"
    case("[7] one run is one prov:Activity, deletable whole", g7_one_run_deletable_whole)

    # -- guarantee 8 -------------------------------------------------------
    def g8_fifteenth_assertion():
        recs, root = R.ast_to_records(MD.ast_of_file(FIX / "map.md"))
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        heads = [g for g, n in nodes.items() if n["type"] == "Header"]
        para = [g for g, n in nodes.items() if n["type"] == "Para"]
        if R.check(recs):
            return False, "fixture graph already unsound"
        run = "11111111-1111-1111-1111-111111111111"
        b = R.Builder()
        b.edge("talks_about", para[0], heads[0], "concept-map",
              primary=True, run=run)
        b.edge("talks_about", para[0], heads[1], "concept-map",
              primary=True, run=run)
        two_caught = any("primary" in p for p in R.check(recs + b.records))

        c = R.Builder()
        c.edge("talks_about", para[0], heads[0], "concept-map", primary=True,
              run="22222222-2222-2222-2222-222222222222")
        c.edge("talks_about", para[0], heads[1], "concept-map", primary=True,
              run="33333333-3333-3333-3333-333333333333")
        spread_clean = not any("primary" in p for p in R.check(recs + c.records))
        return two_caught and spread_clean, \
            f"two-in-one-run caught={two_caught}, two-runs clean={spread_clean}"
    case("[8] exactly one primary talks_about edge per block per run",
         g8_fifteenth_assertion)

    # -- guarantee 9 ---------------------------------------------------
    def g9_abstention_node():
        with tempfile.TemporaryDirectory() as d:
            st, map_root, prompt_root, _ = build_base(Path(d))
            result = L.build_concept_map(st, map_root, prompt_root,
                                         ask=fake_ask, model="m",
                                         batch_size=100)
        abst = [r for r in result["records"] if r["record"] == "node"
               and r["type"] == "abstention"]
        if len(abst) != 1:
            return False, f"{len(abst)} abstention nodes, expected 1"
        abst_edges = [r for r in result["records"]
                     if r.get("type") == "talks_about"
                     and r["destination"] == abst[0]["guid"]]
        ok = (len(abst_edges) == result["abstained"] > 0)
        return ok, f"{result['abstained']} abstained, {len(abst_edges)} " \
                  f"edges to the one abstention node"
    case("[9] abstention is a node, one per run", g9_abstention_node)

    # -- guarantee 10 ------------------------------------------------------
    def g10_over_cap_skipped():
        with tempfile.TemporaryDirectory() as d:
            st = S.Store.init(Path(d) / "base")
            _digest(st, FIX / "over-cap.md", mutability="immutable")
            map_root = _digest(st, FIX / "map.md", mutability="mutable")
            prompt_root = _digest(st, PROMPT_FILE, mutability="mutable")
            plan = L.plan_concept_map(st, map_root, prompt_root)
            recs, _ = st.load()
            nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
            if not plan["oversize"]:
                return False, "no oversize block found"
            big = plan["oversize"][0]
            frag_guids = {f["guid"] for f in plan["fragments"]}
            text_len = len(R.plain_text(nodes[big]) or "")
            return (big not in frag_guids and text_len > L.SIZE_CAP), \
                f"big block {text_len} chars, in fragments={big in frag_guids}"
    case("[10] a block over the 8,000-character cap is skipped, not truncated",
         g10_over_cap_skipped)

    # -- guarantee 11 --------------------------------------------------
    def g11_removed_label_stops_collecting():
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            st, map_root, prompt_root, _ = build_base(tmp)
            recs0, _ = st.load()
            old_concepts = L._concept_map_tree(recs0, map_root)
            old_measurement = next(c["guid"] for c in old_concepts
                                   if c["label"] == "Measurement")

            r1 = L.build_concept_map(st, map_root, prompt_root, ask=fake_ask,
                                     model="m", batch_size=100)
            st.write(f"{r1['run']}.jsonl", r1["records"])
            pages_v1 = V.render_collection(st.load()[0])
            if "measurement" not in pages_v1:
                return False, "sanity check failed: v1 never had a " \
                              "Measurement page to begin with"

            new_map = tmp / "map-v2.md"
            new_map.write_text(MAP_V2_TEXT)
            new_map_root = _digest(st, new_map, updates=map_root)

            # A second run, against the *new* map — a `mutable` re-ingest
            # mints an entirely fresh tree, guids included (decision, TA),
            # so the old run's classification is simply against guids no
            # live map reaches any more; a real workflow re-classifies.
            r2 = L.build_concept_map(st, new_map_root, prompt_root,
                                     ask=fake_ask_no_measurement, model="m",
                                     batch_size=100)
            st.write(f"{r2['run']}.jsonl", r2["records"])

            recs, _ = st.load()
            if R.check(recs):
                return False, f"base unsound after revision: {R.check(recs)}"
            pages = V.render_collection(recs)
            old_edges_present = any(
                r.get("record") == "edge" and r["type"] == "talks_about"
                and r["destination"] == old_measurement for r in recs)
            no_page_for_measurement = "measurement" not in pages
            other_labels_still_collect = "storage" in pages
            return (old_edges_present and no_page_for_measurement
                    and other_labels_still_collect), \
                f"pages={sorted(pages)}, old edges present={old_edges_present}"
    case("[11] a label removed from the map stops collecting; old edges "
         "stay valid", g11_removed_label_stops_collecting)

    # -- guarantee 12 --------------------------------------------------
    def g12_handle_on_every_block():
        with tempfile.TemporaryDirectory() as d:
            st, map_root, prompt_root, _ = build_base(Path(d))
            result = L.build_concept_map(st, map_root, prompt_root,
                                         ask=fake_ask, model="m",
                                         batch_size=100)
            st.write(f"{result['run']}.jsonl", result["records"])
            recs, _ = st.load()
        pages = V.render_collection(recs)
        abst = next(r["guid"] for r in recs if r["record"] == "node"
                   and r["type"] == "abstention")
        real_edges = [r for r in recs if r.get("record") == "edge"
                     and r["type"] == "talks_about"
                     and r["destination"] != abst]
        if not real_edges:
            return False, "no non-abstain talks_about edges to check"
        blob = "\n".join(pages.values())
        missing = [e["source"] for e in real_edges
                  if V.handle(e["source"]) not in blob]
        return not missing, f"{len(missing)} of {len(real_edges)} blocks " \
                            f"missing a handle in the collection view"
    case("[12] the collection view carries a handle on every block",
         g12_handle_on_every_block)

    # -- guarantee 13 -----------------------------------------------------
    def g13_check_and_schema_clean():
        with tempfile.TemporaryDirectory() as d:
            st, map_root, prompt_root, _ = build_base(Path(d))
            result = L.build_concept_map(st, map_root, prompt_root,
                                         ask=fake_ask, model="m",
                                         batch_size=100)
            st.write(f"{result['run']}.jsonl", result["records"])
            recs, _ = st.load()
        problems = R.check(recs)
        import jsonschema
        schema = json.load(open(HERE.parent / "tools" / "record-schema-1.json"))
        validator = jsonschema.Draft202012Validator(schema)
        bad = []
        for r in recs:
            errs = sorted(validator.iter_errors(r), key=lambda e: e.message)
            if errs:
                bad.append(f"{r['type']} {r['guid'][:8]}: {errs[0].message}")
        return not problems and not bad, \
            f"{len(problems)} check problems, {len(bad)} schema violations " \
            f"({bad[:1]})"
    case("[13] check() reports 0 problems, every record validates",
         g13_check_and_schema_clean)

    # -- guarantee 14 -----------------------------------------------------
    def g14_only_llm_reaches_the_network():
        src = HERE.parent / "src"
        bad = []
        for f in src.glob("*.py"):
            if f.name == "llm.py":
                continue
            text = f.read_text()
            if re.search(r"urllib\.request|urlopen|http\.client|openrouter",
                        text, re.I):
                bad.append(f.name)
        return not bad, ", ".join(bad)
    case("[14] nothing in src/ reaches the network except llm.py",
         g14_only_llm_reaches_the_network)

    # -- the seam itself, permanently (CLAUDE.md: READER/ENDPOINT/MODEL each
    # defined exactly once). verify-0.3.0.sh checked this during the build
    # and is deleted with the release, so this is its only surviving home.
    def seam_defined_once():
        src = HERE.parent / "src"
        problems = []
        hits = [f for f in src.glob("*.py")
               if re.search(r"^READER\s*=", f.read_text(), re.M)]
        if len(hits) != 1:
            problems.append(f"READER defined in {[h.name for h in hits]}")
        llm_text = (src / "llm.py").read_text()
        for name in ("ENDPOINT", "MODEL"):
            hits = re.findall(rf"^{name}\s*=", llm_text, re.M)
            if len(hits) != 1:
                problems.append(f"{name} defined {len(hits)}x in llm.py")
        return not problems, "; ".join(problems)
    case("READER/ENDPOINT/MODEL each defined exactly once in src/",
         seam_defined_once)

    # -- decided constants, pinned so a silent re-pick is visible ----------
    def constants_match_the_spec():
        problems = []
        if L.SIZE_CAP != 8000:
            problems.append(f"SIZE_CAP={L.SIZE_CAP}")
        if L.CLASSIFIABLE != {"Para", "Plain", "ListItem", "Header"}:
            problems.append(f"CLASSIFIABLE={L.CLASSIFIABLE}")
        if "concept_run" not in R.UNCONTAINED or "abstention" not in R.UNCONTAINED:
            problems.append(f"UNCONTAINED={R.UNCONTAINED}")
        if "concept-map" not in L.BUILDERS:
            problems.append("concept-map not registered in BUILDERS")
        if not re.search(r"^def render_collection\b",
                         (HERE.parent / "src" / "views.py").read_text(), re.M):
            problems.append("no render_collection() in views.py")
        return not problems, "; ".join(problems)
    case("the decided constants and registrations match docs/roadmap.md",
         constants_match_the_spec)

    # -- v0.3.0 repairs: three defects found by measurement, 2026-09-17 ----
    def batch_size_is_a_bound():
        """The test corpus holds one path-group of 1,140 fragments, and every
        fragment with no ancestor path shares the empty path -- so
        context-free material collapses into a single group of everything.
        _make_batches used to never split a group, which made batch_size a
        hint. A 948-fragment call measured that day returned 1,580 answer
        lines for 948 fragments."""
        groups = [(("p",), [{"guid": str(i), "text": "x", "path": ("p",)}
                            for i in range(250)])]
        batches = L._make_batches(groups, 100)
        biggest = max(sum(len(fs) for _, fs in b) for b in batches)
        total = sum(sum(len(fs) for _, fs in b) for b in batches)
        if biggest > 100:
            return False, f"largest batch holds {biggest}, batch_size is not a bound"
        if total != 250:
            return False, f"splitting lost or duplicated fragments: {total} of 250"
        return True, f"250 fragments -> {len(batches)} batches, largest {biggest}"
    case("[repair] batch_size is a bound: an oversized path-group is split",
         batch_size_is_a_bound)

    def ask_fails_loudly_on_empty_content():
        """A reasoning model truncated at max_tokens returns content=None with
        finish_reason='length'. The old ask() handed that None to the caller,
        which died inside _parse_response with an opaque AttributeError. No
        network here: urlopen is replaced for the duration."""
        import urllib.request as _u
        seen = {}
        class Fake:
            def __init__(self, pl): self._p = json.dumps(pl).encode()
            def read(self): return self._p
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def fake(req, timeout=None):
            seen["body"] = json.loads(req.data.decode())
            return Fake({"choices": [{"message": {"content": None},
                                      "finish_reason": "length"}]})
        real, _u.urlopen = _u.urlopen, fake
        old_key = os.environ.get("OPENROUTER_API_KEY")
        os.environ["OPENROUTER_API_KEY"] = "not-a-real-key"
        try:
            try:
                LLM.ask("s", "u")
                return False, "ask() returned a non-string instead of raising"
            except LLM.LLMError as e:
                if "length" not in str(e):
                    return False, f"the error does not name finish_reason: {e}"
            if not seen["body"].get("max_tokens"):
                return False, "the request sets no max_tokens"
            if seen["body"].get("reasoning") != {"exclude": True}:
                return False, "the request does not exclude the reasoning trace"
        finally:
            _u.urlopen = real
            if old_key is None: os.environ.pop("OPENROUTER_API_KEY", None)
            else: os.environ["OPENROUTER_API_KEY"] = old_key
        return True, "LLMError names finish_reason; max_tokens and reasoning set"
    case("[repair] ask() fails loudly on empty content, and caps its output",
         ask_fails_loudly_on_empty_content)

    def default_model_is_the_measured_one():
        """Measured over 2,207 fragments with ground truth; docs/decisions.md
        carries the table. The first default, gpt-4o-mini, was the worst of
        four tested."""
        if LLM.MODEL != "google/gemini-3.8-flash":
            return False, (f"MODEL={LLM.MODEL!r}, measured default is "
                           "google/gemini-3.8-flash")
        if LLM.MODEL not in LLM.PRICE_TABLE:
            return False, "the default model has no price table entry"
        return True, LLM.MODEL

    case("[repair] the default model is the one that was measured",
         default_model_is_the_measured_one)

    def duplicate_label_is_refused():
        """14 headings repeat across the twelve Wikipedia articles measured on
        2026-09-17 -- Definition, History, Examples, Properties. A flat index
        merged them silently; the map must refuse instead."""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "m.md"
            f.write_text("---\nconcept_map: true\n---\n\n"
                         "# Storage\n\nOne.\n\n# Storage\n\nTwo.\n")
            recs, root = R.ast_to_records(MD.ast_of_file(str(f)))
            try:
                L._label_index(L._concept_map_tree(recs, root))
                return False, "a duplicate label was accepted and merged"
            except L.ConceptMapError as e:
                if "Storage" not in str(e):
                    return False, f"the refusal does not name the label: {e}"
        return True, "refused, naming the label"
    case("[repair] a map naming two labels the same is refused, not merged",
         duplicate_label_is_refused)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<62} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} concept-map guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

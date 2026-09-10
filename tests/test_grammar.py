#!/usr/bin/env python3
"""
test_grammar.py — the record grammar cannot drift from the records.

Through v0.2.11 the ground truth here was `docs/record-grammar.md`, a
**markdown document**, discovered by scraping its prose with regexes:
splitting on the literal heading string `## 3. Node types`, parsing markdown
table pipes, pulling field names out of backticks. Rename that heading and the
suite would not fail — it would find fewer types and quietly assert less.
`TODO-code-review.md` keeps that incident; this file is the fix, scheduled as
v0.2.12 (`docs/roadmap.md`).

**The ground truth is now `tools/record-schema-1.json`**, read with
`json.load` rather than scraped, plus `records.check()` for the ten
cross-record invariants no per-document schema can express — see
`docs/compost.md` §4, "the per-type grammar, now in three layers".

The base against which the schema is held is still **built from the
fixtures**, not from the code: a type the program can emit but no fixture
reaches is a type nobody has ever seen written, and a schema entry for it
would be a guess. Checked in **both directions**, like `test_manpage.py`: the
schema may not name a type the base never produces, and the base may not
produce one the schema does not name. The same for edge `(layer, type)`
pairs, and for the params of every node type — an undocumented param is
exactly the drift this exists to catch. New in v0.2.12: every record in the
base is validated against the schema directly, which no amount of
table-scraping ever did.
"""
import json
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R    # noqa: E402
from src import session as SESS  # noqa: E402
from src import store as S      # noqa: E402
from tools import build_whitepaper as BW   # noqa: E402
from tools import schema_tables as ST      # noqa: E402

HERE = Path(__file__).parent
FIX = HERE / "fixtures"

# Written down rather than discovered, because "the program cannot produce this
# yet" is a claim about intent that no probe can make. Empty since v0.2.4: it
# used to hold `("citation", "cites")`, while `citation_edges` was defined and
# tested but called by nothing in `src/`. Wiring the citation layer
# (`compost layer citation`) was the point of deleting that entry — kept as an
# empty set rather than removed outright, since a future edge pair may need
# the same "documented, not yet exercised" allowance.
NOT_YET_MINTED = set()


def documented_nodes(schema: dict) -> dict:
    """Node type -> the param names the schema allows for it (required and
    optional together — the check here is "no param appears that is
    undocumented", not "every documented param appears"; a fixture is not
    obliged to exercise an optional key)."""
    return {name: set(spec["params"]["properties"])
            for name, spec in schema["$defs"]["node_types"].items()}


def documented_edges(schema: dict) -> set:
    """The `(layer, type)` pairs `$defs/edge_pairs` names."""
    return {(p["layer"], p["type"]) for p in schema["$defs"]["edge_pairs"]}


def build() -> list:
    """Digest every fixture through its real route, and load the base back.

    Through `store._digest` rather than `routes.read`, because `blob`,
    `derived_from` and `launched` are minted by the store and a route-level
    sweep would report them missing when they are merely elsewhere. That is the
    measurement error this suite exists to not repeat.

    Also digests one document written *inside this test*, citing two handles —
    one a real block guid read out of the base already built, one fabricated —
    and runs `compost layer citation` over the whole thing. A committed fixture
    with a hard-coded guid would never resolve in a fresh base, so the
    resolvable citation has to be minted at test time; the fabricated one needs
    no such care. Two citations, so both branches of the layer fire at once: a
    resolved `cites` edge, and an `alias`/`unresolved_citation`/`names` triple
    for the one that does not resolve.

    And one `claude-code-response` wrapper, answering the same guid just read
    out of the base — the only way to exercise `conversation`/`responds_to`
    and `conversation`/`next` here is against a real record, for the same
    reason the citation above cannot be a committed fixture.
    """
    with tempfile.TemporaryDirectory() as d:
        st = S.Store.init(Path(d))
        batches = [
            ("notes", sorted(str(p) for p in (FIX / "notes").glob("*.md"))
             + [str(FIX / "edge-cases/nested-lists.md"),
                str(FIX / "grammar/all-constructors.md")]),
            ("pandoc-ast", [str(FIX / "ast/unreachable-constructors.json")]),
            ("claude-code-transcript",
             [str(FIX / "sessions/session-smoke.jsonl"),
              str(FIX / "sessions/sidechain-parent.jsonl"),
              str(FIX / "grammar/contentblock.jsonl")]),
        ]
        import contextlib
        import io
        for route, args in batches:
            with contextlib.redirect_stdout(io.StringIO()):
                if S._digest(st, route, args, "compost"):
                    raise RuntimeError(f"digest failed for {route}")

        # A `mutable` root, revised once — v0.2.16, "TA". Without this the
        # schema could name `(ingestion, revision_of)` while nothing in the
        # base ever mints one, which is exactly the drift "every (layer,
        # type) the schema names is exercised" exists to catch. Same
        # reasoning as wiring the citation layer in here rather than leaving
        # it merely documented.
        mutable_note = Path(d) / "mutable.md"
        mutable_note.write_text("A mutable paragraph.\n")
        with contextlib.redirect_stdout(io.StringIO()):
            if S._digest(st, "notes", [str(mutable_note)], "compost",
                        mutability="mutable"):
                raise RuntimeError("digest failed for mutable.md")
        recs_mut, _ = st.load()
        mutable_root = next(
            r["guid"] for r in recs_mut if r["record"] == "node"
            and r["type"] == "document"
            and (r.get("params") or {}).get("mutability") == "mutable")
        with contextlib.redirect_stdout(io.StringIO()):
            if S._digest(st, "notes", [str(mutable_note)], "compost",
                        updates=mutable_root):
                raise RuntimeError("revision failed for mutable.md")

        recs, _ = st.load()
        target = next(r for r in recs
                      if r["record"] == "node" and r["type"] == "Para")
        # `responds_to` names a ROOT, never a block — a block is already the
        # source of a pandoc-ast `next` edge to its own sibling, and
        # `Graph._next` keys the whole chain by source alone with no layer
        # discriminator (`src/records.py:302`), so pointing a conversation
        # `next` edge at a block's guid would silently overwrite that block's
        # real sibling link. Roots are nobody's sibling, which is the only
        # reason reusing `next` here is safe (docs/record-grammar.md §4).
        answered_root = next(r for r in recs if r["record"] == "node"
                             and r["type"] in R.ROOT_TYPES)
        citing = Path(d) / "citing.md"
        citing.write_text(
            f"Citing [-](#{target['guid']}) and also "
            f"[-](#deadbeef-0000-0000-0000-000000000000).\n")
        with contextlib.redirect_stdout(io.StringIO()):
            if S._digest(st, "notes", [str(citing)], "compost"):
                raise RuntimeError("digest failed for citing.md")
            from src import layers as LY
            LY.build(st, "citation", "uuid-link")

        wrapper = Path(d) / "response.json"
        wrapper.write_text(json.dumps({
            "responds_to": answered_root["guid"],
            "envelope": {
                "is_error": False, "duration_api_ms": 1, "num_turns": 1,
                "stop_reason": "end_turn", "session_id": "grammar-test",
                "total_cost_usd": 0.0, "usage": {"input_tokens": 1},
                "modelUsage": {}, "permission_denials": [],
                "terminal_reason": "completed", "fast_mode_state": "off",
                "fast_mode_disabled_reason": "n/a", "subtype": "success",
                "api_error_status": None, "result": "A response paragraph.\n",
                "ttft_ms": 1, "ttft_stream_ms": 1, "time_to_request_ms": 1,
                "type": "result", "duration_ms": 1,
                "uuid": "00000000-0000-4000-8000-000000000000",
            },
        }))
        with contextlib.redirect_stdout(io.StringIO()):
            if S._digest(st, "claude-code-response", [str(wrapper)], "compost"):
                raise RuntimeError("digest failed for response.json")

        # A display name, hand-written straight into graph/ — the only way
        # one is ever produced (v0.2.10: the view reads them, nothing in
        # `src/` writes them). Exercises `display_name` / `names` / the
        # `display` layer, none of which any route or layer builder mints.
        b = R.Builder()
        dn = b.node("display_name", {"value": "A hand-written display name"})
        b.edge("names", dn, answered_root["guid"], "display")
        R.stamp_hashes(b.records)
        st.write("display-name.jsonl", b.records)

        # The v0.1 handle dictionary's alias shape, which no other fixture
        # reaches: `tools/v01_dictionary.py` writes 152 of these in a real
        # migrated base, with two params the citation layer's aliases never
        # carry. Without this the schema could name them and the
        # documented-implies-exercised check would fail — which is the check
        # working, and this fixture is the honest answer to it rather than
        # deleting the params from the schema.
        b2 = R.Builder()
        al = b2.node("alias", {"value": "a3f2b1c4", "scheme": "kg-8hex",
                               "generated_by": "tools/v01_dictionary.py",
                               "pandoc": "3.10"})
        for r in b2.records:
            r["created_at"], r["tool_version"] = R._now(), "0.2.12"
        b2.edge("names", al, answered_root["guid"], "citation")
        R.stamp_hashes(b2.records)
        st.write("v01-alias.jsonl", b2.records)

        recs, _ = st.load()
        return recs


# -- guarantee 5: the scrapers are gone --------------------------------------
#
# Built by concatenation rather than as one literal, on purpose: written as a
# single string, this file's own source would contain the exact sequence it
# is searching for, and the check would fail against itself forever. Split
# across a `+`, the two pieces never sit next to each other in this file's
# raw text, so only a *reintroduced* scraper — which would write the whole
# thing as one literal, the way the old one did — can trip it.
_SCRAPED_SPLIT = "text." + 'split("## '
_SCRAPED_TABLE = "strip(" + '"|"' + ")"


def no_markdown_scraping() -> bool:
    """True if this file no longer splits on a heading or parses table pipes."""
    text = Path(__file__).read_text(encoding="utf-8")
    return _SCRAPED_SPLIT not in text and _SCRAPED_TABLE not in text


def main():
    schema = ST.load_schema()
    doc_nodes = documented_nodes(schema)
    doc_edges = documented_edges(schema)
    recs = build()

    seen_nodes = Counter(r["type"] for r in recs if r["record"] == "node")
    seen_edges = {(r["layer"], r["type"]) for r in recs
                  if r["record"] == "edge"}
    seen_params = defaultdict(set)
    for r in recs:
        if r["record"] == "node":
            seen_params[r["type"]] |= set((r.get("params") or {}).keys())

    problems = []
    results = []

    def check(name, ok, detail=""):
        print(f"  {'ok   ' if ok else 'FAIL '} {name:<52} {detail}")
        results.append(ok)
        if not ok:
            problems.append(name)

    # Guarantee 1: every record in the fixture base validates against the
    # schema. The half table-scraping never did at all.
    validator = jsonschema.Draft202012Validator(schema)
    invalid = []
    for r in recs:
        errs = sorted(validator.iter_errors(r), key=lambda e: e.message)
        if errs:
            invalid.append(f"{r['type']} {r['guid'][:8]}: {errs[0].message}")
    check("every record in the fixture base validates against the schema",
          not invalid,
          "; ".join(invalid[:3]) + (f"  (+{len(invalid) - 3} more)"
                                     if len(invalid) > 3 else ""))

    # Guarantee 2, both directions.
    undocumented = sorted(set(seen_nodes) - set(doc_nodes))
    check("every node type in the base is in the schema",
          not undocumented, ", ".join(undocumented))

    unexercised = sorted(set(doc_nodes) - set(seen_nodes))
    check("every node type the schema names is exercised",
          not unexercised, ", ".join(unexercised))

    # Guarantee 4.
    bad_params = []
    for t, params in sorted(seen_params.items()):
        extra = params - doc_nodes.get(t, set())
        if extra:
            bad_params.append(f"{t}: {', '.join(sorted(extra))}")
    check("no node carries a param the schema does not name",
          not bad_params, "; ".join(bad_params))

    # Guarantee 3, both directions.
    e_undoc = sorted(seen_edges - doc_edges)
    check("every (layer, type) in the base is in the schema",
          not e_undoc, ", ".join(map(str, e_undoc)))

    e_unex = sorted(doc_edges - seen_edges - NOT_YET_MINTED)
    check("every (layer, type) the schema names is exercised",
          not e_unex, ", ".join(map(str, e_unex)))

    still_absent = sorted(p for p in NOT_YET_MINTED if p in seen_edges)
    check("the not-yet-minted list is still accurate",
          not still_absent,
          f"{still_absent} is minted now — update the allowance"
          if still_absent else "")

    # The two fixtures this suite added carry the guarantees of their own
    # routes, or they would be documenting a shape the tool cannot read back.
    src = FIX / "grammar/contentblock.jsonl"
    lines = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    srecs, sroot = SESS.session_to_records(src)
    check("the contentblock fixture round-trips exactly",
          SESS.records_to_session(srecs, sroot) == lines)

    # Guarantee 8 (partial — the round-trip half is test_records.py's own
    # 526/526; this is the part that belongs to a graph built here).
    check("the assembled base passes check", not R.check(recs))

    # Guarantee 5.
    check("test_grammar.py contains no markdown-scraping code",
          no_markdown_scraping())

    # Guarantee 6: the committed appendix already holds exactly what the
    # generator produces right now. Sabotage: hand-edit one table cell in
    # docs/compost.md between the markers and this fails.
    wp_text = BW.WHITEPAPER.read_text(encoding="utf-8")
    committed = wp_text.split(BW.BEGIN, 1)[1].split(BW.END, 1)[0].strip()
    fresh = ST.render(schema).strip()
    check("the whitepaper's appendix matches what the generator produces",
          committed == fresh,
          "" if committed == fresh else
          f"{len(committed)} vs {len(fresh)} chars committed/generated")

    # Guarantee 7: running the build twice on a scratch copy is idempotent.
    # A scratch copy, never the tracked file — the property under test is the
    # script's, not a side effect of this suite running.
    with tempfile.TemporaryDirectory() as d:
        scratch = Path(d) / "compost.md"
        scratch.write_text(wp_text, encoding="utf-8")
        BW.build(whitepaper=scratch)
        once = scratch.read_text(encoding="utf-8")
        changed_again = BW.build(whitepaper=scratch)
        twice = scratch.read_text(encoding="utf-8")
        check("the appendix build is idempotent",
              once == twice and not changed_again,
              "" if once == twice else "second run changed the file")

    total = len(results)
    print(f"\n{total - len(problems)}/{total} grammar guarantees hold  |  "
          f"{len(seen_nodes)} node types, {len(seen_edges)} edge pairs, "
          f"{sum(seen_nodes.values())} nodes")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

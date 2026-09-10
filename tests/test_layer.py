#!/usr/bin/env python3
"""
test_layer.py — what `compost layer citation` promises.

Two separate bases, because mixing them breaks property 2: a placeholder gets
a fresh guid every build, so two builds' `cites` edges into a placeholder have
different `destination` and therefore different `record_hash` — the pairing
property only holds when every citation in the base actually resolves.

**Base A** — every citation resolves. Properties 1-3.
**Base B** — some citations do not resolve. Properties 4-6.
**Either base** — properties 7-8.
**Base C** — the legacy `kg-8hex` scheme. Properties 9-15.

Base C is written inline rather than read from `tests/corpus/`, so the legacy
scheme is exercised on a bare clone too. The curated fixture it mirrors is
`corpus/compost-corpus/curated/edge-cases/handles.md`; the recall property
measures against whatever material is actually on disk and states the tier.

Running the builder twice is supposed to produce two full sets of records,
neither removed — that is the design (docs/roadmap.md, "the tool does not
hold your hand"), and property 1 is what stops a later reader "fixing" it.
"""
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import layers as L      # noqa: E402
from src import markdown as MD   # noqa: E402
from src import records as R     # noqa: E402
from src import routes as RT     # noqa: E402
from src import store as S       # noqa: E402
from tests import tier as T      # noqa: E402

FAKE = "deadbeef-0000-0000-0000-000000000000"


def _digest_text(st, tmp, name, text):
    """Write `text` to `tmp/name`, read it as `notes`, and commit it to `st`.

    Goes through the real markdown reader rather than hand-built records, so
    a `[-](#guid)` in the text becomes a genuine `Link` node — the whole point
    of `citation_edges` is that it never regexes text.
    """
    p = tmp / name
    p.write_text(text)
    recs, root = R.ast_to_records(MD.ast_of_file(p), source=name, route="notes")
    st.write(f"{name}.jsonl", recs)
    return recs, root


def _cites(recs):
    return [r for r in recs if r["record"] == "edge" and r["type"] == "cites"]


def _nodes_of_type(recs, t):
    return [r for r in recs if r["record"] == "node" and r["type"] == t]


def build_base_a(tmp: Path):
    """Every citation resolves: one target paragraph, one citing paragraph."""
    st = S.Store.init(tmp / "a")
    target_recs, _ = _digest_text(st, tmp, "target.md", "A target paragraph.\n")
    target = next(r for r in target_recs
                  if r["record"] == "node" and r["type"] == "Para")
    _digest_text(st, tmp, "citing.md",
                 f"Citing [-](#{target['guid']}) here.\n")
    citing_recs, _ = st.load()
    citer = next(r for r in citing_recs if r["record"] == "node"
                 and r["type"] == "Para"
                 and R._links(r) and R._links(r)[0] == f"#{target['guid']}")
    return st, target["guid"], citer["guid"]


def build_base_b(tmp: Path):
    """Some citations do not resolve: one fabricated handle, cited twice."""
    st = S.Store.init(tmp / "b")
    _, root = _digest_text(
        st, tmp, "citing.md",
        f"Citing [-](#{FAKE}) and again [-](#{FAKE}) here.\n")
    recs, _ = st.load()
    citer = next(r for r in recs if r["record"] == "node"
                 and r["type"] == "Para")
    return st, citer["guid"]


# Every form the v0.1 corpus writes, and every decoy it writes beside them.
# `c0ffee11` is a real 8-hex handle placed only inside code: if it ever mints
# an edge, the walk has started reading `params["text"]` and the rule that
# "handles inside code are not citations" has stopped being structural.
BASE_C_TEXT = """A citation {#a1b2c3d4} in the middle of a sentence.

Expanded {#a1b2c3d4+++} and pinned {#a1b2c3d4@latest}, then one that ends a
clause {#a1b2c3d4}.

Metasyntactic: {#handle}, {#uuid:hash}, {#xxxxxxxx} and {#...} are prose about
handles, not handles.

Inside code `{#c0ffee11}` is not a citation, and neither is

```
{#c0ffee11}
```
"""


def build_base_c(tmp: Path):
    """Legacy handles, no dictionary yet."""
    st = S.Store.init(tmp / "c")
    _digest_text(st, tmp, "legacy.md", BASE_C_TEXT)
    recs, _ = st.load()
    target = next(r for r in recs if r["record"] == "node"
                  and r["type"] == "Para")
    return st, target["guid"]


def add_dictionary(st, value: str, target: str, scheme: str = "kg-8hex"):
    """What the migration's one-off script produces, in miniature.

    Hand-written records under `graph/` are allowed for exactly this — see
    docs/decisions.md. `check` is the enforcement, not the identity of the
    writer, so the test asserts `check` afterwards rather than trusting it.
    """
    b = R.Builder()
    al = b.node("alias", {"value": value, "scheme": scheme,
                          "generated_by": "tests/test_layer.py"})
    b.edge("names", al, target, "citation", by=scheme)
    R.stamp_hashes(b.records)
    st.write(f"dictionary-{value}-{target[:8]}.jsonl", b.records)


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

        # -- Base A: every citation resolves ---------------------------------
        st_a, target_guid, citer_guid = build_base_a(tmp)

        def builds_twice():
            with contextlib.redirect_stdout(io.StringIO()):
                L.build(st_a, "citation", "uuid-link")
                recs1, _ = st_a.load()
                c1 = len(_cites(recs1))
                L.build(st_a, "citation", "uuid-link")
                recs2, _ = st_a.load()
                c2 = len(_cites(recs2))
            return c1 == 1 and c2 == 2 * c1, f"{c1} then {c2} cites edges"
        case("building twice produces two full sets", builds_twice)

        def pair_by_hash():
            recs, _ = st_a.load()
            cites = _cites(recs)
            hashes = [e["record_hash"] for e in cites]
            guids = {e["guid"] for e in cites}
            return (len(cites) == 2 and hashes[0] == hashes[1]
                    and len(guids) == 2,
                    f"{len(cites)} edges, {len(set(hashes))} distinct hash(es)")
        case("the two sets pair up by record_hash, distinct guids",
             pair_by_hash)

        def hash_ignores_provenance():
            recs, _ = st_a.load()
            e = _cites(recs)[0]
            other = dict(e, created_at="1970-01-01T00:00:00Z",
                        tool_version="0.0.0")
            return (R.edge_hash(other) == e["record_hash"],
                    "record_hash unchanged by created_at/tool_version")
        case("record_hash ignores created_at and tool_version",
             hash_ignores_provenance)

        # -- Base B: some citations do not resolve ---------------------------
        st_b, citer_b = build_base_b(tmp)
        with contextlib.redirect_stdout(io.StringIO()):
            L.build(st_b, "citation", "uuid-link")
        recs_b, _ = st_b.load()

        def one_alias_one_placeholder():
            aliases = _nodes_of_type(recs_b, "alias")
            placeholders = _nodes_of_type(recs_b, "unresolved_citation")
            cites = _cites(recs_b)
            dests = {e["destination"] for e in cites}
            return (len(aliases) == 1 and len(placeholders) == 1
                    and len(cites) == 2 and dests == {placeholders[0]["guid"]},
                    f"{len(aliases)} alias, {len(placeholders)} placeholder, "
                    f"{len(cites)} cites edges into it")
        case("one alias and one placeholder per distinct value",
             one_alias_one_placeholder)

        def check_is_clean():
            problems = R.check(recs_b)
            return not problems, f"{len(problems)} problems"
        case("check is clean after a build with unresolved citations",
             check_is_clean)

        def lookup_by_alias():
            # Mirrors the reverse path step 8 wires into `compost lookup`:
            # find an alias node by value, follow its `names` edge.
            aliases = [r for r in _nodes_of_type(recs_b, "alias")
                      if r["params"]["value"] == FAKE]
            names = {e["source"]: e["destination"] for e in recs_b
                    if e["record"] == "edge" and e["type"] == "names"}
            placeholders = _nodes_of_type(recs_b, "unresolved_citation")
            targets = {names[a["guid"]] for a in aliases}
            return (len(aliases) == 1 and aliases[0]["params"]["scheme"] == "uuid-link"
                    and targets == {placeholders[0]["guid"]},
                    f"alias -> {targets}, scheme {aliases[0]['params']['scheme'] if aliases else '?'}")
        case("lookup by alias value returns the placeholder, names the scheme",
             lookup_by_alias)

        # -- Either base -------------------------------------------------------
        def linked_keeps_by():
            g = R.Graph(recs_b)
            edges = g.linked(citer_b, "cites")
            return (len(edges) == 2 and all(e.get("by") == "uuid-link" for e in edges),
                    f"{len(edges)} edges, by={[e.get('by') for e in edges]}")
        case("Graph.linked preserves by", linked_keeps_by)

        def every_record_has_schema_version():
            missing = [r for r in recs_b if r.get("schema_version") is None]
            return (not missing,
                    f"{len(missing)} of {len(recs_b)} records lack schema_version")
        case("every record in the base carries schema_version",
             every_record_has_schema_version)

        # -- Base C: the legacy kg-8hex scheme -------------------------------
        st_c, target_c = build_base_c(tmp)
        with contextlib.redirect_stdout(io.StringIO()):
            r_c1 = L.build(st_c, "citation", "kg-8hex")
        recs_c1, _ = st_c.load()

        def prose_only():
            # 4 occurrences of a1b2c3d4, all in prose. c0ffee11 appears twice,
            # both inside code, and must contribute nothing at all.
            handles = {v for v in r_c1["unresolved"]}
            return (r_c1["cites"] == 4 and handles == {"a1b2c3d4"},
                    f"{r_c1['cites']} cites, handles {sorted(handles)}")
        case("kg-8hex reads prose and never code", prose_only)

        def decoys_mint_nothing():
            aliases = {a["params"]["value"] for a in
                       _nodes_of_type(recs_c1, "alias")}
            decoys = {"handle", "uuid:hash", "xxxxxxxx", "...", "c0ffee11"}
            return (not (aliases & decoys) and len(aliases) == 1,
                    f"aliases {sorted(aliases)}")
        case("metasyntactic forms and code handles mint nothing",
             decoys_mint_nothing)

        def four_forms_one_handle():
            # bare, +++, @ver and bare-before-punctuation are one handle cited
            # four times, not four handles: the suffix is not part of the name.
            phs = _nodes_of_type(recs_c1, "unresolved_citation")
            dests = {e["destination"] for e in _cites(recs_c1)}
            return (len(phs) == 1 and dests == {phs[0]["guid"]},
                    f"{len(phs)} placeholder, {len(dests)} distinct target")
        case("all four syntax forms name one handle", four_forms_one_handle)

        def match_is_within_a_str():
            # Runs `legacy_handle_refs` itself against real v0.1-derived prose
            # and compares it to what whole-`Str` equality would have found.
            # Measuring the regex directly would assert a fact about the corpus
            # instead of a property of the reader, and would keep passing after
            # the reader was changed back to equality — which is the exact
            # mistake this property exists to prevent.
            found = whole = 0
            for path in T.markdown("notes"):
                recs, _ = R.ast_to_records(MD.ast_of_file(path), source=path.name,
                                           route="notes")
                found += len(R.legacy_handle_refs(recs))
                for n in recs:
                    if n["record"] != "node":
                        continue
                    for text in R._strs(n):
                        if R.LEGACY_HANDLE.fullmatch(text):
                            whole += 1
            tier = "corpus" if T.have_corpus() else "smoke set"
            lost = found - whole
            return (found > whole > 0,
                    f"{found} found vs {whole} by whole-Str equality — "
                    f"{lost} ({100 * lost / found:.0f}%) would be lost, {tier}")
        case("the match is within a Str, not whole-Str equality",
             match_is_within_a_str)

        def placeholder_resolves_later():
            add_dictionary(st_c, "a1b2c3d4", target_c)
            with contextlib.redirect_stdout(io.StringIO()):
                r2 = L.build(st_c, "citation", "kg-8hex")
            recs2, _ = st_c.load()
            # The dictionary arrived, so the same four citations now reach the
            # real block — and the first build's placeholder is still there.
            resolved = [e for e in _cites(recs2) if e["destination"] == target_c]
            phs = _nodes_of_type(recs2, "unresolved_citation")
            return (r2["cites"] == 4 and r2["placeholders"] == 0
                    and len(resolved) == 4 and len(phs) == 1,
                    f"{len(resolved)} edges to the real block, "
                    f"{len(phs)} placeholder kept, not retracted")
        case("a placeholder resolves once the dictionary arrives",
             placeholder_resolves_later)

        def ignores_own_placeholders():
            # SABOTAGE. Build again: the run above minted no placeholder, but
            # the run before it did, and its alias names one. Following that
            # `names` edge would make a1b2c3d4 ambiguous, and every further
            # build would add another candidate.
            with contextlib.redirect_stdout(io.StringIO()):
                r3 = L.build(st_c, "citation", "kg-8hex")
            honest = (r3["cites"] == 4 and not r3["ambiguous"])

            real = L._alias_targets
            try:
                def blind(recs, scheme):        # the rule, removed
                    aliases = {r["guid"]: (r.get("params") or {}).get("value")
                               for r in recs if r["record"] == "node"
                               and r["type"] == "alias"
                               and (r.get("params") or {}).get("scheme") == scheme}
                    out = {}
                    for e in recs:
                        if e["record"] == "edge" and e["type"] == "names":
                            v = aliases.get(e["source"])
                            if v is not None:
                                out.setdefault(v, set()).add(e["destination"])
                    return out
                L._alias_targets = blind
                recs3, _ = st_c.load()
                sabotaged = L._kg8hex(recs3, "citation", "kg-8hex")
            finally:
                L._alias_targets = real
            return (honest and sabotaged["ambiguous"].get("a1b2c3d4") == 2,
                    f"honest: {r3['cites']} cites, 0 ambiguous | "
                    f"without the rule: {sabotaged['ambiguous']}")
        case("the resolver ignores its own placeholders (sabotaged)",
             ignores_own_placeholders)

        def ambiguity_mints_nothing():
            # A second, different real target for the same handle. Two real
            # candidates is not a tie to break silently.
            other = next(r["guid"] for r in recs_c1 if r["record"] == "node"
                         and r["type"] == "Para" and r["guid"] != target_c)
            add_dictionary(st_c, "a1b2c3d4", other)
            recs4, _ = st_c.load()
            before = len(_cites(recs4))
            with contextlib.redirect_stdout(io.StringIO()):
                r4 = L.build(st_c, "citation", "kg-8hex")
            recs5, _ = st_c.load()
            minted = len(_cites(recs5)) - before
            return (r4["ambiguous"].get("a1b2c3d4") == 2 and minted == 0
                    and r4["cites"] == 0 and not R.check(recs5),
                    f"reported {r4['ambiguous']}, minted {minted} edges, "
                    f"{len(R.check(recs5))} check problems")
        case("an ambiguous handle mints nothing and is reported",
             ambiguity_mints_nothing)

        def default_is_still_uuid_link():
            # Adding a second scheme must not change what bare
            # `compost layer citation` does. Run the real entry point, on a
            # base full of legacy handles and holding no `[-](#guid)` at all:
            # if the default ever slipped to kg-8hex this mints four edges,
            # and on a base without legacy handles it would mint none and the
            # property would pass while guarding nothing.
            st_d = S.Store.init(tmp / "d")
            _digest_text(st_d, tmp, "legacy-d.md", BASE_C_TEXT)
            here = Path.cwd()
            os.chdir(st_d.root)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = L.main(["layer", "citation"])
            finally:
                os.chdir(here)
            recs, _ = st_d.load()
            legacy = [e for e in _cites(recs) if e.get("by") == "kg-8hex"]
            return (rc == 0 and L.DEFAULT_BY["citation"] == "uuid-link"
                    and len(L.BUILDERS["citation"]) > 1
                    and not legacy and not _cites(recs),
                    f"rc={rc}, {len(L.BUILDERS['citation'])} schemes, "
                    f"{len(legacy)} kg-8hex edges from a bare invocation")
        case("bare `layer citation` still means uuid-link",
             default_is_still_uuid_link)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} layer guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

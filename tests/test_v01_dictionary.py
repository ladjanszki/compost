#!/usr/bin/env python3
"""
test_v01_dictionary.py — the alias dictionary the migration needs.

The dictionary is the one thing `compost layer citation --by kg-8hex` cannot
derive for itself: an 8-hex handle is not a guid, so something outside the tool
has to say which block it names. This suite holds that generator to the rules
the rest of the base is held to — `check` passes, provenance is on every
record, and nothing is invented.

Written as a *hand-built* base rather than a corpus read, so it runs on a bare
clone: the v0.1 `.dj` files are private and are not the subject here.
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import layers as L      # noqa: E402
from src import records as R     # noqa: E402
from src import store as S       # noqa: E402
from tools import v01_dictionary as D   # noqa: E402


def base_with_handles(tmp: Path):
    """Three blocks carrying v0.1 ids, one citing another in prose."""
    st = S.Store.init(tmp / "b")
    b = R.Builder()
    doc = b.node("document", {"source": "old.dj", "route": "pandoc-ast"})
    kids = []
    for handle, text in (("a1b2c3d4", "The cited paragraph."),
                         ("e5f6a7b8", "Another one."),
                         ("c0ffee11", "A third.")):
        g = b.node("Div", {"attr": [handle, [], []]})
        p = b.node("Para", None, [{"t": "Str", "c": text}])
        b.children(g, [p])
        kids.append(g)
    citer = b.node("Para", None,
                   [{"t": "Str", "c": "See"}, {"t": "Space"},
                    {"t": "Str", "c": "{#a1b2c3d4}"}])
    kids.append(citer)
    b.children(doc, kids)
    st.write("old.jsonl", b.records)
    return st, citer


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
        st, citer = base_with_handles(tmp)
        recs, _ = st.load()
        built, dupes = D.build(recs)
        aliases = [r for r in built if r["record"] == "node"]
        names = [r for r in built if r["record"] == "edge"]

        def one_each():
            return (len(aliases) == 3 and len(names) == 3 and not dupes,
                    f"{len(aliases)} aliases, {len(names)} names edges")
        case("one alias and one names edge per 8-hex id", one_each)

        def only_8hex():
            vals = {a["params"]["value"] for a in aliases}
            return (vals == {"a1b2c3d4", "e5f6a7b8", "c0ffee11"},
                    f"values {sorted(vals)}")
        case("nothing but 8-hex ids becomes an alias", only_8hex)

        def provenance_present():
            bad = [a for a in aliases
                   if not (a.get("created_at") and a.get("tool_version")
                           and a["params"]["generated_by"].endswith("v01_dictionary.py")
                           and a["params"]["scheme"] == "kg-8hex")]
            return not bad, f"{len(bad)} of {len(aliases)} missing provenance"
        case("every alias records who generated it and how", provenance_present)

        def check_is_clean():
            st.write("dict.jsonl", built)
            all_recs, _ = st.load()
            return not R.check(all_recs), f"{len(R.check(all_recs))} problems"
        case("check passes with the dictionary loaded", check_is_clean)

        def it_actually_resolves():
            with contextlib.redirect_stdout(io.StringIO()):
                r = L.build(st, "citation", "kg-8hex")
            after, _ = st.load()
            real = [e for e in after if e["record"] == "edge"
                    and e["type"] == "cites" and e["source"] == citer]
            return (r["cites"] == 1 and r["placeholders"] == 0
                    and not r["ambiguous"] and len(real) == 1,
                    f"{r['cites']} cites, {r['placeholders']} placeholders, "
                    f"ambiguous={r['ambiguous']}")
        case("the citation resolves through it, no placeholder",
             it_actually_resolves)

        def twice_is_not_ambiguous():
            # Two aliases for one handle both name the SAME block, and
            # _alias_targets collects destinations into a set — so a second
            # dictionary is redundant, never ambiguous. Asserted because the
            # opposite would make a re-run corrupt the base.
            again, _ = D.build(recs)
            st.write("dict-2.jsonl", again)
            with contextlib.redirect_stdout(io.StringIO()):
                r = L.build(st, "citation", "kg-8hex")
            return (not r["ambiguous"] and r["cites"] == 1,
                    f"after a second dictionary: {r['cites']} cites, "
                    f"ambiguous={r['ambiguous']}")
        case("a second dictionary is redundant, not ambiguous",
             twice_is_not_ambiguous)

        def duplicates_are_reported():
            # A handle on two blocks cannot be resolved and must not be guessed.
            b = R.Builder()
            for _ in range(2):
                b.node("Div", {"attr": ["deadbeef", [], []]})
            _, dup = D.build(b.records)
            return dup == ["deadbeef"], f"reported {dup}"
        case("a handle on two blocks is reported, never picked",
             duplicates_are_reported)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} dictionary guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

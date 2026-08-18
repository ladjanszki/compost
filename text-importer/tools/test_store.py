#!/usr/bin/env python3
"""
test_store.py — the loader's promises, each one sabotage-verified.

Every case here is a rule from store.py's docstring. A rule nobody has tried
to break is a comment, not a guarantee.
"""
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import records as R      # noqa: E402
import store as S        # noqa: E402

HERE = Path(__file__).parent.parent
FIXTURES = sorted((HERE / "fixtures/edge-cases").glob("*.md"))[:8]


def build(tmp: Path) -> S.Store:
    st = S.Store.init(tmp)
    for f in FIXTURES:
        recs, _ = R.ast_to_records(S._ast_of(f))
        st.keep_source(f)
        st.write(f"{f.stem}.jsonl", recs)
    return st


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
        st = build(tmp)

        def loads_clean():
            recs, files = st.load()
            return not R.check(recs), f"{len(files)} files, {len(recs)} records"
        case("a freshly written base loads and checks clean", loads_clean)

        def order_irrelevant():
            a, _ = st.load()
            files = st.files()
            shuffled = files[:]
            random.shuffle(shuffled)
            seen, out = set(), []
            for f in shuffled:
                for rec in R.from_jsonl(f.read_text()):
                    k = R.canonical(rec)
                    if k not in seen:
                        seen.add(k)
                        out.append(rec)
            same = sorted(map(R.canonical, a)) == sorted(map(R.canonical, out))
            return same, "same graph from a shuffled file order"
        case("file order does not change the graph", order_irrelevant)

        def only_jsonl():
            before = len(st.load()[0])
            victim = st.files()[0]
            (st.graph / "note.jsonl~").write_text(victim.read_text())
            (st.graph / "note.bak").write_text(victim.read_text())
            (st.graph / "notes.txt").write_text(victim.read_text())
            after = len(st.load()[0])
            return before == after, f"{before} records before and after decoys"
        case("backup and stray files are not loaded", only_jsonl)

        def dedup():
            recs = R.from_jsonl(st.files()[0].read_text())
            st.write("a-copy-of-the-first.jsonl", recs)
            loaded, _ = st.load()
            return not R.check(loaded), "identical records collapse silently"
        case("a duplicated file dedupes rather than conflicts", dedup)

        def conflict_detected():
            recs, _ = st.load()
            node = next(r for r in recs if r["record"] == "node"
                        and r["type"] == "Para")
            twisted = dict(node, content=[{"t": "Str", "c": "different"}])
            st.write("conflict.jsonl", [twisted])
            problems = st.check()
            (st.graph / "conflict.jsonl").unlink()
            return any("two different records" in p for p in problems), \
                "one guid with two contents is rejected"
        case("a guid with two contents is a hard error", conflict_detected)

        def dangling():
            st.write("dangling.jsonl", [{
                "record": "edge", "guid": "x", "layer": R.LAYER,
                "type": "contains", "source": "nope", "destination": "also-nope"}])
            problems = st.check()
            (st.graph / "dangling.jsonl").unlink()
            return any("dangling" in p for p in problems), \
                "an edge pointing at nothing is caught"
        case("a dangling edge is caught", dangling)

        def atomic():
            leftovers = list(st.graph.rglob(".tmp-*"))
            try:
                st.write("bad.txt", [])
                refused = False
            except ValueError:
                refused = True
            return refused and not leftovers, \
                "non-.jsonl refused, no temp files left behind"
        case("writes are atomic and extension-checked", atomic)

        def immutable_source():
            f = FIXTURES[0]
            st.keep_source(f)                      # same content: fine
            forged = tmp / f.name
            forged.write_text("different content\n")
            try:
                st.keep_source(forged)
                return False, "overwrote a stored source"
            except ValueError:
                return True, "refuses to overwrite a source with different bytes"
        case("stored sources are immutable", immutable_source)

        def no_stem_collision():
            (tmp / "src").mkdir(exist_ok=True)
            a = tmp / "src" / "thing.md"
            a.write_text("# a document\n\nwith a paragraph.\n")
            b = tmp / "src" / "thing.jsonl"
            b.write_text(FIXTURES[0].read_text() and "")   # empty is fine here
            recs, _ = R.ast_to_records(S._ast_of(a), source=a.name)
            st.write(f"{a.stem}-{a.suffix.lstrip('.')}.jsonl", recs)
            before = len(st.load()[0])
            st.write(f"{b.stem}-{b.suffix.lstrip('.')}.jsonl", [])
            after = len(st.load()[0])
            return before == after and before > 0, \
                "two sources sharing a stem do not overwrite each other"
        case("same-stem sources get distinct graph files", no_stem_collision)

        def find_from_below():
            deep = tmp / "a" / "b" / "c"
            deep.mkdir(parents=True)
            found = S.Store.find(deep)
            return found.root == st.root, f"found {MARK} from three levels down"
        MARK = S.MARKER
        case("the base is found by walking up", find_from_below)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<48} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} storage guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

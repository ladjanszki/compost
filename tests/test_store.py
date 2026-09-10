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
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import markdown as MD     # noqa: E402
from src import records as R      # noqa: E402
from tests import tier as T  # noqa: E402
from src import store as S        # noqa: E402

HERE = Path(__file__).parent
FIXTURES = T.markdown("edge-cases")[:8]


def build(tmp: Path) -> S.Store:
    st = S.Store.init(tmp)
    for f in FIXTURES:
        recs, _ = R.ast_to_records(MD.ast_of_file(f))
        st.keep_blob(f, f"{uuid.uuid4()}{f.suffix}")
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

        def flat_write_refused():
            # graph/ is flat by rule (docs/roadmap.md, "graph/ becomes flat
            # by rule"): a relpath naming a subdirectory must raise rather
            # than create one.
            try:
                st.write("nested/x.jsonl", [])
                return False, "a nested relpath was accepted"
            except ValueError:
                return (not (st.graph / "nested").exists(),
                        "a nested relpath raises, and creates nothing")
        case("write() refuses a relpath with a subdirectory",
             flat_write_refused)

        def nested_not_loaded():
            # A file placed under graph/ by something other than `write` —
            # an older checkout, a hand copy — must stay invisible to the
            # loader. This is the half of the property `write()` alone
            # cannot cover: `files()` must glob, not walk.
            #
            # The smuggled record must be genuinely new, not a copy of one
            # already in the base: `load()` dedupes byte-identical records
            # (store.py, "Byte-identical duplicates collapse silently"), so a
            # copy of an existing record would make `rglob` and `glob` agree
            # on the count by accident and this property would pass either
            # way — caught by running the sabotage below before writing it
            # this way the first time.
            before, _ = st.load()
            sub = st.graph / "sub"
            sub.mkdir()
            novel = {"record": "node", "guid": str(uuid.uuid4()),
                     "layer": R.LAYER, "type": "smuggled", "params": {}}
            (sub / "smuggled.jsonl").write_text(R.to_jsonl([novel]))
            after, _ = st.load()
            shutil.rmtree(sub)
            return (len(before) == len(after),
                    f"{len(before)} records before, {len(after)} after a "
                    f"novel record placed under graph/sub/")
        case("a .jsonl file under a subdirectory is not loaded",
             nested_not_loaded)

        def atomic():
            leftovers = list(st.graph.rglob(".tmp-*")) + \
                list(st.storage.rglob(".tmp-*"))
            try:
                st.write("bad.txt", [])
                refused = False
            except ValueError:
                refused = True
            return refused and not leftovers, \
                "non-.jsonl refused, no temp files left behind"
        case("writes are atomic and extension-checked", atomic)

        def blob_name_taken():
            # Storage names are minted, not derived from the source, so a
            # collision is a uuid repeating itself rather than a disagreement
            # about content. Stopping is the only correct answer.
            f = FIXTURES[0]
            name = f"taken{f.suffix}"
            st.keep_blob(f, name)
            try:
                st.keep_blob(f, name)
                return False, "overwrote a stored blob"
            except ValueError:
                return True, "refuses a storage name already in use"
        case("a stored blob is never overwritten", blob_name_taken)

        def same_bytes_twice():
            # This replaces the old name-collision rule. Two ingests of one
            # file are now two blobs, and the guarantee is that *both* survive
            # whole — the tool reports the duplication rather than resolving
            # it, because deciding they are one thing is a later layer's call.
            f = FIXTURES[0]
            a = st.keep_blob(f, f"first{f.suffix}")
            b = st.keep_blob(f, f"second{f.suffix}")
            same = a.read_bytes() == b.read_bytes() == f.read_bytes()
            return a != b and same, \
                "identical content stored twice, both copies intact"
        case("the same bytes may be stored more than once", same_bytes_twice)

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

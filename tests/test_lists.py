#!/usr/bin/env python3
"""
test_lists.py — what v0.2.17 ("the list item is a container too") promises.

Same defect v0.2.16 fixed for headings, one level down: a `ListItem` holding
text and a nested list put them side by side as *siblings*, so "everything
under this bullet" was a sibling scan rather than a subtree walk. `_list_item`
already collapsed a bare `[Plain]`/`[Para]` item into the `ListItem` itself,
carrying the text as `content` and the wrapper as `params.wrap`
(`docs/record-format.md`, "Settled" #2) — this release makes a
`[Plain/Para, *lists]` item do the same, via one more case each in
`hoist`/`unhoist` (`src/records.py`, `_hoist_item`/`_unhoist_item`).

`tests/verify-0.2.17.sh` proved each guarantee once, by hand, while the
feature was being built, and is deleted when the release ships. This file is
where they live on, each demonstrated by breaking the thing it claims and
watching the break get caught — the pattern `test_sabotage.py` sets, and the
one `test_sections.py` already followed for the release before this one.

Guarantees needing corpus volume ask `tier.have_corpus()` first and report
themselves skipped when it is absent, exactly like every other suite's
corpus-gated guarantees.
"""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import markdown as MD   # noqa: E402
from src import records as R     # noqa: E402
from src import session as SESS  # noqa: E402
from src import views as V       # noqa: E402
from tests import tier as T      # noqa: E402

HERE = Path(__file__).parent


def _corpus_md_files() -> list[str]:
    """Every corpus `.md`, by `find` rather than `glob.glob(..., recursive=True)`
    — Python's `glob` with `**` skips dot-directories and undercounts against
    `run.sh`'s own `find`-based count (`tests/test_sections.py` found this).
    """
    out = subprocess.run(
        ["find", str(HERE / "corpus"), "-name", "*.md",
         "-not", "-path", "*/.git/*"],
        capture_output=True, text=True)
    return sorted(l for l in out.stdout.splitlines() if l.strip())

# The corpus predicts these exactly (docs/roadmap.md, "the number that
# differs from v0.2.16"): 138 list items whose leading Plain/Para is followed
# by nothing but lists, and exactly one that looks eligible but is not —
# a `['Plain', 'CodeBlock']` item the conservative rule leaves alone.
EXPECTED_HOISTED = 138
EXPECTED_TOTAL_NODES = 19400
BASELINE_NODES = 19538  # measured before this release, unhoisted lists


def _item_shapes(blocks) -> list[tuple]:
    """Every list item's own block-type tuple, walking the same nested
    positions `hoist` reaches (`Div`, `BlockQuote`, `Figure`, `DefinitionList`,
    `Table`, list items), on the RAW (pre-hoist) shape. Used only to measure
    which items are eligible for the conservative rule, independent of
    `hoist` itself — so this suite is not just asking `hoist` to grade its
    own homework.
    """
    shapes: list[tuple] = []

    def blocks_(bs):
        for b in bs:
            block(b)

    def block(b):
        t = b["t"]
        if t == "Div":
            blocks_(b["c"][1])
        elif t == "BlockQuote":
            blocks_(b["c"])
        elif t == "Figure":
            _, (_, cap), kids = b["c"]
            blocks_(cap)
            blocks_(kids)
        elif t == "BulletList":
            for item in b["c"]:
                shapes.append(tuple(x["t"] for x in item))
                blocks_(item)
        elif t == "OrderedList":
            _, items = b["c"]
            for item in items:
                shapes.append(tuple(x["t"] for x in item))
                blocks_(item)
        elif t == "DefinitionList":
            for _term, defs in b["c"]:
                for d in defs:
                    blocks_(d)
        elif t == "Table":
            _, (_, cap), _cs, head, bodies, foot = b["c"]
            blocks_(cap)
            for rg in (head, foot):
                for row in rg[1]:
                    for cell in row[1]:
                        blocks_(cell[4])
            for body in bodies:
                for row in body[2] + body[3]:
                    for cell in row[1]:
                        blocks_(cell[4])

    blocks_(blocks)
    return shapes


def main():
    results = []

    def case(name, ok, detail=""):
        results.append((ok, name, detail))

    def skip(name):
        results.append((None, name, T.WHY))

    # -- guarantees 1, 2, 3, and the two counts from the spec's survey ------
    # One pass over the corpus, everything it can answer in one read — the
    # same efficiency argument test_sections.py makes for reusing one parse.
    if T.have_corpus():
        files = _corpus_md_files()
        bad_hu = bad_full = 0
        total_nodes = 0
        hoisted_items = 0
        eligible_shapes = []
        for f in files:
            raw = MD.ast_of_file(f)
            if R.unhoist(R.hoist(raw["blocks"])) != raw["blocks"]:
                bad_hu += 1
            recs, root = R.ast_to_records(raw)
            if R.records_to_ast(recs, root) != raw:
                bad_full += 1
            total_nodes += sum(1 for r in recs if r["record"] == "node")
            g = R.Graph(recs)
            for n in (r for r in recs if r["record"] == "node"
                     and r["type"] == "ListItem"):
                if (n.get("params") or {}).get("wrap") and g.children(n["guid"]):
                    hoisted_items += 1
            eligible_shapes.extend(
                s for s in _item_shapes(raw["blocks"])
                if len(s) >= 2 and s[0] in ("Plain", "Para"))

        case("hoist and unhoist compose to the identity, now over list "
             "items too", bad_hu == 0,
             f"{len(files) - bad_hu} of {len(files)} documents")
        case("the full round-trip is unchanged in form",
             bad_full == 0,
             f"{len(files) - bad_full} of {len(files)} documents")

        hoisted_shapes = [s for s in eligible_shapes
                          if all(x in ("BulletList", "OrderedList")
                                for x in s[1:])]
        excluded_shapes = [s for s in eligible_shapes
                          if not all(x in ("BulletList", "OrderedList")
                                    for x in s[1:])]
        case("exactly 138 list items are hoisted — a leading Plain/Para "
             "followed by nothing but lists, measured independently of "
             "hoist() itself", len(hoisted_shapes) == EXPECTED_HOISTED
             and hoisted_items == EXPECTED_HOISTED,
             f"{len(hoisted_shapes)} eligible-and-hoistable shapes, "
             f"{hoisted_items} ListItem nodes actually built with wrap+children")
        case("exactly one eligible item is excluded by the conservative "
             "rule, and it is ['Plain', 'CodeBlock']",
             excluded_shapes == [("Plain", "CodeBlock")],
             f"excluded shapes: {excluded_shapes}")
        case(f"hoisting removes exactly one node per hoisted item — "
             f"{BASELINE_NODES} -> {EXPECTED_TOTAL_NODES}",
             total_nodes == EXPECTED_TOTAL_NODES
             and BASELINE_NODES - total_nodes == hoisted_items,
             f"corpus has {total_nodes} nodes ({BASELINE_NODES} - "
             f"{BASELINE_NODES - total_nodes}); {hoisted_items} hoisted items")
    else:
        skip("hoist and unhoist compose to the identity, now over list "
             "items too")
        skip("the full round-trip is unchanged in form")
        skip("exactly 138 list items are hoisted — a leading Plain/Para "
             "followed by nothing but lists, measured independently of "
             "hoist() itself")
        skip("exactly one eligible item is excluded by the conservative "
             "rule, and it is ['Plain', 'CodeBlock']")
        skip(f"hoisting removes exactly one node per hoisted item — "
             f"{BASELINE_NODES} -> {EXPECTED_TOTAL_NODES}")

    # -- guarantee 4: a bullet contains its sub-bullets ----------------------
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text("- parent bullet\n    - child one\n    - child two\n")
        recs, root = R.ast_to_records(MD.ast_of_file(str(p)))
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        g = R.Graph(recs)
        top_list = g.children(root)[0]
        parent_li = g.children(top_list)[0]
        kids = [nodes[k]["type"] for k in g.children(parent_li)]
        case("a bullet with a sub-list carries its own text and the "
             "sub-list becomes its child, no sibling scan anywhere",
             nodes[parent_li]["type"] == "ListItem"
             and (nodes[parent_li].get("params") or {}).get("wrap") == "Plain"
             and R.plain_text(nodes[parent_li]) == "parent bullet"
             and kids == ["BulletList"],
             f"wrap={nodes[parent_li].get('params')}, children={kids}")

    # -- guard: the conservative rule, [Plain, Para] stays siblings ---------
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text("- first para\n\n  second para\n")
        recs, root = R.ast_to_records(MD.ast_of_file(str(p)))
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        g = R.Graph(recs)
        li = g.children(g.children(root)[0])[0]
        kids = [nodes[k]["type"] for k in g.children(li)]
        case("GUARD: two paragraphs in one bullet stay siblings, not "
             "parent and child", kids == ["Para", "Para"]
             and not (nodes[li].get("params") or {}), f"children: {kids}")

    # -- guard: the one excluded shape, [Plain, CodeBlock] ------------------
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text("- text\n\n      code\n")
        recs, root = R.ast_to_records(MD.ast_of_file(str(p)))
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        g = R.Graph(recs)
        li = g.children(g.children(root)[0])[0]
        kids = [nodes[k]["type"] for k in g.children(li)]
        case("GUARD: a bullet with text then a code block is left alone — "
             "the rule's one deliberate exclusion",
             kids == ["Para", "CodeBlock"], f"children: {kids}")

    # -- sabotage: dropping `wrap` breaks the inverse ------------------------
    # Mirrors test_sections.py's header-attr sabotage: the field looks like
    # it merely names which wrapper was used, and is not — for a hoisted
    # item it is also what tells `_to_item` the node's `content` (the text)
    # exists at all. Drop it and `records_to_ast` silently loses the text,
    # keeping only the nested list.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text("- parent bullet\n    - child one\n")
        original = MD.ast_of_file(str(p))
        recs, root = R.ast_to_records(original)
        good = R.records_to_ast(recs, root)
        sabotaged = copy.deepcopy(recs)
        li = next(r for r in sabotaged if r["record"] == "node"
                 and r["type"] == "ListItem" and r.get("params", {}).get("wrap")
                 and R.Graph(sabotaged).children(r["guid"]))
        del li["params"]["wrap"]
        broke = R.records_to_ast(sabotaged, root) != good
        case("sabotage: dropping a hoisted item's `wrap` param breaks the "
             "inverse", broke and good == original,
             "records_to_ast(sabotaged) != records_to_ast(good)")

    # -- sabotage: unhoist must not assume the handle-carrying block is ------
    # -- alone in the list (views.py's v0.2.16 bug, one level down) ---------
    # `_to_item` calls `g.wrap` on the reconstructed `[blk]`, which — for a
    # citable ListItem, exactly like every other citable node — prepends a
    # RawBlock handle marker as a SIBLING before `blk` (djot) or wraps `blk`
    # in a Div (html). A naive `unhoist` that only splices `item_rest` back
    # in when its carrier is the WHOLE length-1 list handed in stops firing
    # the moment either wrapping is in play: the nested list silently
    # vanishes from every rendered view while `ast_to_records`/
    # `records_to_ast` alone never notice, because that path never
    # exercises `wrap` at all.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text("- parent bullet\n    - child one\n    - child two\n")
        recs, root = R.ast_to_records(MD.ast_of_file(str(p)))
        good_view = V.render_djot(recs, root)

        def naive_unhoist(blocks):
            # The bug this release actually shipped, momentarily, before
            # `tests/test_views.py` caught it: splice `item_rest` back in
            # only when its carrier is the WHOLE (length-1) list handed in,
            # exactly the shape `_to_item` produces before any view runs.
            if (len(blocks) == 1 and blocks[0]["t"] in ("Plain", "Para")
                    and "item_rest" in blocks[0]):
                head = {k: v for k, v in blocks[0].items()
                       if k != "item_rest"}
                return [head] + naive_unhoist(blocks[0]["item_rest"])
            return [R._unhoist_block(blk) for blk in blocks]

        real_unhoist = R.unhoist
        R.unhoist = naive_unhoist
        try:
            broken_view = V.render_djot(recs, root)
        finally:
            R.unhoist = real_unhoist
        case("sabotage: a length-1 assumption in unhoist drops the "
             "nested list the instant a view adds a handle marker",
             "child one" in good_view and "child one" not in broken_view,
             f"good view has child text: {'child one' in good_view}; "
             f"naive view has it: {'child one' in broken_view}")

    # -- views.py still calls unhoist before handing blocks to pandoc -------
    src = (Path(__file__).parent.parent / "src/views.py").read_text()
    case("views.py still unhoists before rendering (v0.2.16's bug, as a "
         "standing check, now covering lists too)",
         "R.unhoist(blocks)" in src, "no view-layer change was needed here")

    # -- check() reports zero problems on a hoisted-list base, and no new ---
    # -- node type or schema param was introduced ----------------------------
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text("- plain bullet\n- parent bullet\n    - child one\n"
                     "    - child two\n        - grandchild\n")
        recs, root = R.ast_to_records(MD.ast_of_file(str(p)))
        problems = R.check(recs)
        types = {r["type"] for r in recs if r["record"] == "node"}
        li_params = {k for r in recs if r["record"] == "node"
                    and r["type"] == "ListItem" for k in (r.get("params") or {})}
        case("check() reports 0 problems on a base with hoisted list items",
             problems == [], "; ".join(problems) or "clean")
        case("no new node type was introduced — ListItem is the only type "
             "involved", types <= {"document", "BulletList", "ListItem"},
             f"types: {sorted(types)}")
        case("no new params key beyond `wrap` was needed on ListItem",
             li_params <= {"wrap"}, f"ListItem params seen: {sorted(li_params)}")

    # -- records_to_session is untouched --------------------------------------
    for f in T.sessions():
        lines = [json.loads(l) for l in
                Path(f).read_text().splitlines() if l.strip()]
        recs, root = SESS.session_to_records(f)
        ok = SESS.records_to_session(recs, root) == lines
        case(f"the transcript round-trip still holds exactly ({f.name})",
             ok, f"{len(lines)} lines")
        break  # one is enough here; test_session.py covers every fixture.

    total = len(results)
    skipped = sum(1 for ok, _, _ in results if ok is None)
    failed = [n for ok, n, _ in results if ok is False]
    for ok, name, detail in results:
        mark = "skip " if ok is None else ("pass " if ok else "FAIL ")
        print(f"  {mark} {name:<70} {detail}")
    print(f"\n{total - len(failed) - skipped}/{total - skipped} "
          f"list-item guarantees hold"
          + (f" ({skipped} skipped: {T.WHY})" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""
Site rendering tests: a knowledge base -> a clickable static site.

Run: conda run -n knowledge-graph python tests/test_render/test_site.py
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from src import store as store_mod
from src.canonize import block_hash, canonize_text
from src.refs import reference
from src.render import index as index_mod
from src.render.to_html import load_notes
from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text
from src.render.to_html import backlink_index, load_notes, render

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
        FAILURES.append(name)


def make_base(tmp: Path, sources: list[str]) -> store_mod.Store:
    st = store_mod.init(tmp / "kb")
    for i, md in enumerate(sources):
        r = canonize_text(md)
        (st.conversations / f"019fcc00-0000-7000-8000-{i:012d}.dj").write_text(
            r.djot, encoding="utf-8")
    return st


# --------------------------------------------------------------------------
def tc1_every_block_clickable():
    print("\nTC-1: every block reaches the HTML with its id")
    with tempfile.TemporaryDirectory() as tmp:
        md = (
            "# A heading\n\nA paragraph.\n\n"
            "- item one\n   - nested\n\n"
            "- [ ] a todo\n- [x] done\n\n"
            "1. single ordered item\n\n"
            "> a quote\n"
        )
        st = make_base(Path(tmp), [md])
        stats = render(st)
        check("no unaddressable blocks",
              stats["clickable"] == stats["blocks"],
              f"{stats['blocks']} blocks but {stats['clickable']} clickable")
        check("blocks were actually produced", stats["blocks"] > 6,
              f"only {stats['blocks']}")

        html = next(st.site.glob("019*.html")).read_text()
        check("todo renders as a real checkbox", 'type="checkbox"' in html)
        check("every id carries a data-hash",
              len(re.findall(r'id="[0-9a-f]{8}" data-hash="[0-9a-f]{16}"', html))
              == stats["clickable"])
        check("subtree markers present", 'data-subtree="1"' in html)


def tc2_backlinks():
    print("\nTC-2: backlinks resolve across notes")
    with tempfile.TemporaryDirectory() as tmp:
        st = make_base(Path(tmp), ["# Target\n\nThe referenced paragraph.\n"])
        target = [b for b in walk(get_ast_from_text(
            next(st.conversations.glob("*.dj")).read_text()))
            if b["type"] == "paragraph"][0]
        ref = reference(target["id"])

        r = canonize_text(f"Reacting to {ref} with a comment.\n")
        (st.conversations / "019fcc00-0000-7000-8000-000000000009.dj").write_text(
            r.djot, encoding="utf-8")

        notes = load_notes(st)
        idx = backlink_index(notes)
        check("reference found despite on-disk escaping",
              target["id"] in idx, f"index keys: {list(idx)[:3]}")

        render(st)
        target_html = next(st.site.glob("*000000000000.html")).read_text()
        check("backlink rendered into the target page",
              "Referenced by" in target_html)


def tc3_subtree_flag():
    print("\nTC-3: subtree references are marked as such")
    with tempfile.TemporaryDirectory() as tmp:
        st = make_base(Path(tmp), ["# Target\n\nA paragraph.\n"])
        target = walk(get_ast_from_text(
            next(st.conversations.glob("*.dj")).read_text()))[0]
        ref = reference(target["id"], subtree=True)
        r = canonize_text(f"Rewrite {ref} please.\n")
        (st.conversations / "019fcc00-0000-7000-8000-000000000009.dj").write_text(
            r.djot, encoding="utf-8")

        idx = backlink_index(load_notes(st))
        entry = idx.get(target["id"], [{}])[0]
        check("+++ recorded as a subtree reference", entry.get("subtree") is True)


def tc4_store_resolution():
    print("\nTC-4: the base is found from anywhere")
    with tempfile.TemporaryDirectory() as tmp:
        st = store_mod.init(Path(tmp) / "kb")
        nested = st.root / "conversations"
        import os
        cwd = os.getcwd()
        try:
            os.chdir(nested)
            check("found by walking up to the .kg marker",
                  store_mod.find().root == st.root)
        finally:
            os.chdir(cwd)

        try:
            store_mod.find(str(Path(tmp) / "not-a-base"))
            check("non-base raises StoreError", False, "no error raised")
        except store_mod.StoreError as e:
            check("non-base raises an actionable error", "kg init" in str(e))


# --------------------------------------------------------------------------
# TC-5  blocks.json, and the check that reads it
#
# A dangling reference cannot be repaired in place — the turn containing it is
# immutable — so noticing is the only defence. The check must therefore fire on
# a handle that resolves to nothing, and must not fire on one that resolves.
# --------------------------------------------------------------------------
def tc5_index_and_check():
    print("\nTC-5: blocks.json and kg check")
    with tempfile.TemporaryDirectory() as tmp:
        st = store_mod.init(Path(tmp) / "kb")
        from src.conversation import append_turn
        path = st.conversations / "019fcc00-0000-7000-8000-000000000001.dj"
        append_turn(path, "The block worth citing.\n", "human")

        target = [b for b in load_notes(st)[0]["blocks"] if b["type"] == "paragraph"][0]
        append_turn(path, f"Answering {reference(target['id'])} here.\n", "claude")

        records = index_mod.build(load_notes(st))
        by_handle = {r["handle"]: r for r in records}

        check("every block has a record", len(records) == len(load_notes(st)[0]["blocks"]))
        check("records carry a hash a reader cannot compute from the file",
              all(len(r["hash"]) == 16 for r in records))
        check("authorship comes through from the turn",
              {r.get("author") for r in records} == {"human", "claude"},
              {r.get("author") for r in records})
        check("citations are recorded",
              any(r.get("cites") == [target["id"]] for r in records))

        clean = index_mod.check(records)
        check("a resolving reference is not reported",
              not clean["dangling"] and not clean["collisions"], clean)

        # Sabotage: point at a handle that exists nowhere.
        broken = [dict(r) for r in records]
        next(r for r in broken if r.get("cites"))["cites"] = ["deadbeef"]
        report = index_mod.check(broken)
        check("a dangling reference is reported",
              len(report["dangling"]) == 1, report["dangling"])
        check("the report names the source and the target",
              report["dangling"][0]["target"] == "deadbeef"
              and report["dangling"][0]["source"].endswith(".dj"))

        # Sabotage: two blocks claiming one handle.
        dup = [dict(r) for r in records]
        dup[1]["handle"] = dup[0]["handle"]
        check("a handle collision is reported",
              len(index_mod.check(dup)["collisions"]) == 1)


def main():
    tc1_every_block_clickable()
    tc2_backlinks()
    tc3_subtree_flag()
    tc4_store_resolution()
    tc5_index_and_check()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        sys.exit(1)
    print("All site rendering checks PASSED.")


if __name__ == "__main__":
    main()

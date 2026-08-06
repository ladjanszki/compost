"""
Artifacts: documents that get rewritten without losing their handles.

If regenerating a document renumbered every block, every comment anyone ever
wrote about it would be orphaned — and comments live in immutable turns, so
they could never be corrected. This is the guarantee that makes an artifact
worth commenting on twice.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.artifact import name_for, write
from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        FAILURES.append(name)
        if detail:
            print(f"          {detail}")


def handles(path: Path) -> dict:
    return {b["content"].get("text", ""): b["id"]
            for b in walk(get_ast_from_text(path.read_text(encoding="utf-8")))}


V1 = "# Title\n\nFirst para.\n\nSecond para.\n\n- item a\n- item b\n"


def tc1_unchanged_blocks_keep_their_handles():
    print("\nTC-1: an edit does not renumber the document")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "doc.dj"
        write(p, V1)
        before = handles(p)

        # Insert in the middle and edit one block. Everything else must survive.
        v2 = ("# Title\n\nFirst para.\n\nAn inserted paragraph.\n\n"
              "Second para, revised.\n\n- item a\n- item b\n")
        stats = write(p, v2)
        after = handles(p)

        unchanged = ["Title", "First para.", "item a", "item b"]
        check("unchanged blocks keep their handles",
              all(before[t] == after[t] for t in unchanged),
              {t: (before[t], after.get(t)) for t in unchanged})
        check("an inserted block does not renumber the ones after it",
              before["item a"] == after["item a"], "insertion shifted handles")
        check("an edited block gets a new handle",
              before["Second para."] != after["Second para, revised."])
        check("counts are reported honestly",
              stats == {"kept": 4, "added": 2, "removed": 1}, stats)


def tc2_matching_is_by_content_not_position():
    print("\nTC-2: blocks are matched by content, not by position")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "doc.dj"
        write(p, V1)
        before = handles(p)

        # Reorder. Nothing changed, so nothing should get a new handle.
        reordered = "# Title\n\nSecond para.\n\nFirst para.\n\n- item a\n- item b\n"
        stats = write(p, reordered)
        after = handles(p)

        check("a reordered block keeps its handle",
              before["First para."] == after["First para."]
              and before["Second para."] == after["Second para."],
              {"before": before, "after": after})
        check("reordering adds and removes nothing",
              stats["added"] == 0 and stats["removed"] == 0, stats)


def tc3_duplicate_text_does_not_share_a_handle():
    print("\nTC-3: two blocks with identical text get separate handles")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "doc.dj"
        # Identical text hashes identically, so a naive map would give both
        # blocks the same handle and silently merge two distinct blocks.
        write(p, "- same\n- same\n- different\n")
        blocks = walk(get_ast_from_text(p.read_text(encoding="utf-8")))
        ids = [b["id"] for b in blocks]
        check("handles are unique", len(set(ids)) == len(ids), ids)

        write(p, "- same\n- same\n- different\n- new\n")
        after = walk(get_ast_from_text(p.read_text(encoding="utf-8")))
        ids2 = [b["id"] for b in after]
        check("still unique after an update", len(set(ids2)) == len(ids2), ids2)
        check("both duplicates kept their own handle",
              ids2[:3] == ids[:3], (ids, ids2))


def tc4_names():
    print("\nTC-4: filenames read like titles")
    check("uppercase and extensions are normalised",
          name_for(Path("/x/DEVELOPMENT.md")) == "development")
    check("punctuation becomes hyphens",
          name_for(Path("/x/mvp_design notes.md")) == "mvp-design-notes")


def main():
    tc1_unchanged_blocks_keep_their_handles()
    tc2_matching_is_by_content_not_position()
    tc3_duplicate_text_does_not_share_a_handle()
    tc4_names()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        sys.exit(1)
    print("All artifact checks PASSED.")


if __name__ == "__main__":
    main()

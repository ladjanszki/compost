"""
Canonization tests: Markdown note -> addressable Djot note.

Run: conda run -n knowledge-graph python tests/test_canonize/test_canonize.py
"""
import re
import sys

sys.path.insert(0, ".")

from src.canonize import canonize_text
from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text
from src.refs import HANDLE

FAILURES = []

HANDLE_RE = re.compile(HANDLE)


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
        FAILURES.append(name)


def blocks_of(djot: str) -> list:
    return walk(get_ast_from_text(djot))


# --------------------------------------------------------------------------
# TC-1  Every block is addressable
# --------------------------------------------------------------------------
def tc1_every_block_has_an_id():
    print("\nTC-1: every block receives an id")
    md = (
        "# A heading\n\nA paragraph.\n\n"
        "- item one\n   - nested item\n\n"
        "- [ ] an open task\n- [x] a done task\n\n"
        "> a quoted line\n\n```python\nx = 1\n```\n"
    )
    r = canonize_text(md)
    blocks = blocks_of(r.djot)
    missing = [b["type"] for b in blocks if not b.get("id")]
    check("all blocks carry an id", not missing, f"missing on: {missing}")
    check("ids are unique", len({b["id"] for b in blocks}) == len(blocks))
    check("block count matches result", len(blocks) == len(r.blocks))

    # Every id must be one we assigned. A pandoc-generated heading slug
    # ("{#a-heading}") would satisfy "has an id" while violating the stable-id
    # invariant, since it changes whenever the heading text is edited.
    not_handle = [(b["type"], b["id"]) for b in blocks
                if not HANDLE_RE.fullmatch(b["id"] or "")]
    check("every id is an assigned handle, not a derived slug",
          not not_handle, f"non-handle ids: {not_handle}")

    # No stray attributes either. Pandoc's auto_identifiers leaves a
    # "{#a-heading}" line that our UUID overrides semantically but which stays
    # in the file as noise, so the residue is worth catching directly.
    stray = [a for a in re.findall(r"\{#([^}]*)\}", r.djot)
             if not HANDLE_RE.fullmatch(a)]
    check("no leftover non-handle attributes in the file",
          not stray, f"stray: {stray}")


# --------------------------------------------------------------------------
# TC-2  Lazy nesting is resolved (the pandoc claim)
# --------------------------------------------------------------------------
def tc2_lazy_nesting_becomes_addressable():
    print("\nTC-2: markdown lazy nesting becomes real nesting")
    md = "- level one\n   - level two\n      - level three\n"
    r = canonize_text(md)
    items = [b for b in blocks_of(r.djot) if b["type"] == "list_item"]
    depths = sorted(b["content"].get("depth", 0) for b in items)
    check("three addressable list items", len(items) == 3, f"got {len(items)}")
    check("depths are 0,1,2", depths == [0, 1, 2], f"got {depths}")
    check("each nested item has its own id", len({b["id"] for b in items}) == 3)


# --------------------------------------------------------------------------
# TC-2b  Blocks inside a div stay addressable
#
# A div is a container, so its children must reach the flat block list. Nesting
# them inside the div's content instead makes them invisible to every consumer
# — no hash, no backlinks, no addressability — while inject_ids still writes
# ids for them into the file. Neither the canonize verifier nor the roundtrip
# test can see that: the blocks are simply absent from both sides.
#
# This matters because folded content (tool calls, subagent transcripts) is
# exactly what a div is for.
# --------------------------------------------------------------------------
def tc2b_div_children_are_blocks():
    print("\nTC-2b: blocks inside a div are addressable")
    md = "Before.\n\n::: tool-call\nInside one.\n\nInside two.\n:::\n\nAfter.\n"
    r = canonize_text(md)
    blocks = blocks_of(r.djot)
    texts = [b["content"].get("text", "") for b in blocks]

    check("div children reach the flat block list",
          "Inside one." in texts and "Inside two." in texts, texts)
    check("the div itself is still a block",
          any(b["type"] == "div" for b in blocks))
    check("every block in a div carries an id",
          all(b.get("id") for b in blocks),
          [b["type"] for b in blocks if not b.get("id")])
    check("the div records how many blocks it contains",
          next(b["content"].get("contains") for b in blocks
               if b["type"] == "div") == 2)
    # Ids written into the file but absent from the block list are the actual
    # failure mode: they look clickable in HTML and resolve to nothing.
    check("no id is written that the block list does not know about",
          len(re.findall(r"\{#[0-9a-f]{8}\}", r.djot)) == len(blocks),
          f"{len(re.findall(r'{#[0-9a-f]{8}}', r.djot))} ids, {len(blocks)} blocks")


# --------------------------------------------------------------------------
# TC-3  Task lists survive pandoc
# --------------------------------------------------------------------------
def tc3_tasks_survive():
    print("\nTC-3: task lists survive conversion")
    md = "- [ ] an open task\n- [x] a done task\n"
    r = canonize_text(md)
    tasks = [b for b in blocks_of(r.djot) if b["type"] == "task_item"]
    check("two task items", len(tasks) == 2, f"got {len(tasks)}")
    check("no stray ballot boxes", "☐" not in r.djot and "☒" not in r.djot)
    if len(tasks) == 2:
        check("checked state preserved",
              [t["content"]["checked"] for t in tasks] == [False, True])
        check("tasks are addressable", all(t.get("id") for t in tasks))


# --------------------------------------------------------------------------
# TC-4  The author's text is not rewritten
# --------------------------------------------------------------------------
def tc4_text_is_preserved():
    print("\nTC-4: the author's text survives unchanged")
    md = (
        "so how do I work.\nIn a lot of ways.\n\n"
        "I don't want it's apostrophes changed.\n"
    )
    r = canonize_text(md)
    blocks = blocks_of(r.djot)
    check("line breaks preserved inside a paragraph",
          blocks[0]["content"]["text"] == "so how do I work.\nIn a lot of ways.",
          repr(blocks[0]["content"]["text"]))
    joined = " ".join(b["content"].get("text", "") for b in blocks)
    check("straight apostrophes not smart-quoted",
          "don't" in joined and "’" not in joined)


# --------------------------------------------------------------------------
# TC-5  Block references written by hand survive
# --------------------------------------------------------------------------
def tc5_references_survive():
    print("\nTC-5: hand-written block references survive")
    md = (
        "Regarding {#a3f9c2d1} I think this is incomplete.\n\n"
        "And {#a3f9c2d1@7f2e} pins a version, {#a3f9c2d1+++} takes the subtree.\n"
    )
    r = canonize_text(md)
    blocks = blocks_of(r.djot)
    texts = " ".join(b["content"].get("text", "") for b in blocks)
    check("plain reference survives", "{#a3f9c2d1}" in texts, texts)
    check("version-pinned reference survives", "{#a3f9c2d1@7f2e}" in texts, texts)
    check("subtree reference survives", "{#a3f9c2d1+++}" in texts, texts)

    # A handle and an id attribute are now the same shape, so the only thing
    # separating "a reference the author typed" from "an id we assigned" is
    # pandoc's escaping. If a written reference were ever read as an attribute
    # it would silently become a second block claiming that handle.
    check("a written reference is not mistaken for an id attribute",
          all(b["id"] != "a3f9c2d1" for b in blocks),
          [b["id"] for b in blocks])
    check("written references stay escaped on disk",
          r"\{#a3f9c2d1\}" in r.djot, r.djot)


# --------------------------------------------------------------------------
# TC-6  Injection is inert — it adds ids and nothing else
# --------------------------------------------------------------------------
def tc6_injection_is_inert():
    print("\nTC-6: injection changes ids only, never content")
    from src.canonize.md_to_djot import md_to_djot
    from src.canonize.inject_ids import inject_ids

    md = open("archive/my-workflow.md").read()
    plain = md_to_djot(md)
    injected = inject_ids(plain)

    before = [(b["type"], b["content"].get("text")) for b in blocks_of(plain)]
    after = [(b["type"], b["content"].get("text")) for b in blocks_of(injected)]
    check("block types and text identical", before == after,
          f"{len(before)} vs {len(after)} blocks")

    # Removing the injected id lines must give back the original byte for byte.
    # Note [ \t] rather than \s: \s matches newlines and would swallow the
    # blank lines between blocks, making a purely additive insertion look lossy.
    stripped = re.sub(r"^[ \t]*\{#[0-9a-f]{8}\}\n", "", injected, flags=re.M)
    stripped = re.sub(r"^([ \t]*[-*+] (?:\[[ x]\] )?)\{#[0-9a-f]{8}\}\n[ \t]*",
                      r"\1", stripped, flags=re.M)
    check("stripping ids restores the pandoc output", stripped == plain,
          "id insertion is not purely additive")


# --------------------------------------------------------------------------
# TC-7  Real notes
# --------------------------------------------------------------------------
def tc7_real_notes():
    print("\nTC-7: the author's real files")
    for path in ("archive/my-workflow.md", "archive/mvp-interview.md"):
        try:
            r = canonize_text(open(path).read())
        except Exception as e:
            check(f"{path} canonizes", False, str(e))
            continue
        words_src = set(re.findall(r"[A-Za-z]{4,}", open(path).read()))
        words_out = set(re.findall(
            r"[A-Za-z]{4,}", " ".join(b["text"] for b in r.blocks)))
        lost = words_src - words_out
        check(f"{path}: {len(r.blocks)} blocks, no words lost",
              not lost, f"lost: {sorted(lost)[:8]}")


def main():
    tc1_every_block_has_an_id()
    tc2_lazy_nesting_becomes_addressable()
    tc2b_div_children_are_blocks()
    tc3_tasks_survive()
    tc4_text_is_preserved()
    tc5_references_survive()
    tc6_injection_is_inert()
    tc7_real_notes()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        sys.exit(1)
    print("All canonization checks PASSED.")


if __name__ == "__main__":
    main()

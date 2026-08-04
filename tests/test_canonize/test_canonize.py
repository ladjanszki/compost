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

FAILURES = []

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}")


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
    not_uuid = [(b["type"], b["id"]) for b in blocks
                if not UUID_RE.fullmatch(b["id"] or "")]
    check("every id is an assigned UUID, not a derived slug",
          not not_uuid, f"non-uuid ids: {not_uuid}")

    # No stray attributes either. Pandoc's auto_identifiers leaves a
    # "{#a-heading}" line that our UUID overrides semantically but which stays
    # in the file as noise, so the residue is worth catching directly.
    stray = [a for a in re.findall(r"\{#([^}]*)\}", r.djot)
             if not UUID_RE.fullmatch(a)]
    check("no leftover non-UUID attributes in the file",
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
        "Regarding {#019abc} I think this is incomplete.\n\n"
        "And {#019abc:3f7a2b9c1e8d4f0a} pins a version.\n"
    )
    r = canonize_text(md)
    texts = " ".join(b["content"].get("text", "") for b in blocks_of(r.djot))
    check("plain reference survives", "{#019abc}" in texts, texts)
    check("compound reference survives",
          "{#019abc:3f7a2b9c1e8d4f0a}" in texts, texts)


# --------------------------------------------------------------------------
# TC-6  Injection is inert — it adds ids and nothing else
# --------------------------------------------------------------------------
def tc6_injection_is_inert():
    print("\nTC-6: injection changes ids only, never content")
    from src.canonize.md_to_djot import md_to_djot
    from src.canonize.inject_ids import inject_ids

    md = open("my-workflow.md").read()
    plain = md_to_djot(md)
    injected = inject_ids(plain)

    before = [(b["type"], b["content"].get("text")) for b in blocks_of(plain)]
    after = [(b["type"], b["content"].get("text")) for b in blocks_of(injected)]
    check("block types and text identical", before == after,
          f"{len(before)} vs {len(after)} blocks")

    # Removing the injected id lines must give back the original byte for byte.
    # Note [ \t] rather than \s: \s matches newlines and would swallow the
    # blank lines between blocks, making a purely additive insertion look lossy.
    stripped = re.sub(r"^[ \t]*\{#[0-9a-f-]{36}\}\n", "", injected, flags=re.M)
    stripped = re.sub(r"^([ \t]*[-*+] (?:\[[ x]\] )?)\{#[0-9a-f-]{36}\}\n[ \t]*",
                      r"\1", stripped, flags=re.M)
    check("stripping ids restores the pandoc output", stripped == plain,
          "id insertion is not purely additive")


# --------------------------------------------------------------------------
# TC-7  Real notes
# --------------------------------------------------------------------------
def tc7_real_notes():
    print("\nTC-7: the author's real files")
    for path in ("my-workflow.md", "mvp-interview.md"):
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

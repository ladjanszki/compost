"""
inject_ids.py — write block ids into Djot source as text.

The ids are inserted into the .dj text directly rather than round-tripped
through the AST, so the file is exactly what pandoc emitted plus the inserted
id lines. Nothing the author wrote is re-rendered, and the diff is additive
and reviewable.

Placement was established by testing (mvp-design.md §4.1). For list and task
items there is exactly one form djot accepts:

    - {#id}
      item one          <- attribute attaches to the item's paragraph

`{#id}` on the line *before* a list attaches to the list container, not the
item, and the inline form `- {#id} item one` is silently discarded.
"""
from dataclasses import dataclass

import uuid6

from ..ingest.djot_ast import get_ast_from_text

# Blocks that get an id at their own position, on a preceding line.
SIMPLE_BLOCKS = {
    "heading", "para", "code_block", "thematic_break", "raw_block",
    "table", "definition_list_item",
}
# Containers that emit no block of their own — recurse into children.
LIST_CONTAINERS = {"bullet_list", "ordered_list", "task_list"}
ITEMS = {"list_item", "task_list_item"}


@dataclass
class Insertion:
    line: int        # 1-based line in the source
    col: int         # 1-based column the block's content starts at
    split: bool      # True for list items (split the marker line in two)
    block_id: str


def _new_id() -> str:
    """UUIDv7 — sortable, and its embedded timestamp gives parsed_at for free."""
    return str(uuid6.uuid7())


def _start(node: dict):
    pos = node.get("pos")
    return (pos["start"]["line"], pos["start"]["col"]) if pos else None


def _collect(node: dict, out: list, skip_first_para: bool = False) -> None:
    """Walk the AST accumulating insertion points, mirroring ast_walker."""
    tag = node.get("tag")
    children = node.get("children", []) or []

    if tag == "section" or tag == "doc":
        for c in children:
            _collect(c, out)

    elif tag in LIST_CONTAINERS:
        for c in children:
            _collect(c, out)

    elif tag in ITEMS:
        # The id must land on the item's first paragraph — that is the only
        # placement djot accepts for a list item.
        first_para = next((c for c in children if c.get("tag") == "para"), None)
        if first_para is not None:
            pos = _start(first_para)
            if pos:
                out.append(Insertion(pos[0], pos[1], True, _new_id()))
        # Nested lists and other blocks inside the item are separate blocks.
        seen_para = False
        for c in children:
            if c.get("tag") == "para" and not seen_para:
                seen_para = True
                continue
            _collect(c, out)

    elif tag == "block_quote":
        # ast_walker flattens a block quote into a single block, so the quote
        # gets one id and its children get none.
        pos = _start(node)
        if pos:
            out.append(Insertion(pos[0], pos[1], False, _new_id()))

    elif tag == "div":
        pos = _start(node)
        if pos:
            out.append(Insertion(pos[0], pos[1], False, _new_id()))
        for c in children:
            _collect(c, out)

    elif tag in SIMPLE_BLOCKS:
        if skip_first_para:
            return
        pos = _start(node)
        if pos:
            out.append(Insertion(pos[0], pos[1], False, _new_id()))


def plan_insertions(djot_text: str) -> list[Insertion]:
    """Parse with source positions and return the insertion points."""
    ast = get_ast_from_text(djot_text, sourcepos=True)
    out: list[Insertion] = []
    _collect(ast, out)
    return out


def apply_insertions(djot_text: str, insertions: list[Insertion]) -> str:
    """
    Apply insertions bottom-up so earlier positions stay valid.

    A `split` insertion rewrites a list item's marker line:
        "- item one"  ->  "- {#id}\n  item one"
    Everything else inserts a new line above the block, carrying whatever
    prefix precedes it (so a block quote's "> " is preserved).
    """
    lines = djot_text.split("\n")

    for ins in sorted(insertions, key=lambda i: (i.line, i.col), reverse=True):
        idx = ins.line - 1
        if idx < 0 or idx >= len(lines):
            raise IndexError(f"insertion line {ins.line} outside source")
        line = lines[idx]
        prefix, rest = line[: ins.col - 1], line[ins.col - 1:]

        if ins.split:
            lines[idx: idx + 1] = [
                f"{prefix}{{#{ins.block_id}}}",
                f"{' ' * (ins.col - 1)}{rest}",
            ]
        else:
            lines.insert(idx, f"{prefix}{{#{ins.block_id}}}")

    return "\n".join(lines)


def inject_ids(djot_text: str) -> str:
    """Assign an id to every referenceable block and write them into the text."""
    return apply_insertions(djot_text, plan_insertions(djot_text))

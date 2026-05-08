"""
ast_walker.py — walk a Pandoc AST and yield (type, content) tuples for each block.

Does not generate IDs or hashes — that is block_schema's responsibility.
"""
from typing import Iterator

from .inline_reconstruct import reconstruct


def walk(ast: dict) -> list[dict]:
    """
    Walk the top-level blocks of a Pandoc AST and return an ordered list of
    dicts, each with keys:
      - type:    str  (heading | paragraph | list_item)
      - content: dict (type-specific payload)

    The order matches document order.
    """
    results = []
    _process_blocks(ast["blocks"], results)
    return results


def _process_blocks(nodes: list, results: list) -> None:
    for node in nodes:
        _process_node(node, results)


def _process_node(node: dict, results: list) -> None:
    t = node.get("t")
    c = node.get("c")

    if t == "Div":
        _process_div(c, results)

    elif t == "Header":
        level = c[0]
        inlines = c[2]
        results.append({
            "type": "heading",
            "content": {
                "text": reconstruct(inlines),
                "level": level,
            },
        })

    elif t == "Para":
        inlines = c
        results.append({
            "type": "paragraph",
            "content": {
                "text": reconstruct(inlines),
            },
        })

    elif t == "BulletList":
        # Each item is a list of block nodes; the first node is Plain or Para.
        for item in c:
            first = item[0]
            inlines = first.get("c", [])
            results.append({
                "type": "list_item",
                "content": {
                    "text": reconstruct(inlines),
                    "style": "unordered",
                },
            })

    elif t == "OrderedList":
        # items are in c[1]; c[0] is list attributes
        for item in c[1]:
            first = item[0]
            inlines = first.get("c", [])
            results.append({
                "type": "list_item",
                "content": {
                    "text": reconstruct(inlines),
                    "style": "ordered",
                },
            })

    # All other node types: recurse into children if present, no block emitted.
    elif isinstance(c, list):
        for child in c:
            if isinstance(child, dict):
                _process_node(child, results)
            elif isinstance(child, list):
                _process_blocks(child, results)


def _process_div(c: list, results: list) -> None:
    """
    Handle a Div node.

    c[0] is the attr triple: [id, classes, kvs]
    c[1] is the list of child block nodes.

    Two cases:
      - Div with class "section": Pandoc's representation of a headed section.
        The first child is a Header; remaining children are the section body.
        Both are processed normally — the Div is transparent.
      - Div with kv "wrapper": Pandoc's representation of a {#id}-attributed block.
        Contains exactly one real block element. Process that element directly.
      - Any other Div: recurse into children.
    """
    attrs = c[0]       # [id_str, classes_list, kvs_list]
    children = c[1]    # list of block nodes

    classes = attrs[1]
    kvs = {kv[0]: kv[1] for kv in attrs[2]}

    # Both section Divs and wrapper Divs are transparent: just process children.
    # The ID carried by the Div is not used in Test 00 (no explicit {#id} attrs).
    _process_blocks(children, results)

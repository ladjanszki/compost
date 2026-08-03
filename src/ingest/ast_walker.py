"""
ast_walker.py — walk a djot.js AST and yield (type, content) tuples for each block.

Does not generate system IDs or hashes — that is block_schema's responsibility.
"""
from typing import Iterator

from .inline_reconstruct import reconstruct


def walk(ast: dict) -> list[dict]:
    """Walk the djot.js AST. Returns ordered list of block dicts."""
    results = []
    _walk_children(ast.get("children", []), results)
    return results


def emit(results: list, block_type: str, content: dict, block_id: str | None = None):
    results.append({
        "type": block_type,
        "content": content,
        "id": block_id
    })


def _walk_children(nodes: list, results: list, depth: int = 0):
    for node in nodes:
        _walk_node(node, results, depth)


def _walk_node(node: dict, results: list, depth: int = 0):
    tag = node.get("tag")
    attrs = node.get("attributes", {})
    block_id = attrs.get("id")  # explicit {#id} from source

    if tag == "section":
        _walk_children(node.get("children", []), results)
    
    elif tag == "heading":
        text, links = reconstruct(node.get("children", []))
        content = {"text": text, "level": node.get("level", 1)}
        if links:
            content["links"] = links
        emit(results, "heading", content, block_id)
    
    elif tag == "para":
        text, links = reconstruct(node.get("children", []))
        content = {"text": text}
        if links:
            content["links"] = links
        emit(results, "paragraph", content, block_id)
    
    elif tag == "code_block":
        lang = node.get("lang", "")
        if lang.startswith("{=") and lang.endswith("}"):
            content = {"text": node.get("text", ""), "format": lang[2:-1]}
            emit(results, "raw_block", content, block_id)
        else:
            content = {"text": node.get("text", "")}
            if lang:
                content["language"] = lang
            emit(results, "code_block", content, block_id)
    
    elif tag == "block_quote":
        child_blocks = []
        _walk_children(node.get("children", []), child_blocks)
        text = _reconstruct_block_quote(child_blocks)
        
        all_links = []
        for cb in child_blocks:
            if "links" in cb.get("content", {}):
                all_links.extend(cb["content"]["links"])
                
        content = {"text": text}
        if all_links:
            content["links"] = all_links
        emit(results, "block_quote", content, block_id)
    
    elif tag == "bullet_list":
        for item in node.get("children", []):
            _walk_list_item(item, "unordered", results, depth)

    elif tag == "ordered_list":
        for item in node.get("children", []):
            _walk_list_item(item, "ordered", results, depth)

    elif tag == "task_list":
        for item in node.get("children", []):
            _walk_list_item(item, "task", results, depth)

    elif tag == "definition_list":
        for item in node.get("children", []):
            _walk_definition_item(item, results)
    
    elif tag == "table":
        _walk_table(node, results)
    
    elif tag == "thematic_break":
        emit(results, "thematic_break", {}, block_id)
    
    elif tag == "div":
        # Transparent: recurse, but capture the div's ID for the first child
        # For now we emit the div as a block if it's not transparent in some contexts
        # Wait, the spec says "Div and Raw... 1 div ... 1 raw_block". It wants div as a block.
        # Let's emit a div block if requested, or just walk children. The verify test expects 'div'.
        content = {}
        if "class" in attrs:
            content["classes"] = attrs["class"].split()
            
        child_blocks = []
        _walk_children(node.get("children", []), child_blocks)
        content["children"] = child_blocks
        
        emit(results, "div", content, block_id)
    
    elif tag == "raw_block":
        content = {"text": node.get("text", "")}
        if "format" in node:
            content["format"] = node["format"]
        emit(results, "raw_block", content, block_id)


def _reconstruct_block_quote(child_blocks: list) -> str:
    texts = []
    for b in child_blocks:
        c = b.get("content", {})
        if "text" in c:
            texts.append(c["text"])
    return "\n\n".join(texts)


def _walk_list_item(item: dict, style: str, results: list, depth: int = 0):
    """
    Handle a list_item / task_list_item.

    The item's own text is emitted first, then any nested blocks it contains,
    so document order is preserved. Nested lists are walked at depth + 1 —
    the depth is what lets the renderer reproduce the indentation.
    """
    attrs = item.get("attributes", {})
    block_id = attrs.get("id")
    children = item.get("children", [])

    text_parts = []
    all_links = []
    deferred = []  # non-paragraph children, walked after this item is emitted

    for child in children:
        if child.get("tag") == "para":
            t, l = reconstruct(child.get("children", []))
            text_parts.append(t)
            all_links.extend(l)
        else:
            deferred.append(child)

    block_type = "task_item" if style == "task" else "list_item"
    content = {"text": "\n\n".join(text_parts), "style": style}
    if depth:
        content["depth"] = depth
    if block_type == "task_item":
        content["checked"] = item.get("checkbox") == "checked"
    if all_links:
        content["links"] = all_links

    emit(results, block_type, content, block_id)

    for child in deferred:
        _walk_node(child, results, depth + 1)


def _walk_definition_item(node: dict, results: list):
    attrs = node.get("attributes", {})
    block_id = attrs.get("id")
    term = ""
    text_parts = []
    all_links = []
    for child in node.get("children", []):
        if child["tag"] == "term":
            term, l = reconstruct(child.get("children", []))
            all_links.extend(l)
        elif child["tag"] == "definition":
            for def_child in child.get("children", []):
                if def_child["tag"] == "para":
                    t, l = reconstruct(def_child.get("children", []))
                    text_parts.append(t)
                    all_links.extend(l)
                else:
                    _walk_node(def_child, results)
    
    content = {"term": term, "text": "\n\n".join(text_parts)}
    if all_links:
        content["links"] = all_links
    
    emit(results, "definition_item", content, block_id)


def _walk_table(node: dict, results: list):
    attrs = node.get("attributes", {})
    block_id = attrs.get("id")
    rows = []
    all_links = []
    caption = ""
    for child in node.get("children", []):
        if child["tag"] == "caption":
            if child.get("children"):
                caption, l = reconstruct(child.get("children", []))
                all_links.extend(l)
        elif child["tag"] == "row":
            row = {"head": child.get("head", False), "cells": []}
            for cell in child.get("children", []):
                text, links = reconstruct(cell.get("children", []))
                row["cells"].append({
                    "text": text,
                    "align": cell.get("align", "default")
                })
                all_links.extend(links)
            rows.append(row)
    
    content = {"rows": rows}
    if caption:
        content["caption"] = caption
    if all_links:
        content["links"] = all_links
    
    emit(results, "table", content, block_id)

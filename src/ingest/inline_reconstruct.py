"""
inline_reconstruct.py — reconstruct Djot inline markup from djot.js AST inline nodes.
"""

def _format_attrs(attributes: dict) -> str:
    if not attributes:
        return ""
    parts = []
    for k, v in attributes.items():
        if k == "id":
            parts.append(f"#{v}")
        elif k == "class":
            parts.extend(f".{c}" for c in v.split())
        else:
            parts.append(f'{k}="{v}"')
    return " ".join(parts)

def reconstruct(inlines: list) -> tuple[str, list[dict]]:
    """Reconstruct djot inline markup from djot.js AST inline nodes."""
    links_acc = []
    text = _reconstruct_inner(inlines, links_acc)
    return text, links_acc

def _reconstruct_inner(inlines: list, links_acc: list) -> str:
    parts = []
    for node in inlines:
        tag = node.get("tag")
        
        if tag == "str":
            parts.append(node["text"])
        elif tag == "soft_break":
            parts.append("\n")
        elif tag == "hard_break":
            parts.append("\\\n")
        elif tag == "emph":
            parts.append("_" + _reconstruct_inner(node.get("children", []), links_acc) + "_")
        elif tag == "strong":
            parts.append("*" + _reconstruct_inner(node.get("children", []), links_acc) + "*")
        elif tag == "verbatim":
            parts.append("`" + node["text"] + "`")
        elif tag == "inline_math":
            parts.append("$`" + node["text"] + "`")
        elif tag == "display_math":
            parts.append("$$`" + node["text"] + "`")
        elif tag == "link":
            link_text = _reconstruct_inner(node.get("children", []), links_acc)
            dest = node.get("destination", "")
            parts.append(f"[{link_text}]({dest})")
            links_acc.append({"text": link_text, "url": dest})
        elif tag == "image":
            alt = _reconstruct_inner(node.get("children", []), links_acc)
            src = node.get("destination", "")
            parts.append(f"![{alt}]({src})")
        elif tag == "subscript":
            parts.append("~" + _reconstruct_inner(node.get("children", []), links_acc) + "~")
        elif tag == "superscript":
            parts.append("^" + _reconstruct_inner(node.get("children", []), links_acc) + "^")
        elif tag == "delete":
            parts.append("{-" + _reconstruct_inner(node.get("children", []), links_acc) + "-}")
        elif tag == "insert":
            parts.append("{+" + _reconstruct_inner(node.get("children", []), links_acc) + "+}")
        elif tag == "mark":
            parts.append("{=" + _reconstruct_inner(node.get("children", []), links_acc) + "=}")
        elif tag == "footnote_reference":
            parts.append("[^" + node["text"] + "]")
        elif tag == "span":
            inner = _reconstruct_inner(node.get("children", []), links_acc)
            attrs = _format_attrs(node.get("attributes", {}))
            parts.append(f"[{inner}]{{{attrs}}}")
        elif tag == "raw_inline":
            fmt = node.get("format", "")
            parts.append(f"`{node['text']}`{{={fmt}}}")
        else:
            # Unknown inline: emit children if present, otherwise skip
            if "children" in node:
                parts.append(_reconstruct_inner(node["children"], links_acc))
    
    return "".join(parts)

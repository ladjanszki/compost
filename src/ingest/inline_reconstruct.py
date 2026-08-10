"""
inline_reconstruct.py — reconstruct Djot inline markup from djot.js AST inline nodes.

Structural markup is emitted as djot source (`_emph_`, `` `code` ``, `[x](y)`),
because that is what a block's stored text has always been. Typographic
constructs are the exception and are emitted as the *character* they stand for:
djot has smart punctuation in the spec, so `---` in a source file means an em
dash, and `\\-\\--` means three literal hyphens. Emitting the source spelling for
both would make them indistinguishable in the stored text, which is the loss
this module exists to avoid.

An unrecognised tag raises. It used to emit nothing, which is how every em
dash, en dash and ellipsis in the corpus was silently deleted — and the same
silence dropped task lists and swallowed a div's children before that. Three
bugs, one cause: a missing branch that says nothing. See CHANGELOG v0.1.2.
"""

# djot smart punctuation, resolved to the character it denotes.
SMART_PUNCTUATION = {
    "em_dash": "—",
    "en_dash": "–",
    "ellipses": "…",
    "left_single_quote": "‘",
    "right_single_quote": "’",
    "left_double_quote": "“",
    "right_double_quote": "”",
}

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
        elif tag == "smart_punctuation":
            kind = node.get("type")
            if kind not in SMART_PUNCTUATION:
                raise ValueError(
                    f"unknown smart_punctuation type {kind!r}; add it to "
                    "SMART_PUNCTUATION rather than letting it be dropped")
            parts.append(SMART_PUNCTUATION[kind])
        elif tag == "double_quoted":
            parts.append("“" + _reconstruct_inner(node.get("children", []), links_acc) + "”")
        elif tag == "single_quoted":
            parts.append("‘" + _reconstruct_inner(node.get("children", []), links_acc) + "’")
        elif tag == "url":
            parts.append("<" + node["text"] + ">")
        elif tag == "email":
            parts.append("<" + node["text"] + ">")
        else:
            raise ValueError(
                f"inline_reconstruct: no branch for djot inline tag {tag!r}. "
                "Add one. Emitting nothing deletes the author's text silently, "
                "which is how three bugs shipped past green tests.")

    return "".join(parts)

"""
blocks_to_djot.py — render Block records back to Djot format.
"""

def render_blocks(blocks: list[dict], options: dict = None) -> str:
    """Render a list of blocks to a valid Djot string."""
    if options is None:
        options = {"include_ids": True}
        
    out = []
    include_ids = options.get("include_ids", True)
    
    prev_type = None
    prev_style = None
    
    for i, block in enumerate(blocks):
        btype = block["type"]
        content = block.get("content", {})
        block_id = block.get("id")
        
        # Spacing logic
        if i > 0:
            if btype == "list_item" and prev_type == "list_item":
                style = content.get("style")
                if style == prev_style:
                    # No blank line between items of the same list
                    pass
                else:
                    out.append("")
            else:
                out.append("")
                
        if include_ids and block_id:
            out.append(f"{{#{block_id}}}")
            
        if btype == "heading":
            level = content.get("level", 1)
            text = content.get("text", "")
            out.append(f"{'#' * level} {text}")
            
        elif btype == "paragraph":
            text = content.get("text", "")
            out.append(text)
            
        elif btype == "code_block":
            lang = content.get("language", "")
            text = content.get("text", "")
            # Ensure text ends with a newline before the closing fence
            if text and not text.endswith("\n"):
                text += "\n"
            out.append(f"```{lang}\n{text}```")
            
        elif btype == "block_quote":
            text = content.get("text", "")
            lines = text.split("\n")
            out.append("\n".join(f"> {line}" if line else ">" for line in lines))
            
        elif btype == "list_item":
            style = content.get("style", "unordered")
            text = content.get("text", "")
            prefix = "- " if style == "unordered" else "1. "
            lines = text.split("\n")
            indented = []
            for i_line, line in enumerate(lines):
                if i_line == 0:
                    indented.append(f"{prefix}{line}")
                else:
                    # Indent subsequent lines in the list item
                    indented.append(f"  {line}" if line else "  ")
            out.append("\n".join(indented))
            
        elif btype == "definition_item":
            term = content.get("term", "")
            text = content.get("text", "")
            out.append(f": {term}")
            
            lines = text.split("\n")
            indented = []
            for i_line, line in enumerate(lines):
                if i_line == 0:
                    indented.append(f": {line}")
                else:
                    indented.append(f"  {line}" if line else "  ")
            out.append("\n".join(indented))
            
        elif btype == "thematic_break":
            out.append("---")
            
        elif btype == "div":
            classes = " ".join(content.get("classes", []))
            children = content.get("children", [])
            out.append(f"::: {classes}")
            
            child_text = render_blocks(children, options).rstrip()
            if child_text:
                out.append(child_text)
                
            out.append(":::")
            
        elif btype == "raw_block":
            fmt = content.get("format", "")
            text = content.get("text", "")
            if text and not text.endswith("\n"):
                text += "\n"
            out.append(f"```{{={fmt}}}\n{text}```")
            
        elif btype == "table":
            rows = content.get("rows", [])
            caption = content.get("caption", "")
            
            for row in rows:
                cells = [c.get("text", "") for c in row.get("cells", [])]
                out.append("| " + " | ".join(cells) + " |")
                
                # After header row, output separator
                if row.get("head"):
                    seps = []
                    for c in row.get("cells", []):
                        align = c.get("align", "default")
                        if align == "left":
                            seps.append(":---")
                        elif align == "right":
                            seps.append("---:")
                        elif align == "center":
                            seps.append(":---:")
                        else:
                            seps.append("---")
                    out.append("|" + "|".join(seps) + "|")
                    
            if caption:
                out.append(f"^ {caption}")
                
        prev_type = btype
        if btype == "list_item":
            prev_style = content.get("style")
        else:
            prev_style = None

    return "\n".join(out) + "\n" if out else ""

def render_page(page: dict, blocks: list[dict], options: dict = None) -> str:
    """Render a full page including frontmatter if any."""
    return render_blocks(blocks, options)

def render_context(blocks: list[dict], options: dict = None) -> str:
    """Alias for render_blocks."""
    return render_blocks(blocks, options)
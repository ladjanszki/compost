"""
inline_reconstruct.py — reconstruct Djot inline markup from Pandoc AST inline nodes.
"""


def reconstruct(inlines: list) -> str:
    """
    Walk a list of Pandoc AST inline nodes and return the equivalent Djot
    inline markup as a plain string.

    Supported nodes:
      Str       → literal string
      Space     → single space
      SoftBreak → newline
      Strong    → *...*
      Emph      → _..._
      (others)  → recurse into "c" if it is a list, otherwise skip
    """
    parts = []
    for node in inlines:
        t = node.get("t")
        c = node.get("c")

        if t == "Str":
            parts.append(c)
        elif t == "Space":
            parts.append(" ")
        elif t == "SoftBreak":
            parts.append("\n")
        elif t == "Strong":
            parts.append("*" + reconstruct(c) + "*")
        elif t == "Emph":
            parts.append("_" + reconstruct(c) + "_")
        elif isinstance(c, list):
            # Unknown inline node — recurse into children if possible
            parts.append(reconstruct(c))
        # else: no children, skip silently

    return "".join(parts)

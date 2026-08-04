"""
md_to_djot.py — convert a Markdown note to Djot via pandoc.

Notes are authored in Markdown and stored as Djot. Markdown permits lazy list
nesting (`- a` / `  - b` with no blank line between); djot does not, and parses
the child as continuation text of the parent paragraph. Pandoc resolves this,
so no hand-written normalizer is needed.

Every pandoc flag here prevents a silent rewrite of the author's text. See
mvp-design.md §4.1.
"""
import re
import shutil
import subprocess

# -smart              : without it, apostrophes become curly quotes
#                       ("don't" -> "don’t")
# -auto_identifiers   : without it, pandoc emits a slug attribute of its own
#                       before every heading ("{#a-heading}"). Our injected
#                       UUID still wins semantically, so this is a cleanliness
#                       fix rather than a correctness one — but the slug would
#                       otherwise sit in the file as noise, and slugs derive
#                       from heading text, so keeping them around invites
#                       referencing an id that changes when the text is edited.
# --wrap=preserve     : without it, paragraphs are reflowed to a different
#                       width, destroying the author's line breaks
PANDOC_ARGS = [
    "-f", "markdown-smart-auto_identifiers",
    "-t", "djot",
    "--wrap=preserve",
]

# Pandoc's djot writer has no task-list support: "- [ ] x" is emitted as a
# literal ballot box and stops being a task. No pandoc flag avoids this
# (-task_lists yields an equally inert "\[ \]"), so it is restored here.
#
# The ballot box is used as the marker rather than the escaped brackets
# because an author would never type it, so it cannot collide with prose.
_UNCHECKED = re.compile(r"^(\s*[-*+] )☐ ", re.MULTILINE)
_CHECKED = re.compile(r"^(\s*[-*+] )☒ ", re.MULTILINE)


def _restore_checkboxes(djot_text: str) -> str:
    """Turn pandoc's ballot-box list items back into djot task list items."""
    djot_text = _UNCHECKED.sub(r"\1[ ] ", djot_text)
    djot_text = _CHECKED.sub(r"\1[x] ", djot_text)
    return djot_text


def md_to_djot(md_text: str) -> str:
    """Convert Markdown source to Djot source. Deterministic, no ids assigned."""
    if shutil.which("pandoc") is None:
        raise RuntimeError("pandoc not found. Install pandoc 3.x.")

    result = subprocess.run(
        ["pandoc", *PANDOC_ARGS],
        input=md_text,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed:\n{result.stderr.strip()}")

    return _restore_checkboxes(result.stdout)

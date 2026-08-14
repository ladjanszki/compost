"""
artifact.py — documents that get rewritten, without losing their handles.

An artifact is a README, a TODO, a design note: a document that changes as
understanding improves. That makes it the opposite of a conversation, and it is
why the two are stored apart.

**The whole problem is regeneration.** Canonizing a document a second time mints
fresh handles for every block, so every comment anyone wrote about it is
orphaned — and the comment lives in an immutable turn, so it can never be
corrected. A document you cannot safely update is a document nobody will comment
on twice.

The fix is the delta algorithm from
`archive/architecture/delta_ingestion_and_block_versioning.md`, and it is smaller than
it sounds. Hash each block by `(type, content)`; a block whose hash matches one
in the previous version *is* that block and keeps its handle. Only genuinely new
or changed text gets a new handle. Matching is by content rather than by
position so that inserting a paragraph does not renumber everything after it.

What this does **not** do is track a block across an edit: change a word and the
hash changes, so it is a new block and references to the old one dangle. That is
correct — the old text is what was commented on, and pretending otherwise would
silently reattach a comment to something it was not about. `pandig check` reports
the dangling reference, which is the honest outcome.
"""
import re
from pathlib import Path

from .canonize import block_hash, canonize_text
from .ingest.ast_walker import walk
from .ingest.djot_ast import get_ast_from_text
from .refs import ID_ATTR


def _by_hash(blocks: list) -> dict[str, list[str]]:
    """Content hash -> handles carrying it, in order."""
    out: dict[str, list[str]] = {}
    for b in blocks:
        if b.get("id"):
            out.setdefault(block_hash(b), []).append(b["id"])
    return out


def write(path: Path, md_text: str) -> dict:
    """
    Canonize markdown into `path`, keeping handles for unchanged blocks.

    Returns counts: kept, added, removed.
    """
    result = canonize_text(md_text)
    new_blocks = walk(get_ast_from_text(result.djot))

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.djot, encoding="utf-8")
        return {"kept": 0, "added": len(new_blocks), "removed": 0}

    old_blocks = walk(get_ast_from_text(path.read_text(encoding="utf-8")))
    available = _by_hash(old_blocks)

    # new handle -> the old handle it should adopt
    adopt: dict[str, str] = {}
    for b in new_blocks:
        pool = available.get(block_hash(b))
        if pool:
            adopt[b["id"]] = pool.pop(0)

    djot = ID_ATTR.sub(
        lambda m: "{#" + adopt.get(m.group(1), m.group(1)) + "}", result.djot)

    # The rewrite is textual, so confirm it did not disturb the document.
    checked = walk(get_ast_from_text(djot))
    if [b["type"] for b in checked] != [b["type"] for b in new_blocks]:
        raise ValueError(f"{path.name}: handle rewrite changed the block list")
    if len({b["id"] for b in checked}) != len(checked):
        raise ValueError(f"{path.name}: handle rewrite produced a duplicate")

    path.write_text(djot, encoding="utf-8")
    kept = len(adopt)
    return {"kept": kept, "added": len(new_blocks) - kept,
            "removed": len(old_blocks) - kept}


def name_for(source: Path) -> str:
    """A filename that reads like a title: lowercase, hyphenated, no extension."""
    stem = re.sub(r"[^a-z0-9]+", "-", source.stem.lower()).strip("-")
    return stem or "artifact"

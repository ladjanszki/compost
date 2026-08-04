"""
canonize — turn a Markdown note into a frozen, addressable Djot note.

    note.md
      -> pandoc -f markdown-smart -t djot --wrap=preserve
      -> restore checkbox markers
      -> parse with --sourcepos, inject a UUIDv7 id into every block
      -> notes/<uuid>.dj

The result is verified before it is returned: every block must carry an id,
and the block texts must be identical to those parsed before injection. If
either check fails, canonization raises rather than writing a note that
cannot be referenced.
"""
import hashlib
import json
import os
from dataclasses import dataclass, field

import uuid6

from ..ingest.ast_walker import walk
from ..ingest.djot_ast import get_ast_from_text
from .inject_ids import inject_ids
from .md_to_djot import md_to_djot


@dataclass
class CanonizeResult:
    note_id: str
    path: str
    djot: str
    blocks: list = field(default_factory=list)   # [{id, type, hash, text}]

    @property
    def block_ids(self) -> list[str]:
        return [b["id"] for b in self.blocks]


def block_hash(block: dict) -> str:
    """
    SHA-256 of the block's canonical (type, content). The 16-char prefix is
    what mvp-design.md §6 stores; the full digest is available for exact
    matching. Not written into the note: notes are immutable, so a note
    block's hash never changes and is always recomputable.
    """
    payload = json.dumps(
        {"type": block["type"], "content": block["content"]},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _texts(blocks: list) -> list:
    return [(b["type"], b["content"].get("text", "")) for b in blocks]


def canonize_text(md_text: str) -> CanonizeResult:
    """Canonize Markdown source. Does not touch the filesystem."""
    djot = md_to_djot(md_text)
    before = walk(get_ast_from_text(djot))

    injected = inject_ids(djot)
    after = walk(get_ast_from_text(injected))

    # The injection must be structurally inert: same blocks, same text.
    if _texts(before) != _texts(after):
        raise ValueError(
            "id injection changed the note's content.\n"
            f"  before: {len(before)} blocks\n  after:  {len(after)} blocks"
        )

    missing = [i for i, b in enumerate(after) if not b.get("id")]
    if missing:
        types = [after[i]["type"] for i in missing]
        raise ValueError(
            f"{len(missing)} block(s) received no id: {sorted(set(types))}"
        )

    note_id = str(uuid6.uuid7())
    blocks = [
        {
            "id": b["id"],
            "type": b["type"],
            "hash": block_hash(b)[:16],
            "text": b["content"].get("text", ""),
        }
        for b in after
    ]
    return CanonizeResult(note_id=note_id, path="", djot=injected, blocks=blocks)


def canonize(md_path: str, notes_dir: str = "notes") -> CanonizeResult:
    """Canonize a Markdown file and write it to notes/<uuid>.dj."""
    with open(md_path, "r", encoding="utf-8") as f:
        result = canonize_text(f.read())

    os.makedirs(notes_dir, exist_ok=True)
    result.path = os.path.join(notes_dir, f"{result.note_id}.dj")
    with open(result.path, "w", encoding="utf-8") as f:
        f.write(result.djot)
    return result

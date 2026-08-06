"""
conversation.py — turns, appended into one file.

A conversation is a single `.dj` that grows by appending turns. The file
changes; the blocks in it never do. That distinction is the whole design:
handles stay stable and references keep resolving, so appending is not
mutation and needs none of the delta machinery that artifacts will.

Each turn is fenced in its own div:

    {.turn author="human"}
    :::
    ...the canonized turn...
    :::

One native djot construct doing three jobs at once:

  * **Authorship.** `author` is a djot attribute, so it lives in the `.dj` and
    therefore in git. No frontmatter, no sidecar, nothing outside the reference
    implementation.
  * **A container** the renderer can label and style per turn.
  * **Folding**, since nested divs (`.tool-call`) are how imported tool traffic
    gets hidden.

None of this works without the div fix in ast_walker: a div used to swallow its
children, so every block in a turn would have been unaddressable.

**On the seam.** Concatenating turns can corrupt the join. Measured, appending
a paragraph directly after a heading section merges it into the *previous*
paragraph — the earlier block's text silently grows and the new turn's id is
left attached to nothing — and a list appended after a paragraph is absorbed as
continuation text, losing its id entirely. A single blank line prevents every
case found, and SEPARATOR provides one; the fence then makes merging structurally
impossible rather than merely unlikely. The verifier below is not defending
against a live bug, it is a cheap assertion that an append did what it said.
That is worth keeping precisely because the failure would be silent and
permanent: conversations are append-only so that a block, once referenced, can
never change under the reference.
"""
import re
from pathlib import Path

import uuid6

from .canonize import canonize_text
from .ingest.ast_walker import walk
from .ingest.djot_ast import get_ast_from_text
from .refs import REF, new_handle


# A blank line between turns. Without one, djot merges the seam: see the module
# docstring. Named so tests can tighten it and prove the verifier fires.
SEPARATOR = "\n\n"


class AppendError(Exception):
    """The append would have changed blocks that were already written."""


def new_id() -> str:
    """Conversation and turn ids stay UUIDv7 — the timestamp is the date."""
    return str(uuid6.uuid7())


def _identity(blocks: list) -> list:
    """
    What must not change when a turn is appended.

    Structure is included deliberately: the seam failure does not alter any
    text. Two turns whose lists merge keep every handle and every string, and
    only `depth` moves — the second turn's items quietly become children of the
    first turn's. Comparing text alone would wave that through.
    """
    return [(b.get("id"), b["type"], b["content"].get("text", ""),
             b["content"].get("depth"), b["content"].get("level"),
             b["content"].get("style"), b["content"].get("contains"))
            for b in blocks]


def wrap_turn(djot: str, author: str, turn_id: str) -> str:
    """
    Fence a canonized turn as an authored div.

    The div gets a handle of its own so a whole turn can be cited — shift-click
    copies it as a subtree — and so no block in the file is unaddressable.
    """
    return (f'{{#{new_handle()} .turn author="{author}" turn="{turn_id}"}}\n'
            f":::\n{djot.strip()}\n:::\n")


def append_turn(path: Path, md_text: str, author: str,
                turn_id: str | None = None) -> tuple[str, list]:
    """
    Canonize `md_text` and append it to the conversation at `path`.

    Verifies rather than assumes: after the append, every block that was
    already in the file must still be there, byte for byte, with the same
    handle. If it is not, the file is restored and this raises — an append that
    quietly reparents earlier content would break references permanently, and
    conversations are append-only precisely so that cannot happen.
    """
    turn_id = turn_id or new_id()
    result = canonize_text(md_text)
    turn = wrap_turn(result.djot, author, turn_id)

    before_text = path.read_text(encoding="utf-8") if path.exists() else ""
    before = walk(get_ast_from_text(before_text)) if before_text.strip() else []

    combined = (before_text.rstrip("\n") + SEPARATOR + turn) if before_text.strip() else turn
    after = walk(get_ast_from_text(combined))

    if _identity(after)[: len(before)] != _identity(before):
        raise AppendError(
            f"appending would have altered existing blocks in {path.name}.\n"
            f"  before: {len(before)} blocks, after: {len(after)}"
        )
    added = len(after) - len(before)
    if added < len(result.blocks):
        raise AppendError(
            f"turn lost blocks on append to {path.name}: "
            f"{len(result.blocks)} canonized, {added} landed"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(combined, encoding="utf-8")
    return turn_id, after[len(before):]


def infer_conversation(store, md_text: str) -> str | None:
    """
    Which conversation a draft belongs to, from the blocks it cites.

    You reply by clicking a block, so the thread is already implied by the
    first reference in the draft — there is no second handle to copy. Returns
    None when the draft cites nothing (a new conversation) and raises when it
    cites more than one (say which, explicitly).
    """
    handles = {m.group(1) for m in REF.finditer(md_text)}
    if not handles:
        return None

    hits = set()
    for path in store.conversation_paths():
        text = path.read_text(encoding="utf-8")
        if any(re.search(r"\{#" + h + r"\}", text) for h in handles):
            hits.add(path.stem)

    if len(hits) > 1:
        raise AppendError(
            "this draft cites blocks in several conversations "
            f"({', '.join(sorted(hits))}); pass --conversation to choose one"
        )
    return hits.pop() if hits else None

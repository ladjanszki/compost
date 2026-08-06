"""
refs.py — the block handle and the reference format.

Everything that reads or writes an id goes through here, because the format is
a one-way door: handles are baked into immutable files, and changing them means
re-canonizing the corpus and rewriting every reference ever written.

    {#a3f9c2d1}         a block
    {#a3f9c2d1+++}      that block and its subtree
    {#a3f9c2d1@7f2e}    that block at a specific version

**Handles are 8 random hex characters, not UUIDs.** A UUIDv7 costs 39 bytes per
block on disk and 56 per reference, which was 27% of the corpus and unreadable
in prose. Nothing needed a per-block timestamp: document order comes from file
order, and *note* ids stay UUIDv7 so `_when()` and chronological sorting still
work.

8 hex is ~4.3e9 values. At the projected corpus ceiling of 100k blocks that is
roughly one expected collision, which `kg check` reports rather than prevents —
so minting a handle stays a pure function and canonization never has to read the
corpus. A shorter handle would need a registry file mapping handle to block, and
that file could not be rebuilt from the `.dj` files: losing it would break every
reference at once, which no other artifact in this system can do.

**The version pin is optional, and absent means "the block itself".** Blocks in
conversations are immutable, so their identity already pins their content —
mvp-design.md 6.1 required a pin on every reference so that "which version was
fed to the agent" is answerable, and for immutable content the handle answers
it. Artifacts are mutable and do need `@ver`. Defining both forms now means the
syntax never has to change again when artifacts arrive.
"""
import re
import secrets

HANDLE = r"[0-9a-f]{8}"

# An id attribute as written into a .dj file. The lookbehind matters: pandoc
# escapes an author's reference on disk as \{#a3f9c2d1\}, and that is text the
# author wrote, not an attribute we assigned.
ID_ATTR = re.compile(r"(?<!\\)\{#(" + HANDLE + r")\}")

# A reference as it appears in parsed block text. Scan parsed text, never the
# raw file — parsing is what removes the escaping.
REF = re.compile(r"\{#(" + HANDLE + r")(?:@([0-9a-f]{4,16}))?(\+*)\}")

# An id on a list item's marker line, which loosen() needs to find.
ID_LINE = re.compile(
    r"^\s*(?:[-*+]|\d+[.)]) (?:\[[ x]\] )?\{#" + HANDLE + r"\}\s*$")


def new_handle() -> str:
    """A fresh block handle. Pure — collisions are reported by `kg check`."""
    return secrets.token_hex(4)


def reference(handle: str, version: str | None = None,
              subtree: bool = False) -> str:
    """Build the reference string the HTML copies to the clipboard."""
    return f"{{#{handle}{'@' + version if version else ''}{'+++' if subtree else ''}}}"

"""
store.py — locating and describing a knowledge base on disk.

A knowledge base is a directory created by `kg init`:

    <root>/
      raw/<conv>/<turn>.md      drafts exactly as written, frozen
      conversations/<conv>.dj   turns, appended; every block frozen once written
      artifacts/<name>.dj       agent-written and regenerated; mutable
      site/                     generated HTML (disposable)
      .kg                       marker file identifying the root

The split is by **mutability**, not by author. A conversation is append-only:
turns are added, but no block already in the file ever changes, which is what
keeps handles stable and references resolvable. An artifact is rewritten in
place and needs id-preserving regeneration. Either party can write either kind;
authorship is recorded per turn as a `{.turn author=...}` attribute, so it lives
in the .dj and therefore in git.

A conversation is one file rather than a directory of turns because turns get
concatenated for reading anyway, and because one file is one djot parse: an
imported session of ~70 turns costs about a second instead of two minutes.

`kg` is meant to be run from anywhere, so the root is resolved in order:
KG_HOME, then an explicit --root, then by walking up from the current
directory looking for a `.kg` marker.

Keeping the root outside the tool's own directory is possible but not
required: `kg init .` puts them together, `kg init ~/knowledge` separates
them. Deferring that choice is deliberate.
"""
import os
from dataclasses import dataclass
from pathlib import Path

MARKER = ".kg"
SUBDIRS = ("raw", "conversations", "artifacts", "site")


class StoreError(Exception):
    pass


@dataclass(frozen=True)
class Store:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def conversations(self) -> Path:
        return self.root / "conversations"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def site(self) -> Path:
        return self.root / "site"

    def conversation_paths(self) -> list[Path]:
        """Conversations, oldest first — uuid7 sorts chronologically."""
        return sorted(self.conversations.glob("*.dj"))

    def artifact_paths(self) -> list[Path]:
        """Artifacts, by name — they are titles, not timestamps."""
        return sorted(self.artifacts.glob("*.dj"))

    def source_paths(self) -> list[Path]:
        """Everything with addressable blocks in it."""
        return self.conversation_paths() + self.artifact_paths()

    def drafts_for(self, conv_id: str) -> list[Path]:
        """The turns of a conversation, as they were written."""
        return sorted((self.raw / conv_id).glob("*.md"))


def init(root: str | os.PathLike) -> Store:
    """Create a knowledge base. Safe to run on an existing one."""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (root / name).mkdir(exist_ok=True)
    (root / MARKER).touch()

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("site/\n")
    return Store(root)


def _walk_up(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        if (d / MARKER).exists():
            return d
    return None


def find(explicit: str | None = None) -> Store:
    """
    Resolve the knowledge base root, or raise with an actionable message.

    Order: explicit --root, then $KG_HOME, then a `.kg` marker in the current
    directory or any parent.
    """
    for candidate in (explicit, os.environ.get("KG_HOME")):
        if candidate:
            root = Path(candidate).expanduser().resolve()
            if not (root / MARKER).exists():
                raise StoreError(
                    f"{root} is not a knowledge base (no {MARKER} marker).\n"
                    f"Create one with:  kg init {root}"
                )
            return Store(root)

    found = _walk_up(Path.cwd().resolve())
    if found:
        return Store(found)

    raise StoreError(
        "No knowledge base found.\n"
        "Set KG_HOME, pass --root, or run `kg init <dir>` to create one."
    )

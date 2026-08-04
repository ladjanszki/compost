"""
store.py — locating and describing a knowledge base on disk.

A knowledge base is a directory created by `kg init`:

    <root>/
      raw/     <uuid>.md   the draft exactly as written, frozen
      notes/   <uuid>.dj   canonized and addressable, frozen
      site/                generated HTML (disposable)
      .kg                  marker file identifying the root

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
SUBDIRS = ("raw", "notes", "site")


class StoreError(Exception):
    pass


@dataclass(frozen=True)
class Store:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def notes(self) -> Path:
        return self.root / "notes"

    @property
    def site(self) -> Path:
        return self.root / "site"

    def note_paths(self) -> list[Path]:
        """Canonized notes, oldest first — uuid7 sorts chronologically."""
        return sorted(self.notes.glob("*.dj"))

    def draft_for(self, note_path: Path) -> Path:
        return self.raw / (note_path.stem + ".md")


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

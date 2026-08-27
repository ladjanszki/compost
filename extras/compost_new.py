#!/usr/bin/env python3
"""
compost_new.py — `compost-new`: mint a scratch file, open $EDITOR, digest it.

Installed, but not the tool (DEVELOPMENT.md, "What belongs in extras/"): a
user-facing convenience wrapper around three things the tool already does —
minting a name the way graph and storage names already are, `digest`'s
`notes` route, and spawning an editor — orchestrated so a person does not
have to do it by hand every time they want to write a note that ends up in
the base. Exposed through `[project.scripts]` as `compost-new`, a distinct
command from `compost`, on purpose: `compost new` would read as a
subcommand and move the count `docs/man-compost.md` asserts and
`tests/test_manpage.py` enforces.

    compost-new

No flags. `$EDITOR` must be set — this project already refuses to guess at
things nobody told it (a route, a handle length), and a default editor
guessed wrong would be the same mistake in a different place. `$EDITOR` may
itself carry arguments (`"code --wait"`), split with `shlex.split` the way a
shell would.

The minted file is left on disk after digesting, same as any file `compost
digest` reads: ingestion never deletes its input, only copies the bytes into
`storage/`. An empty draft — the editor opened and closed without a
keystroke, or with only whitespace — is not digested and is removed, so
closing an editor by accident does not mint a blob nobody wanted.
"""
import os
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import store as S    # noqa: E402

ROUTE = "notes"


def main(argv=None) -> int:
    editor = os.environ.get("EDITOR")
    if not editor:
        print("compost-new: $EDITOR is not set")
        return 2

    try:
        st = S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1

    # Minted the same way graph/ and storage/ names already are: a fresh
    # uuid, never derived from anything else (docs/decisions.md, "Storage
    # and graph names must not be derivable from each other").
    path = Path.cwd() / f"{uuid.uuid4()}.md"
    path.write_text("")

    rc = subprocess.call(shlex.split(editor) + [str(path)])
    if rc != 0:
        print(f"compost-new: {editor!r} exited {rc}; nothing digested")
        return rc

    if not path.read_text(encoding="utf-8").strip():
        path.unlink()
        print("compost-new: empty draft, nothing written")
        return 0

    return S._digest(st, ROUTE, [str(path)], "compost-new")


if __name__ == "__main__":
    sys.exit(main(sys.argv))

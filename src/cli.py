"""
cli.py — the `kg` command.

    kg init [dir]     create a knowledge base
    kg new            write a note, submit it on editor exit
    kg submit <file>  canonize an existing markdown file into the base
    kg render         build the static site
    kg serve [-p]     render, then serve site/ on localhost

The base is found via --root, then $KG_HOME, then a `.kg` marker in the
current directory or any parent — so `kg` works from anywhere.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import uuid6

from . import store as store_mod
from .canonize import canonize_text
from .render.to_html import render as render_site


def _editor() -> list[str]:
    return (os.environ.get("KG_EDITOR") or os.environ.get("EDITOR")
            or "nvim").split()


def _submit_file(st: store_mod.Store, md_path: Path, note_id: str) -> None:
    """Canonize a draft into the base. Both files are frozen afterwards."""
    text = md_path.read_text(encoding="utf-8")
    if not text.strip():
        print("Empty note — nothing submitted.", file=sys.stderr)
        if md_path.parent == st.raw:
            md_path.unlink(missing_ok=True)
        raise SystemExit(1)

    result = canonize_text(text)

    st.raw.mkdir(parents=True, exist_ok=True)
    st.notes.mkdir(parents=True, exist_ok=True)
    draft = st.raw / f"{note_id}.md"
    if md_path.resolve() != draft.resolve():
        draft.write_text(text, encoding="utf-8")
    (st.notes / f"{note_id}.dj").write_text(result.djot, encoding="utf-8")

    print(f"submitted {note_id}  ({len(result.blocks)} blocks)")
    print(f"  draft  {draft}")
    print(f"  note   {st.notes / (note_id + '.dj')}")


# ------------------------------------------------------------- commands ---

def cmd_init(args) -> int:
    st = store_mod.init(args.dir)
    print(f"knowledge base ready at {st.root}")
    print(f"  raw/    drafts as written\n  notes/  canonized\n  site/   generated")
    print(f"\nTip: export KG_HOME={st.root}")
    return 0


def cmd_new(args) -> int:
    st = store_mod.find(args.root)
    note_id = str(uuid6.uuid7())
    st.raw.mkdir(parents=True, exist_ok=True)
    draft = st.raw / f"{note_id}.md"
    draft.touch()

    # Submission happens on editor exit, never on save: saving must stay free.
    subprocess.call([*_editor(), str(draft)])
    _submit_file(st, draft, note_id)
    return 0


def cmd_submit(args) -> int:
    st = store_mod.find(args.root)
    md = Path(args.file).expanduser().resolve()
    if not md.exists():
        print(f"no such file: {md}", file=sys.stderr)
        return 1
    _submit_file(st, md, str(uuid6.uuid7()))
    return 0


def cmd_render(args) -> int:
    st = store_mod.find(args.root)
    stats = render_site(st)
    print(f"{stats['notes']} notes, {stats['blocks']} blocks, "
          f"{stats['backlinks']} referenced → {st.site}")
    if stats["clickable"] < stats["blocks"]:
        missing = stats["blocks"] - stats["clickable"]
        print(f"WARNING: {missing} block(s) are not addressable in HTML",
              file=sys.stderr)
        return 1
    return 0


def cmd_serve(args) -> int:
    st = store_mod.find(args.root)
    if cmd_render(args) != 0:
        return 1
    os.chdir(st.site)
    print(f"serving {st.site} at http://localhost:{args.port} (ctrl-c to stop)")
    subprocess.call([sys.executable, "-m", "http.server", str(args.port)])
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="kg", description="notes → addressable wiki")
    p.add_argument("--root", help="knowledge base directory (overrides KG_HOME)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a knowledge base")
    s.add_argument("dir", nargs="?", default=".")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("new", help="write and submit a note")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("submit", help="canonize an existing markdown file")
    s.add_argument("file")
    s.set_defaults(fn=cmd_submit)

    s = sub.add_parser("render", help="build the static site")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("serve", help="render, then serve on localhost")
    s.add_argument("-p", "--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except store_mod.StoreError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

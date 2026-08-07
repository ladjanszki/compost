"""
cli.py — the `kg` command.

    kg init [dir]     create a knowledge base
    kg new            write a turn, append it on editor exit
    kg submit <file>  append an existing markdown file as a turn
    kg render         build the static site and blocks.json
    kg check          report dangling references and handle collisions
    kg import <log>   import a closed Claude Code session as a conversation
    kg artifact <md>  publish a document as an artifact, handles preserved
    kg serve [-p]     render, then serve site/ on localhost

The base is found via --root, then $KG_HOME, then a `.kg` marker in the
current directory or any parent — so `kg` works from anywhere.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import artifact as artifact_mod
from . import conversation as conv_mod
from . import importer as import_mod
from . import store as store_mod
from .canonize import canonize_text
from .render import index as index_mod
from .render.to_html import load_notes, render as render_site


def _editor() -> list[str]:
    return (os.environ.get("KG_EDITOR") or os.environ.get("EDITOR")
            or "nvim").split()


def _submit_turn(st: store_mod.Store, md_path: Path, conv_id: str | None,
                 author: str, turn_id: str | None = None) -> None:
    """Append a draft to a conversation as one turn. Blocks are frozen after."""
    text = md_path.read_text(encoding="utf-8")
    if not text.strip():
        print("Empty turn — nothing submitted.", file=sys.stderr)
        if md_path.parent.parent == st.raw:
            md_path.unlink(missing_ok=True)
        raise SystemExit(1)

    # You reply by clicking a block, so the thread is implied by what the draft
    # cites — no second handle to copy.
    if conv_id is None:
        conv_id = conv_mod.infer_conversation(st, text)
    started = conv_id is None
    conv_id = conv_id or conv_mod.new_id()

    path = st.conversations / f"{conv_id}.dj"
    turn_id, blocks = conv_mod.append_turn(path, text, author, turn_id)

    draft = st.raw / conv_id / f"{turn_id}.md"
    draft.parent.mkdir(parents=True, exist_ok=True)
    if md_path.resolve() != draft.resolve():
        draft.write_text(text, encoding="utf-8")
        if md_path.parent.parent == st.raw:
            md_path.unlink(missing_ok=True)

    print(f"{'started' if started else 'appended to'} conversation {conv_id}")
    print(f"  turn   {turn_id}  ({len(blocks)} blocks, author: {author})")
    print(f"  draft  {draft}")
    print(f"  file   {path}")


# ------------------------------------------------------------- commands ---

def cmd_init(args) -> int:
    st = store_mod.init(args.dir)
    print(f"knowledge base ready at {st.root}")
    print("  raw/            drafts as written\n"
          "  conversations/  turns, appended, blocks frozen\n"
          "  artifacts/      agent-written, regenerated\n"
          "  site/           generated")
    print(f"\nTip: export KG_HOME={st.root}")
    return 0


def cmd_new(args) -> int:
    st = store_mod.find(args.root)
    turn_id = conv_mod.new_id()
    scratch = st.raw / "_drafting"
    scratch.mkdir(parents=True, exist_ok=True)
    draft = scratch / f"{turn_id}.md"
    draft.touch()

    # Submission happens on editor exit, never on save: saving must stay free.
    subprocess.call([*_editor(), str(draft)])
    _submit_turn(st, draft, args.conversation, args.author, turn_id)
    # The draft has moved under its conversation; don't leave the scratch
    # directory sitting in the base.
    if not any(scratch.iterdir()):
        scratch.rmdir()
    return 0


def cmd_submit(args) -> int:
    st = store_mod.find(args.root)
    md = Path(args.file).expanduser().resolve()
    if not md.exists():
        print(f"no such file: {md}", file=sys.stderr)
        return 1
    _submit_turn(st, md, args.conversation, args.author)
    return 0


def cmd_render(args) -> int:
    st = store_mod.find(args.root)
    stats = render_site(st)
    print(f"{stats['conversations']} conversations, {stats['artifacts']} artifacts, "
          f"{stats['blocks']} blocks, {stats['backlinks']} referenced → {st.site}")
    if stats["clickable"] < stats["blocks"]:
        missing = stats["blocks"] - stats["clickable"]
        print(f"WARNING: {missing} block(s) are not addressable in HTML",
              file=sys.stderr)
        return 1
    return 0


def cmd_artifact(args) -> int:
    """Publish a markdown document as an artifact, keeping handles stable."""
    st = store_mod.find(args.root)
    src = Path(args.file).expanduser().resolve()
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 1

    name = args.name or artifact_mod.name_for(src)
    dest = st.artifacts / f"{name}.dj"
    existed = dest.exists()
    stats = artifact_mod.write(dest, src.read_text(encoding="utf-8"))

    print(f"{'updated' if existed else 'published'} artifacts/{name}.dj")
    if existed:
        print(f"  {stats['kept']} blocks kept their handles, "
              f"{stats['added']} new, {stats['removed']} gone")
        if stats["removed"]:
            print("  run `kg check`: references to removed blocks now dangle")
    else:
        print(f"  {stats['added']} blocks")
    return 0


def cmd_import(args) -> int:
    """Turn a closed Claude Code session into a conversation."""
    st = store_mod.find(args.root)
    path = Path(args.session).expanduser()
    if not path.is_file():
        found = import_mod.sessions_for(path)
        if not found:
            print(f"no session log at {path}, and no logs for that directory",
                  file=sys.stderr)
            return 1
        for p in found:
            print(f"  {p.name}  {p.stat().st_size // 1024} KB")
        print("\nPass one of these paths to import it.")
        return 0

    turns = import_mod.turns_from_session(path)
    if not turns:
        print("no user or assistant turns in that session", file=sys.stderr)
        return 1

    md = import_mod.session_markdown(turns)
    result = canonize_text(md)

    conv_id = args.conversation or path.stem
    dest = st.conversations / f"{conv_id}.dj"
    if dest.exists() and not args.force:
        print(f"{dest} already exists; pass --force to replace it",
              file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(result.djot, encoding="utf-8")

    folded = sum(len(t["folded"]) for t in turns)
    authors = {}
    for t in turns:
        authors[t["author"]] = authors.get(t["author"], 0) + 1
    print(f"imported {path.name} -> conversations/{conv_id}.dj")
    print(f"  {len(turns)} turns ({', '.join(f'{k}: {v}' for k, v in authors.items())})")
    print(f"  {len(result.blocks)} blocks, {folded} folded tool/thinking parts")
    return 0


def cmd_check(args) -> int:
    """Report references that resolve to nothing, and handle collisions."""
    st = store_mod.find(args.root)
    report = index_mod.check(index_mod.build(load_notes(st)))

    for d in report["dangling"]:
        print(f"dangling  {d['source']}  {d['from']} -> {d['target']}\n"
              f"          {d['text']}")
    for c in report["collisions"]:
        print(f"collision {c['handle']} used by {len(c['blocks'])} blocks:")
        for src, text in c["blocks"]:
            print(f"          {src}  {text}")

    bad = len(report["dangling"]) + len(report["collisions"])
    print(f"{report['blocks']} blocks, {len(report['dangling'])} dangling, "
          f"{len(report['collisions'])} collisions")
    return 1 if bad else 0


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

    def turn_args(p):
        p.add_argument("-c", "--conversation",
                       help="conversation to append to "
                            "(default: inferred from the blocks the draft cites)")
        p.add_argument("--author", default="human",
                       help="who wrote this turn (default: human)")

    s = sub.add_parser("new", help="write a turn and submit it")
    turn_args(s)
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("submit", help="append an existing markdown file as a turn")
    s.add_argument("file")
    turn_args(s)
    s.set_defaults(fn=cmd_submit)

    s = sub.add_parser("render", help="build the static site")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("artifact", help="publish a markdown file as an artifact")
    s.add_argument("file")
    s.add_argument("-n", "--name", help="artifact name (default: from the filename)")
    s.set_defaults(fn=cmd_artifact)

    s = sub.add_parser("import", help="import a closed Claude Code session")
    s.add_argument("session",
                   help="path to a .jsonl session log, or a project directory "
                        "to list the logs for")
    s.add_argument("-c", "--conversation", help="conversation id (default: the session id)")
    s.add_argument("--force", action="store_true", help="replace an existing conversation")
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("check", help="report dangling references and collisions")
    s.set_defaults(fn=cmd_check)

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

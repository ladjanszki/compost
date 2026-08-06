"""
One-off migration: UUID block ids -> 8-hex handles, notes/ -> conversations/.

Re-canonizing assigns fresh ids, so every `{#uuid:hash}` reference written so
far would break. It does not have to: notes are immutable, so re-canonizing the
same draft produces the *same sequence* of blocks and old-to-new is a positional
map. This builds that map across the whole corpus, rewrites every reference, and
refuses to write anything if the sequences do not correspond.

Run once, from the repo root:

    python tools/migrate_to_handles.py <kb-path> [--apply]

Without --apply it reports what it would do and touches nothing.
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.canonize import canonize_text
from src.conversation import SEPARATOR, wrap_turn
from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text
from src.refs import REF

# References as the old format left them: escaped on disk (the colon too),
# unescaped in the markdown draft.
OLD_ON_DISK = re.compile(r"\\\{#([0-9a-f-]{36})\\:([0-9a-f]{16})(\+*)\\\}")
OLD_IN_DRAFT = re.compile(r"\{#([0-9a-f-]{36}):([0-9a-f]{16})(\+*)\}")

# id -> (kind, author). Order is turn order.
PLAN = [
    ("019fd7b7-9473-7306-8545-ba8e49393728", "turn", "human"),
    ("019fd7e2-c007-799a-a6c0-f054a26f3440", "turn", "claude"),
    ("019fd7eb-12d3-7fba-b8c3-06872d2cfd99", "turn", "human"),
    ("019fd268-3b94-7554-95b0-ff8629edce45", "artifact:roadmap", None),
    ("019fd24c-a801-7a74-bd62-6deada2859b7", "delete", None),
]


def fail(msg):
    print(f"REFUSED: {msg}")
    sys.exit(1)


def main(kb: Path, apply: bool):
    old_notes, raw = kb / "notes", kb / "raw"
    mapping: dict[str, str] = {}
    staged: list[tuple[str, str, str, str]] = []   # id, kind, author, new djot

    # ---- pass 1: re-canonize each draft and map old blocks to new ---------
    for note_id, kind, author in PLAN:
        if kind == "delete":
            continue
        old = walk(get_ast_from_text((old_notes / f"{note_id}.dj").read_text()))
        draft = (raw / f"{note_id}.md").read_text()
        new = canonize_text(draft)
        new_blocks = walk(get_ast_from_text(new.djot))

        if len(old) != len(new_blocks):
            fail(f"{note_id}: {len(old)} blocks before, {len(new_blocks)} after. "
                 "The block sequence changed, so no positional map exists.")
        for a, b in zip(old, new_blocks):
            if a["type"] != b["type"]:
                fail(f"{note_id}: type drift {a['type']} -> {b['type']}")
            mapping[a["id"]] = b["id"]

        staged.append((note_id, kind, author, new.djot))
        print(f"  mapped {note_id[:8]}  {len(old)} blocks  ({kind})")

    # ---- pass 2: rewrite every reference, in the notes and the drafts -----
    def rewrite(text, pattern):
        missing = []

        def sub(m):
            new_id = mapping.get(m.group(1))
            if new_id is None:
                missing.append(m.group(1))
                return m.group(0)
            return (f"\\{{#{new_id}{m.group(3)}\\}}" if pattern is OLD_ON_DISK
                    else f"{{#{new_id}{m.group(3)}}}")

        return pattern.sub(sub, text), missing

    rewritten, dangling = [], []
    for note_id, kind, author, djot in staged:
        text, missing = rewrite(djot, OLD_ON_DISK)
        dangling += [(note_id, h) for h in missing]
        rewritten.append((note_id, kind, author, text))

    if dangling:
        print(f"  {len(dangling)} reference(s) point outside the corpus "
              "and will be left as-is:")
        for src, h in dangling:
            print(f"    {src[:8]} -> {h}")

    # ---- verify: nothing lost, and every rewritten reference resolves -----
    handles = set()
    for note_id, kind, author, text in rewritten:
        blocks = walk(get_ast_from_text(text))
        if any(not b["id"] for b in blocks):
            fail(f"{note_id}: rewriting left a block without a handle")
        handles |= {b["id"] for b in blocks}

    unresolved = []
    for note_id, kind, author, text in rewritten:
        for b in walk(get_ast_from_text(text)):
            for m in REF.finditer(b["content"].get("text", "")):
                if m.group(1) not in handles:
                    unresolved.append((note_id, m.group(1)))
    if unresolved:
        fail(f"{len(unresolved)} rewritten reference(s) do not resolve: "
             f"{unresolved[:5]}")

    print(f"\n  {len(mapping)} blocks remapped, {len(handles)} handles, "
          f"every rewritten reference resolves.")
    if not apply:
        print("\nDry run. Re-run with --apply to write.")
        return

    # ---- write ------------------------------------------------------------
    backup = kb / "_pre-handles-backup"
    if not backup.exists():
        backup.mkdir()
        shutil.copytree(old_notes, backup / "notes")
        shutil.copytree(raw, backup / "raw")

    convs, arts = kb / "conversations", kb / "artifacts"
    convs.mkdir(exist_ok=True)
    arts.mkdir(exist_ok=True)

    turns = [r for r in rewritten if r[1] == "turn"]
    conv_id = turns[0][0]          # the conversation started with its first turn
    parts = [wrap_turn(text, author, turn_id=note_id)
             for note_id, kind, author, text in turns]
    (convs / f"{conv_id}.dj").write_text(SEPARATOR.join(parts), encoding="utf-8")

    for note_id, kind, author, text in rewritten:
        if kind.startswith("artifact:"):
            (arts / f"{kind.split(':', 1)[1]}.dj").write_text(text, encoding="utf-8")

    # Drafts move under their conversation, with references rewritten so a
    # future re-canonization starts from consistent text.
    for note_id, kind, author, text in rewritten:
        draft_text, _ = rewrite((raw / f"{note_id}.md").read_text(), OLD_IN_DRAFT)
        if kind == "turn":
            dest = raw / conv_id / f"{note_id}.md"
        else:
            dest = raw / "artifacts" / f"{kind.split(':', 1)[1]}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(draft_text, encoding="utf-8")

    for note_id, kind, _ in PLAN:
        (raw / f"{note_id}.md").unlink(missing_ok=True)
    shutil.rmtree(old_notes)
    shutil.rmtree(kb / "site", ignore_errors=True)

    conv_blocks = len(walk(get_ast_from_text((convs / f"{conv_id}.dj").read_text())))
    print(f"\n  conversations/{conv_id}.dj   {len(turns)} turns, {conv_blocks} blocks")
    print(f"  artifacts/roadmap.dj")
    print(f"  backup kept at {backup}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(Path(args[0]).expanduser().resolve(), "--apply" in sys.argv)

"""
One-off: split a conversation back into the artifacts it was made from.

The handle migration assembled three standalone notes into one conversation.
That was wrong — they were *files*, written and answered as documents, and
turning them into turns imitated an exchange that never happened. Both kinds
are commentable, so the imitation bought nothing.

The split is textual, so every handle survives and every reference keeps
resolving. Only the three turn wrappers are dropped, and nothing cited them.

    python tools/split_conversation.py <kb> <conversation-id> [--apply]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text

TURN_OPEN = re.compile(r"^\{#[0-9a-f]{8} \.turn .*\}$")

# turn uuid prefix -> artifact name. Named from the first heading, or from what
# the document actually is when it has none.
NAMES = {
    "019fd7b7": "what-to-do-with-this-note",
    "019fd7e2": "untangling-conversations-and-artifacts",
    "019fd7eb": "answers-on-conversations-and-artifacts",
}


def split(text: str) -> list[tuple[str, str]]:
    """[(turn uuid, inner djot)] — one per turn div, wrapper removed."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if TURN_OPEN.match(lines[i]):
            turn = re.search(r'turn="([^"]+)"', lines[i]).group(1)
            assert lines[i + 1].strip() == ":::", lines[i + 1]
            depth, j, body = 1, i + 2, []
            while j < len(lines) and depth:
                if lines[j].strip() == ":::":
                    depth += 1 if body and body[-1].startswith("{.") else -1
                    if depth == 0:
                        break
                body.append(lines[j])
                j += 1
            out.append((turn, "\n".join(body).strip() + "\n"))
            i = j + 1
        else:
            i += 1
    return out


def main(kb: Path, conv_id: str, apply: bool):
    src = kb / "conversations" / f"{conv_id}.dj"
    before = walk(get_ast_from_text(src.read_text(encoding="utf-8")))
    before_ids = [b["id"] for b in before if b["type"] != "div"]

    parts = split(src.read_text(encoding="utf-8"))
    after_ids, plan = [], []
    for turn, body in parts:
        name = NAMES.get(turn[:8], turn[:8])
        blocks = walk(get_ast_from_text(body))
        after_ids += [b["id"] for b in blocks]
        plan.append((name, body, len(blocks)))
        print(f"  {name}.dj  {len(blocks)} blocks")

    if after_ids != before_ids:
        print(f"REFUSED: handles changed. {len(before_ids)} -> {len(after_ids)}")
        sys.exit(1)
    print(f"\n  {len(after_ids)} handles preserved exactly, "
          f"{len(before) - len(after_ids)} turn wrappers dropped.")

    if not apply:
        print("\nDry run. Re-run with --apply to write.")
        return

    for name, body, _ in plan:
        (kb / "artifacts" / f"{name}.dj").write_text(body, encoding="utf-8")
    src.unlink()

    # Drafts follow their artifact.
    raw = kb / "raw" / conv_id
    if raw.exists():
        dest = kb / "raw" / "artifacts"
        dest.mkdir(parents=True, exist_ok=True)
        for turn, _ in parts:
            f = raw / f"{turn}.md"
            if f.exists():
                f.rename(dest / f"{NAMES.get(turn[:8], turn[:8])}.md")
        if not any(raw.iterdir()):
            raw.rmdir()
    print("  written")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(Path(args[0]).expanduser().resolve(), args[1], "--apply" in sys.argv)

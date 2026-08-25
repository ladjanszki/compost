#!/usr/bin/env python3
"""
dj_prepare.py — make a v0.1 `.dj` file's list-item handles survive pandoc.

`pandoc -f djot` **silently drops a block attribute at the start of a list item
when a blank line separates it from the item's content.** The v0.1 canonizer
wrote every handled list item that way:

    - {#1221ba74}

      Volume. One session in that directory is 2.8 MB, because …

The text survives; only the identity is lost. Measured over the 23-file corpus,
that is **767 of 6,601 handles — 11.6%** — and it took citation resolution down
from 96% to 53%, because 74 of the 159 distinct cited handles were among them.

The repair is to delete that one blank line. Nothing else changes: the handle
becomes a `Div` wrapping the item's content, which is what every other handled
block in the corpus already is, so the result is *more* uniform, not less.

**This repairs pandoc's input, never its output.** `CLAUDE.md` forbids the
latter — patching an emitted AST breaks the round-trip by construction. This
runs before pandoc has seen anything, and the round-trip property is unaffected:
whatever pandoc then emits is reproduced exactly.

**Sources stay immutable.** This writes copies. The originals are never opened
for writing, and the copy is what `pandoc -f djot -t json` reads on the way to
`compost digest --as=pandoc-ast`.

    python3 -m tools.dj_prepare SRCDIR OUTDIR      # repair
    python3 -m tools.dj_prepare --verify SRCDIR    # check, repair nothing

`--verify` asserts the property this script exists to establish: **every 8-hex
handle assigned in the text is an id pandoc emits.** It is the acceptance test
for the migration, and it fails loudly on unrepaired input.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

SUFFIX = r"(?:\+\+\+|@[^\s{}\\]+)?"
# A handle opening a list item: "- {#a3f2b1c4}" and nothing else on the line.
LIST_HANDLE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+\{#([0-9a-f]{8})" + SUFFIX + r"\}\s*$")
# A handle assigned on its own line, bulleted or not. Never an escaped one:
# `\{#x\}` is a citation the canonizer escaped, and is not an assignment.
ASSIGNMENT = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\{#([0-9a-f]{8})" + SUFFIX + r"\}\s*$")
# "{#a3f2b1c4 .turn author=…}" — a turn header carries its handle the same way.
ATTR_LINE = re.compile(r"^\s*\{#([0-9a-f]{8})[ .]")
HEX8 = re.compile(r"^[0-9a-f]{8}$")


def repair(text: str) -> tuple[str, int]:
    """Drop the blank line between a list item's handle and its content.

    Fences are skipped: a handle quoted inside ``` is example text, and joining
    there would edit what a conversation *said* rather than how it was written.
    """
    lines = text.split("\n")
    out: list[str] = []
    fence = False
    i = 0
    joined = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            fence = not fence
        out.append(line)
        if (not fence and LIST_HANDLE.match(line)
                and i + 1 < len(lines) and lines[i + 1].strip() == ""):
            i += 1                      # skip exactly one blank line, never more
            joined += 1
        i += 1
    return "\n".join(out), joined


def assigned(text: str) -> set:
    """Every handle the text *assigns*, outside code fences."""
    out = set()
    fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = ASSIGNMENT.match(line) or ATTR_LINE.match(line)
        if m:
            out.add(m.group(1))
    return out


def emitted(path: Path) -> set:
    """Every 8-hex id `pandoc -f djot` actually puts in the AST."""
    r = subprocess.run(["pandoc", "-f", "djot", "-t", "json", str(path)],
                       capture_output=True)
    r.check_returncode()
    out = set()

    def walk(x):
        if isinstance(x, dict):
            c = x.get("c")
            if isinstance(c, list):
                for el in c:
                    if (isinstance(el, list) and len(el) == 3
                            and isinstance(el[0], str) and isinstance(el[1], list)
                            and isinstance(el[2], list) and HEX8.match(el[0])):
                        out.add(el[0])
            walk(c)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(json.loads(r.stdout)["blocks"])
    return out


def main(argv) -> int:
    verify = "--verify" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip().split("\n\n")[-2])
        return 2
    src = Path(args[0])
    files = sorted(src.rglob("*.dj"))
    if not files:
        print(f"no .dj files under {src}")
        return 1

    if verify:
        lost_total = 0
        for f in files:
            missing = assigned(f.read_text()) - emitted(f)
            if missing:
                lost_total += len(missing)
                print(f"  {f.name}: {len(missing)} handles assigned but not emitted")
        print(f"\n{len(files)} files, {lost_total} handles lost")
        print("PASS — every assigned handle survives" if not lost_total
              else "FAIL — run without --verify to repair a copy first")
        return 1 if lost_total else 0

    if len(args) < 2:
        print("need OUTDIR")
        return 2
    out = Path(args[1])
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for f in files:
        fixed, n = repair(f.read_text())
        (out / f.name).write_text(fixed)
        total += n
    print(f"  {len(files)} files -> {out}  ({total:,} blank lines removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

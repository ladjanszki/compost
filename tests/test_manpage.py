#!/usr/bin/env python3
"""
test_manpage.py — the man page cannot drift from the program.

v0.1.4 shipped a test with this name and the rewrite dropped it, leaving the
promise in `src/cli.py` that `docs/man-compost.md` is "kept honest by being
verified against this program". Nothing verified it, and the first thing to rot
was the count: the man page said five subcommands above a list of six, and
`CLAUDE.md` copied the five.

So the ground truth here is the **dispatcher**, not the text of `USAGE`. Every
name is offered to `cli.main` in a scratch directory and has to be routed
somewhere; a name the program rejects is not a subcommand no matter what any
document claims. The man page is then held against that set, in both directions,
down to the number spelled out in prose.
"""
import contextlib
import io
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli  # noqa: E402

MAN = Path(__file__).parent.parent / "docs/man-compost.md"
NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
           7: "seven", 8: "eight", 9: "nine", 10: "ten"}

# Aliases the dispatcher answers to that are not subcommands. Listed here rather
# than discovered, because there is no way to tell a flag from a typo by probing.
ALIASES = ["-h", "--help", "help", "-V", "--version"]


def usage_names():
    """The subcommand column of cli.USAGE — one word at the start of a line."""
    body = cli.USAGE.split("\n\n", 1)[1]
    return [m.group(1) for line in body.splitlines()
            if (m := re.match(r"  ([a-z]+)\b", line))]


def routed(name):
    """True if the dispatcher routes `name` somewhere rather than rejecting it.

    Run in a scratch cwd because `init` is real: it would otherwise make a base
    in whatever directory the suite happened to start in.
    """
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        here = Path.cwd()
        os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    cli.main(["compost", name])
                except SystemExit:
                    raise
                except Exception:
                    pass          # it errored, but the dispatcher did route it
        finally:
            os.chdir(here)
    return "unknown command" not in out.getvalue()


def section_names(man):
    """Subcommand headings under SUBCOMMANDS: `### import FILE...` -> import."""
    body = man.split("## SUBCOMMANDS", 1)[1].split("\n## ", 1)[0]
    return [m.split()[0] for m in re.findall(r"^### (.+)$", body, re.M)]


def synopsis_names(man):
    block = re.search(r"## SYNOPSIS\n+```\n(.*?)```", man, re.S).group(1)
    return [line.split()[1] for line in block.splitlines()
            if line.startswith("compost ")]


def main():
    man = MAN.read_text()
    names = usage_names()
    problems = []

    def check(name, ok, detail=""):
        print(f"  {'ok   ' if ok else 'FAIL '} {name:<46} {detail}")
        if not ok:
            problems.append(name)

    unrouted = [n for n in names if not routed(n)]
    check("every name in USAGE is a real subcommand",
          not unrouted, ", ".join(unrouted))

    missing = [n for n in names if n not in synopsis_names(man)]
    check("SYNOPSIS lists every subcommand", not missing, ", ".join(missing))

    documented = section_names(man)
    undocumented = [n for n in names if n not in documented]
    check("every subcommand has a section", not undocumented,
          ", ".join(undocumented))

    invented = [n for n in documented if n not in names]
    check("the man page documents nothing the program lacks",
          not invented, ", ".join(invented))

    word = NUMBERS[len(names)]
    stated = re.search(r"The (\w+) subcommands below", man)
    check(f"STATUS says there are {word}",
          bool(stated) and stated.group(1) == word,
          f"says {stated.group(1)!r}" if stated else "sentence is gone")

    absent = [a for a in ALIASES if f"`{a}`" not in man]
    check("every alias the dispatcher accepts is in the man page",
          not absent, ", ".join(absent))

    total = 6
    print(f"\n{total - len(problems)}/{total} man-page guarantees hold")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

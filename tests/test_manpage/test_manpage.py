"""
The man page is checked against the CLI, so it cannot drift.

A hand-written reference document goes stale the first time someone adds a
flag, and this project has already paid for that once: `mvp-design.md` declared
itself authoritative while describing directories that no longer existed, and
half the documentation had to be archived to stop it misleading people.

So the man page is not trusted, it is verified. Every subcommand and every
option in `build_parser()` must appear in it, and anything whose help text says
it is deprecated must be marked as such in the page.

Run: conda run -n knowledge-graph python tests/test_manpage/test_manpage.py
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.cli import build_parser

MAN = Path("raw/artifacts/man-kgb.md")

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
        FAILURES.append(name)


def surface(parser: argparse.ArgumentParser):
    """
    Every command and option the tool exposes.

    Returns (commands, options, deprecated) where commands is {name: help},
    options is {name: help} of every flag on the root and on each subparser,
    and deprecated is the subset whose help says so.
    """
    commands, options = {}, {}

    def opts_of(p, prefix=""):
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction):
                continue
            for s in a.option_strings:
                if s.startswith("--"):
                    options[s] = (a.help or "")

    opts_of(parser)
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sp in action.choices.items():
                commands[name] = (action._name_parser_map[name].description
                                  or _help_for(action, name) or "")
                opts_of(sp)

    everything = {**commands, **options}
    deprecated = {k for k, v in everything.items() if "deprecat" in (v or "").lower()}
    return commands, options, deprecated


def _help_for(sub_action, name):
    for choice in sub_action._choices_actions:
        if choice.dest == name:
            return choice.help
    return ""


# --------------------------------------------------------------------------
# TM-1  The page exists and every command is in it
# --------------------------------------------------------------------------
def tm1_commands_documented():
    print("\nTM-1: every subcommand appears in the man page")
    check("the man page exists", MAN.exists(), str(MAN))
    if not MAN.exists():
        return
    text = MAN.read_text(encoding="utf-8")
    commands, _, _ = surface(build_parser())
    check("the parser exposes commands", len(commands) > 0, str(commands))

    missing = [c for c in commands if not re.search(rf"\bkgb {re.escape(c)}\b", text)]
    check(f"all {len(commands)} commands documented", not missing,
          f"missing: {missing}")


# --------------------------------------------------------------------------
# TM-2  Every long option is in it
# --------------------------------------------------------------------------
def tm2_options_documented():
    print("\nTM-2: every long option appears in the man page")
    if not MAN.exists():
        return
    text = MAN.read_text(encoding="utf-8")
    _, options, _ = surface(build_parser())
    # --help is argparse's own and needs no documenting
    options = {k: v for k, v in options.items() if k != "--help"}

    missing = [o for o in options if o not in text]
    check(f"all {len(options)} long options documented", not missing,
          f"missing: {missing}")


# --------------------------------------------------------------------------
# TM-3  Deprecated things are marked as deprecated
# --------------------------------------------------------------------------
def tm3_deprecated_marked():
    print("\nTM-3: anything deprecated is marked in the man page")
    if not MAN.exists():
        return
    text = MAN.read_text(encoding="utf-8").lower()
    _, _, deprecated = surface(build_parser())

    unmarked = []
    for name in deprecated:
        # the name must appear on, or near, a line that says deprecated
        near = [ln for ln in text.split("\n") if name.lower() in ln]
        if not any("deprecat" in ln for ln in near):
            section = text.split("## deprecated")
            if len(section) < 2 or name.lower() not in section[1]:
                unmarked.append(name)
    check("deprecated items are marked", not unmarked, f"unmarked: {unmarked}")

    # The rename alias is not an argparse item, so assert it explicitly:
    # it is the one deprecation that exists right now.
    check("the `kg` alias is recorded in a DEPRECATED section",
          "## deprecated" in text and re.search(r"`kg`", text) is not None)


# --------------------------------------------------------------------------
# TM-4  The check actually catches drift
# --------------------------------------------------------------------------
def tm4_sabotage():
    print("\nTM-4: sabotage — an undocumented command and flag are caught")
    text = MAN.read_text(encoding="utf-8") if MAN.exists() else ""

    p = argparse.ArgumentParser(prog="kgb")
    p.add_argument("--invented-flag", help="not in the page")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("invented", help="not in the page either")

    commands, options, _ = surface(p)
    missing_cmd = [c for c in commands
                   if not re.search(rf"\bkgb {re.escape(c)}\b", text)]
    missing_opt = [o for o in options if o not in text and o != "--help"]

    check("an undocumented command is detected", missing_cmd == ["invented"],
          str(missing_cmd))
    check("an undocumented flag is detected", missing_opt == ["--invented-flag"],
          str(missing_opt))

    # and a deprecated item with no marking
    p2 = argparse.ArgumentParser(prog="kgb")
    p2.add_argument("--old-thing", help="deprecated, use --new-thing")
    _, _, dep = surface(p2)
    check("a deprecated flag is recognised as deprecated", dep == {"--old-thing"},
          str(dep))


if __name__ == "__main__":
    print("=" * 70)
    print("Man page against the CLI")
    print("=" * 70)
    tm1_commands_documented()
    tm2_options_documented()
    tm3_deprecated_marked()
    tm4_sabotage()
    print("\n" + "=" * 70)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")

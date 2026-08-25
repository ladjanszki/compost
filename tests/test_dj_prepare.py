#!/usr/bin/env python3
"""
test_dj_prepare.py — the v0.1 list-item handle survives pandoc.

`pandoc -f djot` drops a block attribute at the start of a list item when a
blank line separates it from the content. Property 1 asserts the defect itself,
against the live pandoc, because everything else here exists only to work
around it: the day a pandoc release fixes it, property 1 fails and tells us the
repair can be retired rather than leaving it applied forever for no reason.

The rest assert that the repair is *narrow* — it removes blank lines and does
nothing else. A preprocessing step that quietly altered prose would be the
textual pass this project forbids, applied to the one corpus that quotes its
own syntax constantly.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools import dj_prepare as P     # noqa: E402

LOOSE = """- {#aaaaaaa1}

  A paragraph inside a list item.

- {#aaaaaaa2}

  Second item.
"""

FENCED = """```
- {#bbbbbbb1}

  Quoted example, must not be touched.
```
"""

MIXED = """{#ccccccc1}
A top-level paragraph.

- {#ccccccc2}

  In a list.

Citing them: \\{#ccccccc1\\} and \\{#ccccccc2\\}.
"""


def _ids(text: str) -> set:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.dj"
        p.write_text(text)
        return P.emitted(p)


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    def defect_is_real():
        # If this ever passes, pandoc fixed it and dj_prepare can be retired.
        got = _ids(LOOSE)
        v = subprocess.run(["pandoc", "--version"], capture_output=True,
                           text=True).stdout.split("\n")[0]
        return not got, f"{v}: emits {sorted(got) or 'no ids'} for 2 handles"
    case("pandoc still drops a list item's leading attribute", defect_is_real)

    def repair_recovers_them():
        fixed, n = P.repair(LOOSE)
        return (_ids(fixed) == {"aaaaaaa1", "aaaaaaa2"} and n == 2,
                f"{n} blank lines removed, ids {sorted(_ids(fixed))}")
    case("after the repair both handles survive", repair_recovers_them)

    def only_blank_lines_go():
        fixed, _ = P.repair(LOOSE)
        before = [l for l in LOOSE.split("\n") if l.strip()]
        after = [l for l in fixed.split("\n") if l.strip()]
        return before == after, f"{len(before)} non-blank lines, identical: {before == after}"
    case("every non-blank line is byte-identical", only_blank_lines_go)

    def fences_untouched():
        fixed, n = P.repair(FENCED)
        return fixed == FENCED and n == 0, f"{n} removals inside a fence"
    case("a handle quoted inside a fence is not touched", fences_untouched)

    def idempotent():
        once, a = P.repair(MIXED)
        twice, b = P.repair(once)
        return once == twice and b == 0, f"second pass removed {b}"
    case("the repair is idempotent", idempotent)

    def one_blank_line_only():
        text = "- {#ddddddd1}\n\n\n  Two blank lines above.\n"
        fixed, n = P.repair(text)
        return (n == 1 and "\n\n  Two blank" in fixed,
                f"{n} removed, one blank line kept")
    case("exactly one blank line is removed, never a run", one_blank_line_only)

    def escaped_is_not_an_assignment():
        # `\{#x\}` is how the canonizer wrote a citation. Counting it as an
        # assignment would make the migration mint a self-citation.
        a = P.assigned("Citing \\{#eeeeeee1\\} here.\n{#eeeeeee2}\ncontent\n")
        return a == {"eeeeeee2"}, f"assigned={sorted(a)}"
    case("an escaped handle is a citation, not an assignment",
         escaped_is_not_an_assignment)

    def verify_agrees_end_to_end():
        fixed, _ = P.repair(MIXED)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.dj"
            p.write_text(MIXED)
            before = P.assigned(MIXED) - P.emitted(p)
            p.write_text(fixed)
            after = P.assigned(fixed) - P.emitted(p)
        return (before and not after,
                f"{len(before)} lost before, {len(after)} after")
    case("assigned-minus-emitted goes to empty", verify_agrees_end_to_end)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} dj_prepare guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

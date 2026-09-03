#!/usr/bin/env python3
"""
build_whitepaper.py — regenerate docs/compost.md's grammar appendix.

    python3 -m tools.build_whitepaper

Reads `tools/record-schema-1.json`, renders it through
`tools/schema_tables.py`, and replaces everything between two markers in
`docs/compost.md` with the result. Nothing else in the file is touched.

**The appendix is generated, never hand-edited.** Running this twice leaves
the file byte-identical the second time — the tables are rendered fresh from
the schema on every call and nothing about that output depends on what was
there before. `tests/test_grammar.py` asserts both halves of this: that the
committed file already holds exactly what a fresh render produces, and that
running the build again does not change it.

Not a subcommand, the same way `tools/v01_dictionary.py` is not one: a
whitepaper build touches a file under `docs/`, which is prose a person edits
by hand everywhere except between these two markers, and `compost` has no
business writing to `docs/`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import schema_tables as ST   # noqa: E402

WHITEPAPER = Path(__file__).resolve().parent.parent / "docs" / "compost.md"
BEGIN = "<!-- BEGIN GENERATED: tools/schema_tables.py -->"
END = "<!-- END GENERATED -->"


def build(whitepaper: Path = WHITEPAPER,
          schema_path: Path = ST.SCHEMA_PATH) -> bool:
    """Regenerate the appendix in place. Returns True if the file changed."""
    text = whitepaper.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise RuntimeError(
            f"{whitepaper}: markers not found — expected {BEGIN!r} and "
            f"{END!r}")
    pre, rest = text.split(BEGIN, 1)
    _, post = rest.split(END, 1)
    body = ST.render(ST.load_schema(schema_path))
    new_text = f"{pre}{BEGIN}\n\n{body}\n\n{END}{post}"
    changed = new_text != text
    whitepaper.write_text(new_text, encoding="utf-8")
    return changed


def main():
    changed = build()
    print(f"{WHITEPAPER}: appendix {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

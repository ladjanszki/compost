"""
Inline reconstruction tests: nothing the author typed may be silently dropped.

The defect this suite exists for: djot has smart punctuation in its spec, so
`---` in a source file *means* an em dash. Pandoc writes it that way correctly.
`inline_reconstruct` had no branch for djot's `smart_punctuation` node and its
fallback emitted nothing, so every em dash, en dash and ellipsis in the corpus
was deleted from the stored text. `readme.dj`'s own title read
"kg  conversations to an addressable wiki".

The branch is the small half of the fix. The large half is that a missing
branch now raises: the same silence dropped task lists and swallowed a div's
children before this, which is three bugs from one cause.

Run: conda run -n knowledge-graph python tests/test_inlines/test_inlines.py
"""
import glob
import sys

sys.path.insert(0, ".")

from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text
from src.ingest import inline_reconstruct
from src.ingest.inline_reconstruct import reconstruct

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
        FAILURES.append(name)


def text_of(djot: str) -> str:
    """The reconstructed text of the first block."""
    return walk(get_ast_from_text(djot))[0]["content"]["text"]


# --------------------------------------------------------------------------
# TI-1  Smart punctuation survives, and stays distinct from a literal
# --------------------------------------------------------------------------
def ti1_smart_punctuation_survives():
    print("\nTI-1: smart punctuation reaches the stored text")

    check("em dash", text_of("An em dash --- here.\n") == "An em dash — here.",
          text_of("An em dash --- here.\n"))
    check("en dash", text_of("An en dash -- here.\n") == "An en dash – here.",
          text_of("An en dash -- here.\n"))
    check("ellipsis", text_of("An ellipsis ... here.\n") == "An ellipsis … here.",
          text_of("An ellipsis ... here.\n"))

    # The whole point of resolving rather than echoing the source spelling: an
    # em dash and three literal hyphens must not collapse to the same text.
    em = text_of("An em dash --- here.\n")
    literal = text_of("Three \\-\\-- here.\n")
    check("an em dash and a literal --- are distinguishable",
          "—" in em and "—" not in literal,
          f"em={em!r} literal={literal!r}")


# --------------------------------------------------------------------------
# TI-2  Autolinks are not dropped
# --------------------------------------------------------------------------
def ti2_url_survives():
    print("\nTI-2: a bare autolink survives")
    t = text_of("See <https://example.com/x> here.\n")
    check("url", "https://example.com/x" in t, t)


# --------------------------------------------------------------------------
# TI-3  An unknown tag raises rather than emitting nothing
# --------------------------------------------------------------------------
def ti3_unknown_tag_raises():
    print("\nTI-3: an unrecognised inline raises")

    try:
        reconstruct([{"tag": "not_a_real_djot_inline", "text": "x"}])
        check("unknown inline raises", False, "it returned instead")
    except ValueError as e:
        check("unknown inline raises", "no branch" in str(e), str(e))

    # A container is the dangerous case: emitting nothing loses the children,
    # not just the wrapper.
    try:
        reconstruct([{"tag": "not_a_real_container",
                      "children": [{"tag": "str", "text": "lost"}]}])
        check("unknown container raises", False, "it returned instead")
    except ValueError as e:
        check("unknown container raises", "no branch" in str(e), str(e))

    try:
        reconstruct([{"tag": "smart_punctuation", "type": "invented", "text": "?"}])
        check("unknown smart_punctuation type raises", False, "it returned instead")
    except ValueError as e:
        check("unknown smart_punctuation type raises",
              "smart_punctuation" in str(e), str(e))


# --------------------------------------------------------------------------
# TI-4  The whole corpus parses with no unhandled tag
# --------------------------------------------------------------------------
def ti4_corpus_is_fully_handled():
    print("\nTI-4: every tag in the corpus has a branch")
    files = sorted(glob.glob("artifacts/*.dj") + glob.glob("conversations/*.dj"))
    check("there is a corpus to test against", len(files) > 0, f"{len(files)} files")

    failed = []
    for f in files:
        try:
            walk(get_ast_from_text(open(f).read()))
        except ValueError as e:
            failed.append(f"{f}: {e}")
    check(f"all {len(files)} files walk without an unhandled tag",
          not failed, "\n          ".join(failed[:5]))


# --------------------------------------------------------------------------
# TI-5  Sabotage: removing the branch must fail the suite
# --------------------------------------------------------------------------
def ti5_sabotage():
    print("\nTI-5: sabotage — deleting the smart_punctuation table is caught")

    saved = dict(inline_reconstruct.SMART_PUNCTUATION)
    inline_reconstruct.SMART_PUNCTUATION.clear()
    try:
        text_of("An em dash --- here.\n")
        caught = False
    except ValueError:
        caught = True
    finally:
        inline_reconstruct.SMART_PUNCTUATION.update(saved)

    check("an em dash with no table entry raises rather than vanishing", caught,
          "the em dash was dropped silently, which is the original bug")

    check("the table is restored",
          inline_reconstruct.SMART_PUNCTUATION == saved)


if __name__ == "__main__":
    print("=" * 70)
    print("Inline reconstruction")
    print("=" * 70)
    ti1_smart_punctuation_survives()
    ti2_url_survives()
    ti3_unknown_tag_raises()
    ti4_corpus_is_fully_handled()
    ti5_sabotage()
    print("\n" + "=" * 70)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")

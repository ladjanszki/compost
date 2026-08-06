"""
Conversations: turns appended into one file, without disturbing what is there.

A conversation file changes; the blocks inside it must not. That is what makes
appending safe and keeps every reference resolvable, so it is checked directly
rather than assumed.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import store as store_mod
from src import conversation as conv
from src.conversation import AppendError, append_turn, infer_conversation
from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        FAILURES.append(name)
        if detail:
            print(f"          {detail}")


def blocks_of(path: Path) -> list:
    return walk(get_ast_from_text(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# TC-1  Appending never disturbs what is already written
#
# The failure this guards is silent: a turn ending in a list and a turn
# starting with one parse as a single list when concatenated naively, which
# reparents the second turn's items under the first. Nothing errors; the file
# is simply wrong, permanently, and every reference into it is wrong too.
# --------------------------------------------------------------------------
def tc1_append_preserves_earlier_turns():
    print("\nTC-1: appending leaves earlier turns untouched")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "conv.dj"
        append_turn(path, "- turn one item a\n- turn one item b\n", "human")
        first = blocks_of(path)
        first_ids = [b["id"] for b in first]

        append_turn(path, "- turn two item a\n", "claude")
        after = blocks_of(path)

        check("earlier blocks keep their handles",
              [b["id"] for b in after][:len(first)] == first_ids)
        check("earlier blocks keep their text",
              [b["content"].get("text") for b in after][:len(first)]
              == [b["content"].get("text") for b in first])

        # The seam: turn one's items must not have absorbed turn two's.
        turn_one = next(b for b in after if b["type"] == "div")
        check("the first turn still contains only its own blocks",
              turn_one["content"]["contains"] == len(first) - 1,
              f'contains={turn_one["content"]["contains"]}, expected {len(first) - 1}')

        divs = [b for b in after if b["type"] == "div"]
        check("each turn is its own fenced div", len(divs) == 2, len(divs))

        check("turn two's items did not become children of turn one",
              all(b["content"].get("depth", 0) == 0
                  for b in after if b["type"] == "list_item"),
              [(b["content"].get("text"), b["content"].get("depth"))
               for b in after if b["type"] == "list_item"])


# --------------------------------------------------------------------------
# TC-1b  A corrupting append is refused, not written
#
# The verifier is the guarantee, so it is checked against a forced failure:
# append content that would merge with what is already there and confirm the
# file on disk is left exactly as it was.
# --------------------------------------------------------------------------
def tc1b_corrupting_append_is_refused():
    print("\nTC-1b: an append that would disturb earlier blocks is refused")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "conv.dj"

        # Remove both defences — the fence and the blank line — to reach the
        # measured failure: a paragraph appended tight after a heading section
        # is merged into the *previous* paragraph, so an already-referenced
        # block's text silently grows. Both turns must be unfenced, or the
        # closing ::: of the first one prevents the merge on its own.
        orig_wrap, orig_sep = conv.wrap_turn, conv.SEPARATOR
        conv.wrap_turn = lambda djot, author, turn_id: djot.strip() + "\n"
        conv.SEPARATOR = "\n"
        try:
            append_turn(path, "# A heading\n\nUnder it.\n", "human")
            before = path.read_text(encoding="utf-8")
            n_before = len(blocks_of(path))
            append_turn(path, "New turn text.\n", "claude")
            check("a corrupting append raises rather than writing", False,
                  "append_turn returned normally")
        except AppendError:
            check("a corrupting append raises rather than writing", True)
        finally:
            conv.wrap_turn, conv.SEPARATOR = orig_wrap, orig_sep

        check("the file on disk is untouched after a refusal",
              path.read_text(encoding="utf-8") == before)
        check("no blocks were lost", len(blocks_of(path)) == n_before)


# --------------------------------------------------------------------------
# TC-2  Authorship survives into the file
# --------------------------------------------------------------------------
def tc2_authorship_is_recorded():
    print("\nTC-2: authorship is recorded per turn, in the djot")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "conv.dj"
        append_turn(path, "A human thought.\n", "human")
        append_turn(path, "An agent reply.\n", "claude")

        authors = [b["content"].get("attrs", {}).get("author")
                   for b in blocks_of(path) if b["type"] == "div"]
        check("both turns carry an author", authors == ["human", "claude"], authors)
        check("authorship lives in the file, not a sidecar",
              'author="claude"' in path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# TC-3  Blocks inside a turn stay addressable
#
# The turn fence is a div, and a div used to swallow its children. If that
# regresses, every block of every turn becomes unreferenceable.
# --------------------------------------------------------------------------
def tc3_turn_content_is_addressable():
    print("\nTC-3: every block inside a turn is addressable")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "conv.dj"
        _, added = append_turn(
            path, "# A heading\n\nA paragraph.\n\n- an item\n", "human")
        blocks = blocks_of(path)
        types = [b["type"] for b in blocks]

        check("the turn's blocks reach the block list",
              {"heading", "paragraph", "list_item"} <= set(types), types)
        check("every block has a handle", all(b.get("id") for b in blocks),
              [b["type"] for b in blocks if not b.get("id")])
        # A turn div's handle is followed by its other attributes rather than a
        # closing brace, so match either.
        written = re.findall(r"(?<!\\)\{#([0-9a-f]{8})[ }]",
                             path.read_text(encoding="utf-8"))
        check("no handle is written that the block list does not know about",
              sorted(written) == sorted(b["id"] for b in blocks),
              f"{len(written)} written, {len(blocks)} blocks")
        check("the caller is told which blocks landed",
              len(added) == len(blocks), f"{len(added)} vs {len(blocks)}")


# --------------------------------------------------------------------------
# TC-4  The thread is inferred from what a draft cites
#
# You reply by clicking a block, so requiring a separate conversation handle
# would be a second thing to copy for no information gain.
# --------------------------------------------------------------------------
def tc4_thread_is_inferred_from_citations():
    print("\nTC-4: the conversation is inferred from the blocks cited")
    with tempfile.TemporaryDirectory() as tmp:
        st = store_mod.init(Path(tmp) / "kb")
        a = st.conversations / "019fcc00-0000-7000-8000-000000000001.dj"
        b = st.conversations / "019fcc00-0000-7000-8000-000000000002.dj"
        append_turn(a, "The block worth answering.\n", "human")
        append_turn(b, "An unrelated thread.\n", "human")

        target = blocks_of(a)[1]["id"]
        check("a draft citing a block resolves to its conversation",
              infer_conversation(st, f"Answering {{#{target}}} now.\n") == a.stem)
        check("a draft citing nothing starts a new conversation",
              infer_conversation(st, "A fresh thought.\n") is None)

        both = f"Comparing {{#{target}}} with {{#{blocks_of(b)[1]['id']}}}.\n"
        try:
            infer_conversation(st, both)
            check("citing two conversations is refused, not guessed", False)
        except AppendError:
            check("citing two conversations is refused, not guessed", True)


def main():
    tc1_append_preserves_earlier_turns()
    tc1b_corrupting_append_is_refused()
    tc2_authorship_is_recorded()
    tc3_turn_content_is_addressable()
    tc4_thread_is_inferred_from_citations()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        sys.exit(1)
    print("All conversation checks PASSED.")


if __name__ == "__main__":
    main()

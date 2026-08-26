#!/usr/bin/env python3
"""
test_loop.py — the two traps `tools/loop.py` exists to avoid.

`docs/roadmap.md`, v0.2.6, "the loop, end to end", names them explicitly:

1. **The round filename must be unique per round.** `view_names()`
   (`src/views.py:372-375`) breaks a stem collision by appending the root's
   handle to *both* documents, so a second round reusing one name silently
   renames the first round's view out from under whatever URL was already
   open.
2. **`digest`'s printed `root <8 hex>` is a display prefix, not a guid.** The
   loop needs the whole thing for the next round's `responds_to`, and there is
   no machine-readable surface for it — `root_of()` reads it back out of the
   graph file `_digest` just wrote.

Property 1 below reproduces the trap directly (two documents sharing a stem,
through the ordinary `notes` route) so the claim about `view_names()` is
checked against the code rather than quoted from the roadmap. The rest exercise
`tools/loop.py` end to end with a stubbed `ask`, so a round costs no API call.
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R      # noqa: E402
from src import store as S        # noqa: E402
from src import views as V        # noqa: E402
from tools import loop as L       # noqa: E402

FAKE_ROOT = "deadbeef-0000-0000-0000-000000000000"


def _ask(text: str) -> dict:
    """A canned envelope, standing in for `claude --print`."""
    return {
        "is_error": False, "duration_api_ms": 1, "num_turns": 1,
        "stop_reason": "end_turn", "session_id": "loop-test",
        "total_cost_usd": 0.0, "usage": {"input_tokens": len(text)},
        "modelUsage": {}, "permission_denials": [], "terminal_reason": "completed",
        "fast_mode_state": "off", "fast_mode_disabled_reason": "n/a",
        "subtype": "success", "api_error_status": None,
        "result": "An answer paragraph.\n",
        "ttft_ms": 1, "ttft_stream_ms": 1, "time_to_request_ms": 1,
        "type": "result", "duration_ms": 1,
        "uuid": "11111111-1111-4111-8111-111111111111",
    }


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        def round_names_never_collide():
            names = {L.round_name() for _ in range(2000)}
            return len(names) == 2000, f"{len(names)} of 2000 calls, all distinct"
        case("round_name() cannot repeat", round_names_never_collide)

        def the_collision_trap_is_real():
            # Reproduces the exact mechanism `round_name()` exists to dodge:
            # two documents digested under the SAME stem, through the plain
            # `notes` route — `view_names()` must give both a suffixed name
            # rather than let the second overwrite the first.
            st = S.Store.init(tmp / "collide")
            a = tmp / "same-stem-source"
            a.mkdir()
            f1 = a / "round.md"
            f1.write_text("First round.\n")
            with contextlib.redirect_stdout(io.StringIO()):
                S._digest(st, "notes", [str(f1)], "compost")
            f1.write_text("Second round.\n")   # a fresh mint, same basename
            with contextlib.redirect_stdout(io.StringIO()):
                S._digest(st, "notes", [str(f1)], "compost")
            recs, _ = st.load()
            docs = [r for r in recs if r["record"] == "node"
                    and r["type"] in R.ROOT_TYPES]
            names = V.view_names(docs)
            stems = set(names.values())
            return (len(docs) == 2 and len(stems) == 2
                    and not any(s == "round" for s in stems),
                    f"{len(docs)} docs sharing a source stem, resolved to "
                    f"{sorted(stems)} — neither is the bare stem")
        case("a reused filename would collide (the trap, reproduced)",
             the_collision_trap_is_real)

        st = S.Store.init(tmp / "base")

        def digest_one_returns_the_written_guid():
            note = tmp / "note-x.md"
            note.write_text("A note.\n")
            with contextlib.redirect_stdout(io.StringIO()):
                root = L.digest_one(st, note, "notes")
            recs, _ = st.load()
            found = [r["guid"] for r in recs if r["record"] == "node"
                    and r["type"] in R.ROOT_TYPES
                    and R._p(r, "source") == "note-x.md"]
            return (len(found) == 1 and found[0] == root,
                    f"digest_one returned {root}, base holds {found}")
        case("digest_one returns the whole guid actually written",
             digest_one_returns_the_written_guid)

        def root_of_raises_when_absent():
            note = tmp / "note-y.md"
            note.write_text("Another note.\n")
            before = set(st.files())
            with contextlib.redirect_stdout(io.StringIO()):
                S._digest(st, "notes", [str(note)], "compost")
            new = (set(st.files()) - before).pop()
            try:
                L.root_of(new, "wrong-name.md")
                return False, "did not raise for a source name not in the file"
            except RuntimeError:
                return True, "raises rather than guessing"
        case("root_of refuses to guess a guid for the wrong source",
             root_of_raises_when_absent)

        def a_wrong_root_breaks_the_next_digest():
            # SABOTAGE. If `root_of` returned the wrong guid, the response
            # route's `responds_to` would name something nobody minted, and
            # `store._digest`'s structural guid check (docs/roadmap.md, item
            # 3) refuses it — this is what proves getting the whole guid
            # right, not just *a* guid, is load-bearing for the loop.
            real = L.root_of
            L.root_of = lambda graph_file, source_name: FAKE_ROOT
            try:
                st2 = S.Store.init(tmp / "wrongroot")
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        L.run_round(st2, "A note for the wrong-root case.\n",
                                   ask=_ask, scratch=tmp)
                    ran = True
                except RuntimeError:
                    ran = False
            finally:
                L.root_of = real
            return (not ran,
                    "run_round fails rather than silently mis-wiring the "
                    "conversation when root_of answers the wrong guid")
        case("a wrong root_of breaks the loop rather than mis-wiring it "
             "(sabotaged)", a_wrong_root_breaks_the_next_digest)

        def run_round_end_to_end():
            st3 = S.Store.init(tmp / "round")
            with contextlib.redirect_stdout(io.StringIO()):
                note_root, resp_root = L.run_round(
                    st3, "The note for this round.\n", ask=_ask, scratch=tmp)
            recs, _ = st3.load()
            nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
            has_responds = any(
                e["record"] == "edge" and e["type"] == "responds_to"
                and e["source"] == resp_root and e["destination"] == note_root
                for e in recs)
            has_next = any(
                e["record"] == "edge" and e["type"] == "next"
                and e["layer"] == "conversation"
                and e["source"] == note_root and e["destination"] == resp_root
                for e in recs)
            return (note_root in nodes and resp_root in nodes
                    and has_responds and has_next and not R.check(recs),
                    f"note {note_root[:8]}, response {resp_root[:8]}, "
                    f"responds_to: {has_responds}, next: {has_next}, "
                    f"check: {len(R.check(recs))} problems")
        case("run_round wires one full round, check clean", run_round_end_to_end)

        def two_rounds_do_not_collide():
            st4 = S.Store.init(tmp / "tworounds")
            with contextlib.redirect_stdout(io.StringIO()):
                n1, r1 = L.run_round(st4, "Round one.\n", ask=_ask, scratch=tmp)
                n2, r2 = L.run_round(st4, "Round two.\n", ask=_ask, scratch=tmp)
            guids = {n1, r1, n2, r2}
            recs, _ = st4.load()
            return (len(guids) == 4 and not R.check(recs),
                    f"{len(guids)} distinct roots across two rounds, "
                    f"{len(R.check(recs))} check problems")
        case("consecutive rounds never collide", two_rounds_do_not_collide)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} loop guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

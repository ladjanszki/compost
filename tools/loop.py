#!/usr/bin/env python3
"""
loop.py — one round of `nvim -> compost -> claude -> compost`.

**Not a subcommand and will not become one** — see `docs/decisions.md`,
"Anything may write records", and `docs/roadmap.md`, v0.2.6, "the loop, end to
end". This is that shell pipeline turned into one importable function, because
two of its eight steps are traps rather than plumbing and getting them wrong
fails in a way that is easy to miss:

**The round filename must be unique per round.** `view_names()`
(`src/views.py:372-375`) breaks a stem collision by appending the root's own
handle to *both* documents, so reusing one name does not overwrite the first
round's view — it silently renames it out from under whatever URL was already
open, and the second round's `cat` of the guessed stem then reads a file that
is no longer there. `date +%s` is one-second resolution and this loop can run
faster than that; `round_name()` mints a uuid instead, which cannot repeat in
any way that matters.

**`digest`'s printed `root <8 hex>` is a display prefix, not a guid.** The
wrapper needs the whole thing to put in the next round's `responds_to`, and
`digest` has no machine-readable output for it — so `root_of()` reads it back
out of the graph file `_digest` just wrote, which is the file `digest_one()`
finds by diffing `st.files()` before and after. That needs no new surface on
`digest` itself, at the cost of this module knowing the graph is `*.jsonl`
under `graph/` — which it already has to know to be a caller of `Store` at
all.

    python3 -m tools.loop "the note's text" [BASE_DIR]

Real use calls `claude --print --output-format json` for real, through
`_ask_claude`. A caller that wants to test the plumbing without paying for an
API call passes its own `ask` to `run_round` instead — see
`tests/test_response.py`.
"""
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import layers as L      # noqa: E402
from src import records as R     # noqa: E402
from src import store as S       # noqa: E402
from src import views as V       # noqa: E402


def round_name(prefix: str = "round", ext: str = "md") -> str:
    """A filename no round can collide with, unlike `date +%s`.

    `ext` is not cosmetic: `storage/` keeps every source under `GUID.EXT`
    (`store._digest`), so the wrapper's suffix is what the archived bytes are
    named with. A JSON wrapper stored as `.md` would make the one directory
    that is meant to be the honest record of what arrived lie about it.
    """
    return f"{prefix}-{uuid.uuid4().hex}.{ext}"


def root_of(graph_file: Path, source_name: str) -> str:
    """The whole guid of the root `_digest` just wrote for `source_name`.

    `_digest`'s own summary line truncates to `root <8 hex>` for a human to
    read in a terminal, which is not a citation — a handle is the whole guid
    (`docs/record-grammar.md` §2). This reads the same record `digest` itself
    just wrote to `graph_file`, rather than re-deriving the guid some other
    way that could drift from what was actually written.
    """
    for rec in R.from_jsonl(graph_file.read_text(encoding="utf-8")):
        if (rec["record"] == "node" and rec["type"] in R.ROOT_TYPES
                and rec.get("params", {}).get("source") == source_name):
            return rec["guid"]
    raise RuntimeError(f"no root for {source_name!r} in {graph_file}")


def digest_one(st: S.Store, path: Path, route: str) -> str:
    """`compost digest --as=<route>` on one file, returning the root's whole
    guid.

    `notes` and `claude-code-response` both name no referrals (`src/routes.py`
    `ROUTES`), so exactly one graph file is written per call — the set
    difference below is never more than one file, and `root_of` is handed
    exactly the file this call produced rather than an older one that happens
    to share a source name.
    """
    before = set(st.files())
    if S._digest(st, route, [str(path)], "compost") != 0:
        raise RuntimeError(f"digest failed for {path}")
    new = set(st.files()) - before
    if len(new) != 1:
        raise RuntimeError(
            f"expected exactly one new graph file, got {len(new)}")
    return root_of(new.pop(), path.name)


def _ask_claude(djot_text: str) -> dict:
    """The real seam: `claude --print --output-format json` over the note's
    rendered view. Not exercised by the test suite, which supplies its own
    `ask` — digesting a round should not cost an API call every run."""
    r = subprocess.run(["claude", "--print", "--output-format", "json"],
                       input=djot_text, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


def run_round(st: S.Store, note_text: str, ask=_ask_claude,
              scratch: Path | None = None,
              follows: str | None = None) -> tuple[str, str]:
    """One full round: a note in, a response out, both already cited.

    Mirrors `docs/roadmap.md`'s "the loop, end to end" one shell line at a
    time: write, digest, layer, render, ask, wrap, digest, layer, render.
    Returns `(note_root_guid, response_root_guid)`.

    `follows` is the previous round's response root, and passing it is what
    makes the conversation a chain instead of unconnected pairs — feed the
    second element of one call's result into the next call's `follows`. `None`
    for the first round of a conversation, which follows nothing.
    """
    scratch = scratch or st.root
    note_path = scratch / round_name()
    note_path.write_text(note_text, encoding="utf-8")

    note_root = digest_one(st, note_path, "notes")
    L.build(st, "citation", "uuid-link")
    V.render_all(st)

    view = st.views / "default-djot" / f"{note_path.stem}.dj"
    envelope = ask(view.read_text(encoding="utf-8"))

    wrapper_path = scratch / round_name("response", "json")
    wrapper = {"responds_to": note_root, "envelope": envelope}
    if follows is not None:
        wrapper["follows"] = follows
    wrapper_path.write_text(json.dumps(wrapper), encoding="utf-8")

    response_root = digest_one(st, wrapper_path, "claude-code-response")
    L.build(st, "citation", "uuid-link")
    V.render_all(st)

    return note_root, response_root


def main(argv):
    if len(argv) < 2:
        print("usage: python3 -m tools.loop NOTE_TEXT [BASE_DIR]")
        return 2
    try:
        st = S.Store.find(Path(argv[2]) if len(argv) > 2 else None)
    except S.NotABase as e:
        print(e)
        return 1
    note_root, response_root = run_round(st, argv[1])
    print(f"  note     {note_root}")
    print(f"  response {response_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

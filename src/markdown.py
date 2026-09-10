#!/usr/bin/env python3
"""
markdown.py — the one digestor for markdown text, file or fragment.

Through v0.2.13 there were two: `routes.py:_ast_of_text` for a
`claude-code-response`'s answer, and `session.py:_md_blocks` for a turn's
prose, reaching into `records._block` — a private function — to do what
`ast_to_records` already does publicly. Both ran the same pandoc invocation
with the same `READER`, so a change to one flag in one copy would have
silently diverged from the other. `docs/decisions.md` records every flag here
as load-bearing and measured; this module is now the only place `READER` is
defined, so there is exactly one invocation to keep honest.

`text_to_records` is the whole surface: markdown text that has no file of its
own — a response's `result`, a transcript turn's prose — in, `(records, root)`
out, same shape `ast_to_records` returns for a file. The caller decides what,
if anything, `params["source"]` on the root should say; this module never
sets one, because a fragment delegated out of a transcript has no filename at
all (docs/roadmap.md, "the recursion made explicit").
"""
import json
import subprocess
from pathlib import Path

from . import records as R

# The markdown dialect, and the three extensions that must stay off. Each one
# prevents a specific silent corruption and the measurements are in
# `docs/decisions.md`: `-attributes` keeps `{#...}` literal text instead of an
# anchor definition, `-smart` keeps `---` three hyphens, and `-fancy_lists`
# is what makes `+task_lists` actually apply. This is not a tunable, and this
# is the only place in `src/` it is defined — `routes.py` imports it rather
# than redefining it, so a file-based read and a text-based read can never
# quietly drift onto different dialects.
READER = "commonmark_x-smart-attributes-fancy_lists"

# The sectioning filter, v0.2.16: `make_sections` wraps every heading in a
# Div, and it does so through pandoc's own code rather than a rule compost
# authors and defends (docs/roadmap.md, "TA: revisions, and structure that
# means something"; `TODO-section-container.md`). Applied by both functions
# below, so a markdown-reading path can never sectionless one document and
# section another — see `ast_of_file`, the file-reading seam this release
# adds so there is exactly one place to apply it to a path, matching
# `_ast_of_text`'s one place for a fragment.
_FILTER = str(Path(__file__).resolve().parent / "make_sections.lua")


def _run(pandoc_args: list[str], input_text: str | None = None) -> dict:
    """The one pandoc invocation: same reader, same filter, stdin or a path.

    `ast_of_file` and `_ast_of_text` differ only in whether `pandoc_args`
    names a file or leaves stdin to carry the text — the dialect and the
    sectioning filter are identical either way, which is the whole of
    guarantee 6.
    """
    r = subprocess.run(
        ["pandoc", "-f", READER, "-t", "json", "--lua-filter", _FILTER,
         *pandoc_args],
        input=input_text, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


def _ast_of_text(text: str) -> dict:
    """Markdown text, with no file of its own, through pandoc's reader.

    `text` goes to pandoc on stdin rather than by path, because there is no
    file to name it with. Same reader, same three extensions disabled, same
    sectioning filter — the dialect must not depend on how the bytes arrived,
    or a citation link in a claude response would parse differently from the
    identical text in a note.
    """
    return _run([], input_text=text)


def ast_of_file(path) -> dict:
    """A file through pandoc's markdown reader, as a pandoc JSON document.

    The single file-reading seam markdown text takes, v0.2.16: through
    v0.2.15 this was `routes.py:_ast_of`, its own separate subprocess call
    with the same `READER` but no way to guarantee it stayed in step with
    `_ast_of_text` — two invocations meant the sectioning filter could be
    added to one and not the other, `TODO-section-container.md`'s "worst
    available outcome". `routes.py` now calls this instead of shelling out
    itself.

    The path is resolved before it is handed over, so it always begins with a
    slash. A relative name starting with a dash is otherwise read by pandoc as
    a flag — `-dash.md` becomes `-d ash.md`, i.e. `--defaults ash.md` — and the
    failure arrives as a confusing pandoc error about a file nobody named.
    """
    return _run([str(Path(path).resolve())])


def text_to_records(text: str, mint=None, route: str | None = None):
    """Markdown text -> `(records, root_guid)`, the same shape a file gives.

    No `source` is ever set on the root: this function has nothing to put
    there, and a caller with a real file (`routes.py:_notes`,
    `:_pandoc_ast`) uses `records.ast_to_records` directly instead, exactly
    as before. A caller with a *named but fileless* origin — the response
    route's answer text, a delegated transcript turn — sets `params["source"]`
    itself afterward if it has one to give, and re-stamps hashes; see
    `routes.py:_response`.
    """
    return R.ast_to_records(_ast_of_text(text), mint=mint, route=route)

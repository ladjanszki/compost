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


def _ast_of_text(text: str) -> dict:
    """Markdown text, with no file of its own, through pandoc's reader.

    `text` goes to pandoc on stdin rather than by path, because there is no
    file to name it with. Same reader, same three extensions disabled — the
    dialect must not depend on how the bytes arrived, or a citation link in a
    claude response would parse differently from the identical text in a
    note.
    """
    r = subprocess.run(["pandoc", "-f", READER, "-t", "json"],
                       input=text, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


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

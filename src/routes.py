#!/usr/bin/env python3
"""
routes.py — the named ways material enters a base.

Ingestion used to dispatch on the file extension: `*.jsonl` was a Claude Code
transcript and *everything else* was handed to pandoc as markdown. Two things
were wrong with that. The `else` was not "markdown", it was "anything at all",
so a PNG became a pandoc error rather than a compost one. And `.jsonl` is a
container, not a format — the moment a second kind of JSONL exists, the suffix
stops naming the reader.

So the reader is named, never inferred:

    compost digest --as=notes            notes.md
    compost digest --as=claude-code-transcript  019ff17b-....jsonl
    compost digest --as=pandoc-ast       manual.json

**No route may look at the suffix to decide anything.** A file called
`notes.jsonl` digested `--as=notes` is markdown, because that is what was
asked for. The extension survives into `storage/` as a decoration for whoever
pulls the bytes back out, and nothing reads it.

Each route is a function `(path, mint, route) -> (records, root_guid)`. It
parses and mints and does not touch the disk beyond reading its input, which
is what lets `digest` validate a whole batch before writing any of it.
"""
import json
import subprocess
from pathlib import Path

from . import records as R
from . import session as SESS

# The markdown dialect, and the three extensions that must stay off. Each one
# prevents a specific silent corruption and the measurements are in
# `docs/decisions.md`: `-attributes` keeps `{#...}` literal text instead of an
# anchor definition, `-smart` keeps `---` three hyphens, and `-fancy_lists`
# is what makes `+task_lists` actually apply. This is not a tunable.
READER = "commonmark_x-smart-attributes-fancy_lists"


def _ast_of(path: Path) -> dict:
    """A file through pandoc's markdown reader, as a pandoc JSON document.

    The path is resolved before it is handed over, so it always begins with a
    slash. A relative name starting with a dash is otherwise read by pandoc as
    a flag — `-dash.md` becomes `-d ash.md`, i.e. `--defaults ash.md` — and the
    failure arrives as a confusing pandoc error about a file nobody named.
    """
    r = subprocess.run(
        ["pandoc", "-f", READER, "-t", "json", str(Path(path).resolve())],
        capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


# -- the routes -------------------------------------------------------------

def _notes(path: Path, mint, route: str):
    """Prose, read as the one fixed markdown dialect above."""
    return R.ast_to_records(_ast_of(path), mint=mint,
                            source=path.name, route=route)


def _transcript(path: Path, mint, route: str):
    """A Claude Code session log: the whole JSONL, tool calls and all."""
    return SESS.session_to_records(path, mint=mint, route=route)


def _pandoc_ast(path: Path, mint, route: str):
    """
    A pandoc JSON document somebody else already produced.

    The narrowest route of the three, because there is no reading step in it
    to be wrong: `ast_to_records` takes exactly this shape. Whatever pandoc
    invocation produced the file stays outside the tool, where the person who
    wrote it can inspect and tune it — which is the point. What compost
    guarantees here is only that the AST it was handed became records
    faithfully, and that is the round-trip property.
    """
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"not JSON ({e}). Produce a pandoc JSON document "
                           f"with `pandoc -t json`.") from None
    if not isinstance(doc, dict) or "blocks" not in doc:
        raise RuntimeError(
            "not a pandoc JSON document: no 'blocks' key. "
            "Produce one with `pandoc -t json`.")
    return R.ast_to_records(doc, mint=mint, source=path.name, route=route)


# -- referrals: files a source says exist ------------------------------------
#
# A route may declare that the file it just read *names other files*. This is
# the one place `digest` reads something it was not handed, and it is allowed
# for exactly one reason: it is not a guess. A transcript that launched a
# subagent records that agent's id in its own log, the agent's turns are in a
# file named after that id, and the parent is *incomplete* without it — the
# output of that tool call is simply somewhere else.
#
# The distinction that makes this safe is between **following a reference** and
# **globbing a directory**. Globbing would be a guess about layout: everything
# here looks related, take it. Following a reference reads only what the file
# said to read, which is the same contract as digesting the file itself.

def _transcript_referrals(path: Path) -> list[Path]:
    """The sidechain transcripts this Claude Code log names.

    A subagent's id appears in `toolUseResult.agentId` on the line carrying the
    `Agent` call's result, and its turns are at `agent-<agentId>.jsonl`. Where
    that file sits depends on which side of the boundary we are on: a root
    session keeps its sidechains in `<session-id>/subagents/`, while a sidechain
    that spawned its own keeps them beside itself. `isSidechain` tells the two
    apart and is reliable — measured at 0 of 756 lines in a parent and 5 of 5
    in each sidechain.

    Missing files are skipped rather than raised. A transcript copied out of
    `~/.claude/projects` without its `subagents/` directory is a perfectly
    ordinary thing to digest, and refusing it would make the common case fail
    for the sake of the rare one. `digest` says which ones it could not find.
    """
    try:
        lines = [json.loads(l) for l in
                 path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    if any(d.get("isSidechain") for d in lines):
        base = path.parent                    # a sibling of this sidechain
    else:
        base = path.parent / path.stem / "subagents"
    out, seen = [], set()
    for d in lines:
        tur = d.get("toolUseResult")
        if not isinstance(tur, dict):
            continue
        aid = tur.get("agentId")
        if not isinstance(aid, str) or aid in seen:
            continue
        seen.add(aid)
        out.append(base / f"agent-{aid}.jsonl")
    return out


ROUTES = {
    "notes": (_notes, "prose, read as commonmark_x", None),
    "claude-code-transcript": (_transcript, "a Claude Code session *.jsonl",
                               _transcript_referrals),
    "pandoc-ast": (_pandoc_ast, "a pandoc JSON document, already parsed", None),
}


def referrals(route: str, path: Path) -> list[Path]:
    """Files `path` names, which digesting it should also bring in."""
    fn = ROUTES[route][2]
    return fn(Path(path)) if fn else []


def read(route: str, path: Path, mint=None):
    """Records and root guid for `path`, read as `route`."""
    fn = ROUTES[route][0]
    return fn(Path(path), mint, route)


def listing() -> str:
    w = max(len(n) for n in ROUTES)
    return "\n".join(
        f"  {n:<{w}}  {d}" + ("  (follows references)" if r else "")
        for n, (_, d, r) in ROUTES.items())

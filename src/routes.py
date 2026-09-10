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
import re
from pathlib import Path

from . import records as R
from . import session as SESS
from . import markdown as MD

# The markdown dialect and the sectioning filter both live in `markdown.py`
# now, as `MD.READER` and `MD.ast_of_file` — v0.2.16 collapsed what used to be
# a second pandoc invocation here (`_ast_of`, reading a file on this module's
# own subprocess call) into that one seam, so a file-based read and a
# text-based read can never quietly drift onto different dialects or apply
# `make_sections` to one and not the other (`TODO-section-container.md`'s
# "worst available outcome"; docs/roadmap.md, "TA", guarantee 6).


# -- the routes -------------------------------------------------------------

def _notes(path: Path, mint, route: str):
    """Prose, read as the one fixed markdown dialect above."""
    return R.ast_to_records(MD.ast_of_file(path), mint=mint,
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


# The layer for the two edges a response digest mints between document
# roots. Its own layer, the way `ingestion` and `agent` are their own layers:
# "this response answered that note" is a different kind of fact from either
# a document's structure or its bytes, and keeping it apart is what lets any
# one of the three be reasoned about alone.
CONVERSATION_LAYER = "conversation"


def _response(path: Path, mint, route: str):
    """
    A `claude --print --output-format json` envelope, answering an earlier
    document — docs/roadmap.md, "the conversation loop".

    The file is not the bare envelope but a one-key wrapper the loop writes,
    because the wrapper already knows the note's root guid at the moment it
    calls claude and putting it in the file being written anyway avoids a
    second file and a second route just to state one fact:

        {"responds_to": "<the note's root guid>",
         "follows":     "<the previous round's response root>",   # optional
         "envelope":    {...}}

    `follows` is what makes a conversation a *chain* rather than a pile of
    unconnected pairs, and it was missing from the first implementation. The
    route mints `next` from the note to its own response, but nothing could
    join one round to the next: this file is the only one that carries
    structural guids, and it did not name the round before it. Two rounds gave
    `note1 -> resp1` and `note2 -> resp2` with nothing between them, so "walk
    the conversation" — the whole reason no container node was needed — did not
    work. With `follows` the chain closes:

        note1 --next--> resp1 --next--> note2 --next--> resp2

    Optional, because the first round of a conversation follows nothing. It is
    *asserted* rather than derived: the loop knows the order exactly, and
    recovering it from `created_at` would be guesswork the moment two rounds
    interleave.

    Every key `claude --print` produced lands in `params`, verbatim and
    unrenamed — CLAUDE.md's digest-everything rule, and the reason this route
    exists at all rather than a route that keeps only `result`. Filtering
    would be keeping the half anyone predicted would matter; this keeps
    `total_cost_usd`, `permission_denials` and the rest of the eighteen keys
    nobody has a use for yet, because deciding they are noise while reading
    them is a decision made once, silently, and unrecoverably.

    `result` is the other half, and it is markdown: it goes through the same
    reader `notes` uses, so the answer's paragraphs become addressable blocks
    like any other document's. Keeping it only in `params` — the way every
    other key is kept — would make the response readable but never citable,
    which defeats the point of the route existing at all.
    """
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"not JSON ({e}). Expected "
            '{"responds_to": "<guid>", "envelope": {...}}.') from None
    if not isinstance(wrapper, dict) or "envelope" not in wrapper \
            or "responds_to" not in wrapper:
        raise RuntimeError(
            'not a response wrapper: need "responds_to" and "envelope" '
            'keys. See docs/roadmap.md, "the conversation loop".')
    envelope = wrapper["envelope"]
    if not isinstance(envelope, dict):
        raise RuntimeError(
            f"envelope is not an object: {type(envelope).__name__}")
    responds_to = wrapper["responds_to"]
    follows = wrapper.get("follows")
    if follows is not None and not isinstance(follows, str):
        raise RuntimeError(
            f"follows is not a guid: {type(follows).__name__}")
    result = envelope.get("result", "")
    if not isinstance(result, str):
        raise RuntimeError(
            f"envelope['result'] is not a string: {type(result).__name__}")

    recs, root = MD.text_to_records(result, mint=mint, route=route)
    root_rec = next(r for r in recs if r["guid"] == root)
    # `params` already holds meta/pandoc_api_version/route from
    # `text_to_records` (never empty — `route` is always given above), so
    # this is always a real dict to update in place, never a fresh one.
    # `source` is not one of them: `text_to_records` never sets it, because
    # most of its callers (a delegated transcript turn) have none to give.
    # This route does have one — the wrapper file itself — so it is set here
    # rather than passed down, the one place a fileless read gets a filename
    # after all.
    params = root_rec["params"]
    params["source"] = path.name
    params.update(envelope)
    # `params["uuid"]` is now the ENVELOPE's own uuid, not this record's own
    # `guid` — one word naming two different things in the same record. This
    # looks like a bug and is not one: renaming it on the way in would stop
    # this route being a faithful, verbatim copy of what claude printed, and
    # leaving it alone means whoever reads params["uuid"] later has to know
    # which of the two they are asking for. Decided in docs/roadmap.md,
    # "the conversation loop" — recorded here because the record itself gives
    # no other sign that this was deliberate.
    #
    # `ast_to_records` already stamped `root_rec`'s hashes, over `params`
    # *before* this update — so they are stale the moment `params.update`
    # runs, and re-stamping is not optional. Only the root's own hash and its
    # own fold can have changed (every other node's params are untouched), but
    # re-running over the whole tree is cheap for one response document and is
    # the same call every other writer makes, rather than a special case that
    # has to reason about which one node needs it.
    R.stamp_hashes(recs)

    b = R.Builder(mint)
    # Both structural, so neither carries `by` — see docs/record-grammar.md
    # §2 on when that field is present. `responds_to` is the fact a citation
    # never states on its own (this document answers that one); `next` is
    # reading order, note before its response, and is what lets a reader
    # walk a conversation without a container node existing anywhere.
    b.edge("responds_to", root, responds_to, CONVERSATION_LAYER)
    b.edge("next", responds_to, root, CONVERSATION_LAYER)
    if follows is not None:
        # The link across rounds: the previous response is followed by this
        # round's note. Minted here rather than when the note was digested,
        # because `notes` reads a markdown file and cannot be told about a
        # guid — this wrapper is the only file in the loop that carries
        # structural guids at all. `_digest` refuses the batch if `follows`
        # names nothing, the same as `responds_to`.
        b.edge("next", follows, responds_to, CONVERSATION_LAYER)
    return recs + b.records, root


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


# -- the transcript default: what a filename alone says about identity ------
#
# `--updates=guid` names the root explicitly because "which of fifty
# README.md files" has no safe automatic answer (docs/roadmap.md, "AoTA") —
# but a Claude Code transcript is not an arbitrary file. Archived transcripts
# come in exactly two shapes, and both name their own identity: a root
# session is written to `<sessionId>.jsonl`, and the session root already
# stores `session_id`; a subagent's is `agent-<toolUseId>.jsonl`, and its
# root's `agent` sidecar already carries that same `toolUseId` (the identical
# equality `store.py:_link_agents` draws, read the other way). Measured
# against the archived base: 6 of 18 real filenames match the first rule, the
# other 12 match the second, and together they resolve all 18.
#
# This is a *filename* fact, deliberately not wired to change what `digest`
# does: omitting `--updates` still mints a second root, silently — that stays
# principle 10's answer this release (docs/roadmap.md). What this buys is
# something to print, not something to act on: `store.py` uses it to name a
# candidate `--updates` value when one exists, so the default is at least
# visible rather than found by accident later.
_SESSION_NAME = re.compile(r"^(%s)\.jsonl$" % R.HANDLE_RE)
_AGENT_NAME = re.compile(r"^agent-(%s)\.jsonl$" % R.HANDLE_RE)


def transcript_identity(path: Path):
    """What `path`'s name alone claims about a transcript's identity.

    Returns `("session_id", value)`, `("agent_tool_use_id", value)`, or
    `None` for a name matching neither archived shape. Never opens the file
    and never looks at a base, so it composes with whatever a caller wants
    to match it against.
    """
    m = _SESSION_NAME.match(path.name)
    if m:
        return ("session_id", m.group(1))
    m = _AGENT_NAME.match(path.name)
    if m:
        return ("agent_tool_use_id", m.group(1))
    return None


def find_transcript_root(records: list, path: Path) -> str | None:
    """The existing session root `path`'s filename identifies, or `None`.

    `session_id` is matched against `session.params["session_id"]`, which
    every session root already stores. `agent_tool_use_id` is matched
    against `session.params["agent"]["toolUseId"]`, the sidecar
    `store.py:_link_agents` already reads to join a subagent to the tool
    call that launched it.
    """
    ident = transcript_identity(path)
    if ident is None:
        return None
    kind, value = ident
    for r in records:
        if r["record"] != "node" or r["type"] != "session":
            continue
        params = r.get("params") or {}
        if kind == "session_id" and params.get("session_id") == value:
            return r["guid"]
        if kind == "agent_tool_use_id":
            agent = params.get("agent") or {}
            if agent.get("toolUseId") == value:
                return r["guid"]
    return None


ROUTES = {
    "notes": (_notes, "prose, read as commonmark_x", None),
    "claude-code-transcript": (_transcript, "a Claude Code session *.jsonl",
                               _transcript_referrals),
    "pandoc-ast": (_pandoc_ast, "a pandoc JSON document, already parsed", None),
    "claude-code-response": (_response,
                             "a {responds_to, envelope} wrapper around "
                             "`claude --print --output-format json`", None),
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

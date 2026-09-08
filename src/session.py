#!/usr/bin/env python3
"""
session.py — a Claude Code session log into records.

The question this file answers is which text gets *parsed* and which is kept
verbatim, and the answer is not the same for all of it:

- **assistant and human prose is parsed as markdown**, through exactly the same
  path a `.md` file takes. It is markdown — that is what the interface renders
  — and it is where every citation in this corpus points. A paragraph of an
  answer has to be a node or the whole workflow stops working.
- **tool output is kept verbatim.** It is terminal text, not markdown, and
  parsing it as markdown invents structure that was never there: 60 real tool
  outputs from this corpus produce a Header, a BulletList and a Div, and a
  table of numbers splits into three blocks on indentation alone. Inventing a
  heading inside a `ls` listing is worse than storing it whole.
- **tool input is kept verbatim** for the same reason. A shell command is not
  prose.

Tool output stays a node, so it is still addressable and a view can collapse
it and expand it on citation. Addressable and markdown-parsed are different
things, and only the first one was ever wanted.

Attribution has one trap worth naming. A `user` line is not necessarily a
human: the transcript wraps every tool result in one. Only a user line
carrying real text is a human turn, which is the attribution bug the old
importer shipped. Note that recognising an envelope is about *what to call
it*, not about whether to keep it — the line is stored either way.

**Nothing in the file is filtered out here.** Every line becomes a node and
carries its own original JSON, verbatim, in `params["log"]`. That is the
guarantee: reading a transcript adds information and never subtracts it, and
what to ignore is a question for a view or a query, asked later and by a
person. An audit on 2026-08-21 found this importer discarding 46% of a real
transcript's lines and seventeen log-line keys, each one a decision made
silently at read time and unrecoverable without re-reading the source.

So there are two things in the graph, deliberately, and they are different:

- **`params["log"]`** is the line as it was. Nothing is promoted out of it,
  nothing is normalised, and it is what makes the import lossless.
- **the nodes and edges** are what compost understood of it — turns, tool
  calls, parsed prose. These are an interpretation and may improve.

The cost is that a message's text is held twice: once raw inside `log`, once
as parsed blocks. That is accepted. The raw text is the source and the blocks
are a derivation, which is the same relationship `storage/` has with the whole
graph, and the alternative is deciding at import which of the two matters.
"""
import hashlib
import json
import sys
from pathlib import Path

from . import records as R
from . import markdown as M

# Structure any transcript source would have. Kept separate from the
# source-specific layer below so another agent's log format can reuse it
# without inheriting Claude Code's threading model.
LAYER = "session"
# Facts particular to this log format: the parentUuid chain.
SOURCE_LAYER = "claude-code"
# Same value as `store.py`'s own `INGEST_LAYER` — not imported from there,
# because `store` imports `routes` imports `session`, and importing `store`
# from here would close that into a cycle. A layer name is a string, not
# code; two modules owning the same literal is the accepted cost, the same
# way `LAYER`/`SOURCE_LAYER` are already each module's own.
INGEST_LAYER = "ingestion"
# Line types this importer interprets. Everything else still becomes a node —
# a `logline` carrying its whole original JSON — because "we have no reading
# for this yet" and "this can be thrown away" are different statements.
INTERPRETED = ("user", "assistant")

# Tool inputs that name a file the call touched.
PATH_KEYS = ("file_path", "path", "notebook_path")


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _result_text(block):
    """`tool_result.content`, mapped without dropping anything.

    A string body is prose-shaped and is kept as a string. A list-shaped body
    is **stored whole** — total mapping (design-total-mapping.md): the
    old code joined only the `text` key of each dict element, so an element
    with no `text` key (a `tool_reference`, say) vanished without a trace.
    Measured at 2 occurrences in the whole corpus, and both are now exact:
    the list comes back byte-for-byte on the round trip, same as everything
    else `params` carries verbatim.
    """
    body = block.get("content")
    if isinstance(body, list):
        return body
    return "" if body is None else str(body)


class SessionImporter:
    def __init__(self, mint=None):
        self.b = R.Builder(mint)
        self.files: dict[str, str] = {}      # path -> guid, deduped per session
        self.calls: dict[str, str] = {}      # tool_use_id -> toolcall guid
        self.by_uuid: dict[str, str] = {}    # log line uuid -> turn guid
        self._route: str | None = None       # set in run(); read by _delegate

    # -- helpers -----------------------------------------------------------
    def _file_node(self, path: str) -> str:
        if path not in self.files:
            self.files[path] = self.b.node("file", {"path": path})
        return self.files[path]

    def _delegate(self, text: str, block, selector: str) -> str | None:
        """One turn's prose, handed to the shared markdown digestor.

        v0.2.14, "the recursion made explicit": a digestor that meets content
        it does not own delegates to the digestor that does, and the
        delegated input is stored like any other digestor input. `block` is
        exactly what sat at `selector` in the source line — the whole
        `{"type": "text", "text": ...}` dict when a turn's `content` is a
        list, or the bare string when it is one already — and is stored
        as-is as a fragment blob's `content`, addressed by `selector` as a
        JSON Pointer into the parent transcript's line array (ours, not
        RFC 6901's own convention: a `.jsonl` blob is the JSON array of its
        lines).

        Returns the delegated document's root guid, or None when there is no
        text to delegate — the same as the old `_prose` on an empty block,
        which minted nothing either. The second `derived_from` hop, fragment
        blob to transcript blob, is not minted here: this importer does not
        yet know the transcript's own blob guid (that is minted generically,
        once, in `store.py:_digest`, after every route has returned) — see
        `store.py`'s per-plan writing loop, which wires it up for every
        `blob` node any route's own output already carries.
        """
        if not text.strip():
            return None
        data = R.canonical(block)
        frag = self.b.mint()
        self.b.node("blob", {
            "original_name": None,
            "stored_as": f"{frag}.json",
            "bytes_sha256": hashlib.sha256(data).hexdigest(),
            "imported_at": R._now(),
            "route": self._route,
            "selector_conforms_to": "RFC 6901",
            "selector_value": selector,
        }, content=block, guid=frag)
        recs, root = M.text_to_records(text, mint=self.b.mint,
                                       route=self._route)
        self.b.records.extend(recs)
        self.b.edge("derived_from", root, frag, INGEST_LAYER)
        return root

    def _tool_use(self, block: dict) -> str:
        params = {
            "name": block.get("name"),
            "tool_use_id": block.get("id"),
            "input": block.get("input", {}),
        }
        # Total mapping: `caller` is dropped by nothing else that reads this
        # block, so if the source has it, the node must too. Conditional on
        # presence — 902 of 903 `tool_use` blocks in the corpus carry it, one
        # does not, and inventing a value for the one that lacks it would be
        # asserting a fact the transcript never stated.
        if "caller" in block:
            params["caller"] = block["caller"]
        guid = self.b.node("toolcall", params)
        self.calls[block.get("id")] = guid
        inp = block.get("input") or {}
        if isinstance(inp, dict):
            for k in PATH_KEYS:
                if isinstance(inp.get(k), str):
                    self.b.edge("touches", guid, self._file_node(inp[k]),
                                LAYER)
        return guid

    def _tool_result(self, block: dict):
        """Fold a result into the call that produced it, matched on id."""
        parent = self.calls.get(block.get("tool_use_id"))
        out = self.b.node("tooloutput", {
            "tool_use_id": block.get("tool_use_id"),
            "is_error": bool(block.get("is_error")),
            "text": _result_text(block),
        })
        if parent:
            self.b.children(parent, [out], LAYER)
        return out, parent

    # -- the walk ----------------------------------------------------------
    def run(self, path: Path, route: str | None = None) -> tuple[list, str]:
        self._route = route
        lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        meta = next((d for d in lines if d.get("sessionId")), {})
        params = {
            "source": path.name,
            "session_id": meta.get("sessionId"),
            "version": meta.get("version"),
        }
        # `lines` used to live here and is gone: `len(children)`, recomputable
        # in one call, and a derived param that is a function of the node's
        # *subtree* rather than the node itself. It was the sole reason a
        # re-ingested transcript's root failed to match itself — measured on
        # session-04.jsonl truncated to 70% and re-read, the identical prefix
        # was 0 of 2,306 nodes with `lines`, 100.00% without. See
        # design-total-mapping.md §6.
        # A sidechain's `.meta.json` sidecar, stored verbatim on the root. It
        # carries `toolUseId`, which names the `Agent` call in the *parent*
        # that launched this agent, plus `spawnDepth`, `agentType`, `model` and
        # `parentAgentId` when nested.
        #
        # Stored rather than only used, so the join outlives the invocation
        # that found it: digest a sidechain by itself and the fact that it
        # belongs to a tool call is still recorded, and the edge can be derived
        # whenever the other end turns up. Same reasoning as citations being
        # derived from stored links rather than asserted once.
        sidecar = path.with_suffix(".meta.json")
        if sidecar.is_file():
            try:
                params["agent"] = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        if route:
            params["route"] = route
        session = self.b.node("session", params)

        turns: list[str] = []
        pending: list[tuple[str, str]] = []
        for i, d in enumerate(lines):
            kind = d.get("type")

            # A line type this importer has no reading for is still a line, and
            # still gets a node carrying everything it said. Skipping it would
            # be a filtering decision taken at read time, which is exactly the
            # thing this importer stopped doing.
            if kind not in INTERPRETED:
                turns.append(self.b.node("logline", {
                    "line_type": kind,
                    "uuid": d.get("uuid"),
                    "timestamp": d.get("timestamp"),
                    "log": d,
                }))
                continue

            content = (d.get("message") or {}).get("content")
            blocks = content if isinstance(content, list) else []
            prose = _text_of(content)

            # One delegated fragment per turn, and no more — see
            # TODO-multiple-text-blocks.md. v0.2.14 hands a turn's markdown to
            # the text digestor and reaches the result through one
            # `delegates_to` edge; several text blocks would need several, with
            # nothing ordering them against the turn's other children.
            #
            # Measured 0 times in 2,839 corpus turns, so this cannot fire on
            # any material this project has. It is an error rather than a
            # warning because the alternative is a silent partial import, which
            # is exactly what `digest everything` exists to prevent: a base
            # built from a guess is wrong in a way nothing can detect later.
            # Soften it to a warning only after it has actually fired.
            n_text = sum(1 for b in blocks
                         if isinstance(b, dict) and b.get("type") == "text"
                         and b.get("text", "").strip())
            if n_text > 1:
                raise NotImplementedError(
                    f"{path.name}: a turn carries {n_text} text blocks, and "
                    f"delegating more than one fragment per turn is not built "
                    f"— see TODO-multiple-text-blocks.md. Line uuid "
                    f"{d.get('uuid')}.")

            children: list[str] = []
            orphan_results: list[str] = []
            has_text = bool(prose.strip())
            delegated_root: str | None = None

            for idx, blk in enumerate(blocks):
                if not isinstance(blk, dict):
                    children.append(self.b.node("contentblock",
                                                {"block_type": None,
                                                 "block": blk}))
                    continue
                t = blk.get("type")
                if t == "text":
                    delegated_root = self._delegate(
                        blk.get("text", ""), blk,
                        f"/{i}/message/content/{idx}")
                elif t == "thinking":
                    # Kept as a node even though these logs carry no text: the
                    # fact that reasoning happened, and where in the turn, is
                    # the part the transcript actually records. `signature` is
                    # stored too, total mapping: it was dropped until now, and
                    # dropping it is what made every empty `thinking` node
                    # hash identically (design-total-mapping.md). `empty`
                    # stays a derived param — it is `f(text)`, never a
                    # function of the node's subtree, so it cannot move the
                    # fold the way `lines` on `session` did.
                    children.append(self.b.node("thinking", {
                        "text": blk.get("thinking", ""),
                        "empty": not blk.get("thinking"),
                        "signature": blk.get("signature"),
                    }))
                elif t == "tool_use":
                    children.append(self._tool_use(blk))
                elif t == "tool_result":
                    out, parent = self._tool_result(blk)
                    if parent is None:
                        orphan_results.append(out)
                else:
                    # An unrecognised block type is stored whole and loudly,
                    # rather than falling off the end of the if-chain. The old
                    # `else` was silence, so a new block type would have
                    # vanished without a word.
                    children.append(self.b.node("contentblock",
                                                {"block_type": t,
                                                 "block": blk}))
            if isinstance(content, str) and content.strip():
                delegated_root = self._delegate(
                    content, content, f"/{i}/message/content")
                has_text = True

            # A user line carrying only tool results is the transcript's
            # envelope, not something a person typed. That is a statement about
            # *authorship* and never about whether to keep the line: the node
            # is created either way, and a view decides what to show.
            author = "assistant" if kind == "assistant" else (
                "human" if has_text else "envelope")

            turn = self.b.node("turn", {
                "author": author,
                "timestamp": d.get("timestamp"),
                "uuid": d.get("uuid"),
                "log": d,
            })
            self.b.children(turn, children + orphan_results, LAYER)
            if delegated_root is not None:
                # The delegated document is a root that nobody `contains` —
                # `document` is in `ROOT_TYPES`, and a root with a `contains`
                # parent is a reported `check()` problem. The turn reaches it
                # by this edge instead, the same shape a launched subagent
                # session already uses (`store.py:_link_agents`).
                self.b.edge("delegates_to", turn, delegated_root, LAYER)
            turns.append(turn)
            if d.get("uuid"):
                self.by_uuid[d["uuid"]] = turn
            if d.get("parentUuid"):
                pending.append((turn, d["parentUuid"]))

        self.b.children(session, turns, LAYER)

        # Two orderings, deliberately both. `next` above is *log order*, which
        # is what regenerates the file; `replies_to` is the conversational
        # truth, and the two diverge the moment a session has a sidechain.
        # Storing only one of them means guessing the other.
        for turn, parent_uuid in pending:
            parent = self.by_uuid.get(parent_uuid)
            if parent:
                self.b.edge("replies_to", turn, parent, SOURCE_LAYER)

        R.stamp_hashes(self.b.records)
        return self.b.records, session


def session_to_records(path: Path, mint=None,
                       route: str | None = None) -> tuple[list, str]:
    return SessionImporter(mint).run(Path(path), route)


def records_to_session(records, root: str | None = None) -> list[dict]:
    """
    The transcript's lines back, in order, exactly as they were read.

    The counterpart to `session_to_records`, and the reason the pair is worth
    having is the property between them:

        records_to_session(session_to_records(lines)) == lines

    That is the transcript's version of the AST round-trip, and it says the one
    thing worth guaranteeing about an importer: **it did not throw anything
    away.** It holds by construction — every line node carries its own JSON in
    `params["log"]` — and stating it as a property is what makes it stay true.
    The moment somebody filters a line type again, this fails.

    Note what it does *not* claim. The nodes are an interpretation and may get
    better; this only says the source of that interpretation is still here.
    """
    g = R.Graph(records)
    if root is None:
        roots = [n["guid"] for n in g.nodes.values() if n["type"] == "session"]
        if len(roots) != 1:
            raise ValueError(f"expected one session, found {len(roots)}")
        root = roots[0]
    out = []
    for k in g.children(root):
        n = g.nodes[k]
        if n["type"] not in ("turn", "logline"):
            raise ValueError(f"{k}: a session's child is {n['type']!r}, "
                             "so it is not a log line and the file cannot be "
                             "reconstructed")
        out.append(n["params"]["log"])
    return out

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
importer shipped.
"""
import json
import subprocess
import sys
from pathlib import Path

from . import records as R

# Structure any transcript source would have. Kept separate from the
# source-specific layer below so another agent's log format can reuse it
# without inheriting Claude Code's threading model.
LAYER = "session"
# Facts particular to this log format: the parentUuid chain.
SOURCE_LAYER = "claude-code"
READER = "commonmark_x-smart-attributes-fancy_lists"

# Tool inputs that name a file the call touched.
PATH_KEYS = ("file_path", "path", "notebook_path")


def _md_blocks(text: str) -> list:
    """Markdown text -> pandoc blocks. Empty list if it parses to nothing."""
    if not text.strip():
        return []
    r = subprocess.run(["pandoc", "-f", READER, "-t", "json"],
                       input=text, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)["blocks"]


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _result_text(block) -> str:
    body = block.get("content")
    if isinstance(body, list):
        return "\n".join(x.get("text", "") for x in body if isinstance(x, dict))
    return "" if body is None else str(body)


class SessionImporter:
    def __init__(self, mint=None):
        self.b = R.Builder(mint)
        self.files: dict[str, str] = {}      # path -> guid, deduped per session
        self.calls: dict[str, str] = {}      # tool_use_id -> toolcall guid
        self.by_uuid: dict[str, str] = {}    # log line uuid -> turn guid

    # -- helpers -----------------------------------------------------------
    def _file_node(self, path: str) -> str:
        if path not in self.files:
            self.files[path] = self.b.node("file", {"path": path})
        return self.files[path]

    def _prose(self, text: str) -> list[str]:
        """Parsed markdown, as node guids. The text importer, reused whole."""
        return [R._block(self.b, blk) for blk in _md_blocks(text)]

    def _tool_use(self, block: dict) -> str:
        guid = self.b.node("toolcall", {
            "name": block.get("name"),
            "tool_use_id": block.get("id"),
            "input": block.get("input", {}),
        })
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
        lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        meta = next((d for d in lines if d.get("sessionId")), {})
        params = {
            "source": path.name,
            "session_id": meta.get("sessionId"),
            "version": meta.get("version"),
        }
        if route:
            params["route"] = route
        session = self.b.node("session", params)

        turns: list[str] = []
        pending: list[tuple[str, str]] = []
        for d in lines:
            kind = d.get("type")
            if kind not in ("user", "assistant"):
                continue
            content = (d.get("message") or {}).get("content")
            blocks = content if isinstance(content, list) else []
            prose = _text_of(content)

            children: list[str] = []
            orphan_results: list[str] = []
            has_text = bool(prose.strip())

            for blk in blocks:
                if not isinstance(blk, dict):
                    continue
                t = blk.get("type")
                if t == "text":
                    children += self._prose(blk.get("text", ""))
                elif t == "thinking":
                    # Kept as a node even though these logs carry no text: the
                    # fact that reasoning happened, and where in the turn, is
                    # the part the transcript actually records.
                    children.append(self.b.node("thinking", {
                        "text": blk.get("thinking", ""),
                        "empty": not blk.get("thinking"),
                    }))
                elif t == "tool_use":
                    children.append(self._tool_use(blk))
                elif t == "tool_result":
                    out, parent = self._tool_result(blk)
                    if parent is None:
                        orphan_results.append(out)
            if isinstance(content, str) and content.strip():
                children += self._prose(content)
                has_text = True

            # A user line carrying only tool results is the transcript's
            # envelope, not something a person typed.
            if not children and not orphan_results:
                continue
            author = "assistant" if kind == "assistant" else (
                "human" if has_text else "envelope")
            if author == "envelope":
                continue

            turn = self.b.node("turn", {
                "author": author,
                "timestamp": d.get("timestamp"),
                "uuid": d.get("uuid"),
            })
            self.b.children(turn, children + orphan_results, LAYER)
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

        return self.b.records, session


def session_to_records(path: Path, mint=None,
                       route: str | None = None) -> tuple[list, str]:
    return SessionImporter(mint).run(Path(path), route)

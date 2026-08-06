"""
importer.py — a closed Claude Code session becomes a conversation.

Sessions are JSONL at `~/.claude/projects/<cwd-slug>/<session>.jsonl`. Each line
carries a `type` (`user`, `assistant`, plus bookkeeping types we skip), a
`message` in Anthropic format, a `timestamp`, and `parentUuid` — which makes the
log a tree rather than a list, with `isSidechain` marking subagent branches.

**The whole session is turned into one markdown document and canonized once.**
Pandoc carries fenced divs and their key=value attributes through to djot, so
the turn structure survives a single pass. Canonizing turn by turn would cost
two subprocess spawns each — roughly two minutes for a seventy-turn session
against about a second this way.

**Nothing is filtered.** Tool traffic is the bulk of a session and almost none
of its value, but it is wrapped in `.tool-call` divs that the renderer folds
away, so the whole transcript is present and addressable while what you read is
the conversation. Compressing or filtering is a later, separate decision; the
importer's job is to lose nothing.

Every block gets a handle like any other, so an imported conversation is citable
the moment it lands.
"""
import json
import re
from pathlib import Path

SKIP_TYPES = {"mode", "permission-mode", "file-history-snapshot", "ai-title",
              "last-prompt", "system", "attachment"}


def sessions_for(cwd: Path) -> list[Path]:
    """Session logs for a working directory, oldest first."""
    slug = str(cwd.resolve()).replace("/", "-")
    d = Path.home() / ".claude" / "projects" / slug
    return sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if d.exists() else []


def _fence(text: str, char: str, minimum: int = 3) -> str:
    """A fence longer than any run of `char` starting a line inside `text`."""
    runs = [len(m.group(0)) for m in
            re.finditer(rf"^{re.escape(char)}+", text, flags=re.M)]
    return char * max(minimum, (max(runs) + 1) if runs else minimum)


def _code(text: str) -> str:
    f = _fence(text, "~", 4)
    return f"{f}\n{text}\n{f}"


def _parts(msg: dict) -> tuple[list[str], list[str]]:
    """Split a message into prose and folded parts."""
    content = msg.get("content")
    if isinstance(content, str):
        return ([content] if content.strip() else [], [])

    prose, folded = [], []
    for blk in content or []:
        kind = blk.get("type")
        if kind == "text":
            if blk.get("text", "").strip():
                prose.append(blk["text"])
        elif kind == "thinking":
            if blk.get("thinking", "").strip():
                folded.append(("thinking", "", blk["thinking"]))
        elif kind == "tool_use":
            folded.append(("tool-call", blk.get("name", "tool"),
                           json.dumps(blk.get("input", {}), ensure_ascii=False,
                                      indent=1)))
        elif kind == "tool_result":
            body = blk.get("content")
            if isinstance(body, list):
                body = "\n".join(x.get("text", "") for x in body
                                 if isinstance(x, dict))
            folded.append(("tool-result", "", str(body or "")))
    return prose, folded


def turns_from_session(path: Path) -> list[dict]:
    """Ordered turns: author, uuid, prose, folded parts."""
    turns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("type") not in ("user", "assistant"):
            continue
        prose, folded = _parts(d.get("message") or {})
        if not prose and not folded:
            continue
        who = "human" if d["type"] == "user" else "claude"
        if d.get("isSidechain"):
            who += ":sidechain"
        turns.append({"author": who, "uuid": d.get("uuid", ""),
                      "timestamp": d.get("timestamp", ""),
                      "prose": prose, "folded": folded})
    return turns


def session_markdown(turns: list[dict]) -> str:
    """
    One markdown document: turns as fenced divs, tool traffic nested inside.

    Fence lengths are computed from the content rather than fixed. Tool output
    is arbitrary text and routinely contains both `:::` and code fences — this
    file's own source would close a fixed fence early — so each fence is made
    longer than the longest run it must contain, and the turn fence longer
    still.
    """
    bodies = []
    for t in turns:
        inner = "\n\n".join(t["prose"])
        for cls, name, payload in t["folded"]:
            f = _fence(payload, ":", 4)
            attr = "{." + cls + (f' name="{name}"' if name else "") + "}"
            inner += f"\n\n{f} {attr}\n{_code(payload)}\n{f}"
        bodies.append(inner.strip())

    outer = _fence("\n\n".join(bodies), ":", 6)
    return "\n\n".join(
        f'{outer} {{.turn author="{t["author"]}" turn="{t["uuid"]}"}}\n'
        f"{body}\n{outer}"
        for t, body in zip(turns, bodies)) + "\n"

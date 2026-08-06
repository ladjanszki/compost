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

# A `user` line is not the same thing as "the human typed this". Tool results
# come back as user messages because that is the API protocol, the harness
# injects its own, and a slash command echoes its name and its output. In one
# real 18-"user"-turn session only 2 were typed by a person. Attributing the
# rest to the human is a lie the reader cannot detect — a directory listing
# appears above their name — so each is recognised and re-attributed.
META_MARKERS = ("<command-name>", "<command-message>", "<local-command-stdout>",
                "[Request interrupted by user")
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>",
                             re.DOTALL)


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


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or []
                     if isinstance(b, dict) and b.get("type") == "text")


def _result_text(blk: dict) -> str:
    body = blk.get("content")
    if isinstance(body, list):
        body = "\n".join(x.get("text", "") for x in body if isinstance(x, dict))
    return str(body or "")


def turns_from_session(path: Path) -> list[dict]:
    """
    Ordered turns: author, uuid, prose, folded parts.

    A tool result is not a turn. It is folded into the call that produced it,
    matched on `tool_use_id`, so one fold holds the request and its output the
    way the TUI shows them.
    """
    turns: list[dict] = []
    calls: dict[str, dict] = {}      # tool_use_id -> the fold awaiting a result

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("type") not in ("user", "assistant"):
            continue
        content = (d.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []

        # Tool results: attach to the call, never to a turn of their own.
        results = [b for b in blocks if b.get("type") == "tool_result"]
        if results and not _text_of(content).strip():
            for r in results:
                fold = calls.pop(r.get("tool_use_id"), None)
                if fold is not None:
                    fold["body"] += "\n\n→ result\n" + _result_text(r)
                elif turns:
                    turns[-1]["folded"].append(
                        {"cls": "tool-call", "name": "result",
                         "body": _result_text(r)})
            continue

        prose, folded = [], []
        if isinstance(content, str):
            if content.strip():
                prose.append(content)
        else:
            for blk in blocks:
                kind = blk.get("type")
                if kind == "text" and blk.get("text", "").strip():
                    prose.append(blk["text"])
                elif kind == "thinking" and blk.get("thinking", "").strip():
                    folded.append({"cls": "thinking", "name": "",
                                   "body": blk["thinking"]})
                elif kind == "tool_use":
                    fold = {"cls": "tool-call", "name": blk.get("name", "tool"),
                            "body": json.dumps(blk.get("input", {}),
                                               ensure_ascii=False, indent=1)}
                    folded.append(fold)
                    calls[blk.get("id", "")] = fold

        if d["type"] == "user":
            joined = "\n".join(prose)
            # The harness writes as the user: injected context, and the echo of
            # a slash command together with its output. The person typed the
            # command, not the listing it printed.
            if d.get("isMeta") or any(m in joined for m in META_MARKERS):
                who = "system"
                folded += [{"cls": "tool-call", "name": "harness", "body": p}
                           for p in prose]
                prose = []
            else:
                who = "human"
                # A system-reminder is injected into the middle of real typing.
                cleaned = []
                for p in prose:
                    reminders = SYSTEM_REMINDER.findall(p)
                    folded += [{"cls": "tool-call", "name": "system-reminder",
                                "body": r} for r in reminders]
                    rest = SYSTEM_REMINDER.sub("", p).strip()
                    if rest:
                        cleaned.append(rest)
                prose = cleaned
        else:
            who = "claude"
        if d.get("isSidechain"):
            who += ":sidechain"

        if not prose and not folded:
            continue
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
        for fold in t["folded"]:
            payload = fold["body"]
            f = _fence(payload, ":", 4)
            attr = ("{." + fold["cls"]
                    + (f' name="{fold["name"]}"' if fold["name"] else "") + "}")
            inner += f"\n\n{f} {attr}\n{_code(payload)}\n{f}"
        bodies.append(inner.strip())

    outer = _fence("\n\n".join(bodies), ":", 6)
    return "\n\n".join(
        f'{outer} {{.turn author="{t["author"]}" turn="{t["uuid"]}"'
        + (f' time="{t["timestamp"]}"' if t["timestamp"] else "")
        + f"}}\n{body}\n{outer}"
        for t, body in zip(turns, bodies)) + "\n"

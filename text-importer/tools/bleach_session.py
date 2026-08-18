#!/usr/bin/env python3
"""
bleach_session.py — the same trick as bleach.py, for session transcripts.

A session log is JSON, so the prose hides in nested string values rather than
in a document. Everything that makes the log *work* survives untouched — line
types, roles, block types, tool names, the uuid/parentUuid chain, tool_use_id
pairing, timestamps, sidechain flags — and every string that could carry
content is replaced.

Identifiers are remapped rather than kept, consistently, so the linkage graph
is intact while the identity is gone: parentUuid still points at the line it
pointed at, and a tool_result still finds its tool_use.

As with markdown, correctness is checkable rather than eyeballed. The bleached
log must have the same line types, the same block types per line, the same tool
names, and an isomorphic parent chain. `verify` asserts all four.
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bleach import bleach  # noqa: E402

# Values that are structure, not content. Bleaching these would break the very
# thing a fixture exists to exercise.
# gitBranch is deliberately absent: a branch name is content, not structure,
# and "conversations" was the one word of the original that walked through.
KEEP = {
    "type", "role", "name", "isSidechain", "isMeta", "userType", "entrypoint",
    "stop_reason", "stop_sequence", "model", "version", "effort",
    "speed", "service_tier", "sessionKind", "is_error", "subtype", "level",
    "mode", "permissionMode", "caller", "status", "outcome", "verdict",
}
# Values that are identifiers: remapped, never bleached, so linkage survives.
IDS = {
    "uuid", "parentUuid", "sessionId", "session_id", "id", "tool_use_id",
    "requestId", "messageUuid", "leafUuid", "toolUseID", "agentId",
}
UUIDISH = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Schema keys are plain identifiers. Anything else used as a key is content —
# file-history-snapshot maps absolute paths to backups, and a path sitting in
# key position is how 57 of them walked straight through the first version of
# this script.
SCHEMA_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# ISO timestamps are structure to anything that renders a transcript, but the
# actual instants say when someone was working. Shifted by a fixed offset and
# kept well-formed: the format survives, the schedule does not.
ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
                 r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


class Remapper:
    """Stable, deterministic identifier substitution."""

    def __init__(self, salt: str):
        self.salt = salt
        self.seen: dict[str, str] = {}

    def __call__(self, value: str) -> str:
        if value in self.seen:
            return self.seen[value]
        h = hashlib.sha256(f"{self.salt}:{value}".encode()).hexdigest()
        if UUIDISH.match(value):
            out = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
        else:
            keep = value.split("_", 1)
            out = (f"{keep[0]}_{h[:len(keep[1])]}" if len(keep) == 2
                   else h[:len(value)])
        self.seen[value] = out
        return out


def _shift(stamp: str) -> str:
    """Same shape, different instant."""
    m = ISO.match(stamp)
    y, mo, d, h, mi, se = (int(m.group(i)) for i in range(1, 7))
    y = 2000 + (y % 7)
    return (f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{se:02d}"
            f"{m.group(7) or ''}{m.group(8) or ''}")


def scrub(obj, remap: Remapper, salt: str, key: str | None = None):
    if isinstance(obj, dict):
        return {(k if SCHEMA_KEY.match(k) else bleach(k, salt=salt)):
                scrub(v, remap, salt, k if SCHEMA_KEY.match(k) else None)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v, remap, salt, key) for v in obj]
    if isinstance(obj, str):
        if key in KEEP:
            return obj
        if key in IDS:
            return remap(obj)
        if UUIDISH.match(obj):
            return remap(obj)
        if ISO.match(obj):
            return _shift(obj)
        return bleach(obj, salt=salt)
    return obj


def bleach_session(text: str, salt: str) -> str:
    remap = Remapper(salt)
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        out.append(json.dumps(scrub(json.loads(line), remap, salt),
                              ensure_ascii=False, sort_keys=True))
    return "\n".join(out) + "\n"


def shape(text: str) -> dict:
    """The structural fingerprint a bleached log must preserve exactly."""
    types, blocks, tools, chain = Counter(), Counter(), Counter(), []
    for line in text.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        types[d.get("type")] += 1
        chain.append((d.get("uuid") is not None, d.get("parentUuid") is not None))
        msg = d.get("message") or {}
        c = msg.get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict):
                    blocks[b.get("type")] += 1
                    if b.get("type") == "tool_use":
                        tools[b.get("name")] += 1
    return {"types": dict(types), "blocks": dict(blocks),
            "tools": dict(tools), "chain": chain}


def verify(original: str, bleached: str) -> tuple[bool, str]:
    a, b = shape(original), shape(bleached)
    for k in ("types", "blocks", "tools", "chain"):
        if a[k] != b[k]:
            return False, f"{k} differs"
    # linkage must be isomorphic: the parent graph, rewritten consistently
    def links(t):
        m = {}
        for line in t.splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("uuid"):
                m[d["uuid"]] = d.get("parentUuid")
        return m
    la, lb = links(original), links(bleached)
    if len(la) != len(lb):
        return False, "different number of linked lines"
    order_a = list(la.items())
    order_b = list(lb.items())
    mapping = {}
    for (ua, pa), (ub, pb) in zip(order_a, order_b):
        mapping[ua] = ub
        if (pa is None) != (pb is None):
            return False, "parent presence differs"
    for (ua, pa), (ub, pb) in zip(order_a, order_b):
        if pa is not None and mapping.get(pa, pb) != pb:
            return False, "parent chain is not isomorphic"
    return True, "structure preserved"

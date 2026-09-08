#!/usr/bin/env python3
"""
test_mapping_totality.py — every key a digestor reads is accounted for.

`design-total-mapping.md`: hashing the record is only the same thing as
hashing the source object if the record holds everything the object held.
Where the mapping drops a key, the two diverge invisibly — the dropped key is
not in the record to be missed. Three such drops were found and fixed in
v0.2.13: `thinking.signature`, `toolcall.caller`, and structure inside a
list-shaped `tool_result.content` (docs/roadmap.md, "v0.2.13 — the fold",
build step 4).

The property, stated once rather than per violation:

    For every `message.content[]` block a transcript line carries, whose type
    is `thinking`, `tool_use` or `tool_result`, every key that block holds is
    recoverable from the params of the one node `session.py` mints for it.

`text` blocks are *parsed*, fanning out into however many prose nodes the
markdown contains, and *that* fan-out's totality is what
`records_to_session(session_to_records(f)) == lines` already covers via
`params["log"]` holding the whole line verbatim — a different, stronger
guarantee this file does not need to repeat. But v0.2.14 ("the recursion made
explicit") gives a text block one more node before it fans out at all: the
fragment `blob` delegation mints to store it, byte for byte, as a digestor
input like any other. That node's totality — is the whole block recoverable
from what got minted — is exactly this file's question, so text blocks are
included after all, checked the fourth way build step 6 names: "the delegated
value must equal the stored blob's bytes", i.e. `node["content"] == block`,
rather than a key-by-key `params` comparison like the other three (a `blob`
node's `params` hold storage metadata, not the block's own fields — the block
itself lives in `content`).

**Positional correlation, not a second mapping.** `SessionImporter` mints
exactly one `thinking`/`toolcall`/`tooloutput`/`blob` node per matching raw
block, in the order it scans them, and never reorders across a file. So the
raw blocks of these four types and the nodes of the four matching types can be
zipped by position rather than re-implemented — checking the real mapping's
output against the real input, not a second copy of the mapping that could
drift
from the first the way a hand-written SQL mirror can (`docs/queries.md`).

Sabotage, in the `tests/test_sabotage.py` idiom: patch `_tool_use` to stop
writing `caller` and the suite must go red. It currently stays green, which
is the whole point.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R    # noqa: E402
from src import session as S    # noqa: E402
from tests import tier as T     # noqa: E402

FIXTURES = T.sessions()

# raw block "type" -> the node type session.py mints for it, one each.
# "text" -> "blob" since v0.2.14: the fragment blob delegation mints for a
# non-empty text block, not a prose node itself (those fan out from it, and
# their own totality is `records_to_session` round-trip's job, not this
# file's — see the module docstring).
NODE_OF = {"thinking": "thinking", "tool_use": "toolcall",
          "tool_result": "tooloutput", "text": "blob"}


def _raw_blocks(path: Path) -> list[dict]:
    """Every `message.content[]` block of a mapped type, in file order.

    A `text` block with nothing but whitespace is skipped: `session.py`'s
    delegation mints no fragment blob for one either (the same condition
    `SessionImporter._delegate` uses, `not text.strip()`), so counting it here
    would break the positional zip against `_mapped_nodes` rather than catch
    a real drop.
    """
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        content = (d.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not (isinstance(b, dict) and b.get("type") in NODE_OF):
                continue
            if b["type"] == "text" and not (b.get("text") or "").strip():
                continue
            out.append(b)
    return out


def _is_list_fragment(blob_node: dict) -> bool:
    """True for a fragment blob delegated out of a `message.content[]` list
    entry, false for one delegated out of a bare string `content` (a line
    with no content *list* at all — `/{i}/message/content`, one segment
    shorter than `/{i}/message/content/{idx}`). `_raw_blocks` only reaches
    into list-shaped content, matching `message.content[]` in this file's
    stated property, so a string-content delegation is out of scope here the
    same way it always was — it is not a `message.content[]` block, it *is*
    `message.content`."""
    sel = (blob_node.get("params") or {}).get("selector_value") or ""
    return sel.count("/") == 4


def _mapped_nodes(recs: list) -> list[dict]:
    """Every thinking/toolcall/tooloutput node, plus every list-shaped-content
    fragment blob, in the order `Builder` appended them — which is scan
    order, since each is minted the instant its raw block is processed and
    nothing here reorders afterwards."""
    return [r for r in recs if r["record"] == "node"
            and r["type"] in NODE_OF.values()
            and (r["type"] != "blob" or _is_list_fragment(r))]


def uncovered_key(block: dict, node: dict) -> str | None:
    """The first key of `block` not recoverable from `node`, or None if every
    key is. `type` never counts: it is consumed structurally, by choosing
    which node type gets minted at all."""
    if NODE_OF.get(block.get("type")) != node["type"]:
        return "type"          # positions came out of step; not a key drop
    t = block["type"]
    if t == "text":
        # Delegation's mapping is not a `params` field-by-field one like the
        # other three — the whole block is the fragment blob's `content`,
        # verbatim (build step 6: "the delegated value must equal the stored
        # blob's bytes"). `store.py`'s `_digest` writes exactly
        # `records.canonical(node["content"])` to `storage/`, so equality
        # here is equality there too.
        return None if node.get("content") == block else "content"
    p = node.get("params") or {}
    if t == "thinking":
        mapped = {"thinking": p.get("text"), "signature": p.get("signature")}
    elif t == "tool_use":
        mapped = {"id": p.get("tool_use_id"), "name": p.get("name"),
                  "input": p.get("input"), "caller": p.get("caller")}
    else:                        # tool_result
        mapped = {"tool_use_id": p.get("tool_use_id"),
                  "is_error": bool(p.get("is_error")),
                  "content": p.get("text")}
    for k, v in block.items():
        if k == "type":
            continue
        if k not in mapped or mapped[k] != v:
            return k
    return None


def check_file(path: Path) -> list[str]:
    """Every dropped key in this one file, as `"type.key"` strings."""
    raw = _raw_blocks(path)
    recs, _ = S.session_to_records(path)
    nodes = _mapped_nodes(recs)
    if len(raw) != len(nodes):
        return [f"{len(raw)} raw blocks vs {len(nodes)} mapped nodes — "
                f"positional correlation broken, cannot check further"]
    problems = []
    for b, n in zip(raw, nodes):
        bad = uncovered_key(b, n)
        if bad:
            problems.append(f"{b['type']}.{bad}")
    return problems


def main():
    results = []

    def case(name, ok, detail=""):
        results.append((ok, name, detail))
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")

    # -- the property, on every fixture and (if fetched) every corpus session
    all_problems = {}
    total_blocks = 0
    for f in FIXTURES:
        total_blocks += len(_raw_blocks(f))
        p = check_file(f)
        if p:
            all_problems[f.name] = p
    detail = (f"{total_blocks} blocks over {len(FIXTURES)} files"
             if not all_problems else
             "; ".join(f"{k}: {v[:3]}" for k, v in list(all_problems.items())[:3]))
    case("every key of every thinking/tool_use/tool_result/text block is "
         "recoverable from its node", not all_problems and total_blocks > 0,
         detail)

    # -- sabotage: prove the check is not vacuous, the test_sabotage.py idiom
    if FIXTURES:
        # Pick a fixture that actually carries what the sabotage strips.
        # Selecting on "has any blocks" chose session-slash.jsonl, which has
        # no `tool_use.caller`, so the sabotage skipped itself and the board
        # quietly went from 2/2 to 1/1 — a check that weakens without failing
        # is worse than no check (TODO-code-review.md, item 2).
        probe = next((f for f in FIXTURES
                      if any(b.get("type") == "tool_use" and "caller" in b
                             for b in _raw_blocks(f))),
                     next((f for f in FIXTURES if _raw_blocks(f)), FIXTURES[0]))
        orig = S.SessionImporter._tool_use

        def stripped(self, block):
            block = dict(block)
            block.pop("caller", None)
            guid = self.b.node("toolcall", {
                "name": block.get("name"),
                "tool_use_id": block.get("id"),
                "input": block.get("input", {}),
            })
            self.calls[block.get("id")] = guid
            return guid

        has_caller = any(b.get("type") == "tool_use" and "caller" in b
                         for b in _raw_blocks(probe))
        if has_caller:
            S.SessionImporter._tool_use = stripped
            try:
                sabotaged = check_file(probe)
            finally:
                S.SessionImporter._tool_use = orig
            case("sabotage: dropping `caller` from the mapping turns the "
                 "check red", any("caller" in p for p in sabotaged),
                 f"problems found: {sabotaged[:3]}")
        else:
            case("sabotage: dropping `caller` from the mapping turns the "
                 "check red", None, "no tool_use.caller in this fixture set")

    ran = [r for r in results if r[0] is not None]
    total = len(ran)
    passed = sum(1 for ok, _, _ in ran if ok)
    print(f"\n{passed}/{total} mapping-totality guarantees hold")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

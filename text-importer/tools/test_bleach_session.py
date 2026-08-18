#!/usr/bin/env python3
"""
test_bleach_session.py — the session fixtures are safe and still useful.

Two different promises, and both have to hold once the originals are gone:
the fixtures must carry no content from the logs they came from, and they must
still exercise everything a session importer needs — line types, block types,
tool names, and an intact parent chain.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bleach_session as B    # noqa: E402
from bleach import LOREM      # noqa: E402

FIXTURES = sorted((Path(__file__).parent.parent / "fixtures/sessions").glob("*.jsonl"))

SYNTHETIC = "\n".join(json.dumps(d) for d in [
    {"type": "user", "uuid": "11111111-1111-1111-1111-111111111111",
     "parentUuid": None, "cwd": "/Users/someone/PROJECTS/secret-thing",
     "message": {"role": "user", "content": [
         {"type": "text", "text": "my private note about the merger"}]}},
    {"type": "assistant", "uuid": "22222222-2222-2222-2222-222222222222",
     "parentUuid": "11111111-1111-1111-1111-111111111111",
     "message": {"role": "assistant", "content": [
         {"type": "thinking", "thinking": "reasoning that should not survive"},
         {"type": "tool_use", "id": "toolu_abc", "name": "Bash",
          "input": {"command": "cat /etc/passwd"}}]}},
    {"type": "file-history-snapshot",
     "snapshot": {"trackedFileBackups": {
         "/Users/someone/PROJECTS/secret-thing/plan.md": {"backup": "x"}}}},
])


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    out = B.bleach_session(SYNTHETIC, salt="test")

    def structure_holds():
        ok, why = B.verify(SYNTHETIC, out)
        return ok, why
    case("structure survives bleaching", structure_holds)

    def secrets_gone():
        leaks = [w for w in ("private", "merger", "passwd", "secret", "someone",
                             "reasoning", "survive", "plan")
                 if re.search(rf"\b{w}", out, re.I)]
        return not leaks, f"no content words survive ({leaks or 'none'})"
    case("prose, commands and paths are destroyed", secrets_gone)

    def paths_as_keys_gone():
        return "secret-thing" not in out, \
            "a path in key position is bleached too"
    case("paths hiding in dict keys are caught", paths_as_keys_gone)

    def linkage_kept():
        lines = [json.loads(l) for l in out.splitlines()]
        uuids = {d["uuid"] for d in lines if d.get("uuid")}
        parents = {d["parentUuid"] for d in lines if d.get("parentUuid")}
        return parents <= uuids and len(uuids) == 2, \
            "parentUuid still points at a line that exists"
    case("the parent chain stays intact", linkage_kept)

    def tools_kept():
        return '"name": "Bash"' in out or '"name":"Bash"' in out, \
            "tool names survive, or the fixture tests nothing"
    case("tool names are preserved", tools_kept)

    def committed_fixtures_clean():
        if not FIXTURES:
            return False, "no session fixtures found"
        text = "\n".join(f.read_text() for f in FIXTURES)
        bad = [w for w in ("ladjanszki", "PROJECTS", "compost", "knowledge-graph")
               if w in text]
        return not bad, f"{len(FIXTURES)} fixtures, no leaked identifiers"
    case("the committed fixtures leak nothing", committed_fixtures_clean)

    def committed_fixtures_useful():
        types, blocks, tools = Counter(), Counter(), Counter()
        for f in FIXTURES:
            s = B.shape(f.read_text())
            types.update(s["types"]); blocks.update(s["blocks"]); tools.update(s["tools"])
        ok = (blocks.get("tool_use", 0) > 100 and blocks.get("thinking", 0) > 50
              and blocks.get("text", 0) > 100 and len(tools) >= 5
              and types.get("assistant", 0) > 500)
        return ok, (f"{sum(types.values())} lines, "
                    f"{blocks.get('tool_use',0)} tool calls, "
                    f"{blocks.get('thinking',0)} thinking, {len(tools)} tools")
    case("the fixtures still exercise a real importer",
         committed_fixtures_useful)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<44} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} session-fixture guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

"""
Source preservation: the base keeps its own copy of what it ingested.

Before this, an imported conversation's source lived only in
`~/.claude/projects/` — outside the base, outside git, owned by another tool's
storage layout. Everything the importer drops on purpose (`sessionId`,
`parentUuid`, `turn_duration`, the slash-command events recording where a
conversation was branched) existed nowhere the base could reach, so no future
version could recover it.

Run: conda run -n knowledge-graph python tests/test_preserve/test_preserve.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from src.importer import preserve_source

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
        FAILURES.append(name)


def line(uuid: str, text: str) -> str:
    return json.dumps({"type": "user", "uuid": uuid, "sessionId": "s1",
                       "message": {"role": "user", "content": text}}) + "\n"


# --------------------------------------------------------------------------
# TP-1  The log lands in raw/
# --------------------------------------------------------------------------
def tp1_stored():
    print("\nTP-1: an imported log is copied into raw/")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        raw = d / "raw"
        log = d / "sess.jsonl"
        log.write_text(line("a", "one") + line("b", "two"))

        r = preserve_source(raw, "conv1", log)
        dest = raw / "conv1" / "sess.jsonl"

        check("status is stored", r["status"] == "stored", r["status"])
        check("the file exists in raw/", dest.exists())
        check("it is byte-identical to the source",
              dest.read_bytes() == log.read_bytes())
        check("line count reported", r["added"] == 2, str(r["added"]))


# --------------------------------------------------------------------------
# TP-2  A refresh grows the copy and is idempotent
# --------------------------------------------------------------------------
def tp2_grows():
    print("\nTP-2: refreshing a live session appends, and repeats are no-ops")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        raw = d / "raw"
        log = d / "sess.jsonl"
        log.write_text(line("a", "one"))
        preserve_source(raw, "conv1", log)

        # the session continues
        log.write_text(line("a", "one") + line("b", "two"))
        r = preserve_source(raw, "conv1", log)
        check("status is grew", r["status"] == "grew", r["status"])
        check("one line was added", r["added"] == 1, str(r["added"]))

        r = preserve_source(raw, "conv1", log)
        check("importing again is unchanged", r["status"] == "unchanged", r["status"])

        check("the copy matches the source",
              (raw / "conv1" / "sess.jsonl").read_bytes() == log.read_bytes())


# --------------------------------------------------------------------------
# TP-3  A rewritten log is refused, not absorbed
# --------------------------------------------------------------------------
def tp3_refuses_rewrite():
    print("\nTP-3: a log that was rewritten rather than appended to is refused")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        raw = d / "raw"
        log = d / "sess.jsonl"
        log.write_text(line("a", "one") + line("b", "two"))
        preserve_source(raw, "conv1", log)
        before = (raw / "conv1" / "sess.jsonl").read_bytes()

        # history rewritten underneath us: the first turn changed
        log.write_text(line("a", "CHANGED") + line("b", "two"))
        try:
            preserve_source(raw, "conv1", log)
            check("a rewritten log raises", False, "it overwrote silently")
        except ValueError as e:
            check("a rewritten log raises", "rewritten" in str(e), str(e))

        check("the stored copy was left untouched",
              (raw / "conv1" / "sess.jsonl").read_bytes() == before,
              "the record of what was ingested was destroyed")


# --------------------------------------------------------------------------
# TP-4  What the importer drops is recoverable from the copy
# --------------------------------------------------------------------------
def tp4_dropped_fields_survive():
    print("\nTP-4: the fields the importer discards survive in raw/")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        raw = d / "raw"
        log = d / "sess.jsonl"
        log.write_text(
            json.dumps({"type": "system", "subtype": "local_command",
                        "sessionId": "child", "parentUuid": "p1",
                        "content": "<local-command-stdout>Branched conversation"
                                   " from parent-session</local-command-stdout>"}) + "\n"
            + json.dumps({"type": "system", "subtype": "turn_duration",
                          "sessionId": "child", "durationMs": 4200}) + "\n"
            + line("a", "a real turn"))

        preserve_source(raw, "conv1", log)
        stored = (raw / "conv1" / "sess.jsonl").read_text()

        check("the branch event survives", "Branched conversation" in stored)
        check("turn_duration survives", "turn_duration" in stored)
        check("sessionId survives", "sessionId" in stored)
        check("parentUuid survives", "parentUuid" in stored)


# --------------------------------------------------------------------------
# TP-5  Sabotage: without the append-only guard, evidence is destroyed
# --------------------------------------------------------------------------
def tp5_sabotage():
    print("\nTP-5: sabotage — a plain overwrite loses the ingested record")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        dest = d / "sess.jsonl"
        dest.write_text(line("a", "one") + line("b", "two"))
        original = dest.read_bytes()

        # what the naive implementation does
        rewritten = line("a", "CHANGED") + line("b", "two")
        dest.write_text(rewritten)

        check("a plain overwrite destroys the original, which is why the "
              "guard exists", dest.read_bytes() != original)


if __name__ == "__main__":
    print("=" * 70)
    print("Source preservation")
    print("=" * 70)
    tp1_stored()
    tp2_grows()
    tp3_refuses_rewrite()
    tp4_dropped_fields_survive()
    tp5_sabotage()
    print("\n" + "=" * 70)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")

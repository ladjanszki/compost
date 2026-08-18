#!/usr/bin/env python3
"""
roundtrip.py — assert that a document survives a pandoc round-trip.

The property tested is the *AST fixed point*, not a byte diff:

    doc -> AST1 -> doc' -> AST2 ,  assert AST1 == AST2

A byte diff measures the author's typing habits. Pandoc deliberately does not
record whether a heading was setext or ATX, how wide a list was indented, or
how many blank lines separated two paragraphs, so comparing bytes reports
failures that are not losses. What must survive is what the graph stores, and
the graph stores the AST.

Usage:
    python3 -m src.roundtrip [path ...]          default: tests/fixtures/
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

READ = ["-f", "commonmark_x-smart-attributes-fancy_lists"]
WRITE = ["-t", "commonmark_x-smart", "--wrap=preserve"]

# Fixtures that do not reach a fixed point because of a defect in pandoc's
# writer, not in anything we control. Each is documented in decisions.md.
# They are listed rather than deleted: the fixture is the evidence, and the
# day pandoc fixes one, this suite says so by turning an xfail into a pass.
KNOWN_FAILURES = {
    "code-blocks.md": "code block inside a tight list item is written with no "
                      "blank line, so it re-reads as paragraph text",
    "task-lists.md":  "writer injects <!-- --> to keep adjacent lists apart; "
                      "it re-reads as a RawBlock nobody wrote",
    "blockquotes.md": "same <!-- --> injection, inside a quote",
}


def pandoc(args, data=None, path=None):
    cmd = ["pandoc", *args]
    if path:
        cmd.append(str(path))
    r = subprocess.run(cmd, input=data, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"pandoc {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def blocks(doc):
    return json.loads(doc)["blocks"]


def count(bs):
    n = 0
    for b in bs:
        n += 1
        if b["t"] == "BulletList":
            for i in b["c"]:
                n += count(i)
        elif b["t"] == "OrderedList":
            for i in b["c"][1]:
                n += count(i)
    return n


def types(x, acc=None):
    acc = acc if acc is not None else Counter()
    if isinstance(x, dict):
        if "t" in x:
            acc[x["t"]] += 1
        for v in x.values():
            types(v, acc)
    elif isinstance(x, list):
        for v in x:
            types(v, acc)
    return acc


def check(path):
    ast1 = pandoc([*READ, "-t", "json"], path=path)
    text2 = pandoc(["-f", "json", *WRITE], data=ast1)
    ast2 = pandoc([*READ, "-t", "json"], data=text2)
    a, b = blocks(ast1), blocks(ast2)
    meta1 = json.loads(ast1)["meta"]
    return {
        "path": path,
        "ok": a == b,
        "blocks": count(a),
        "bytes_same": path.read_text() == text2,
        "meta": bool(meta1),
        "a": a, "b": b,
    }


def explain(r):
    """Name what drifted, rather than dumping two ASTs."""
    ta, tb = types(r["a"]), types(r["b"])
    gone = ta - tb
    new = tb - ta
    bits = []
    if gone:
        bits.append("lost " + ", ".join(f"{k}x{v}" for k, v in gone.most_common(4)))
    if new:
        bits.append("gained " + ", ".join(f"{k}x{v}" for k, v in new.most_common(4)))
    return "; ".join(bits) or "same node types, different content or order"


def main(argv):
    roots = [Path(a) for a in argv[1:]] or [Path(__file__).parent.parent / "tests" / "fixtures"]
    files = sorted(
        f for root in roots
        for f in ([root] if root.is_file() else root.rglob("*.md"))
    )
    if not files:
        print("no .md files found")
        return 1

    passed = failed = xfailed = 0
    identical = 0
    total_blocks = 0
    failures = []
    for f in files:
        try:
            r = check(f)
        except RuntimeError as e:
            failed += 1
            failures.append((f, str(e)))
            continue
        total_blocks += r["blocks"]
        identical += r["bytes_same"]
        known = KNOWN_FAILURES.get(f.name)
        if r["ok"]:
            passed += 1
            if known:
                print(f"XPASS {f.name}\n      known failure no longer reproduces: {known}")
        elif known:
            xfailed += 1
        else:
            failed += 1
            failures.append((f, explain(r)))

    for f, why in failures:
        print(f"FAIL  {f}\n      {why}")
    print(f"\n{passed}/{passed + failed + xfailed} fixed point"
          f"   |   {xfailed} known pandoc defects"
          f"   |   {identical}/{len(files)} byte-identical"
          f"   |   {total_blocks} addressable blocks")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

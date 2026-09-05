#!/usr/bin/env python3
"""
test_records.py — the acceptance test for the record format.

    records_to_ast(*ast_to_records(ast)) == ast

on every fixture and every document in corpus/, plus the structural invariants
the design says must hold. Usage:  python3 tools/test_records.py [path ...]
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R  # noqa: E402

READ = ["-f", "commonmark_x-smart-attributes-fancy_lists"]
HERE = Path(__file__).parent


def ast_of(path):
    r = subprocess.run(["pandoc", *READ, "-t", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


def invariants(recs, root):
    """Everything the design promises about the shape of the graph."""
    problems = []
    nodes = {r["guid"] for r in recs if r["record"] == "node"}
    edges = [r for r in recs if r["record"] == "edge"]

    parents = Counter(e["destination"] for e in edges if e["type"] == "contains")
    orphans = nodes - set(parents) - {root}
    if orphans:
        problems.append(f"{len(orphans)} node(s) with no parent")
    twice = [g for g, n in parents.items() if n > 1]
    if twice:
        problems.append(f"{len(twice)} node(s) with two parents")
    if parents.get(root):
        problems.append("document root has a parent")

    # guid uniqueness, and no guid carrying two different contents
    seen = {}
    for r in recs:
        key = r["guid"]
        if key in seen and seen[key] != r:
            problems.append("a guid appears twice with different content")
            break
        seen[key] = r

    # acyclic containment
    kids = {}
    for e in edges:
        if e["type"] == "contains":
            kids.setdefault(e["source"], []).append(e["destination"])
    colour = {}

    def visit(g):
        colour[g] = 1
        for k in kids.get(g, []):
            if colour.get(k) == 1:
                return True
            if not colour.get(k) and visit(k):
                return True
        colour[g] = 2
        return False
    if visit(root):
        problems.append("cycle in the contains graph")

    # next chains: Graph.children raises on any malformed chain
    g = R.Graph(recs)
    for parent in list(kids):
        try:
            g.children(parent)
        except ValueError as e:
            problems.append(str(e))
            break

    # record_hash and record_subtree_hash present on every node, and both
    # recompute — the fold, docs/roadmap.md "v0.2.13 — the fold".
    for r in recs:
        if r["record"] != "node":
            continue
        if "record_hash" not in r or "record_subtree_hash" not in r:
            problems.append(f"{r['type']}: missing record_hash or "
                            f"record_subtree_hash")
            break
        if r["record_hash"] != R.record_hash(r):
            problems.append(f"{r['type']}: record_hash does not recompute")
            break
    return problems


def main(argv):
    roots = [Path(a) for a in argv[1:]] or [HERE / "fixtures", HERE / "corpus"]
    # `*.json` here means "a pandoc AST fixture", and that is a claim about
    # what is *in* the file, not about its extension — so the sweep is narrowed
    # to where AST fixtures live. It used to rglob the whole tree and swallowed
    # a transcript's `agent-<id>.meta.json` sidecar the day one appeared, which
    # is the same mistake `digest` stopped making: deciding what a file is from
    # what it is called.
    files = sorted(f for root in roots
                   for f in ([root] if root.is_file()
                             else list(root.rglob("*.md"))
                             + list(root.rglob("ast/*.json"))))
    if not files:
        print("no .md files found")
        return 1

    ok = bad = 0
    kinds = Counter()
    total_nodes = total_edges = 0
    for f in files:
        try:
            # A .json fixture is an AST directly: the only way to reach the
            # constructors our reader cannot produce but another input format
            # could — Figure, LineBlock, and tables with spans and a foot.
            ast = json.loads(f.read_text()) if f.suffix == ".json" else ast_of(f)
            recs, root = R.ast_to_records(ast)
            recs = R.from_jsonl(R.to_jsonl(recs))       # survives serialisation
            back = R.records_to_ast(recs, root)
        except Exception as e:
            bad += 1
            print(f"ERROR {f.relative_to(HERE)}\n      {type(e).__name__}: {e}")
            continue
        total_nodes += sum(1 for r in recs if r["record"] == "node")
        total_edges += sum(1 for r in recs if r["record"] == "edge")
        for r in recs:
            if r["record"] == "node":
                kinds[r["type"]] += 1
        problems = invariants(recs, root)
        if back == ast and not problems:
            ok += 1
        else:
            bad += 1
            print(f"FAIL  {f.relative_to(HERE)}")
            if back != ast:
                print("      round-trip is not the identity")
            for p in problems:
                print(f"      {p}")

    print("\nnode types: "
          + ", ".join(f"{k}={v}" for k, v in kinds.most_common()))
    print(f"{ok}/{ok + bad} identity round-trip"
          f"   |   {total_nodes} nodes, {total_edges} edges")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

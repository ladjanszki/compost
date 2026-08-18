#!/usr/bin/env python3
"""
test_sabotage.py — verify that the invariants fail when they should.

A check that has never rejected anything is not known to work. Each case here
reintroduces one defect the design claims to prevent and asserts that
something complains — either an invariant or the round-trip itself.

The `wrap` case is the interesting one: nothing structural is wrong after it,
and no invariant fires. It is caught because a tight list comes back loose,
which is the whole reason `params.wrap` exists.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R                       # noqa: E402
from tests.test_records import invariants, ast_of   # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures/edge-cases/nested-lists.md"


def _contains(recs):
    kids = {}
    for r in recs:
        if r["record"] == "edge" and r["type"] == "contains":
            kids.setdefault(r["source"], []).append(r["destination"])
    return kids


def drop_next(recs):
    for i, r in enumerate(recs):
        if r["record"] == "edge" and r["type"] == "next":
            del recs[i]
            return


def two_parents(recs):
    e = [r for r in recs if r["record"] == "edge" and r["type"] == "contains"]
    recs.append({**e[-1], "guid": "sabotage", "source": e[0]["source"]})


def cross_parent(recs):
    kids = _contains(recs)
    ps = [p for p, k in kids.items() if len(k) > 1][:2]
    recs.append({"record": "edge", "guid": "sabotage", "layer": R.LAYER,
                 "type": "next", "source": kids[ps[0]][-1],
                 "destination": kids[ps[1]][0]})


def cycle(recs):
    p = [k for k in _contains(recs).values() if len(k) > 2][0]
    recs.append({"record": "edge", "guid": "sabotage", "layer": R.LAYER,
                 "type": "next", "source": p[-1], "destination": p[0]})


def strip_wrap(recs):
    for r in recs:
        if r["record"] == "node" and r["type"] == "ListItem" and "params" in r:
            r["params"].pop("wrap", None)
            return


def bogus_hash(recs):
    for r in recs:
        if r["record"] == "node" and r["type"] == "BulletList":
            r["content_hash"] = "0" * 64
            return


CASES = [
    ("a dropped next edge", drop_next),
    ("a node with two parents", two_parents),
    ("a next edge crossing parents", cross_parent),
    ("a cycle in the next chain", cycle),
    ("a ListItem with wrap removed", strip_wrap),
    ("content_hash on a node with no content", bogus_hash),
]


def main():
    ast = ast_of(FIXTURE)
    base, root = R.ast_to_records(ast)
    missed = 0
    for name, fn in CASES:
        recs = copy.deepcopy(base)
        fn(recs)
        problems = invariants(recs, root)
        try:
            round_trips = R.records_to_ast(recs, root) == ast
        except Exception:
            round_trips = False
        caught = bool(problems) or not round_trips
        why = problems[0] if problems else "round-trip is no longer the identity"
        print(f"  {'caught ' if caught else 'MISSED '} {name:<40} {why if caught else ''}")
        missed += not caught
    print(f"\n{len(CASES) - missed}/{len(CASES)} sabotages caught")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())

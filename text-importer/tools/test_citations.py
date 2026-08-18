#!/usr/bin/env python3
"""
test_citations.py — `{@handle}` in the text becomes an edge in the graph.

The syntax matters as much as the mechanism. `{#x}` means "this element *has*
id x" in every markup language that knows the notation, and pandoc and djot
both act on it. Using it to mean "points at x" was backwards, and any reader
with `attributes` enabled silently agreed with the language rather than with
us. `{@x}` says what it means and no parser claims it.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import records as R  # noqa: E402

RD = "commonmark_x-smart-attributes-fancy_lists"


def ingest(src: str):
    ast = json.loads(subprocess.run(["pandoc", "-f", RD, "-t", "json"],
                                    input=src, capture_output=True,
                                    text=True).stdout)
    return R.ast_to_records(ast)


def cite(recs, source_type, handle):
    """Put a citation into the text of the first node of a given type."""
    for r in recs:
        if r["record"] == "node" and r["type"] == source_type:
            r["content"] = r["content"] + [{"t": "Space"},
                                           {"t": "Str", "c": "{@" + handle + "}"}]
            return r["guid"]
    raise AssertionError(f"no {source_type} node")


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    def resolves():
        recs, _ = ingest("First paragraph.\n\n## A heading\n")
        target = next(r for r in recs if r["record"] == "node"
                      and r["type"] == "Header")
        src = cite(recs, "Para", target["guid"][:R.HANDLE_LEN])
        edges, unresolved = R.citation_edges(recs)
        ok = (len(edges) == 1 and not unresolved
              and edges[0]["source"] == src
              and edges[0]["destination"] == target["guid"]
              and edges[0]["layer"] == R.CITATION_LAYER
              and edges[0]["type"] == "cites")
        return ok, "one edge, pointing the right way"
    case("a citation becomes an edge", resolves)

    def unresolved_is_reported():
        recs, _ = ingest("A paragraph.\n")
        cite(recs, "Para", "deadbeef")
        edges, unresolved = R.citation_edges(recs)
        return not edges and unresolved == ["deadbeef"], \
            "an invented handle is reported, not silently dropped"
    case("an unresolvable handle is reported", unresolved_is_reported)

    def hash_is_not_a_citation():
        recs, _ = ingest("First paragraph.\n\n## A heading\n")
        target = next(r for r in recs if r["record"] == "node"
                      and r["type"] == "Header")
        for r in recs:
            if r["record"] == "node" and r["type"] == "Para":
                r["content"] += [{"t": "Str",
                                  "c": "{#" + target["guid"][:R.HANDLE_LEN] + "}"}]
                break
        edges, unresolved = R.citation_edges(recs)
        return not edges and not unresolved, \
            "{#x} is an id, not a reference, and produces nothing"
    case("{#handle} is not read as a citation", hash_is_not_a_citation)

    def survives_the_pipeline():
        # the syntax has to come back out of a real read/write cycle intact
        src = "A paragraph citing {@a1b2c3d4} and {@a1b2c3d4+++} inline.\n"
        out = subprocess.run(["pandoc", "-f", RD, "-t", "commonmark_x-smart",
                              "--wrap=preserve"],
                             input=json.dumps(json.loads(subprocess.run(
                                 ["pandoc", "-f", RD, "-t", "json"], input=src,
                                 capture_output=True, text=True).stdout)),
                             capture_output=True, text=True)
        return ("{@a1b2c3d4}" in out.stdout and "{@a1b2c3d4+++}" in out.stdout), \
            "unescaped through read and write"
    case("the syntax survives a round-trip", survives_the_pipeline)

    def many_in_one_block():
        recs, _ = ingest("Para one.\n\n## H one\n\n## H two\n")
        hs = [r for r in recs if r["record"] == "node" and r["type"] == "Header"]
        for r in recs:
            if r["record"] == "node" and r["type"] == "Para":
                for h in hs:
                    r["content"] += [{"t": "Space"},
                                     {"t": "Str",
                                      "c": "{@" + h["guid"][:R.HANDLE_LEN] + "}"}]
                break
        edges, _ = R.citation_edges(recs)
        return len(edges) == 2, "two citations in one block make two edges"
    case("several citations in one block", many_in_one_block)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<42} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} citation guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

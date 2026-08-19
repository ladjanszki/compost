#!/usr/bin/env python3
"""
test_citations.py — a citation is a link, and a link is a node.

The syntax was chosen for a structural reason rather than an aesthetic one.
`{#x}` means "this element *has* id x" in every markup language that knows the
notation, so using it for "points at x" was backwards and any reader with
`attributes` enabled agreed with the language instead of with us. `{@x}` fixed
the meaning but not the mechanism: it was still text, so extraction was a regex
over flattened content, and a handle quoted inside a code block became a real
edge. This corpus quotes its own syntax constantly, so that was not
hypothetical.

`[-](#<guid>)` is a `Link` node. A code block holds text with no inlines, so it
contains no links and *cannot* contribute a citation however often it shows the
syntax. The rule CLAUDE.md says has been broken three times becomes a property
of the format rather than something to remember.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import records as R  # noqa: E402

RD = "commonmark_x-smart-attributes-fancy_lists"


def ingest(src: str):
    ast = json.loads(subprocess.run(["pandoc", "-f", RD, "-t", "json"],
                                    input=src, capture_output=True,
                                    text=True).stdout)
    return R.ast_to_records(ast)


def link(target: str, text: str = "-") -> dict:
    return {"t": "Link", "c": [["", [], []],
                               [{"t": "Str", "c": text}], ["#" + target, ""]]}


def cite(recs, node_type, target, text="-"):
    for r in recs:
        if r["record"] == "node" and r["type"] == node_type:
            r["content"] = r["content"] + [{"t": "Space"}, link(target, text)]
            return r["guid"]
    raise AssertionError(f"no {node_type} node")


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
        src = cite(recs, "Para", target["guid"])
        edges, unresolved = R.citation_edges(recs)
        ok = (len(edges) == 1 and not unresolved
              and edges[0]["source"] == src
              and edges[0]["destination"] == target["guid"]
              and edges[0]["layer"] == R.CITATION_LAYER
              and edges[0]["type"] == "cites")
        return ok, "one edge, pointing the right way"
    case("a link to a handle becomes an edge", resolves)

    def code_block_is_not_a_citation():
        recs, _ = ingest("A paragraph.\n\n## Target\n")
        target = next(r for r in recs if r["record"] == "node"
                      and r["type"] == "Header")
        # the exact defect the old text-based extractor had
        for r in recs:
            if r["record"] == "node" and r["type"] == "Para":
                r["content"] = r["content"]
                break
        recs.append({"record": "node", "guid": "11111111-1111-1111-1111-111111111111",
                     "type": "CodeBlock",
                     "params": {"attr": ["", [], []],
                                "text": f"you cite it as [-](#{target['guid']})"},
                     "content_hash": "0" * 64})
        edges, unresolved = R.citation_edges(recs)
        return not edges and not unresolved, \
            "a handle quoted inside a code block produces nothing"
    case("code blocks cannot cite", code_block_is_not_a_citation)

    def ordinary_link_ignored():
        recs, _ = ingest("A paragraph.\n")
        for r in recs:
            if r["record"] == "node" and r["type"] == "Para":
                r["content"] += [{"t": "Space"}, link("some-heading", "the section")]
                break
        edges, unresolved = R.citation_edges(recs)
        return not edges and not unresolved, \
            "a link to a heading anchor is not a citation"
    case("an ordinary anchor link is not a citation", ordinary_link_ignored)

    def unresolved_reported():
        recs, _ = ingest("A paragraph.\n")
        cite(recs, "Para", "deadbeef-0000-0000-0000-000000000000")
        edges, unresolved = R.citation_edges(recs)
        return not edges and len(unresolved) == 1, \
            "an invented handle is reported, not silently dropped"
    case("an unresolvable handle is reported", unresolved_reported)

    def prefix_is_not_a_handle():
        recs, _ = ingest("A paragraph.\n\n## Target\n")
        target = next(r for r in recs if r["record"] == "node"
                      and r["type"] == "Header")
        cite(recs, "Para", target["guid"][:8])
        edges, unresolved = R.citation_edges(recs)
        # Not merely unresolved — a prefix does not match HANDLE_RE at all, so
        # it is an ordinary link and never claims to be a citation. There was a
        # resolver that accepted any unambiguous length; it was removed rather
        # than left as an optimisation nobody had asked for.
        return not edges and not unresolved, \
            "a prefix is an ordinary link, not a short handle"
    case("a shortened handle is not a citation", prefix_is_not_a_handle)

    def display_text_is_free():
        recs, _ = ingest("A paragraph.\n\n## Target\n")
        target = next(r for r in recs if r["record"] == "node"
                      and r["type"] == "Header")
        cite(recs, "Para", target["guid"], text="the em dash argument")
        edges, _ = R.citation_edges(recs)
        return len(edges) == 1, "prose link text cites the same block"
    case("the link text carries no meaning", display_text_is_free)

    def survives_the_pipeline():
        src = "A paragraph citing [-](#d826c4dd-eb36-4da9-acab-f6f424a90803).\n"
        a = subprocess.run(["pandoc", "-f", RD, "-t", "json"], input=src,
                           capture_output=True, text=True).stdout
        outs = {}
        for w in ("djot", "commonmark_x-smart"):
            outs[w] = subprocess.run(["pandoc", "-f", "json", "-t", w,
                                      "--wrap=preserve"], input=a,
                                     capture_output=True, text=True).stdout
        ok = all("[-](#d826c4dd-eb36-4da9-acab-f6f424a90803)" in v
                 for v in outs.values())
        return ok, "unescaped through both writers, unlike {@x} and [[x]]"
    case("the syntax survives every writer", survives_the_pipeline)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<44} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} citation guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

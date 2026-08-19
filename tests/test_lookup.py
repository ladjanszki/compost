#!/usr/bin/env python3
"""
test_lookup.py — resolving a handle, and finding what cites it.

`lookup` is the first thing in the program to call `citation_edges`, which
until now only tests ever called. That matters: `cites` edges are a projection
of the text and nothing persists them, so the backlinks a lookup prints are
derived over the whole loaded base at the moment you ask. The cases below pin
both halves — that a prefix resolves exactly when it is unambiguous, and that
"what cites this" inherits the property citations already have, namely that a
handle quoted inside code is not a citation.
"""
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli             # noqa: E402
from src import records as R    # noqa: E402
from src import store as S      # noqa: E402

TARGET = "A target paragraph worth citing.\n\nAnother block entirely.\n"


def build(tmp: Path):
    """A base with one cited paragraph, and two decoys that must not count."""
    st = S.Store.init(tmp)
    a = tmp / "a.md"
    a.write_text(TARGET)
    recs, _ = R.ast_to_records(S._ast_of(a), source=a.name)
    st.write("a-md.jsonl", recs)
    guid = next(r["guid"] for r in recs
                if r["record"] == "node" and r["type"] == "Para")

    b = tmp / "b.md"
    b.write_text(f"See [-](#{guid}) for the point.\n\n"
                 f"Inline code span: `[-](#{guid})` is not a citation.\n\n"
                 f"```\n[-](#{guid})\n```\n")
    recs_b, _ = R.ast_to_records(S._ast_of(b), source=b.name)
    st.write("b-md.jsonl", recs_b)
    # The one node that really does cite: the prose paragraph, not the span and
    # not the fence. Named here so a test can assert *which* node cites rather
    # than how many do — a text-scanning implementation gets the count right by
    # finding the fenced block and losing the paragraph.
    citer = next(r["guid"] for r in recs_b
                 if r["record"] == "node" and r["type"] == "Para"
                 and R.plain_text(r).startswith("See"))
    return st, guid, citer


def run(tmp: Path, *args):
    """`compost <args>` inside `tmp`, captured. Returns (exit code, output)."""
    out = io.StringIO()
    here = Path.cwd()
    os.chdir(tmp)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(["compost", *args])
    finally:
        os.chdir(here)
    return code, out.getvalue()


def main():
    results = []

    def case(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((ok, name, detail))

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        st, guid, citer = build(tmp)
        recs, _ = st.load()
        index = R.prefix_index(recs)

        def exact():
            got, _ = R.resolve(guid, index)
            return got == guid, guid[:8]
        case("a full guid resolves to itself", exact)

        def every_prefix():
            lengths = range(R.MIN_HANDLE, len(guid) + 1)
            got = {R.resolve(guid[:n], index)[0] for n in lengths}
            return got == {guid}, f"lengths {R.MIN_HANDLE}..{len(guid)} agree"
        case("every unambiguous prefix resolves to the same node", every_prefix)

        def too_short():
            n = R.MIN_HANDLE - 1
            got, hits = R.resolve(guid[:n], index)
            return got is None and not hits, f"{n} chars is not a handle"
        case("a prefix below the minimum resolves to nothing", too_short)

        def ambiguous():
            # Two guids sharing a prefix cannot be minted, so they are built.
            twin = [{"record": "node", "guid": guid[:9] + "0" * 27,
                     "type": "Para"},
                    {"record": "node", "guid": guid[:9] + "1" * 27,
                     "type": "Para"}]
            got, hits = R.resolve(guid[:9], R.prefix_index(twin))
            return got is None and len(hits) == 2, "2 candidates, no winner"
        case("an ambiguous prefix resolves to nothing, with candidates",
             ambiguous)

        def absent():
            got, hits = R.resolve("deadbeef", index)
            return got is None and not hits, "no such handle"
        case("a handle that exists nowhere resolves to nothing", absent)

        def backlinks():
            edges, _ = R.citation_edges(recs)
            citers = [e["source"] for e in edges if e["destination"] == guid]
            # b.md writes the handle three times: prose, code span, fence. Only
            # the prose one is a citation, and it must be *that* node — asserting
            # the count alone passes for an implementation that finds the fence
            # and misses the paragraph.
            return citers == [citer], f"{len(citers)} citer of 3 written"
        case("only the prose citation counts, span and fence do not", backlinks)

        def cli_hit():
            code, out = run(tmp, "lookup", guid[:R.MIN_HANDLE])
            return (code == 0 and guid in out and "1 node, 1 citing" in out,
                    out.strip().splitlines()[-1])
        case("the CLI prints the node and its citer, exit 0", cli_hit)

        def cli_miss():
            code, out = run(tmp, "lookup", "deadbeef")
            return code == 1 and "0 nodes match" in out, out.strip()
        case("a miss exits 1 and says so", cli_miss)

        def cli_no_arg():
            code, out = run(tmp, "lookup")
            return code == 2 and "usage:" in out, out.strip()
        case("no handle is a usage error, exit 2", cli_no_arg)

        def survives_broken_graph():
            # `render` refuses on a broken graph; a query must not. One dangling
            # edge in another file should not make a good handle unresolvable.
            (st.graph / "junk.jsonl").write_text(
                '{"record": "edge", "guid": "deadbeef-0000-0000-0000-'
                '000000000001", "layer": "pandoc-ast", "type": "contains", '
                '"source": "deadbeef-0000-0000-0000-000000000000", '
                '"destination": "cafe0000-0000-0000-0000-000000000000"}\n')
            broken, _ = st.load()
            problems = bool(R.check(broken))
            code, out = run(tmp, "lookup", guid[:R.MIN_HANDLE])
            (st.graph / "junk.jsonl").unlink()
            return (problems and code == 0 and guid in out,
                    "check fails, lookup answers")
        case("a lookup answers even when check would fail",
             survives_broken_graph)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<52} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} lookup guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

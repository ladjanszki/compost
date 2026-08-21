#!/usr/bin/env python3
"""
test_lookup.py — resolving a handle to the node it names.

A handle is a whole guid. A prefix of one is not a shorter handle, it is not a
handle at all, and there is no resolver that would make it one — the cases
below pin that as a property rather than a convention, because the resolver
that used to accept any unambiguous length was removed on purpose.

`lookup` prints the node and stops there. What cites a block is a question for
the citation layer, which does not exist yet; answering it here would have
meant deriving `cites` edges on every query, and a layer built by accident at
query time is harder to replace than one that was never built.
"""
import contextlib
import io
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli             # noqa: E402
from src import records as R    # noqa: E402
from src import routes as RT    # noqa: E402
from src import store as S      # noqa: E402

TARGET = "A target paragraph worth citing.\n\nAnother block entirely.\n"


def build(tmp: Path):
    st = S.Store.init(tmp)
    a = tmp / "a.md"
    a.write_text(TARGET)
    recs, _ = R.ast_to_records(RT._ast_of(a), source=a.name)
    st.write("a-md.jsonl", recs)
    guid = next(r["guid"] for r in recs
                if r["record"] == "node" and r["type"] == "Para")
    return st, guid


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
        st, guid = build(tmp)

        def full_guid():
            code, out = run(tmp, "lookup", guid)
            return (code == 0 and guid in out and "A target paragraph" in out,
                    "node and its text")
        case("a full guid prints the node it names", full_guid)

        def no_prefix_resolves():
            codes = {run(tmp, "lookup", guid[:n])[0]
                     for n in range(1, len(guid))}
            return codes == {1}, f"all {len(guid) - 1} prefixes miss"
        case("no prefix of a guid resolves, at any length", no_prefix_resolves)

        def prefix_is_not_even_a_citation():
            # HANDLE_RE matches a whole guid only, so a prefix in a link is an
            # ordinary link: it cannot be an unresolved citation either.
            return (R.CITATION_TARGET.match("#" + guid) is not None
                    and R.CITATION_TARGET.match("#" + guid[:8]) is None,
                    "a prefix does not match HANDLE_RE")
        case("a prefix is not a handle by construction",
             prefix_is_not_even_a_citation)

        def absent():
            code, out = run(tmp, "lookup",
                            "deadbeef-0000-0000-0000-000000000000")
            return code == 1 and "no node with handle" in out, out.strip()
        case("a handle that exists nowhere exits 1 and says so", absent)

        def names_one_node():
            # The property, not the wording: a lookup mentions the node asked
            # for and no other. Backlinks would name a second, and that would
            # mean deriving the citation layer on every query, before it has
            # been designed. Matching guids rather than the words "cited by"
            # keeps this true however the output is later reworded.
            _, out = run(tmp, "lookup", guid)
            named = set(re.findall(R.HANDLE_RE, out))
            return named == {guid}, f"{len(named)} guid named"
        case("lookup names the node asked for and no other", names_one_node)

        def no_arg():
            code, out = run(tmp, "lookup")
            return code == 2 and "usage:" in out, out.strip()
        case("no handle is a usage error, exit 2", no_arg)

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
            code, out = run(tmp, "lookup", guid)
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

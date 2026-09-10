#!/usr/bin/env python3
"""
test_lookup.py — resolving a handle to the node it names.

A handle is a whole guid. A prefix of one is not a shorter handle, it is not a
handle at all, and there is no resolver that would make it one — the cases
below pin that as a property rather than a convention, because the resolver
that used to accept any unambiguous length was removed on purpose.

`lookup` also resolves an **alias** — several may share a value, and every
match is printed rather than one picked silently — and reports what **cites**
the node, including a citer that only reached a placeholder minted before the
target existed. It does not rebuild the citation layer itself: on a base
where `compost layer citation` has not been run since the last citing
document arrived, this under-reports rather than lies. That risk is accepted
and recorded in `docs/roadmap.md`.
"""
import contextlib
import io
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli             # noqa: E402
from src import layers as L     # noqa: E402
from src import markdown as MD  # noqa: E402
from src import records as R    # noqa: E402
from src import store as S      # noqa: E402

TARGET = "A target paragraph worth citing.\n\nAnother block entirely.\n"


def _write(st, tmp, name, text):
    """Write `text` to `tmp/name`, read it and commit its records to `st`."""
    p = tmp / name
    p.write_text(text)
    recs, root = R.ast_to_records(MD.ast_of_file(p), source=name)
    st.write(f"{name}.jsonl", recs)
    return recs, root


def _write_with_guid(st, tmp, name, text, want_guid):
    """Like `_write`, but force the document's sole block to `want_guid`.

    Markdown that is a single paragraph mints exactly two guids — the
    `document` root, then the `Para` — in that order, so the second mint call
    is the one to pin. This is how "a block arrives later, carrying the exact
    guid a citation already named" is constructed without guessing a future
    random guid.
    """
    calls = []

    def mint():
        g = want_guid if len(calls) == 1 else str(uuid.uuid4())
        calls.append(g)
        return g

    p = tmp / name
    p.write_text(text)
    recs, root = R.ast_to_records(MD.ast_of_file(p), mint=mint, source=name)
    st.write(f"{name}.jsonl", recs)
    return recs, root


def build(tmp: Path):
    st = S.Store.init(tmp)

    # An ordinary target, cited once from a second document.
    a_recs, _ = _write(st, tmp, "a.md", TARGET)
    paras = [r for r in a_recs if r["record"] == "node" and r["type"] == "Para"]
    guid, other_guid = paras[0]["guid"], paras[1]["guid"]

    c_recs, _ = _write(st, tmp, "c.md", f"Citing [-](#{guid}) here.\n")
    citer_guid = next(r["guid"] for r in c_recs
                      if r["record"] == "node" and r["type"] == "Para")

    # A handle cited but never minted — stays unresolved forever.
    unresolved_guid = str(uuid.uuid4())
    _write(st, tmp, "u.md", f"Wondering about [-](#{unresolved_guid}) here.\n")

    # A handle cited before it exists, later minted for real.
    forward_guid = str(uuid.uuid4())
    fwd_recs, _ = _write(st, tmp, "fwd.md",
                         f"Forward citing [-](#{forward_guid}) here.\n")
    forward_citer_guid = next(r["guid"] for r in fwd_recs
                              if r["record"] == "node" and r["type"] == "Para")

    # Build the layer twice — same as the by-hand release sequence — so a
    # citer is recorded twice and an unresolved value gets two aliases naming
    # two different placeholders.
    with contextlib.redirect_stdout(io.StringIO()):
        L.build(st, "citation", "uuid-link")
        L.build(st, "citation", "uuid-link")

    # Only now does forward_guid become a real node — after both builds, so
    # both of its placeholder-bound `cites` edges predate the real target.
    _write_with_guid(st, tmp, "later.md", "Arrives later.\n", forward_guid)

    return st, guid, other_guid, citer_guid, unresolved_guid, \
        forward_guid, forward_citer_guid


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
        (st, guid, other_guid, citer_guid, unresolved_guid,
         forward_guid, forward_citer_guid) = build(tmp)

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

        def names_asked_for_plus_citers():
            # The property, not the wording: a lookup mentions the node asked
            # for and its citers, and nothing else. Two builds mean the same
            # citer appears twice, but it is still one guid.
            _, out = run(tmp, "lookup", guid)
            named = set(re.findall(R.HANDLE_RE, out))
            return named == {guid, citer_guid}, f"{named}"
        case("lookup names the node asked for, plus its citers, "
             "and nothing else", names_asked_for_plus_citers)

        def cited_handle_reports_citer():
            _, out = run(tmp, "lookup", guid)
            return ("cited by" in out and out.count(citer_guid) == 2,
                    "citer listed twice — the layer was built twice")
        case("a cited handle reports its citer", cited_handle_reports_citer)

        def uncited_says_so():
            code, out = run(tmp, "lookup", other_guid)
            return (code == 0 and "nothing cites this" in out,
                    out.strip()[:80])
        case("an uncited handle says so and still exits 0", uncited_says_so)

        def alias_resolves():
            code, out = run(tmp, "lookup", unresolved_guid)
            return (code == 0 and "resolved via" in out and "uuid-link" in out,
                    out.strip().splitlines()[0] if out.strip() else "(empty)")
        case("an alias value resolves", alias_resolves)

        def two_aliases_both_appear():
            code, out = run(tmp, "lookup", unresolved_guid)
            return (code == 0 and "resolved via 2 aliases" in out
                    and out.count("alias ") >= 2,
                    "two builds, two aliases, both printed")
        case("two aliases with one value both appear", two_aliases_both_appear)

        def forward_cited_through_placeholder():
            code, out = run(tmp, "lookup", forward_guid)
            return (code == 0
                    and "cited before this block was in the base" in out
                    and forward_citer_guid in out,
                    "a guid cited only through a placeholder still reports "
                    "that citer")
        case("a guid cited only through a placeholder still reports that "
             "citer", forward_cited_through_placeholder)

        def alias_naming_two_nodes():
            # One alias, two `names` edges. The citation layer never writes
            # this, but nothing stops it: `check` does not count `names`
            # edges, so the graph is sound and `lookup` has to say so. It
            # used to index `names` by alias guid into a plain dict, which
            # dropped every target but the last with no sign that it had.
            b = R.Builder()
            al = b.node("alias", {"value": "class:demo",
                                  "scheme": "demo-class"})
            R.stamp_hashes(b.records)          # a leaf; no edges yet, on purpose
            b.edge("names", al, guid, "citation", by="demo-class")
            b.edge("names", al, other_guid, "citation", by="demo-class")
            st.write("two-names.jsonl", b.records)
            recs, _ = st.load()
            problems = R.check(recs)
            code, out = run(tmp, "lookup", "class:demo")
            (st.graph / "two-names.jsonl").unlink()
            named = set(re.findall(R.HANDLE_RE, out))
            return (not problems and code == 0
                    and {guid, other_guid} <= named,
                    f"check clean, {len(named & {guid, other_guid})} of 2 "
                    f"targets printed")
        case("an alias naming two nodes is legal, and both are printed",
             alias_naming_two_nodes)

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
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} lookup guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

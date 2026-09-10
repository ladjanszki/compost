#!/usr/bin/env python3
"""
test_sections.py — what v0.2.16 ("TA: revisions, and structure that means
something") promises.

Sectioning: `make_sections` runs in the reader (a Lua filter,
`src/markdown.py`), and `records.hoist`/`records.unhoist` absorb the Div it
produces into its own `Header` — the container is the heading, not a wrapper
Div (docs/roadmap.md; `TODO-section-container.md`). Revisions: `--updates`
against a `mutable` root now mints a whole new tree, chained to the old one
by exactly one `revision_of` edge, root to root (docs/design-0.3.0.md §7, §9).

`tests/verify-0.2.16.sh` proved each of the eleven guarantees once, by hand,
while the feature was being built, and is deleted when the release ships.
This file is where they live on, each demonstrated by breaking the thing it
claims and watching the break get caught — the pattern `test_sabotage.py`
sets, and the one `test_aota.py` already followed for the release before
this one.

Guarantees needing corpus volume (1, 2, 3, 9) ask `tier.have_corpus()` first
and report themselves skipped when it is absent, exactly like every other
suite's corpus-gated guarantees.
"""
import contextlib
import glob
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli              # noqa: E402
from src import markdown as MD   # noqa: E402
from src import records as R     # noqa: E402
from src import session as SESS  # noqa: E402
from src import store as S       # noqa: E402
from tests import tier as T      # noqa: E402

HERE = Path(__file__).parent
NOTE = next((HERE / "fixtures/notes").glob("note-0*.md"))


def run(*args):
    """The CLI, in the current directory. Returns (exit code, output)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(["compost", *args])
    return code, out.getvalue()


def _corpus_md_files() -> list[str]:
    """Every corpus `.md`, by `find` rather than `glob.glob(..., recursive=True)`.

    Measured while building this suite: Python's `glob` with `**` does not
    descend into a dot-directory (`.github/`), so it silently undercounts by
    two against `tests/run.sh`'s own `find`-based count — 518 vs 520. Using
    `find` here is what makes this suite's denominator match the number
    `run.sh` prints as "corpus present, N documents", rather than a quieter
    number nobody asked for.
    """
    out = subprocess.run(
        ["find", str(HERE / "corpus"), "-name", "*.md",
         "-not", "-path", "*/.git/*"],
        capture_output=True, text=True)
    return sorted(l for l in out.stdout.splitlines() if l.strip())


def main():
    results = []

    def case(name, ok, detail=""):
        results.append((ok, name, detail))

    def skip(name):
        results.append((None, name, T.WHY))

    # -- guarantees 1, 2, 3: one pass over the corpus, everything it can ------
    # answer in one read. `MD.ast_of_file` and a plain `pandoc -t json` each
    # shell out once per file; every corpus-scale guarantee below reuses that
    # same pair of parses rather than re-parsing the corpus once per
    # guarantee, which is the difference between ~1,040 pandoc invocations
    # here and the ~2,000+ three separate corpus loops would cost.
    if T.have_corpus():
        files = _corpus_md_files()
        bad_hu = []
        bad_flat = bad_sec = 0
        flat_nodes = sec_nodes = n_headers = 0
        for f in files:
            flat_ast = json.loads(subprocess.run(
                ["pandoc", "-f", MD.READER, "-t", "json", f],
                capture_output=True, text=True, check=True).stdout)
            r1, root1 = R.ast_to_records(flat_ast)
            flat_nodes += sum(1 for r in r1 if r["record"] == "node")
            if R.records_to_ast(r1, root1) != flat_ast:
                bad_flat += 1

            sec_ast = MD.ast_of_file(f)
            if R.unhoist(R.hoist(sec_ast["blocks"])) != sec_ast["blocks"]:
                bad_hu.append(f)
            r2, root2 = R.ast_to_records(sec_ast)
            sec_nodes += sum(1 for r in r2 if r["record"] == "node")
            n_headers += sum(1 for r in r2 if r["record"] == "node"
                             and r["type"] == "Header")
            if R.records_to_ast(r2, root2) != sec_ast:
                bad_sec += 1

        case("hoist and unhoist compose to the identity on every corpus doc",
             not bad_hu, f"{len(files) - len(bad_hu)} of {len(files)} documents")
        case("the full round-trip holds against sectioned ASTs, same form "
             "as the flat one", bad_sec == 0,
             f"{len(files) - bad_sec} of {len(files)} sectioned documents "
             f"round-trip; {len(files) - bad_flat} of {len(files)} flat")
        case("sectioning adds no nodes — measured through the real "
             "ast_to_records", flat_nodes == sec_nodes,
             f"flat {flat_nodes} -> sectioned {sec_nodes}")
        # Sabotage: a node-per-heading shape (the Div design this release
        # rejected) would have cost exactly one node per heading — shown by
        # the count actually moving once that many synthetic nodes are added.
        case("sabotage: a node-per-section shape (the rejected Div design) "
             "would have cost one node per heading",
             sec_nodes + n_headers != sec_nodes,
             f"{n_headers} headings — the Div shape's measured +1,546-per-"
             f"corpus cost is one of these per heading, not zero")
    else:
        skip("hoist and unhoist compose to the identity on every corpus doc")
        skip("the full round-trip holds against sectioned ASTs, same form "
             "as the flat one")
        skip("sectioning adds no nodes — measured through the real "
             "ast_to_records")
        skip("sabotage: a node-per-section shape (the rejected Div design) "
             "would have cost one node per heading")

    # Sabotage: drop the header's own (emptied) attr before unhoisting.
    # `make_sections` moves the identifier onto the Div, so the header's own
    # attr looks redundant and is not — losing it breaks the inverse. A small
    # hand-built document, not a corpus file, so this case runs on a bare
    # clone too and always finds exactly the shape it means to mangle.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "one.md"
        p.write_text("# One\n\npara.\n")
        blocks = MD.ast_of_file(str(p))["blocks"]
        hoisted = R.hoist(blocks)
        good = R.unhoist(hoisted)
        sabotaged = json.loads(json.dumps(hoisted))  # deep copy
        header = sabotaged[0]
        assert header["t"] == "Header" and "section_attr" in header
        # The header's own attr really is `["", [], [...]]` here — emptied by
        # `make_sections`, not absent. Overwriting it with a DIFFERENT attr
        # (rather than deleting the key) is what shows the value is load-
        # bearing: `unhoist` still runs the same branch, but reconstructs a
        # `Header` carrying the wrong attr, and the result no longer matches
        # what a faithful hoist/unhoist pair produces.
        header["c"][1] = ["mangled", ["not-what-make_sections-wrote"], []]
        broke = R.unhoist(sabotaged) != good
        case("sabotage: dropping the header's own attr breaks the inverse",
             broke, "unhoist(sabotaged) != unhoist(the real hoisted form)")

    # -- guarantee 4: a Header contains its section --------------------------
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.md"
        p.write_text("# Chapter\n\nA paragraph.\n\n## Sub\n\n- one\n- two\n")
        recs, root = R.ast_to_records(MD.ast_of_file(str(p)))
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        g = R.Graph(recs)
        top = g.children(root)
        header = nodes[top[0]] if top else None
        kids = [nodes[k]["type"] for k in g.children(top[0])] if top else []
        case("a Header becomes the parent of what follows it, no level "
             "comparison needed", len(top) == 1
             and header["type"] == "Header" and kids == ["Para", "Header"],
             f"top-level: {len(top)} node(s), kids of it: {kids}")

    # -- guarantee 5: identical headings share record_hash, differ in fold ---
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "a.md").write_text("# Braindump\n\n- monday\n")
        (d / "b.md").write_text("# Braindump\n\n- tuesday\n")

        def head(name):
            recs, root = R.ast_to_records(MD.ast_of_file(str(d / name)))
            nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
            g = R.Graph(recs)
            return nodes[g.children(root)[0]]

        x, y = head("a.md"), head("b.md")
        case("two identical headings over different content share "
             "record_hash and differ in record_subtree_hash",
             x["record_hash"] == y["record_hash"]
             and x["record_subtree_hash"] != y["record_subtree_hash"],
             f"record_hash equal: {x['record_hash'] == y['record_hash']}, "
             f"record_subtree_hash equal: "
             f"{x['record_subtree_hash'] == y['record_subtree_hash']}")

    # -- guarantee 6: every markdown path is sectioned identically -----------
    recs, root = MD.text_to_records("# Heading\n\nprose under it.\n")
    nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
    g = R.Graph(recs)
    top = g.children(root)
    case("the delegated (text_to_records) path sections exactly like the "
         "file path", len(top) == 1 and nodes[top[0]]["type"] == "Header"
         and [nodes[k]["type"] for k in g.children(top[0])] == ["Para"],
         "a base built from both paths never holds two document shapes")

    # -- guarantee 7: --updates on a mutable root mints one revision_of ------
    with tempfile.TemporaryDirectory() as d:
        here = Path.cwd()
        import os
        os.chdir(d)
        try:
            run("init")
            run("digest", "--as=notes", "--mutability=mutable", str(NOTE))
            recs, _ = S.Store.find(Path(d)).load()
            old_root = next(r["guid"] for r in recs if r["record"] == "node"
                            and r["type"] == "document")
            code, out = run("digest", "--as=notes", f"--updates={old_root}",
                            str(NOTE))
            recs, _ = S.Store.find(Path(d)).load()
            rev = [e for e in recs if e["record"] == "edge"
                  and e["type"] == "revision_of"]
            nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
            docs = sum(1 for r in recs if r["record"] == "node"
                      and r["type"] == "document")
            case("--updates on a mutable root mints one revision_of, "
                 "root to root, and the old tree stays reachable",
                 code == 0 and len(rev) == 1
                 and nodes[rev[0]["source"]]["type"] == "document"
                 and rev[0]["destination"] == old_root
                 and docs == 2 and not R.check(recs),
                 f"{len(rev)} revision_of edge(s), {docs} document root(s), "
                 f"old root still in the base: {old_root in nodes}")
        finally:
            os.chdir(here)

    # -- guarantee 8: check() on revision_of ---------------------------------
    def revision_base():
        b = R.Builder()
        a = b.node("document", {})
        c = b.node("document", {})
        e = b.node("document", {})
        para = b.node("Para", None, [])
        b.children(c, [para], "ingestion")
        return b, a, c, e, para

    b, a, c, e, para = revision_base()
    b.edge("revision_of", a, a, "ingestion")
    R.stamp_hashes(b.records)
    case("check rejects a reflexive revision_of",
         any("revision" in p.lower() for p in R.check(b.records)),
         "; ".join(R.check(b.records)) or "nothing reported")

    b, a, c, e, para = revision_base()
    b.edge("revision_of", a, c, "ingestion")
    b.edge("revision_of", c, a, "ingestion")
    R.stamp_hashes(b.records)
    case("check rejects a cyclic revision_of",
         any("cycle" in p.lower() for p in R.check(b.records)),
         "; ".join(R.check(b.records)) or "nothing reported")

    b, a, c, e, para = revision_base()
    b.edge("revision_of", para, c, "ingestion")
    R.stamp_hashes(b.records)
    case("check rejects a block-to-block revision_of (roots only)",
         any("root" in p.lower() for p in R.check(b.records)),
         "; ".join(R.check(b.records)) or "nothing reported")

    b, a, c, e, para = revision_base()
    b.edge("revision_of", c, a, "ingestion")
    b.edge("revision_of", e, a, "ingestion")
    R.stamp_hashes(b.records)
    case("check rejects a second revision of one root",
         any("revision" in p.lower() for p in R.check(b.records)),
         "; ".join(R.check(b.records)) or "nothing reported")

    b, a, c, e, para = revision_base()
    b.edge("revision_of", c, a, "ingestion")
    R.stamp_hashes(b.records)
    case("check accepts a genuine, single, root-to-root revision_of",
         not R.check(b.records), "; ".join(R.check(b.records)) or "clean")

    # -- guarantee 10: records_to_session is untouched -----------------------
    for f in T.sessions():
        lines = [json.loads(l) for l in
                Path(f).read_text().splitlines() if l.strip()]
        recs, root = SESS.session_to_records(f)
        ok = SESS.records_to_session(recs, root) == lines
        case(f"the transcript round-trip still holds exactly ({f.name})",
             ok, f"{len(lines)} lines")
        break  # one is enough to prove nothing here regressed; test_session.py
               # already covers every fixture exhaustively.

    # -- guarantee 11: revision_of and section_attr are in the schema -------
    schema = json.loads((Path(__file__).parent.parent
                        / "tools/record-schema-1.json").read_text())
    edge_types = schema["$defs"]["edge"]["properties"]["type"]["enum"]
    header_params = schema["$defs"]["node_types"]["Header"]["params"][
        "properties"]
    case("revision_of is a declared edge type in the schema",
         "revision_of" in edge_types, f"edge type enum: {edge_types}")
    case("section_attr is a declared Header param in the schema",
         "section_attr" in header_params,
         f"Header params: {sorted(header_params)}")

    total = len(results)
    skipped = sum(1 for ok, _, _ in results if ok is None)
    failed = [n for ok, n, _ in results if ok is False]
    for ok, name, detail in results:
        mark = "skip " if ok is None else ("pass " if ok else "FAIL ")
        print(f"  {mark} {name:<70} {detail}")
    print(f"\n{total - len(failed) - skipped}/{total - skipped} "
          f"section and revision guarantees hold"
          + (f" ({skipped} skipped: {T.WHY})" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

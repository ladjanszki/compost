#!/usr/bin/env python3
"""
test_digest.py — what `compost digest --as=<route>` promises.

Ingestion used to dispatch on the file extension. The rules below are what
replaced it, and each one is a thing the old importer could not have said:

- **the route is named, never inferred.** The suffix decides nothing, so a
  `.jsonl` digested `--as=notes` is markdown. This is the whole point, and it
  is tested by making the extension lie.
- **nothing is written until everything parses.** Storage names are minted
  now, so a batch that dies halfway cannot simply be re-run — the files it
  already ingested would come in a second time under fresh guids. Validating
  first is what makes a glob safe to pass.
- **the bytes are reachable from the graph.** The path from a document to its
  source is the `derived_from` edge and `blob.params["stored_as"]`, because
  the original name is no longer where the file lives.
- **duplication is reported, not resolved.** The same bytes twice are two
  blobs and a note, since deciding they are one thing is a later layer's job.
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli              # noqa: E402
from src import records as R     # noqa: E402
from src import routes as RT     # noqa: E402
from src import store as S       # noqa: E402

HERE = Path(__file__).parent
NOTE = HERE / "fixtures/notes"
SESSION = HERE / "fixtures/sessions/session-smoke.jsonl"


def run(*args):
    """The CLI, in the current directory. Returns (exit code, output)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(["compost", *args])
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
        here = Path.cwd()
        os.chdir(tmp)
        try:
            run("init")
            st = S.Store.find(tmp)
            note = next(NOTE.glob("note-0*.md"))
            # One document through each route, so the cases below are checked
            # against all three rather than against whichever happened to run
            # first. `pandoc-ast` is fed an AST produced the way a person
            # would produce one: outside the tool, with pandoc.
            ast_file = tmp / "manual.json"
            ast_file.write_text(json.dumps(RT._ast_of(note)))
            for route, path in (("notes", note),
                                ("claude-code-transcript", SESSION),
                                ("pandoc-ast", ast_file)):
                code, out = run("digest", f"--as={route}", str(path))
                assert code == 0, f"seeding {route} failed: {out}"

            def every_route_dispatches():
                # A route in the table that the CLI will not accept is a route
                # that does not exist. Probed rather than listed, so adding one
                # to ROUTES without wiring it is caught here.
                bad = []
                for name in RT.ROUTES:
                    _, out = run("digest", f"--as={name}", "definitely-absent")
                    if "unknown route" in out:
                        bad.append(name)
                return not bad, f"{len(RT.ROUTES)} routes, all accepted"
            case("every route in the table is dispatched",
                 every_route_dispatches)

            def route_is_required():
                code, out = run("digest", str(note))
                listed = all(n in out for n in RT.ROUTES)
                return code == 2 and listed, \
                    "no --as: exits 2 and names the routes"
            case("the route is never guessed", route_is_required)

            def suffix_decides_nothing():
                # The extension lies on purpose: markdown named .jsonl. If any
                # routing still consulted the suffix this would be read as a
                # transcript and produce a session, not a document.
                liar = tmp / "actually-markdown.jsonl"
                liar.write_bytes(note.read_bytes())
                code, _ = run("digest", "--as=notes", str(liar))
                recs, _ = st.load()
                doc = [r for r in recs if r["record"] == "node"
                       and R._p(r, "source") == liar.name]
                return code == 0 and len(doc) == 1 \
                    and doc[0]["type"] == "document", \
                    "a .jsonl read --as=notes is a document"
            case("the extension decides nothing", suffix_decides_nothing)

            def route_is_recorded():
                recs, _ = st.load()
                roots = [r for r in recs if r["record"] == "node"
                         and r["type"] in R.ROOT_TYPES]
                missing = [r for r in roots if not R._p(r, "route")]
                return roots and not missing, \
                    f"{len(roots)} roots, all carrying the route they came by"
            case("the root records how it was read", route_is_recorded)

            def bytes_are_reachable():
                recs, _ = st.load()
                roots = [r for r in recs if r["record"] == "node"
                         and r["type"] in R.ROOT_TYPES]
                bad = []
                for root in roots:
                    blob = R.blob_of(recs, root["guid"])
                    if blob is None:
                        bad.append(root["guid"])
                        continue
                    stored = st.storage / R._p(blob, "stored_as")
                    if not stored.is_file():
                        bad.append(root["guid"])
                    elif hashlib.sha256(stored.read_bytes()).hexdigest() \
                            != R._p(blob, "bytes_sha256"):
                        bad.append(root["guid"])
                return roots and not bad, \
                    f"{len(roots)} documents, each reaching bytes that hash right"
            case("a document reaches its bytes through the graph",
                 bytes_are_reachable)

            def storage_name_is_not_the_original():
                recs, _ = st.load()
                blobs = [r for r in recs if r["record"] == "node"
                         and r["type"] == "blob"]
                same = [b for b in blobs
                        if R._p(b, "stored_as") == R._p(b, "original_name")]
                kept = [b for b in blobs
                        if Path(R._p(b, "stored_as")).suffix
                        == Path(R._p(b, "original_name")).suffix]
                return blobs and not same and len(kept) == len(blobs), \
                    f"{len(blobs)} blobs stored under a guid, extension kept"
            case("storage names are minted, extensions survive",
                 storage_name_is_not_the_original)

            def nothing_written_on_a_bad_batch():
                # The first file is a real pandoc AST and would ingest fine on
                # its own; the second is markdown, which is not JSON. The
                # promise is that the *first* one does not land either — a
                # batch that half-lands cannot be re-run, because the half
                # that landed would come in again under fresh guids.
                before_g = len(list(st.graph.glob("*.jsonl")))
                before_s = len(list(st.storage.iterdir()))
                code, out = run("digest", "--as=pandoc-ast",
                                str(ast_file), str(note))
                after_g = len(list(st.graph.glob("*.jsonl")))
                after_s = len(list(st.storage.iterdir()))
                return (code == 1 and before_g == after_g
                        and before_s == after_s), \
                    "a batch with one bad file writes nothing at all"
            case("a batch is all or nothing", nothing_written_on_a_bad_batch)

            def directories_are_refused():
                sub = tmp / "adir"
                sub.mkdir(exist_ok=True)
                (sub / "x.md").write_text("# x\n")
                code, out = run("digest", "--as=notes", str(sub))
                return code == 1 and "directory" in out and "*" in out, \
                    "a directory is refused, pointing at the shell's glob"
            case("directories are refused, not walked", directories_are_refused)

            def duplication_is_reported():
                run("digest", "--as=notes", str(note))
                code, out = run("digest", "--as=notes", str(note))
                recs, _ = st.load()
                sha = hashlib.sha256(note.read_bytes()).hexdigest()
                blobs = [r for r in recs if r["record"] == "node"
                         and r["type"] == "blob"
                         and R._p(r, "bytes_sha256") == sha]
                return code == 0 and len(blobs) >= 2 and "already" in out, \
                    f"{len(blobs)} blobs for one file, and it said so"
            case("the same bytes twice are reported, not merged",
                 duplication_is_reported)

            def names_are_independent():
                # Storage and graph names must not be derivable from each
                # other, or something will eventually derive one from the
                # other — which is suffix routing wearing a different hat.
                recs, _ = st.load()
                stored = {Path(R._p(r, "stored_as")).stem for r in recs
                          if r["record"] == "node" and r["type"] == "blob"}
                graph = {f.stem for f in st.graph.glob("*.jsonl")}
                return stored and graph and not (stored & graph), \
                    f"{len(stored)} blobs, {len(graph)} graph files, no shared name"
            case("storage and graph names never coincide", names_are_independent)

            def ast_route_matches_the_reader():
                # `pandoc-ast` is `notes` with the reading step removed, so
                # feeding it the AST that `notes` would have produced must give
                # the same graph. Guids differ — they are minted — so the
                # comparison is over content hashes, which are the identity of
                # what was recorded rather than of when it was recorded.
                recs, _ = st.load()

                def hashes(route, name):
                    root = next(r for r in recs if r["record"] == "node"
                                and R._p(r, "route") == route
                                and R._p(r, "source") == name)
                    g = R.Graph(recs)
                    out, stack = [], [root["guid"]]
                    while stack:
                        n = g.nodes[stack.pop()]
                        if "content_hash" in n:
                            out.append(n["content_hash"])
                        stack += g.children(n["guid"])
                    return sorted(out)

                a = hashes("notes", note.name)
                b = hashes("pandoc-ast", ast_file.name)
                return a and a == b, \
                    f"{len(a)} hashed blocks, identical either way"
            case("pandoc-ast is the reader minus the reading",
                 ast_route_matches_the_reader)

            def awkward_names_are_still_files():
                # A name beginning with a dash reached pandoc as a flag:
                # `-dash.md` parsed as `-d ash.md`, and the failure surfaced as
                # a pandoc error about a file nobody had named. Paths are
                # resolved before pandoc sees them, and `--` ends the options.
                dash = tmp / "-dash.md"
                dash.write_text("# t\n\npara\n")
                spaced = tmp / "two words.md"
                spaced.write_text("# t\n\npara\n")
                bare = tmp / "noext"
                bare.write_text("# t\n\npara\n")
                # Relative on purpose: an absolute path already begins with a
                # slash, so it can never be mistaken for a flag and would not
                # exercise the bug. `Path("./-dash.md")` normalises to
                # `-dash.md`, which is exactly what reached pandoc.
                a, _ = run("digest", "--as=notes", "./-dash.md")
                b, _ = run("digest", "--as=notes", "--", "-dash.md")
                c, _ = run("digest", "--as=notes", str(spaced), str(bare))
                recs, _ = st.load()
                stored = {R._p(r, "stored_as") for r in recs
                          if r["record"] == "node" and r["type"] == "blob"}
                # A source with no extension is stored under a bare guid, and
                # that is fine: the extension is decoration, never a fallback.
                bareblob = any("." not in n for n in stored)
                return a == b == c == 0 and bareblob, \
                    "dashes, spaces and no extension at all"
            case("an awkward filename is still just a filename",
                 awkward_names_are_still_files)

            def base_still_checks():
                code, _ = run("check")
                return code == 0, "everything ingested above checks clean"
            case("a digested base checks clean", base_still_checks)
        finally:
            os.chdir(here)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<52} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} ingestion guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

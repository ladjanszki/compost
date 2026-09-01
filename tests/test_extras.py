#!/usr/bin/env python3
"""
test_extras.py — what `compost-new` promises.

`extras/compost_new.py` is installed but is not the tool (DEVELOPMENT.md,
"What belongs in extras/"), so nothing here goes through `src/cli.py` —
`extras.compost_new.main` is called directly, the same way a shell would call
the `compost-new` console script `pyproject.toml` wires it to. `$EDITOR` is
stood in for with a small python script written per case, so no suite here
depends on an interactive editor being on PATH.
"""
import contextlib
import io
import os
import stat
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from extras import compost_new as N   # noqa: E402
from extras import compost_name as CN  # noqa: E402
from src import records as R          # noqa: E402
from src import store as S            # noqa: E402
from src import views as V            # noqa: E402

FAKE_EDITOR = """#!/usr/bin/env python3
import sys
from pathlib import Path
# sys.argv[-1], not sys.argv[1]: an $EDITOR invoked with its own flags
# ("code --wait") gets the target file appended last, and a script that
# assumed argv[1] would silently write to the flag string instead — caught
# once, by "$EDITOR may carry arguments" writing nothing until this was
# argv[-1].
Path(sys.argv[-1]).write_text({content!r})
sys.exit({rc})
"""


def _fake_editor(tmp: Path, name: str, content: str, rc: int = 0) -> Path:
    """A script `compost-new` can run as `$EDITOR`: writes `content` into the
    file it is given, exits `rc`. Executable, so `shlex.split($EDITOR)`
    invokes it directly the way a shell would."""
    p = tmp / name
    p.write_text(FAKE_EDITOR.format(content=content, rc=rc))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


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
        base = tmp / "base"
        S.Store.init(base)
        editor_dir = tmp / "editors"
        editor_dir.mkdir()

        def run(editor_env, cwd):
            """Call main() with $EDITOR and cwd set, restoring both after."""
            old_editor = os.environ.get("EDITOR")
            old_cwd = Path.cwd()
            if editor_env is None:
                os.environ.pop("EDITOR", None)
            else:
                os.environ["EDITOR"] = editor_env
            os.chdir(cwd)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    rc = N.main([])
                return rc, out.getvalue()
            finally:
                os.chdir(old_cwd)
                if old_editor is None:
                    os.environ.pop("EDITOR", None)
                else:
                    os.environ["EDITOR"] = old_editor

        def no_editor_refuses():
            before = set((base / ".compost" / "graph").glob("*.jsonl"))
            rc, out = run(None, base)
            after = set((base / ".compost" / "graph").glob("*.jsonl"))
            return (rc == 2 and "$EDITOR" in out and before == after,
                    f"rc={rc}, {out.strip()!r}")
        case("refuses cleanly when $EDITOR is unset", no_editor_refuses)

        def mints_and_digests():
            editor = _fake_editor(editor_dir, f"e{uuid.uuid4().hex[:6]}",
                                  "A fresh note, minted for this test.\n")
            before_md = set(base.glob("*.md"))
            rc, out = run(str(editor), base)
            after_md = set(base.glob("*.md")) - before_md
            if len(after_md) != 1:
                return False, f"expected one new .md, found {len(after_md)}"
            minted = next(iter(after_md))
            is_uuid_name = minted.stem.count("-") == 4 and len(minted.stem) == 36
            recs, _ = S.Store(base).load()
            found = any("fresh note" in R.plain_text(r) for r in recs
                       if r["record"] == "node")
            return (rc == 0 and is_uuid_name and minted.exists() and found,
                    f"rc={rc}, minted {minted.name}, digested={found}, "
                    f"left on disk={minted.exists()}")
        case("mints a uuid filename, opens $EDITOR, digests it, leaves it",
             mints_and_digests)

        def empty_draft_skipped():
            editor = _fake_editor(editor_dir, f"e{uuid.uuid4().hex[:6]}",
                                  "   \n\n  \t\n")   # whitespace only
            recs_before, _ = S.Store(base).load()
            before_md = set(base.glob("*.md"))
            rc, out = run(str(editor), base)
            after_md = set(base.glob("*.md")) - before_md
            recs_after, _ = S.Store(base).load()
            return (rc == 0 and not after_md and "empty draft" in out
                    and len(recs_before) == len(recs_after),
                    f"rc={rc}, leftover files={after_md}, {out.strip()!r}")
        case("an empty draft is not digested and is removed",
             empty_draft_skipped)

        def nonzero_exit_aborts():
            editor = _fake_editor(editor_dir, f"e{uuid.uuid4().hex[:6]}",
                                  "Written, but the editor still failed.\n",
                                  rc=17)
            recs_before, _ = S.Store(base).load()
            before_md = set(base.glob("*.md"))
            rc, out = run(str(editor), base)
            after_md = set(base.glob("*.md")) - before_md
            recs_after, _ = S.Store(base).load()
            # The file the editor wrote is left in place (same treatment as
            # any other failed step: nothing is silently cleaned up), but
            # nothing new reaches the graph.
            return (rc == 17 and len(after_md) == 1
                    and len(recs_before) == len(recs_after),
                    f"rc={rc}, leftover files={after_md}")
        case("a nonzero $EDITOR exit aborts without digesting",
             nonzero_exit_aborts)

        def editor_with_arguments():
            # $EDITOR may itself carry flags ("code --wait") — shlex.split,
            # not a bare exec of the whole string as one path. Checked by
            # content actually reaching the graph, not just rc == 0: a
            # script that wrote to the wrong argv slot would still exit 0
            # and produce an empty-draft "success".
            script = _fake_editor(editor_dir, f"e{uuid.uuid4().hex[:6]}",
                                  "Note via an editor invoked with a flag.\n")
            rc, out = run(f"{script} --some-flag", base)
            recs, _ = S.Store(base).load()
            found = any("invoked with a flag" in R.plain_text(r) for r in recs
                       if r["record"] == "node")
            return (rc == 0 and found, f"rc={rc}, digested={found}")
        case("$EDITOR may carry arguments", editor_with_arguments)

        def not_a_base_refuses():
            outside = tmp / "not-a-base"
            outside.mkdir()
            editor = _fake_editor(editor_dir, f"e{uuid.uuid4().hex[:6]}",
                                  "Should never be digested.\n")
            rc, out = run(str(editor), outside)
            return (rc == 1 and "no .compost" in out,
                    f"rc={rc}, {out.strip()!r}")
        case("refuses outside a base, same message as any other command",
             not_a_base_refuses)

    # -- compost-name (docs/roadmap.md, v0.2.10) -------------------------
    with tempfile.TemporaryDirectory() as d2:
        base2 = Path(d2) / "base"
        S.Store.init(base2)
        note = Path(d2) / "note-for-naming.md"
        note.write_text("A note somebody will give a display name.\n",
                        encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            S._digest(S.Store(base2), "notes", [str(note)], "compost")
        recs, _ = S.Store(base2).load()
        root = next(r["guid"] for r in recs
                   if r["record"] == "node" and r["type"] == "document")
        para = next(r["guid"] for r in recs
                   if r["record"] == "node" and r["type"] == "Para")

        def _run_name(*args):
            old = Path.cwd()
            os.chdir(base2)
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = CN.main(list(args))
                return rc, out.getvalue()
            finally:
                os.chdir(old)

        def writes_a_file_check_accepts_and_the_view_shows_it():
            before = set(S.Store(base2).graph.glob("*.jsonl"))
            rc, out = _run_name(root, "A Name From compost-name")
            after = set(S.Store(base2).graph.glob("*.jsonl")) - before
            problems = S.Store(base2).check()
            with contextlib.redirect_stdout(io.StringIO()):
                V.render_all(S.Store(base2))
            idx = (S.Store(base2).views / "default-html" / "index.html").read_text()
            return (rc == 0 and len(after) == 1 and not problems
                    and "A Name From compost-name" in idx), \
                (f"rc={rc}, new files={len(after)}, check problems={problems}, "
                 f"shown in index={'A Name From compost-name' in idx}")
        case("compost-name writes a file check accepts, and the view shows "
             "the name", writes_a_file_check_accepts_and_the_view_shows_it)

        def refuses_an_unknown_identifier():
            before = set(S.Store(base2).graph.glob("*.jsonl"))
            rc, out = _run_name("deadbeef-0000-0000-0000-000000000000", "x")
            after = set(S.Store(base2).graph.glob("*.jsonl")) - before
            return rc == 1 and not after and "does not resolve" in out, \
                f"rc={rc}, new files={len(after)}, {out.strip()!r}"
        case("compost-name refuses an unknown identifier",
             refuses_an_unknown_identifier)

        def refuses_a_non_root_target():
            before = set(S.Store(base2).graph.glob("*.jsonl"))
            rc, out = _run_name(para, "a paragraph is not a root")
            after = set(S.Store(base2).graph.glob("*.jsonl")) - before
            return rc == 1 and not after and "not a root" in out, \
                f"rc={rc}, new files={len(after)}, {out.strip()!r}"
        case("compost-name refuses a target that is not a root",
             refuses_a_non_root_target)

        def refuses_an_empty_name():
            before = set(S.Store(base2).graph.glob("*.jsonl"))
            rc, out = _run_name(root, "   ")
            after = set(S.Store(base2).graph.glob("*.jsonl")) - before
            return rc == 1 and not after and "must not be empty" in out, \
                f"rc={rc}, new files={len(after)}, {out.strip()!r}"
        case("compost-name refuses an empty name", refuses_an_empty_name)

        def two_runs_leave_two_files_and_the_view_shows_the_newer():
            before = set(S.Store(base2).graph.glob("*.jsonl"))
            orig_now = R._now
            try:
                R._now = lambda: "2020-01-01T00:00:00Z"
                _run_name(root, "An Older compost-name Run")
                R._now = lambda: "2030-01-01T00:00:00Z"
                _run_name(root, "A Newer compost-name Run")
            finally:
                R._now = orig_now
            after = set(S.Store(base2).graph.glob("*.jsonl")) - before
            with contextlib.redirect_stdout(io.StringIO()):
                V.render_all(S.Store(base2))
            idx = (S.Store(base2).views / "default-html" / "index.html").read_text()
            return (len(after) == 2
                    and "A Newer compost-name Run" in idx
                    and "An Older compost-name Run" not in idx), \
                (f"{len(after)} new files, newest shown: "
                 f"{'A Newer compost-name Run' in idx}, "
                 f"older not shown: {'An Older compost-name Run' not in idx}")
        case("two runs of compost-name leave two files; the view shows "
             "the newer name", two_runs_leave_two_files_and_the_view_shows_the_newer)

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} extras guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

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
from src import records as R          # noqa: E402
from src import store as S            # noqa: E402

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

    for ok, name, detail in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<58} {detail}")
    bad = sum(1 for ok, _, _ in results if not ok)
    print(f"\n{len(results) - bad}/{len(results)} extras guarantees hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

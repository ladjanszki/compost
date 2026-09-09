#!/usr/bin/env python3
"""
test_aota.py — what v0.2.15 ("AoTA: an artifact that grows") promises.

`mutability` is declared at creation and never changes; `--updates=guid`
names an existing root for both append and (later) revision; an append mints
only the tail and rewrites the root's fold rather than its content; and the
alignment walk that makes any of this possible has to follow `delegates_to`
or it silently measures half the graph (docs/roadmap.md, "AoTA").

`tests/verify-0.2.15.sh` proved each of these once, by hand, while the
feature was being built, and is deleted when the release ships. This file is
where the eleven guarantees it named live on, each demonstrated by breaking
the thing it claims and watching the break get caught — the pattern
`test_sabotage.py` sets.

The append/alignment guarantees (4, 5, 6, 8, 9, and the extra round-trip
check under 10) need a real growth pair — the smoke set's one transcript is 9
lines and has nothing to truncate meaningfully — so they ask
`tier.have_corpus()` first and report themselves skipped when it is absent,
exactly like every other suite's corpus-gated guarantees.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import uuid as _uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cli               # noqa: E402
from src import records as R      # noqa: E402
from src import routes as RT      # noqa: E402
from src import session as SESS   # noqa: E402
from src import store as S        # noqa: E402
from tests import tier as T       # noqa: E402

HERE = Path(__file__).parent
NOTE = next((HERE / "fixtures/notes").glob("note-0*.md"))


def run(*args):
    """The CLI, in the current directory. Returns (exit code, output)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(["compost", *args])
    return code, out.getvalue()


def _corpus_session() -> Path | None:
    for p in T.sessions():
        n = sum(1 for l in p.read_text().splitlines() if l.strip())
        if n >= 40:
            return p
    return None


def main():
    results = []

    def case(name, ok, detail=""):
        results.append((ok, name, detail))

    def skip(name):
        results.append((None, name, T.WHY))

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        here = Path.cwd()
        os.chdir(tmp)
        try:
            run("init")

            # -- guarantee 1 -------------------------------------------------
            code, out = run("digest", "--as=notes", str(NOTE))
            names_all = all(v in out for v in S.MUTABILITIES)
            case("--mutability is required at creation, naming the three "
                 "values", code != 0 and names_all,
                 f"refused (code {code}), named {S.MUTABILITIES}")

            code, out = run("digest", "--as=notes", "--mutability=immutable",
                            str(NOTE))
            note_root = None
            if code == 0:
                recs, _ = S.Store.find(tmp).load()
                note_root = next(r["guid"] for r in recs
                                 if r["record"] == "node"
                                 and r["type"] == "document")
            case("--mutability accepted at creation mints the root",
                 code == 0 and note_root is not None, f"root {note_root}")

            # -- guarantee 2 -------------------------------------------------
            code, _ = run("digest", "--as=notes", "--mutability=mutable",
                          f"--updates={note_root}", str(NOTE))
            case("--mutability together with --updates is refused",
                 code != 0, f"code {code}")

            code, out = run("digest", "--as=notes", f"--updates={note_root}",
                            str(NOTE))
            case("--updates naming an immutable root is refused",
                 code != 0 and "immutable" in out.lower(), out.strip())

            # `mutable` is refused too, until v0.2.16 builds `revision_of`.
            # Routing it through the append path instead runs and passes
            # `check`, which is why this is a test and not a comment: a
            # `mutable` root put through delta ingest inherits the
            # head-unchanged refusal, so the one contract that promised
            # "anything here may change" would be the one told its start
            # moved. Refusing is recoverable; shipping the wrong reading is
            # not (src/store.py, and the report on v0.2.15).
            code, out = run("digest", "--as=notes", "--mutability=mutable",
                            str(NOTE))
            ta_root = None
            if code == 0:
                recs, _ = S.Store.find(tmp).load()
                ta_root = next(r["guid"] for r in recs
                               if r["record"] == "node"
                               and r["type"] == "document"
                               and (r.get("params") or {}).get("mutability")
                               == "mutable")
            code, out = run("digest", "--as=notes", f"--updates={ta_root}",
                            str(NOTE))
            case("--updates naming a mutable root is refused until "
                 "revision_of exists (v0.2.16), not silently appended to",
                 code != 0 and "revision_of" in out, out.strip())

            recs, _ = S.Store.find(tmp).load()
            non_root = next(r["guid"] for r in recs
                            if r["record"] == "node"
                            and r["type"] not in R.ROOT_TYPES)
            code, out = run("digest", "--as=notes", f"--updates={non_root}",
                            str(NOTE))
            case("--updates naming a non-root is refused",
                 code != 0, f"code {code}")

            # -- guarantee 3 -------------------------------------------------
            sids = [str(_uuid.uuid4()) for _ in range(6)]
            tids = [str(_uuid.uuid4()) for _ in range(12)]
            names = ([f"{s}.jsonl" for s in sids]
                    + [f"agent-{t}.jsonl" for t in tids])
            full = sum(1 for n in names
                      if RT.transcript_identity(Path(n)) is not None)

            session_only = RT._SESSION_NAME
            agent_only = RT._AGENT_NAME
            never = __import__("re").compile(r"(?!x)x")
            RT._AGENT_NAME = never
            drop_agent = sum(1 for n in names
                             if RT.transcript_identity(Path(n)) is not None)
            RT._AGENT_NAME = agent_only
            RT._SESSION_NAME = never
            drop_session = sum(1 for n in names
                               if RT.transcript_identity(Path(n)) is not None)
            RT._SESSION_NAME = session_only

            case("the transcript default resolves 18 of 18 archived-shape "
                 "filenames, and either rule alone resolves only its half",
                 full == 18 and drop_agent == 6 and drop_session == 12,
                 f"both rules: {full} of {len(names)}; session rule alone: "
                 f"{drop_agent}; agent rule alone: {drop_session}")

            # -- guarantee 7 ---------------------------------------------
            b = R.Builder()
            iroot = b.node("session", {
                "source": "s.jsonl", "session_id": "x", "version": None,
                "mutability": "immutable"})
            k = b.node("turn", {"author": "human", "uuid": "u1",
                                "timestamp": "t", "log": {}})
            b.children(iroot, [k], "session")
            blob1 = b.node("blob", {
                "original_name": "s.jsonl", "stored_as": "a.jsonl",
                "bytes_sha256": "a" * 64, "imported_at": "2020-01-01T00:00:00Z",
                "route": "claude-code-transcript"})
            b.edge("derived_from", iroot, blob1, "ingestion")
            R.stamp_hashes(b.records)
            clean = R.check(b.records)
            blob2 = b.node("blob", {
                "original_name": "s.jsonl", "stored_as": "b.jsonl",
                "bytes_sha256": "b" * 64, "imported_at": "2020-01-02T00:00:00Z",
                "route": "claude-code-transcript"})
            b.edge("derived_from", iroot, blob2, "ingestion")
            R.stamp_hashes([r for r in b.records if r["guid"] == blob2])
            dirty = R.check(b.records)
            case("an immutable root that gains a second derived_from edge "
                 "is a reported problem",
                 not clean and dirty
                 and any("immutable" in p for p in dirty),
                 f"before: {clean or 'clean'}; after: {dirty}")

            # -- guarantee 5 (structural, no corpus needed) --------------
            b2 = R.Builder()
            aroot = b2.node("session", {
                "source": "s.jsonl", "session_id": "y", "version": None,
                "mutability": "append-only"})
            kk = [b2.node("turn", {"author": "human", "uuid": f"u{i}",
                                   "timestamp": "t", "log": {}})
                 for i in (1, 2)]
            b2.children(aroot, kk, "session")
            R.stamp_hashes(b2.records)
            k3 = b2.node("turn", {"author": "human", "uuid": "u3",
                                  "timestamp": "t", "log": {}})
            b2.edge("contains", aroot, k3, "session")
            b2.edge("next", kk[1], k3, "session")
            R.stamp_hashes([r for r in b2.records if r["guid"] == k3])
            before_refresh = R.check(b2.records)
            R.refresh_fold(b2.records, aroot)
            after_refresh = R.check(b2.records)
            case("check reports the fold as stale before refresh_fold, and "
                 "clean after",
                 any("record_subtree_hash does not recompute" in p
                    for p in before_refresh) and not after_refresh,
                 f"before: {before_refresh[:1]}; after: {after_refresh}")

            # -- guarantee 6 (structural) ---------------------------------
            n = next(r for r in b2.records if r["guid"] == kk[0])
            n["params"]["author"] = "assistant"
            sabotaged = R.check(b2.records)
            case("an append-only root whose head was edited in place is a "
                 "reported problem naming the mutability contract",
                 any("mutability" in p for p in sabotaged), sabotaged)

            # -- guarantee 9 -----------------------------------------------
            b3 = R.Builder()
            broot = b3.node("session", {"source": "s.jsonl",
                                        "session_id": "z", "version": None,
                                        "mutability": "append-only"})
            bb1 = b3.node("blob", {
                "original_name": "s.jsonl", "stored_as": "old.jsonl",
                "bytes_sha256": "c" * 64, "imported_at": "2020-01-01T00:00:00Z",
                "route": "claude-code-transcript"})
            bb2 = b3.node("blob", {
                "original_name": "s.jsonl", "stored_as": "new.jsonl",
                "bytes_sha256": "d" * 64, "imported_at": "2020-06-01T00:00:00Z",
                "route": "claude-code-transcript"})
            b3.edge("derived_from", broot, bb1, "ingestion")
            b3.edge("derived_from", broot, bb2, "ingestion")
            R.stamp_hashes(b3.records)
            current = R.blob_of(b3.records, broot)
            everything = R.blobs_of(b3.records, broot)
            case("blob_of returns the current (most recently imported) "
                 "blob, and blobs_of keeps the older one reachable",
                 current is not None and current["guid"] == bb2
                 and len(everything) == 2
                 and {x["guid"] for x in everything} == {bb1, bb2},
                 f"current={current['guid'] if current else None}, "
                 f"all={[x['guid'] for x in everything]}")

            # ...and the answer does not depend on load order when the two
            # blobs tie. `_now()` records whole seconds, so two ingests
            # inside one second carry the SAME `imported_at` — measured,
            # reversing the records was enough to flip which blob came back,
            # against `Store.load()`'s standing guarantee that file order
            # carries no meaning (CLAUDE.md). `_blob_order` breaks the tie on
            # guid, which is stable but arbitrary: this asserts determinism,
            # which is what was broken, and deliberately not "the newer
            # blob", which the records cannot currently answer at all.
            b4 = R.Builder()
            troot = b4.node("session", {"source": "s.jsonl",
                                        "session_id": "tie", "version": None,
                                        "mutability": "append-only"})
            same = "2020-01-01T00:00:00Z"
            tb = [b4.node("blob", {
                "original_name": "s.jsonl", "stored_as": f"{i}.jsonl",
                "bytes_sha256": chr(97 + i) * 64, "imported_at": same,
                "route": "claude-code-transcript"}) for i in range(2)]
            for x in tb:
                b4.edge("derived_from", troot, x, "ingestion")
            R.stamp_hashes(b4.records)
            shuffles = [b4.records, list(reversed(b4.records))]
            rng = __import__("random").Random(0)
            for _ in range(20):
                s_ = list(b4.records)
                rng.shuffle(s_)
                shuffles.append(s_)
            answers = {R.blob_of(s_, troot)["guid"] for s_ in shuffles}
            orders = {tuple(x["guid"] for x in R.blobs_of(s_, troot))
                      for s_ in shuffles}
            case("blob_of and blobs_of give one answer for two blobs that "
                 "share an imported_at, whatever order the records load in",
                 len(answers) == 1 and len(orders) == 1,
                 f"{len(answers)} distinct current-blob answer(s) and "
                 f"{len(orders)} distinct ordering(s) over "
                 f"{len(shuffles)} record orderings")

            # -- guarantees 4, 8, and the append-specific half of 10 --------
            src = _corpus_session()
            if src is None:
                for g in (4, 8):
                    skip(f"guarantee {g} needs a real growth pair "
                        f"(no session >=40 lines on disk)")
                skip("an appended session round-trips to the grown file's "
                    "exact original lines")
            else:
                lines = [l for l in src.read_text().splitlines() if l.strip()]
                cut = int(len(lines) * 0.7)
                old_text = "\n".join(lines[:cut]) + "\n"
                new_text = "\n".join(lines) + "\n"

                d2 = tmp / "b2"
                d2.mkdir()
                os.chdir(d2)
                run("init")
                sf = d2 / "s.jsonl"
                sf.write_text(old_text)
                run("digest", "--as=claude-code-transcript",
                    "--mutability=append-only", str(sf))
                st2 = S.Store.find(d2)
                recs1, _ = st2.load()
                n1 = sum(1 for r in recs1 if r["record"] == "node")
                sroot = next(r["guid"] for r in recs1
                            if r["record"] == "node" and r["type"] == "session")

                # guarantee 8, measured directly against the alignment walk,
                # BEFORE the second ingest changes anything on disk.
                sf.write_text(new_text)
                new_recs, new_root = SESS.session_to_records(
                    sf, route="claude-code-transcript")
                # the fresh re-read needs the same declared mutability
                # stamped on it or record_hash will differ for that reason
                # alone (store.py:_digest_update does the same thing)
                nr = next(r for r in new_recs if r["guid"] == new_root)
                nr.setdefault("params", {})["mutability"] = "append-only"
                R.stamp_hashes(new_recs)
                pre, tot = R.align(recs1, sroot, new_recs, new_root)
                n_old_all = sum(1 for r in recs1 if r["record"] == "node")

                def walk_no_delegation(records, root):
                    g = R.Graph(records)
                    out = []

                    def visit(guid):
                        out.append(guid)
                        for kk_ in g.children(guid):
                            visit(kk_)
                    visit(root)
                    return out, g

                oo, og = walk_no_delegation(recs1, sroot)
                no, ng = walk_no_delegation(new_recs, new_root)
                narrow = 0
                for x, y in zip(oo, no):
                    if og.nodes[x].get("record_hash") != ng.nodes[y].get("record_hash"):
                        break
                    narrow += 1
                # The trap this guarantee exists to catch is not a lower
                # match rate — the narrow walk still reports 100% of what it
                # reaches (`narrow == len(oo)`), which is exactly what makes
                # it dangerous: it reads as a clean, complete prefix while
                # its own *denominator* silently shrank. `len(oo)` well
                # below `tot` is the real defect docs/roadmap.md names —
                # "the prefix collapses ... which reads as 100% of half the
                # graph".
                #
                # The wide walk does not reach *every* node, and the bound
                # is `0.75 * n_old_all` rather than equality for that
                # reason. What it misses is `blob` and `file` nodes, which
                # are UNCONTAINED by rule and so sit outside any
                # contains/delegates_to walk by construction — not a defect
                # and not something to widen the walk for. Measured on the
                # older tree: session-04 misses 102 of 2,481 (73 `blob`, 29
                # `file`) and session-02 misses 25 of 498 (17 `blob`, 8
                # `file`) — blobs are the larger half, which is worth
                # stating precisely because the first account of this gap
                # named only the `file` nodes.
                case("align() follows delegates_to and reaches most of the "
                    "older tree; dropping the hop halves the denominator "
                    "while still reporting 100%",
                    pre == tot and tot > 0.75 * n_old_all
                    and narrow == len(oo) and len(oo) < 0.75 * tot,
                    f"with delegation: {pre} of {tot} matched "
                    f"({tot} of {n_old_all} nodes reached); without: "
                    f"{narrow} of {len(oo)} matched ({len(oo)} of "
                    f"{n_old_all} nodes reached) — both read as 100%, but "
                    f"of a denominator {tot - len(oo)} nodes smaller")

                # now the real append, through the CLI
                code, out = run("digest", "--as=claude-code-transcript",
                                f"--updates={sroot}", str(sf))
                recs2, _ = st2.load()
                n2 = sum(1 for r in recs2 if r["record"] == "node")
                roots2 = [r["guid"] for r in recs2 if r["record"] == "node"
                         and r["type"] == "session"]
                # "mints only the tail" as a property, not a ratio: every one
                # of the n1 old nodes is byte-identical in the merged graph —
                # not merely present under the same guid, but unchanged
                # `params`/`content`/`record_hash` — except the root, whose
                # `record_subtree_hash` legitimately moves (the fold refresh)
                # while its `record_hash` (what it *claims*) does not. A ratio
                # bound (docs/roadmap.md's own `n2 < n1*1.8`) is a proxy for
                # this and does not hold on every real session — see the
                # report.
                old_by_guid = {r["guid"]: r for r in recs1
                              if r["record"] == "node"}
                new_by_guid = {r["guid"]: r for r in recs2
                              if r["record"] == "node"}
                re_minted = []
                for g, r in old_by_guid.items():
                    r2 = new_by_guid.get(g)
                    if r2 is None:
                        re_minted.append((g, "missing from the merged graph"))
                    elif g == sroot:
                        if r["record_hash"] != r2["record_hash"]:
                            re_minted.append((g, "root's own record_hash "
                                              "moved — its assertions "
                                              "changed, not just its fold"))
                    elif r != r2:
                        re_minted.append((g, "changed"))
                case("an append keeps one root, and every old node is "
                    "byte-identical in the merged graph (not re-minted)",
                    code == 0 and len(roots2) == 1 and n2 > n1
                    and not re_minted,
                    f"{n1} -> {n2} nodes ({n2 - n1} new, ratio "
                    f"{n2 / n1:.3f} — the roadmap's own 1.8x proxy for "
                    f"'not re-minted' {'holds' if n2 < n1 * 1.8 else 'does NOT hold'} "
                    f"here), {len(roots2)} root(s), "
                    f"{len(re_minted)} old node(s) re-minted or changed")

                problems = R.check(recs2)
                case("check is clean after the real append", not problems,
                    problems[:3])

                # guarantee 10's append-specific half: the merged graph
                # reconstructs the FULL grown file's exact original lines.
                rebuilt = SESS.records_to_session(recs2, sroot)
                original = [json.loads(l) for l in lines]
                case("an appended session round-trips to the grown file's "
                    "exact original lines",
                    rebuilt == original,
                    f"{len(rebuilt)} lines reconstructed, "
                    f"{len(original)} expected")

                # -- guarantee 6 (behavioural) ---------------------------
                # The guarantee is "an append-only root whose head changed
                # is a reported problem", and the structural case above is
                # NOT that: it edits params in place, which trips the hash
                # assertions and gets *relabelled* with the contract's
                # name. The mechanism that actually enforces append-only is
                # `_digest_update`'s alignment refusal, and until this case
                # existed nothing tested it — deleting the refusal outright
                # left `test_aota` 15/15 and `verify-0.2.15.sh` 11/0, which
                # is precisely the "check reporting on something other than
                # what it names" this project keeps finding.
                #
                # So: grow the file the honest way, but edit a line inside
                # the head, and require the refusal AND that nothing was
                # written. Both halves matter — a refusal that had already
                # written the delta would be worse than no refusal.
                d3 = tmp / "b3"
                d3.mkdir()
                os.chdir(d3)
                run("init")
                sf3 = d3 / "s.jsonl"
                sf3.write_text(old_text)
                run("digest", "--as=claude-code-transcript",
                    "--mutability=append-only", str(sf3))
                st3 = S.Store.find(d3)
                recs3a, _ = st3.load()
                n3a = sum(1 for r in recs3a if r["record"] == "node")
                root3 = next(r["guid"] for r in recs3a
                             if r["record"] == "node"
                             and r["type"] == "session")
                tampered = list(lines)
                head = json.loads(tampered[3])
                if isinstance(head.get("message"), dict):
                    head["message"]["content"] = "TAMPERED"
                else:
                    head["_tampered"] = True
                tampered[3] = json.dumps(head)
                sf3.write_text("\n".join(tampered) + "\n")
                code3, out3 = run("digest", "--as=claude-code-transcript",
                                  f"--updates={root3}", str(sf3))
                recs3b, _ = st3.load()
                n3b = sum(1 for r in recs3b if r["record"] == "node")
                case("appending a file whose head was edited is refused at "
                    "ingest, and nothing is written",
                    code3 != 0 and "no longer matches" in out3
                    and n3a == n3b,
                    f"exit {code3}, {n3a} -> {n3b} nodes, "
                    f"said: {out3.strip().splitlines()[0] if out3.strip() else '(nothing)'}")

                os.chdir(tmp)

            # -- guarantee 11 ------------------------------------------------
            code, out = run("check")
            case("the base built across every case above passes check "
                 "with 0 problems", code == 0, out.strip().splitlines()[-1]
                 if out.strip() else "")
        finally:
            os.chdir(here)

    for ok, name, detail in results:
        mark = "skip" if ok is None else ("pass" if ok else "FAIL")
        print(f"  {mark}  {name:<70} {detail}")
    skipped = sum(1 for ok, _, _ in results if ok is None)
    ran = len(results) - skipped
    bad = sum(1 for ok, _, _ in results if ok is False)
    tail = f"   ({skipped} skipped: {T.WHY})" if skipped else ""
    print(f"\n{ran - bad}/{ran} AoTA guarantees hold{tail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

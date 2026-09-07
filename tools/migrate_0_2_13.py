#!/usr/bin/env python3
"""
migrate_0_2_13.py — bring a pre-v0.2.13 base up to the fold.

**Why this exists rather than "just re-digest".** v0.2.13 made `record_hash`
and `record_subtree_hash` unconditional on every node, and `check()`'s ninth
and eleventh assertions demand both. A base written by v0.2.12 or earlier has
neither, so `check` reports one problem *per node* and `render` refuses — a
base that worked yesterday is unusable today. Re-digesting is not an escape:
guids are minted fresh, so every citation into that base would break, and
citations are the whole workflow.

**What it does**, as a whole-file rewrite — the only honest form of change to
immutable records (`CLAUDE.md`):

  1. stamps `record_hash` and `record_subtree_hash` on every node;
  2. renames an edge's `content_hash` to `record_hash` (same value: the field
     is excluded from its own input, so only the key changes);
  3. drops the old per-node `content_hash`, which v0.2.13 replaced;
  4. drops `lines` from `session` roots — a derived param that is a function
     of the subtree, which is why a re-ingested transcript's root failed to
     match itself. See `design-total-mapping.md` §6.

**What it deliberately does not do.** It does not retro-fit the v0.2.13
mapping fixes: `signature` and `caller` are recoverable from the parent turn's
`params["log"]`, but reconstructing them here would make a migrated base and a
freshly-digested one silently differ in a *third* way. A migrated base is
valid, not identical to a re-digest, and that distinction should stay visible.

**Idempotent.** Running it twice changes nothing the second time.

    python3 -m tools.migrate_0_2_13 /path/to/base          # report only
    python3 -m tools.migrate_0_2_13 /path/to/base --write  # rewrite

The path is required and is never inferred. Every other tool here walks *up*
the tree looking for `.compost/`; this one refuses to, because the base it
would find on a developer's machine is not a base anyone wants migrated by
accident.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import records as R  # noqa: E402


def graph_dir(base: Path) -> Path:
    """`.compost/graph/` under an explicitly named base. No walking up."""
    for cand in (base / "graph", base / ".compost" / "graph"):
        if cand.is_dir():
            return cand
    raise SystemExit(f"no graph/ under {base} — name the base explicitly, "
                     f"e.g. /path/to/project/.compost")


def migrate(base: Path, write: bool) -> int:
    gd = graph_dir(base)
    files = sorted(gd.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"{gd}: no .jsonl files")

    by_file: dict[Path, list] = {}
    every: list = []
    for f in files:
        recs = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        by_file[f] = recs
        every.extend(recs)

    stats = dict(files=len(files), nodes=0, edges=0, node_content_hash=0,
                 edge_renamed=0, lines_dropped=0, already=0)
    for r in every:
        if r["record"] == "node":
            stats["nodes"] += 1
            if "content_hash" in r:
                del r["content_hash"]
                stats["node_content_hash"] += 1
            if r["type"] == "session" and "lines" in (r.get("params") or {}):
                del r["params"]["lines"]
                stats["lines_dropped"] += 1
            if "record_hash" in r and "record_subtree_hash" in r:
                stats["already"] += 1
        else:
            stats["edges"] += 1
            if "content_hash" in r:
                r["record_hash"] = r.pop("content_hash")
                stats["edge_renamed"] += 1

    # One pass over the whole base: `contains` edges may live in a different
    # file from the nodes they join, so the tree is only whole here.
    R.stamp_hashes(every)

    problems = R.check(every)
    for k, v in stats.items():
        print(f"  {k:20} {v}")
    print(f"  {'check problems':20} {len(problems)}")
    for p in problems[:5]:
        print(f"      {p}")

    if problems:
        print("\nrefusing to write: the migrated records do not pass check()")
        return 1
    if not write:
        print("\nreport only — pass --write to rewrite the files")
        return 0

    for f, recs in by_file.items():
        tmp = f.with_suffix(".jsonl.new")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                               for r in recs), encoding="utf-8")
        tmp.replace(f)
    print(f"\nrewrote {len(by_file)} files")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) != 1:
        raise SystemExit(__doc__.strip().splitlines()[-6].strip())
    sys.exit(migrate(Path(args[0]).resolve(), "--write" in sys.argv))

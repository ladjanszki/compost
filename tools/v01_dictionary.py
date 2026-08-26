#!/usr/bin/env python3
"""
v01_dictionary.py — the v0.1 alias dictionary, built from a digested base.

`compost layer citation --by kg-8hex` can resolve an old `{#a3f2b1c4}` only if
something says which block that handle names. Nothing in the tool can know: an
8-hex handle is not a guid, and the mapping exists only in the material. This
builds it, once, from a base the v0.1 `.dj` files have already been digested
into — **a direct read of the records**. Every node whose pandoc `attr` id is
eight hexadecimal characters maps that handle to the node's guid. No text
matching, no positional alignment, no folding rule, nothing fuzzy.

    python3 -m tools.v01_dictionary [BASE] [--out NAME] [--dry-run]

**This is not a subcommand and will not become one.** `docs/decisions.md`,
"Hand-written graph files are allowed; `check` is the gate": the records
`digest` writes are produced by ordinary Python, and a script producing valid
JSONL is not different in kind. `Store.load()` does not care who wrote a file;
`check` is what enforces every invariant. Run `compost check` afterwards — that
is the gate, and it is not optional.

**Run `tools/dj_prepare.py` before pandoc, or this dictionary is short.**
`pandoc -f djot` drops a block attribute opening a list item, which costs 767
of the corpus's 6,601 handles, and this script cannot see what never arrived.
It reports the count so a short dictionary is visible rather than silent.

**Running it twice is harmless but pointless.** Two aliases for one handle both
name the same block, and `_alias_targets` collects destinations into a set, so
one target remains and nothing becomes ambiguous. It still writes a second
whole file; delete it rather than editing one, which is the one deletion the
rules allow.
"""
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import __version__          # noqa: E402
from src import records as R         # noqa: E402
from src import store as S           # noqa: E402

HEX8 = re.compile(r"^[0-9a-f]{8}$")
SCHEME = "kg-8hex"
PANDOC = "pandoc -f djot -t json"    # recorded, so the base says how it was read


def handles(records: list) -> list[tuple[str, str]]:
    """(legacy handle, node guid) for every node carrying an 8-hex `attr` id."""
    out = []
    for n in records:
        if n["record"] != "node":
            continue
        attr = (n.get("params") or {}).get("attr")
        if not (isinstance(attr, list) and attr and isinstance(attr[0], str)):
            continue
        if HEX8.match(attr[0]):
            out.append((attr[0], n["guid"]))
    return out


def build(records: list) -> tuple[list, list]:
    """Alias nodes and `names` edges. Returns (records, duplicate handles).

    A handle appearing twice would make the dictionary ambiguous by
    construction, so it is returned rather than resolved. The v0.1 corpus has
    none — 6,601 ids, 6,601 distinct — and this exists so that a corpus which
    does say so instead of quietly picking one.
    """
    b = R.Builder()
    seen: dict[str, str] = {}
    dupes = []
    for handle, guid in handles(records):
        if handle in seen:
            dupes.append(handle)
            continue
        seen[handle] = guid
        al = b.node("alias", {"value": handle, "scheme": SCHEME,
                              "generated_by": "tools/v01_dictionary.py",
                              "pandoc": PANDOC})
        n = b.records[-1]
        n["created_at"], n["tool_version"] = R._now(), __version__
        b.edge("names", al, guid, R.CITATION_LAYER, by=SCHEME)
    return b.records, dupes


def main(argv) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in argv
    name = None
    for a in argv[1:]:
        if a.startswith("--out="):
            name = a.split("=", 1)[1]

    try:
        st = S.Store.find(Path(args[0])) if args else S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1

    records, _ = st.load()
    recs, dupes = build(records)
    n = sum(1 for r in recs if r["record"] == "node")
    print(f"  {n:,} aliases, {len(recs):,} records")
    if dupes:
        print(f"  {len(dupes)} handle(s) appear more than once and were skipped:")
        for h in sorted(set(dupes))[:10]:
            print(f"    {h}")
        return 1
    if dry:
        print("  --dry-run: nothing written")
        return 0
    out = name or f"v01-alias-dictionary-{uuid.uuid4()}.jsonl"
    st.write(out, recs)
    print(f"  -> {st.graph.name}/{out}")
    print("  now run: compost check")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

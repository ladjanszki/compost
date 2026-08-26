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

    python3 -m tools.v01_dictionary [BASE] [--all] [--out NAME] [--dry-run]

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

**Only cited handles by default.** The corpus assigns 6,601 and cites 159, so
the full dictionary is 13,202 records answering about two hundred questions.
Nothing is lost: the handle is on the block, in `params["attr"][0]`, so this is
an index over data that stays in the base and `--all` rebuilds it whole. What
it costs is that the filter is a snapshot — a document imported later, citing a
handle nobody had cited before, will not resolve until the dictionary is built
again, and nothing will tell you.

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


def build(records: list, cited_only: bool = True) -> tuple[list, list, dict]:
    """Alias nodes and `names` edges. Returns (records, duplicates, counts).

    **Only handles something actually cites, by default.** The corpus assigns
    6,601 handles and cites 159 of them, so a full dictionary is 13,202 records
    to answer about two hundred questions. The other 6,442 aliases would name
    blocks nobody refers to.

    Nothing is lost by leaving them out, and that is why this is the default
    rather than an option: **the handle itself is on the block**, in
    `params["attr"][0]`, put there by `digest` and never removed. This function
    is an index over data that stays in the base, so a filtered dictionary is
    regenerable in full at any time — `--all` does it. The cost is that the
    filter is a snapshot of what was cited *when it ran*: import a document
    later that cites a handle nobody had cited before and it will not resolve
    until the dictionary is rebuilt. Nothing detects that, in keeping with
    everything else here — the tool does not hold your hand.

    Which handles are cited is read from the records with
    `records.legacy_handle_refs`, the same reader `layer citation --by kg-8hex`
    uses, so the two cannot drift apart or disagree about what a citation is.

    A handle on two blocks would make the dictionary ambiguous by construction,
    so it is reported rather than resolved.
    """
    found = handles(records)
    wanted = None
    if cited_only:
        wanted = {h for h, _ in R.legacy_handle_refs(records)}

    b = R.Builder()
    seen: dict[str, str] = {}
    dupes = []
    for handle, guid in found:
        if wanted is not None and handle not in wanted:
            continue
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

    counts = {"assigned": len({h for h, _ in found}), "minted": len(seen)}
    if wanted is not None:
        counts["cited"] = len(wanted)
        # Cited but assigned nowhere in this base. These get no alias and no
        # `names` edge, so `layer` mints a placeholder for each — which is the
        # correct record of a reference whose target is not here.
        counts["dangling"] = len(wanted - set(seen))
    return b.records, dupes, counts


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
    recs, dupes, c = build(records, cited_only="--all" not in argv)
    n = sum(1 for r in recs if r["record"] == "node")
    print(f"  {n:,} aliases, {len(recs):,} records")
    if "cited" in c:
        print(f"  {c['assigned']:,} handles assigned in the base, "
              f"{c['cited']:,} of them cited")
        if c["dangling"]:
            print(f"  {c['dangling']} cited but assigned nowhere here — "
                  f"`layer` will mint a placeholder for each")
    else:
        print(f"  --all: every assigned handle, cited or not")
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

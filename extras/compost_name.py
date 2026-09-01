#!/usr/bin/env python3
"""
compost_name.py — `compost-name`: give a root a display name.

Installed, but not the tool (DEVELOPMENT.md, "What belongs in extras/"): the
same standing as `compost-new`. It composes things the tool already does — a
lookup through `derived_from`, a `records.Builder` node and edge, `check` —
rather than adding a capability of its own, so it stays out of `compost`'s
own dispatch table and never moves the subcommand count `docs/man-compost.md`
asserts and `tests/test_manpage.py` enforces. Exposed through
`[project.scripts]` as `compost-name`, a distinct command from `compost`:
`compost name` would read as a subcommand.

    compost-name <root-guid | storage-name> "The display name"

A display name is a **record**, not a field on the root — records are
immutable and the root is not ours to edit (docs/roadmap.md, v0.2.10). It is
its own node,

    {"type": "display_name", "params": {"value": "..."}}

joined to the root by a `names` edge in its own `display` layer — not a
reuse of `alias`'s use of `names`: an alias answers "what does this string
resolve to" (input to node), a display name answers "what should be shown
for this node" (node to string). Opposite directions, and overloading them
would put display names in `lookup`'s resolver.

The identifier is a root's own guid, or the storage name as it appears under
`.compost/storage/` — `GUID.EXT` — resolved by finding the `blob` whose
`params["stored_as"]` matches and then the `derived_from` edge pointing at
it, **never** by parsing the string into a guid: `CLAUDE.md` is explicit that
nothing turns a filename into a storage path.

Refuses three things, each with its own message and nothing written: an
identifier that resolves to nothing, a resolved target that is not in
`records.ROOT_TYPES` (a display name is for a root; naming a paragraph would
write a record nothing reads), and an empty name.

Each run writes a **new** `graph/<uuid>.jsonl` file holding the node and its
edge — it never edits one, the same append-only rule every writer here
follows. Renaming is running it again; the view takes the newest by the
naming edge's `created_at`, ties broken by the node's own guid, so the older
names simply stay as the record of what the thing used to be called. `check`
runs on the result and is reported, because a writer outside the tool is
exactly the case it exists for.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import records as R    # noqa: E402
from src import store as S      # noqa: E402

LAYER = "display"
NODE_TYPE = "display_name"

USAGE = 'usage: compost-name <root-guid | storage-name> "The display name"'


def _resolve(recs: list, nodes: dict, ident: str) -> str | None:
    """`ident` to a root guid, or None.

    A guid already in the graph is used as-is. Otherwise `ident` is tried as
    a storage name (`GUID.EXT`, as it appears under `.compost/storage/`):
    the `blob` whose `params["stored_as"]` matches, then the `derived_from`
    edge whose destination is that blob — its source is the root. Nothing
    here strips an extension or otherwise guesses a guid out of a string.
    """
    if ident in nodes:
        return ident
    blob_guid = None
    for r in recs:
        if (r["record"] == "node" and r["type"] == "blob"
                and r.get("params", {}).get("stored_as") == ident):
            blob_guid = r["guid"]
            break
    if blob_guid is None:
        return None
    for r in recs:
        if (r["record"] == "edge" and r["type"] == "derived_from"
                and r["destination"] == blob_guid):
            return r["source"]
    return None


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(USAGE)
        return 2
    ident, name = argv

    try:
        st = S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1

    recs, _ = st.load()
    nodes = {r["guid"]: r for r in recs if r["record"] == "node"}

    guid = _resolve(recs, nodes, ident)
    if guid is None:
        print(f"compost-name: {ident!r} does not resolve to anything in "
              f"this base — not a guid, not a storage name")
        return 1

    target = nodes[guid]
    if target["type"] not in R.ROOT_TYPES:
        print(f"compost-name: {guid} is a {target['type']!r}, not a root "
              f"({sorted(R.ROOT_TYPES)}) — a display name is for a root")
        return 1

    print(f"  resolved {ident!r} -> {guid} ({target['type']})")

    if not name.strip():
        print("compost-name: the name must not be empty")
        return 1

    b = R.Builder()
    dn = b.node(NODE_TYPE, {"value": name})
    b.edge("names", dn, guid, LAYER)
    dest = st.write(f"{uuid.uuid4()}.jsonl", b.records)
    print(f"  wrote {dest.relative_to(st.root)}: {guid} named {name!r}")

    problems = st.check()
    if problems:
        print(f"  check: {len(problems)} problem(s) after this write")
        for p in problems[:5]:
            print(f"    PROBLEM {p}")
        return 1
    print("  check: 0 problems")
    return 0


if __name__ == "__main__":
    sys.exit(main())

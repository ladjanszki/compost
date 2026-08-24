#!/usr/bin/env python3
"""
layers.py — compost layer.

The second writer to graph/. Unlike `digest`, which reads bytes nobody has
seen before, a layer reads the base itself and derives new records from what
is already there — a citation resolved against every earlier import, not just
the batch it arrived in.

    compost layer                        list what can be built
    compost layer NAME [--by SCHEME]     build it

Bare `compost layer` is static help: the registry of what *can* be built, not
a report on the base. There is no `drop`, no bookkeeping of what has been
built, and no declaration written into the graph — running a builder twice
produces two complete sets of records and removes neither, which is the
governing decision this whole release is built on (docs/roadmap.md).
"""
import uuid
from pathlib import Path

from . import __version__          # NOT `import src`; that fails inside the package
from . import records as R
from . import store as S


def _citation(recs, name, by):
    """Citation edges, plus a placeholder for every target that is not here.

    An unresolved target cannot become an edge — a dangling endpoint fails
    `check` and takes the whole graph down. Before this it had nowhere to live
    at all: not in the text, not in the graph, only in terminal output. Now the
    absence is a record.
    """
    b = R.Builder()
    edges, unresolved = R.citation_edges(recs)
    for e in edges:
        # schema_version is NOT optional here. citation_edges builds raw dict
        # literals rather than going through Builder.edge(), so nothing has
        # added it — and "required on write" would be violated by the very
        # release that introduces it.
        e["schema_version"] = R.SCHEMA_VERSION
        e["layer"], e["by"] = name, by
        e["created_at"], e["tool_version"] = R._now(), __version__
        e["content_hash"] = R.edge_hash(e)

    # One alias and one placeholder per *distinct* value in this build. Two
    # citations of the same missing handle share one placeholder.
    seen = {}
    for value, source in unresolved:
        if value not in seen:
            ph = b.node("unresolved_citation")
            al = b.node("alias", {"value": value, "scheme": by})
            b.edge("names", al, ph, name, by=by)
            seen[value] = ph
        b.edge("cites", source, seen[value], name, by=by)
    return {"cites": len(edges) + sum(1 for _ in unresolved),
            "placeholders": len(seen),
            "records": edges + b.records,
            "unresolved": sorted(seen)}


# name -> {by -> builder}. Named the way routes are named, and for the same
# reason: what produced a record is written down, never inferred.
# Defined AFTER _citation — a module-level dict that names a function defined
# below it raises NameError at import time, and the module would not load.
BUILDERS = {
    "citation": {"uuid-link": _citation},
}


def build(st, name: str, by: str) -> dict:
    """Generate a layer. Reads the base; writes one new file. Nothing else.

    This does NOT look at what a previous run wrote. Running it twice produces
    two complete sets of records and removes neither. That is deliberate: see
    docs/roadmap.md, "the tool does not hold your hand".
    """
    recs, _ = st.load()
    r = BUILDERS[name][by](recs, name, by)
    st.write(f"{uuid.uuid4()}.jsonl", r["records"])
    return r


def main(argv):
    """Called as `layers.main(argv[1:])` from `cli.main`, so `argv[0]` is the
    subcommand name itself — `"layer"` — exactly like `views.main`. NAME and
    `--by` are parsed from `argv[1:]`."""
    try:
        st = S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1

    rest = argv[1:]
    if not rest:
        print("what can be built:")
        for name, bys in BUILDERS.items():
            print(f"  {name} ({', '.join(bys)})")
        return 0

    name = rest[0]
    if name not in BUILDERS:
        print(f"unknown layer {name!r}")
        print("what can be built:")
        for n, bys in BUILDERS.items():
            print(f"  {n} ({', '.join(bys)})")
        return 2

    bys = BUILDERS[name]
    by = None
    opts = rest[1:]
    i = 0
    while i < len(opts):
        a = opts[i]
        if a == "--by":
            if i + 1 >= len(opts):
                print("--by needs a scheme")
                return 2
            by = opts[i + 1]
            i += 2
        elif a.startswith("--by="):
            by = a.split("=", 1)[1]
            i += 1
        else:
            print(f"unknown option {a!r}")
            return 2

    if by is None:
        if len(bys) == 1:
            by = next(iter(bys))
        else:
            print(f"--by is required for {name!r}; choices: {', '.join(bys)}")
            return 2
    if by not in bys:
        print(f"unknown scheme {by!r} for {name!r}; choices: {', '.join(bys)}")
        return 2

    r = build(st, name, by)
    n_unresolved = len(r["unresolved"])
    n_placeholders = r["placeholders"]
    print(f"  {r['cites']:,} cites edges  |  {n_unresolved} unresolved -> "
          f"{n_placeholders} placeholder{'' if n_placeholders == 1 else 's'}")
    for v in r["unresolved"][:10]:
        print(f"    {v}")
    if n_unresolved > 10:
        print(f"    … and {n_unresolved - 10} more")
    return 0

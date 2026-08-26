#!/usr/bin/env python3
"""
layers.py — compost layer.

The tool's second writer to graph/ — not the base's. Anything emitting valid
JSONL under graph/ writes records on the same terms; `check` is the gate, not
authorship (docs/decisions.md, "Anything may write records").

Unlike `digest`, which reads bytes nobody has seen before, a layer reads the
base itself and derives new records from what is already there — a citation resolved against every earlier import, not just
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


def _entity(b, type_, params=None):
    """`b.node()`, plus provenance as top-level keys, never inside `params`.

    Only `alias` and `unresolved_citation` need this today — both carry no
    `content_hash`, whose input is `canonical([type, params, content])` and
    so is blind to whatever else a record carries. Putting created_at and
    tool_version in `params` would work for these two but set a precedent
    that breaks the first time a *hashed* type needs provenance. Decided
    once, here, while it is free — general node types keep Builder.node()'s
    existing shape, since the grammar (record-grammar.md §2) already gives
    nodes no provenance fields and this release does not extend that.
    """
    guid = b.node(type_, params)
    n = b.records[-1]
    n["created_at"], n["tool_version"] = R._now(), __version__
    return guid


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
            ph = _entity(b, "unresolved_citation")
            al = _entity(b, "alias", {"value": value, "scheme": by})
            b.edge("names", al, ph, name, by=by)
            seen[value] = ph
        b.edge("cites", source, seen[value], name, by=by)
    return {"cites": len(edges) + sum(1 for _ in unresolved),
            "placeholders": len(seen),
            "records": edges + b.records,
            "unresolved": sorted(seen),
            "ambiguous": {}}


def _alias_targets(recs, scheme) -> dict:
    """value -> the real nodes its aliases name. Placeholders excluded.

    **The rule that keeps this linear.** After one build with no dictionary
    present, every legacy handle already has an `alias` naming an
    `unresolved_citation`. A second build looking aliases up by value would
    find those beside the real target, and each pre-dictionary build would add
    another candidate — growth quadratic in build count rather than linear, and
    every handle permanently ambiguous. So a `names` edge whose destination is
    a placeholder is not followed. The placeholder itself is never retracted;
    it just stops being an answer.
    """
    placeholders = {r["guid"] for r in recs if r["record"] == "node"
                    and r["type"] == "unresolved_citation"}
    aliases = {r["guid"]: (r.get("params") or {}).get("value")
               for r in recs if r["record"] == "node" and r["type"] == "alias"
               and (r.get("params") or {}).get("scheme") == scheme}
    out: dict[str, set] = {}
    for e in recs:
        if e["record"] != "edge" or e["type"] != "names":
            continue
        value = aliases.get(e["source"])
        if value is None or e["destination"] in placeholders:
            continue
        out.setdefault(value, set()).add(e["destination"])
    return out


def _kg8hex(recs, name, by):
    """v0.1 `{#8hex}` citations, resolved through the alias dictionary.

    The second customer of v0.2.4's naming machinery, and the first scheme
    whose placeholders can actually resolve later: a `uuid-link` target is
    absent because the document is not in the base, but a `kg-8hex` target is
    absent because the *dictionary* is not, and the dictionary arrives from
    outside. Build before it lands and every handle gets a placeholder; add the
    file, rebuild, and the same handles mint real edges. Nothing is retracted —
    the old placeholder stays as the record of a moment when it did not resolve.

    Nothing here rewrites the corpus. The v0.1 syntax stays exactly as written,
    on disk and at render time; what this adds is a way to look it up.
    """
    b = R.Builder()
    targets = _alias_targets(recs, by)

    n_cites = 0
    ambiguous: dict[str, int] = {}
    unresolved: list[tuple[str, str]] = []
    for handle, source in R.legacy_handle_refs(recs):
        found = targets.get(handle) or set()
        if len(found) == 1:
            # Straight through Builder.edge, which is where schema_version,
            # created_at, tool_version and content_hash already live. The
            # uuid-link path decorates raw dicts only because citation_edges
            # predates all four.
            b.edge("cites", source, next(iter(found)), name, by=by)
            n_cites += 1
        elif found:
            ambiguous[handle] = len(found)   # mint nothing; say so instead
        else:
            unresolved.append((handle, source))

    seen: dict[str, str] = {}
    for value, source in unresolved:
        if value not in seen:
            ph = _entity(b, "unresolved_citation")
            al = _entity(b, "alias", {"value": value, "scheme": by})
            b.edge("names", al, ph, name, by=by)
            seen[value] = ph
        b.edge("cites", source, seen[value], name, by=by)
        n_cites += 1

    return {"cites": n_cites, "placeholders": len(seen),
            "records": b.records, "unresolved": sorted(seen),
            "ambiguous": ambiguous}


# name -> {by -> builder}. Named the way routes are named, and for the same
# reason: what produced a record is written down, never inferred.
# Defined AFTER _citation — a module-level dict that names a function defined
# below it raises NameError at import time, and the module would not load.
BUILDERS = {
    "citation": {"uuid-link": _citation, "kg-8hex": _kg8hex},
}

# The default has to be *named*, not "the only one there is". Until v0.2.5
# `citation` had a single scheme and bare `compost layer citation` fell through
# to it; adding a second would have turned that into "--by is required" and
# broken every documented invocation. It also matters which one wins: the
# legacy scheme reads prose for eight hex characters, and a conversation that
# says in words "handles look like {#a3f2b1c4}" mints a real edge if that
# string is also a real handle. Nothing structural excludes it, so kg-8hex
# stays opt-in and is never what you get by not choosing.
DEFAULT_BY = {
    "citation": "uuid-link",
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
        by = DEFAULT_BY.get(name)
        if by is None:
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

    # Ambiguity is not an error and does not stop the build: the resolvable
    # handles still mint edges. It is reported because nothing else would say
    # so — an ambiguous handle mints no record at all, so silence would look
    # exactly like a handle nobody cited.
    if r["ambiguous"]:
        print(f"  {len(r['ambiguous'])} ambiguous, minted nothing:")
        for h, count in sorted(r["ambiguous"].items())[:10]:
            print(f"    {h} -> {count} distinct targets")
        if len(r["ambiguous"]) > 10:
            print(f"    … and {len(r['ambiguous']) - 10} more")
    return 0

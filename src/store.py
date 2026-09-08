#!/usr/bin/env python3
"""
store.py — the on-disk graph.

    .compost/
      storage/    immutable sources, exactly as ingested
      graph/      *.jsonl records, committed
      views/      generated, disposable
      graphviz/   generated, disposable — `compost draw`'s DOT and SVG

`.compost/` is also the marker: the root is found by walking up until a
directory of that name appears. Nothing else identifies a base, so a base
cannot be half-configured.

Four rules the loader depends on, each of which exists because breaking it
is silent rather than loud:

- **Only `*.jsonl` is loaded.** A `.jsonl~` editor backup, a `.bak`, a
  half-written temp file — none of them are the graph.
- **Writes are a temp file plus an atomic rename.** A partial write never
  holds the extension, so a crash mid-write cannot produce a file the loader
  would believe.
- **Filenames carry no meaning and load order is irrelevant.** Records are
  concatenated from every matching file; grouping is for humans to read, and
  shuffling the file order must produce an identical graph.
- **`graph/` is flat.** `write()` refuses a relpath naming a subdirectory and
  `files()` globs rather than walks, so nothing can land somewhere a second
  reader would not look. v0.2.8 added this ahead of a read-only SQL view
  beside this one — a directory is meaning, and a subdirectory visible to one
  reader and not the other is a silent disagreement about the graph
  (docs/roadmap.md, "graph/ becomes flat by rule").

The loaded file list is returned rather than hidden, because the failure mode
of "everything in graph/ is the graph" is surprise about what was in there.
"""
import hashlib
import os
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path

from . import records as R
from . import routes as RT

MARKER = ".compost"
# Ingestion facts — which bytes a document came from — kept apart from the
# structure pandoc found inside them.
INGEST_LAYER = "ingestion"
# Which agent ran under which tool call. Its own layer: an agent launching
# another is a different kind of fact from a document coming from some bytes,
# and keeping them apart is what lets either be reasoned about alone.
AGENT_LAYER = "agent"


class NotABase(Exception):
    pass


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    # -- locating ----------------------------------------------------------
    @classmethod
    def find(cls, start: Path | None = None) -> "Store":
        here = Path(start or Path.cwd()).resolve()
        for d in [here, *here.parents]:
            if (d / MARKER).is_dir():
                return cls(d)
        raise NotABase(f"no {MARKER}/ in {here} or any parent")

    @classmethod
    def init(cls, root: Path) -> "Store":
        s = cls(root)
        for d in (s.graph, s.storage, s.views, s.graphviz):
            d.mkdir(parents=True, exist_ok=True)
        return s

    @property
    def base(self) -> Path:
        return self.root / MARKER

    @property
    def graph(self) -> Path:
        return self.base / "graph"

    @property
    def storage(self) -> Path:
        return self.base / "storage"

    @property
    def views(self) -> Path:
        return self.base / "views"

    @property
    def graphviz(self) -> Path:
        # A peer of graph/, storage/ and views/, not a subdirectory of
        # views/: an HTML view will eventually *embed* this output, so it is
        # an input to `render` rather than one of its products — the same
        # direction storage/ feeds graph/. See docs/roadmap.md,
        # "v0.2.7 — a graph view".
        return self.base / "graphviz"

    # -- writing -----------------------------------------------------------
    def write(self, relpath: str, recs: list) -> Path:
        """Write records to graph/<relpath>, atomically.

        `graph/` is flat by rule: a subdirectory is meaning, and
        `docs/decisions.md` already says filenames carry none — so `relpath`
        must name a bare file directly under `graph/`, and this refuses
        rather than creating one, on purpose (docs/roadmap.md, "graph/
        becomes flat by rule"). Checked by comparing `dest.parent` to
        `self.graph` rather than scanning for a separator character, so it
        also catches `..` and anything else that would land outside it.
        """
        dest = self.graph / relpath
        if dest.suffix != ".jsonl":
            raise ValueError(f"graph files must be .jsonl, got {dest.name}")
        if dest.parent != self.graph:
            raise ValueError(
                f"graph/ is flat: {relpath!r} is not a bare filename")
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(R.to_jsonl(recs))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)      # atomic within a filesystem
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return dest

    def keep_bytes(self, data: bytes, name: str) -> Path:
        """
        Write `data` into `storage/<name>`, which must not already exist.

        `name` is a guid plus an extension, so a collision is a minted uuid
        repeating itself and the right response is to stop rather than to
        merge — see `keep_blob`, below, which shares this reasoning and this
        body. This is the form a source with no file of its own to copy from
        uses: a delegated fragment (v0.2.14, "the recursion made explicit")
        has already been read into memory by the digestor that found it, so
        there is no path to hand over, only the bytes themselves.

        Written through a temp file and renamed, for the same reason graph
        writes are: a half-written source is a corrupt immutable original,
        and a crash must not be able to produce one.
        """
        dest = self.storage / name
        if dest.exists():
            raise ValueError(f"{name} is already in storage/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return dest

    def keep_blob(self, path: Path, name: str) -> Path:
        """Copy `path`'s bytes into `storage/<name>`. See `keep_bytes`."""
        return self.keep_bytes(Path(path).read_bytes(), name)

    def blobs(self) -> dict:
        """Bytes hash -> every blob guid carrying those bytes."""
        recs, _ = self.load()
        out: dict[str, list[str]] = {}
        for r in recs:
            if r["record"] == "node" and r["type"] == "blob":
                out.setdefault(r["params"]["bytes_sha256"], []).append(r["guid"])
        return out

    # -- loading -----------------------------------------------------------
    def files(self) -> list[Path]:
        # `glob`, not `rglob`: graph/ is flat by rule (see `write`, above), so
        # nothing under a subdirectory is the graph even if one exists — from
        # an older checkout, a hand-copied file, or anything else that put one
        # there. Restoring `rglob` here would make such a file visible to
        # Python again while a SQL glob over the same directory still misses
        # it, which is the exact divergence this rule exists to close.
        return sorted(p for p in self.graph.glob("*.jsonl") if p.is_file())

    def load(self) -> tuple[list, list[Path]]:
        """
        Every record under graph/, deduplicated.

        Byte-identical duplicates collapse silently — two writers asserting the
        same fact is agreement, not conflict. A guid carrying two *different*
        records is a hard error and is left for `check` to report rather than
        resolved here, because picking a winner is how a corpus starts lying.
        """
        seen: dict[bytes, dict] = {}
        out: list = []
        for f in self.files():
            for rec in R.from_jsonl(f.read_text(encoding="utf-8")):
                key = R.canonical(rec)
                if key in seen:
                    continue
                seen[key] = rec
                out.append(rec)
        return out, self.files()

    def check(self) -> list[str]:
        recs, _ = self.load()
        return R.check(recs)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _route_of(argv: list) -> tuple[str | None, list[str], bool, str | None]:
    """Split `--as=ROUTE` and `--no-follow` out of the argument list.

    Returns (route, files, follow, error). The route is never inferred: a
    missing or unknown `--as` is an error naming the routes, not a guess at
    what the caller meant. That refusal is the point of the flag.
    """
    route, files, follow, i = None, [], True, 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            # The usual end-of-options escape, so a file whose name begins
            # with a dash can still be named.
            files.extend(argv[i + 1:])
            break
        if a.startswith("--as="):
            route = a.split("=", 1)[1]
        elif a == "--as":
            if i + 1 >= len(argv):
                return None, [], True, "--as needs a route"
            route = argv[i + 1]
            i += 1
        elif a == "--no-follow":
            follow = False
        elif a.startswith("-"):
            return None, [], True, f"unknown option {a!r}"
        else:
            files.append(a)
        i += 1
    if route is None:
        return None, files, True, "--as is required"
    if route not in RT.ROUTES:
        return None, files, True, f"unknown route {route!r}"
    return route, files, follow, None


def _link_agents(plans) -> int:
    """Join each subagent transcript to the tool call that launched it.

    The sidechain's root carries its `.meta.json` sidecar, whose `toolUseId`
    names an `Agent` block in the transcript that spawned it — and that block
    is already a `toolcall` node keyed by the same id. So the join is an
    equality between two things both already in the graph, not an inference.

    `launched` rather than `contains`: the subagent's turns are not *inside*
    the tool call, and `check` allows a node exactly one container. It runs
    across the whole batch, which is why nesting works — a depth-2 agent finds
    its parent among the depth-1 transcripts pulled in by the same invocation.

    Only edges whose both ends are in this batch are minted. Digest a sidechain
    alone and it simply carries its sidecar until the other end arrives; the
    fact is stored either way, and this only writes down what follows from it.
    """
    calls = {}
    for _, _, recs, _, _, _, _ in plans:
        for r in recs:
            if r["record"] == "node" and r["type"] == "toolcall":
                calls[r["params"].get("tool_use_id")] = r["guid"]
    n = 0
    for plan in plans:
        recs, root = plan[2], plan[3]
        node = next((r for r in recs if r.get("guid") == root), None)
        tuid = (node or {}).get("params", {}).get("agent", {}).get("toolUseId")
        parent = calls.get(tuid)
        if parent is None:
            continue
        b = R.Builder()
        b.edge("launched", parent, root, AGENT_LAYER)
        plan[2] = recs + b.records
        n += 1
    return n


def _structural_gaps(plans, known_guids: set) -> list[tuple[str, str, str, str]]:
    """`(filename, edge type, end, missing guid)` for every edge endpoint
    this batch mints that resolves to nothing.

    Pulled out of `_digest` as its own function so the guarantee it gives —
    every structural edge a batch mints has to resolve, or nothing is
    written — can be sabotaged in isolation in the test suite: patch this to
    always return `[]` and a batch with a broken `responds_to` writes a
    dangling edge straight into the graph, which is exactly the failure this
    exists to prevent (`docs/roadmap.md`, "the conversation loop").
    """
    out = []
    for src, _, recs, _, _, _, _ in plans:
        for r in recs:
            if r["record"] != "edge":
                continue
            for end in ("source", "destination"):
                if r[end] not in known_guids:
                    out.append((src.name, r["type"], end, r[end]))
    return out


def _digest(s: Store, route: str, args: list[str], prog: str,
            follow: bool = True) -> int:
    """
    Ingest every file in `args` as `route`, plus the files those name.

    Two phases, and the split is load-bearing. **Nothing is written until
    every input has been read and parsed**, because storage names are now
    minted rather than derived: a batch that dies halfway leaves the files it
    already ingested in the base, and re-running it after fixing the bad input
    would ingest them a *second* time under fresh guids. Validating first
    makes a batch safe to re-run, which is the only reason it is safe to pass
    a glob to this command.

    A route may also say that the file it read **names other files**, and those
    join the batch. That is the one place this command reads something it was
    not handed; `--no-follow` turns it off. Every discovery is printed, because
    a side effect nobody can see is the kind that gets discovered by accident
    two months later.

    A **third** promise, added for the route that names a guid from outside
    its own file (`claude-code-response`'s `responds_to`): every edge endpoint
    a route mints must resolve, either within this batch or already in the
    base, or nothing is written — see the guid check below, after every file
    has been read.
    """
    plans, seen = [], {}
    base_recs, _ = s.load()
    base_guids = {r["guid"] for r in base_recs if r["record"] == "node"}
    known: dict[str, list[str]] = {}
    for r in base_recs:
        if r["record"] == "node" and r["type"] == "blob":
            known.setdefault(r["params"]["bytes_sha256"], []).append(r["guid"])
    queue = [(Path(a), None) for a in args]
    done: set[Path] = set()
    while queue:
        src, referrer = queue.pop(0)
        try:
            key = src.resolve()
        except OSError:
            key = src
        if key in done:
            continue
        done.add(key)

        if src.is_dir():
            print(f"  {src}: is a directory. Ingest the files themselves — "
                  f"the shell already expands them:")
            print(f"    {prog} digest --as={route} {str(src).rstrip('/')}/*")
            return 1
        if not src.is_file():
            if referrer is not None:
                # A referenced file that is not here is not an error: a
                # transcript copied out of ~/.claude without its subagents/
                # directory is an ordinary thing to digest. Say so and move on.
                print(f"  {referrer.name} names {src.name}, which is not here"
                      f" — skipped")
                continue
            print(f"  {src}: no such file")
            return 1

        data = src.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        try:
            recs, root = RT.read(route, src)
        except Exception as e:
            # Named with the file and the route, because "it failed" about a
            # glob of forty is not a report anyone can act on.
            print(f"  {src.name}: cannot read as {route}: {e}")
            print("  nothing was written")
            return 1

        b = R.Builder()
        guid = b.mint()
        stored = guid + src.suffix
        b.node("blob", {
            "original_name": src.name,
            "stored_as": stored,
            "bytes_sha256": sha,
            "imported_at": R._now(),
            "route": route,
        }, guid=guid)
        # The document was derived *from* the bytes; it is not contained by
        # them. Its own layer, so the ingestion facts can be reasoned about
        # without touching the structure pandoc found.
        b.edge("derived_from", root, guid, INGEST_LAYER)
        # A route may have already delegated part of its own input to the
        # digestor that owns it (v0.2.14, "the recursion made explicit") —
        # `session.py` does, for a transcript turn's prose. Each delegated
        # fragment already carries a `derived_from` edge from the document it
        # produced to its own fragment blob; this is the second hop, fragment
        # blob to the *whole file's* blob, and it can only be minted here —
        # this is the first place `guid`, the file's own blob, exists.
        # Detected structurally, not by route name: any `blob` node already
        # in the route's own output (`original_name is None` — a fragment,
        # never a file, since it has no filename of its own) is awaiting
        # exactly this edge. `recs` at this point is still the route's own
        # output only, before this plan's own file blob joins it below, so
        # the check would even be safe without the `original_name` filter —
        # kept anyway so this loop and the write loop below read the same
        # discriminator rather than two that happen to agree here.
        for r in recs:
            if (r["record"] == "node" and r["type"] == "blob"
                    and r["params"].get("original_name") is None):
                b.edge("derived_from", r["guid"], guid, INGEST_LAYER)
        # `blob` is UNCONTAINED — a leaf, and the whole tree `b.records`
        # holds — so this is the same one-node fold `layers.py` does for its
        # own mints.
        R.stamp_hashes(b.records)

        plans.append([src, stored, recs + b.records, root, guid,
                      known.get(sha, []) + seen.get(sha, []), referrer])
        seen.setdefault(sha, []).append(guid)

        if follow:
            for ref in RT.referrals(route, src):
                queue.append((ref, src))

    _link_agents(plans)

    # Every edge endpoint any route or `_link_agents` minted must be a guid
    # this batch is *about to write* or one that is *already committed* —
    # never an absence pretending to be a fact. This is deliberately not the
    # citation path: a citation whose target is missing is real information
    # (something was cited that is not here yet) and `compost layer citation`
    # records it as a placeholder. A structural field like `responds_to`
    # naming a guid nobody minted is not a fact about the world, it is a typo
    # in whatever produced the file, and minting an `unresolved_citation` for
    # it would write that typo into the graph as if it meant something.
    # Checked here, once, rather than per-route, so every future route that
    # names a guid from outside its own file is covered for free.
    batch_guids = {r["guid"] for _, _, recs, _, _, _, _ in plans
                   for r in recs if r["record"] == "node"}
    gaps = _structural_gaps(plans, base_guids | batch_guids)
    if gaps:
        name, etype, end, missing = gaps[0]
        print(f"  {name}: a {etype} edge's {end} names {missing}, which is "
              f"not in this batch or the base")
        print("  nothing was written")
        return 1

    total_n = total_e = 0
    for src, stored, recs, root, guid, dup, referrer in plans:
        s.keep_blob(src, stored)
        # Every delegated fragment this route's own output carries — see the
        # `derived_from` wiring above. `content` is the fragment exactly as
        # `session.py` stored it (the whole content-block dict, or the bare
        # string when a line's `content` was a string already); `R.canonical`
        # is the same serialisation `record_hash` already trusts, so the
        # bytes on disk and the bytes the hash was taken over are one
        # decision, made once.
        # `recs` here is the route's own output *plus* this plan's own
        # top-level blob (appended below, before the plan was queued) — so
        # `original_name is None` is the discriminator, not `type == "blob"`
        # alone: the top-level blob's bytes were just copied by `keep_blob`
        # above, and writing it a second time here would collide with itself.
        for r in recs:
            if (r["record"] == "node" and r["type"] == "blob"
                    and r["params"].get("original_name") is None):
                s.keep_bytes(R.canonical(r.get("content")),
                            r["params"]["stored_as"])
        # A fresh uuid, unrelated to the blob's. The two names must not be
        # derivable from each other, or something will eventually derive one
        # from the other — which is the suffix-routing mistake wearing a
        # different hat.
        dest = s.write(f"{uuid.uuid4()}.jsonl", recs)
        n = sum(1 for r in recs if r["record"] == "node")
        total_n += n
        total_e += len(recs) - n
        via = f"  (named by {referrer.name})" if referrer is not None else ""
        print(f"  {src.name} -> {dest.relative_to(s.root)}  "
              f"({n} nodes, {len(recs) - n} edges, "
              # The whole guid, not an 8-character prefix: `lookup` refuses a
              # prefix outright, so printing one here handed back a string you
              # could not paste back into the tool. docs/roadmap.md, v0.2.9.
              f"root {root}, blob {guid}){via}")
        if dup:
            # Not an error. Storage is a blob store and the same bytes may
            # legitimately arrive twice; what would be wrong is for the second
            # copy to be silent. The count matters more than the guid — one
            # accidental re-ingest is a shrug, five is a habit.
            n_dup = len(dup)
            print(f"    note: these bytes are already in "
                  f"{n_dup} blob{'s' if n_dup > 1 else ''}, e.g. {dup[0]}")
    print(f"{total_n} nodes, {total_e} edges")
    return 0


def main(argv):
    # `compost` when the CLI dispatched us, `store.py` when this module was run
    # directly. Taken from argv rather than hard-coded, so the usage a reader
    # sees is always a command they can actually type.
    prog = Path(argv[0]).name
    usage = (f"usage: {prog} init [dir] | digest --as=<route> <file>... | ls"
             f" | check | lookup <handle>")
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0])
        print(usage)
        return 2
    cmd = argv[1]

    if cmd == "init":
        s = Store.init(Path(argv[2]) if len(argv) > 2 else Path.cwd())
        print(f"initialised {s.base}")
        return 0

    if cmd not in ("digest", "ls", "check", "lookup"):
        print(f"unknown command {cmd!r}")
        print(usage)
        return 2

    try:
        s = Store.find()
    except NotABase as e:
        print(e)
        return 1

    if cmd == "digest":
        route, files, follow, err = _route_of(argv[2:])
        if err or not files:
            print(f"usage: {prog} digest --as=<route> <file>...")
            if err:
                print(f"  {err}")
            print("\nroutes:")
            print(RT.listing())
            print("\nThe route is never guessed from the extension. A file "
                  "named\n`notes.jsonl` digested --as=notes is markdown, "
                  "because that is what was asked for.")
            return 2
        return _digest(s, route, files, prog, follow)

    if cmd == "ls":
        recs, files = s.load()
        for f in files:
            print(f"  {f.relative_to(s.root)}")
        nodes = sum(1 for r in recs if r["record"] == "node")
        roots = sum(1 for r in recs if r["record"] == "node"
                    and r["type"] in R.ROOT_TYPES)
        print(f"{len(files)} files, {roots} documents and sessions, "
              f"{nodes} nodes, {len(recs) - nodes} edges")
        return 0

    if cmd == "lookup":
        if len(argv) < 3:
            print(f"usage: {prog} lookup <handle>")
            return 2
        handle = argv[2]
        recs, _ = s.load()
        # No `check` gate, deliberately, and unlike `render`. A view asserts the
        # whole graph is sound; a lookup answers one question from whatever is
        # on disk. Refusing to resolve a handle because some other file has a
        # dangling edge would make a broken base harder to debug, not safer.
        # It is also not gated on `compost layer` having been rebuilt: on a
        # base where the citation layer is stale, this under-reports rather
        # than lies — an accepted risk, recorded in docs/roadmap.md.
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        edges = [r for r in recs if r["record"] == "edge"]

        parent = {e["destination"]: e["source"] for e in edges
                  if e["type"] == "contains"}
        # v0.2.14: a prose block's `contains` chain now ends at a delegated
        # `document` rather than at a `session` — that document is a root
        # nobody contains (`docs/roadmap.md`, "the recursion made explicit")
        # and it carries no `source` of its own. `delegated_by` is the
        # reverse of the edge that reached it, document guid -> the turn
        # that delegated to it, so `where` can step back onto the turn's own
        # `contains` chain and keep going from there.
        delegated_by = {e["destination"]: e["source"] for e in edges
                        if e["type"] == "delegates_to"}

        def where(g):
            """The source file of the root that contains `g`.

            Follows `delegates_to` backwards once a parentless `document` is
            reached — the edge exists precisely to say where a fragment came
            from, and reading it is cheaper and more honest than copying the
            transcript's `source` onto every fragment at import time.
            """
            seen = set()
            while g in parent and g not in seen:
                seen.add(g)
                g = parent[g]
            n = nodes.get(g, {})
            src = n.get("params", {}).get("source")
            if src is not None:
                return src
            turn = delegated_by.get(g)
            if turn is not None and turn not in seen:
                return where(turn)
            return "?"

        # value -> every alias node naming it. Several aliases sharing a
        # value is expected, not an error — two builds of the citation layer
        # mint two aliases for the same missing handle, naming two different
        # placeholders. Never picked from silently; every match is printed.
        by_value: dict[str, list[dict]] = {}
        for n in nodes.values():
            if n["type"] == "alias":
                by_value.setdefault(n.get("params", {}).get("value"),
                                    []).append(n)

        # alias -> every node it names. A *list*, not one destination: the
        # citation layer mints exactly one `names` edge per alias
        # (docs/record-grammar.md §3.4), but that is its convention and not an
        # invariant — `records.check()` does not count `names` edges, so an
        # alias with two of them loads and passes `check` with 0 problems.
        # This was a dict keyed by alias guid until v0.2.13, which meant the
        # second edge silently overwrote the first and `lookup` reported one
        # target of two with nothing to say it had dropped anything. Anything
        # may write records (docs/decisions.md); a reader that assumes more
        # than `check` enforces is the reader that is wrong.
        names: dict[str, list[str]] = {}
        for e in edges:
            if e["type"] == "names":
                names.setdefault(e["source"], []).append(e["destination"])
        cites_by_dest: dict[str, list[dict]] = {}
        for e in edges:
            if e["type"] == "cites":
                cites_by_dest.setdefault(e["destination"], []).append(e)

        def print_node(guid, node, indent="  "):
            print(f"{indent}{guid}  {node['type']}  in {where(guid)}")
            text = R.plain_text(node).strip()
            if text:
                print()
                for line in textwrap.wrap(text, 74 - len(indent)):
                    print(f"{indent}{line}")

        def print_citers(guid):
            """Every `cites` edge landing on `guid`, direct or reflected.

            A citation to a guid that was not yet in the base points at a
            placeholder rather than at `guid` itself, and that edge is never
            retracted once the real target arrives — so a citer reachable
            only through a placeholder is reported too, labelled apart, or
            `lookup` would say "nothing cites this" about a block that is
            cited (docs/roadmap.md).
            """
            direct = cites_by_dest.get(guid, [])
            indirect = []
            for al in by_value.get(guid, []):
                for ph in names.get(al["guid"], []):
                    indirect.extend(cites_by_dest.get(ph, []))

            def show(label, es):
                print(f"  {label} ({len(es)}):")
                for e in es:
                    src = nodes.get(e["source"])
                    if src is None:
                        continue
                    t = R.plain_text(src).strip().replace("\n", " ")
                    if len(t) > 60:
                        t = t[:60] + "…"
                    print(f"    {e['source']}  {src['type']}  {t}")

            if not direct and not indirect:
                print("  nothing cites this")
                return
            if direct:
                show("cited by", direct)
            if indirect:
                show("cited before this block was in the base", indirect)

        node = nodes.get(handle)
        if node is not None:
            # A handle is a whole guid. A prefix is not a shorter handle, it
            # is not a handle, and there is no resolver to make it one.
            print_node(handle, node)
            print()
            print_citers(handle)
            return 0

        matches = by_value.get(handle, [])
        if not matches:
            print(f"no node with handle {handle!r}")
            return 1

        plural = "es" if len(matches) != 1 else ""
        print(f"  {handle!r} is not a guid in this base; resolved via "
              f"{len(matches)} alias{plural}")
        for al in matches:
            targets = names.get(al["guid"], [])
            scheme = al.get("params", {}).get("scheme", "?")
            named = f", names {len(targets)}" if len(targets) != 1 else ""
            print(f"\n  alias {al['guid']}  (scheme {scheme}{named})")
            if not targets:
                print("    -> names nothing")
                continue
            for target_guid in targets:
                target = nodes.get(target_guid)
                if target is None:
                    print(f"    -> {target_guid}  (missing)")
                    continue
                print_node(target_guid, target, indent="    ")
                print()
                print_citers(target_guid)
        return 0

    if cmd == "check":
        recs, files = s.load()
        problems = R.check(recs)
        for f in files:
            print(f"  loaded {f.relative_to(s.root)}")
        nodes = sum(1 for r in recs if r["record"] == "node")
        for p in problems[:20]:
            print(f"  PROBLEM {p}")
        print(f"{nodes} nodes, {len(recs) - nodes} edges, "
              f"{len(problems)} problems")
        return 1 if problems else 0

    print(f"unknown command {cmd!r}")
    print(usage)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

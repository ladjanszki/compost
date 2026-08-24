#!/usr/bin/env python3
"""
store.py — the on-disk graph.

    .compost/
      storage/    immutable sources, exactly as ingested
      graph/      *.jsonl records, committed
      views/      generated, disposable

`.compost/` is also the marker: the root is found by walking up until a
directory of that name appears. Nothing else identifies a base, so a base
cannot be half-configured.

Three rules the loader depends on, each of which exists because breaking it
is silent rather than loud:

- **Only `*.jsonl` is loaded.** A `.jsonl~` editor backup, a `.bak`, a
  half-written temp file — none of them are the graph.
- **Writes are a temp file plus an atomic rename.** A partial write never
  holds the extension, so a crash mid-write cannot produce a file the loader
  would believe.
- **Filenames carry no meaning and load order is irrelevant.** Records are
  concatenated from every matching file; grouping is for humans to read, and
  shuffling the file order must produce an identical graph.

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
        for d in (s.graph, s.storage, s.views):
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

    # -- writing -----------------------------------------------------------
    def write(self, relpath: str, recs: list) -> Path:
        """Write records to graph/<relpath>, atomically."""
        dest = self.graph / relpath
        if dest.suffix != ".jsonl":
            raise ValueError(f"graph files must be .jsonl, got {dest.name}")
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

    def keep_blob(self, path: Path, name: str) -> Path:
        """
        Copy bytes into `storage/<name>`, which must not already exist.

        `name` is a guid plus the original extension, so a collision is a
        minted uuid repeating itself and the right response is to stop rather
        than to merge. That is why this refuses instead of comparing bytes:
        storage names no longer carry meaning, so two files with the same name
        is not a conflict about content, it is a broken assumption about
        uniqueness.

        Written through a temp file and renamed, for the same reason graph
        writes are: a half-copied source is a corrupt immutable original, and
        a crash must not be able to produce one.
        """
        dest = self.storage / name
        if dest.exists():
            raise ValueError(f"{name} is already in storage/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(Path(path).read_bytes())
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return dest

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
        return sorted(p for p in self.graph.rglob("*.jsonl") if p.is_file())

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
    """
    plans, seen = [], {}
    known = s.blobs()
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

        plans.append([src, stored, recs + b.records, root, guid,
                      known.get(sha, []) + seen.get(sha, []), referrer])
        seen.setdefault(sha, []).append(guid)

        if follow:
            for ref in RT.referrals(route, src):
                queue.append((ref, src))

    _link_agents(plans)

    total_n = total_e = 0
    for src, stored, recs, root, guid, dup, referrer in plans:
        s.keep_blob(src, stored)
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
              f"root {root[:8]}, blob {guid[:8]}){via}")
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
        nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
        # A handle is a whole guid. A prefix is not a shorter handle, it is not
        # a handle, and there is no resolver to make it one.
        node = nodes.get(handle)
        if node is None:
            print(f"no node with handle {handle!r}")
            return 1

        parent = {r["destination"]: r["source"] for r in recs
                  if r["record"] == "edge" and r["type"] == "contains"}

        def where(g):
            """The source file of the root that contains `g`."""
            seen = set()
            while g in parent and g not in seen:
                seen.add(g)
                g = parent[g]
            return nodes.get(g, {}).get("params", {}).get("source", "?")

        print(f"  {handle}  {node['type']}  in {where(handle)}")
        text = R.plain_text(node).strip()
        if text:
            print()
            for line in textwrap.wrap(text, 74):
                print(f"  {line}")
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

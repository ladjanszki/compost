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
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import records as R  # noqa: E402
import session as SESS  # noqa: E402

MARKER = ".compost"


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

    def keep_source(self, path: Path) -> Path:
        """Copy a source into storage/, refusing to overwrite a different one."""
        dest = self.storage / path.name
        data = Path(path).read_bytes()
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError(
                f"{dest.name} already in storage/ with different content; "
                "sources are immutable")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

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

def _ast_of(path: Path) -> dict:
    import subprocess
    r = subprocess.run(
        ["pandoc", "-f", "commonmark_x-smart-attributes-fancy_lists",
         "-t", "json", str(path)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0])
        print("usage: store.py init [dir] | import <file.md> | check | ls")
        return 2
    cmd = argv[1]

    if cmd == "init":
        s = Store.init(Path(argv[2]) if len(argv) > 2 else Path.cwd())
        print(f"initialised {s.base}")
        return 0

    try:
        s = Store.find()
    except NotABase as e:
        print(e)
        return 1

    if cmd == "import":
        total_n = total_e = 0
        for arg in argv[2:]:
            src = Path(arg)
            if src.suffix == ".jsonl":
                recs, root = SESS.session_to_records(src)
            else:
                recs, root = R.ast_to_records(_ast_of(src), source=src.name)
            s.keep_source(src)
            dest = s.write(f"{src.stem}.jsonl", recs)
            n = sum(1 for r in recs if r["record"] == "node")
            total_n += n
            total_e += len(recs) - n
            print(f"  {src.name} -> {dest.relative_to(s.root)}  "
                  f"({n} nodes, {len(recs) - n} edges, root {root[:8]})")
        print(f"{total_n} nodes, {total_e} edges")
        return 0

    if cmd == "ls":
        recs, files = s.load()
        for f in files:
            print(f"  {f.relative_to(s.root)}")
        nodes = sum(1 for r in recs if r["record"] == "node")
        docs = sum(1 for r in recs
                   if r["record"] == "node" and r["type"] == "document")
        print(f"{len(files)} files, {docs} documents, "
              f"{nodes} nodes, {len(recs) - nodes} edges")
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
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

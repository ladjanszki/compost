#!/usr/bin/env python3
"""
cli.py — the `compost` command.

A thin dispatcher and nothing more. Each subcommand lives with the code it
drives, so this file has no logic to get wrong: `store` owns the base,
`views` owns rendering. Adding a subcommand here should never mean adding
behaviour here.

    compost init [DIR]      create a base
    compost import FILE...  ingest markdown or a session transcript
    compost ls              list what is loaded
    compost check           verify the graph
    compost lookup HANDLE   print the node a handle names
    compost render          generate the three views
    compost version         print the version

`docs/man-compost.md` is the full description and is kept honest by being
verified against this program rather than written from memory.
"""
import sys

from . import __version__

USAGE = """usage: compost <command> [args]

  init [DIR]      create a base in DIR, or here
  import FILE...  ingest markdown (any suffix) or a transcript (*.jsonl)
  ls              list loaded graph files and counts
  check           verify the graph, non-zero if it fails
  lookup HANDLE   print the node a handle names
  render          generate views/default-{djot,html,md}
  version         print the version

A base is found by walking up to the nearest .compost/ directory."""


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(USAGE)
        return 0 if len(argv) > 1 else 2

    cmd = argv[1]

    if cmd in ("version", "-V", "--version"):
        print(f"compost {__version__}")
        return 0

    if cmd == "render":
        from . import views
        return views.main(argv[1:])

    if cmd in ("init", "import", "ls", "check", "lookup"):
        from . import store
        return store.main(argv)

    print(f"unknown command {cmd!r}\n")
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())

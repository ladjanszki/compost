#!/usr/bin/env python3
"""
cli.py — the `compost` command.

A thin dispatcher and nothing more. Each subcommand lives with the code it
drives, so this file has no logic to get wrong: `store` owns the base,
`views` owns rendering. Adding a subcommand here should never mean adding
behaviour here.

    compost init [DIR]      create a base
    compost digest --as=R FILE...  ingest, by a named route
    compost ls              list what is loaded
    compost check           verify the graph
    compost lookup HANDLE   print the node a handle names
    compost render          generate the three views
    compost serve [-p N]    hand the HTML view to a browser
    compost version         print the version

`docs/man-compost.md` is the full description and is kept honest by being
verified against this program rather than written from memory.
"""
import sys

from . import __version__

USAGE = """usage: compost <command> [args]

  init [DIR]      create a base in DIR, or here
  digest FILE...  ingest via --as=<route>; --as alone lists the routes
  ls              list loaded graph files and counts
  check           verify the graph, non-zero if it fails
  lookup HANDLE   print the node a handle names
  render          generate views/default-{djot,html,md}
  serve [-p N]    serve the HTML view on 127.0.0.1:7373
  version         print the version

A base is found by walking up to the nearest .compost/ directory.
The route a source is read by is always named, never inferred from its
suffix: `compost digest --as` lists what is available."""


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

    if cmd == "layer":
        from . import layers
        return layers.main(argv[1:])

    if cmd == "serve":
        from . import serve
        return serve.main(argv[1:])

    if cmd in ("init", "digest", "ls", "check", "lookup"):
        from . import store
        return store.main(argv)

    print(f"unknown command {cmd!r}\n")
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())

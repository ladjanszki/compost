"""
tools/ — committed scripts that are not the tool.

Nothing here is reachable from `compost`. These are the fixture bleachers, the
round-trip harness, and one-off migration scripts: they are kept because the
work they did has to be repeatable and auditable, not because the package needs
them. `pyproject.toml` lists `packages = ["src"]` explicitly, so this directory
is importable from a checkout and is never installed.

If something here ever becomes a subcommand, it moves to `src/` — and stops
being auxiliary. The traffic does not run the other way.
"""

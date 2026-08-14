"""pandig — conversations to an addressable wiki.

The version lives here rather than in `pyproject.toml`, and the packaging reads
it back out with `dynamic = ["version"]`. The usual arrangement is the reverse,
and it failed here in the ordinary way: with an editable install, packaging
metadata is only refreshed by reinstalling, so `pip show` reported 0.1.0
through three releases while the code was current. Code as the source cannot go
stale, because the code is what runs.
"""

__version__ = "0.1.5"

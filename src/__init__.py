"""
compost — conversations and text to an addressable, agent-writable graph.

The version lives here rather than in `pyproject.toml`, and the packaging reads
it back out with `dynamic = ["version"]`. That way the number is importable at
runtime and there is exactly one place to change it.
"""

__version__ = "0.2.11"

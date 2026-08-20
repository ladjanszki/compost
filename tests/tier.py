#!/usr/bin/env python3
"""
tier.py — which test material is on disk.

Two tiers. The **smoke set** under `fixtures/` is committed, about 80 KB, and
holds the few documents the suites name directly: the one markdown file that
reaches every sabotage, a hand-built AST no reader can produce, three notes and
one trimmed transcript. It exists so that every suite runs on a bare clone.

The **corpus** under `corpus/` is fetched, hundreds of megabytes eventually, and
is what makes a green board mean something. `tests/fetch-corpus.sh` puts it
there at the commits pinned in `tests/corpus.txt`.

Suites glob through here rather than naming paths, so adding a document to the
corpus extends coverage without touching code. Guarantees that need volume ask
`have_corpus()` first and report themselves skipped when it is absent — a
suite that quietly passes on 8% of its material is worse than one that fails.
"""
from pathlib import Path

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
CORPUS = HERE / "corpus"

# What a skipped guarantee says, so the reason is never a mystery.
WHY = "corpus not fetched (tests/fetch-corpus.sh)"


def have_corpus() -> bool:
    """True when the fetched corpus is present and not an empty directory."""
    return CORPUS.is_dir() and any(CORPUS.iterdir())


def sessions() -> list[Path]:
    """Every transcript: the trimmed one, plus the corpus's when fetched."""
    out = sorted(FIXTURES.glob("sessions/*.jsonl"))
    if have_corpus():
        out += sorted(CORPUS.rglob("sessions/*.jsonl"))
    return out


def markdown(sub: str) -> list[Path]:
    """Markdown under `fixtures/<sub>/`, plus any `<sub>/` the corpus carries."""
    out = sorted((FIXTURES / sub).glob("*.md"))
    if have_corpus():
        out += sorted(CORPUS.rglob(f"{sub}/*.md"))
    return out

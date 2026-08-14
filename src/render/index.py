"""
index.py — blocks.json, the machine-readable view of the corpus.

Every block in one file: handle, hash, type, where it lives, what it says.
Written by `pandig render`, so it is **derived and disposable** — delete it, render
again, it is back. That is what lets it exist at all without violating the rule
that `.dj` files in git are the only source of truth.

It earns its place three times over:

  * An agent cannot compute a handle's hash by reading a `.dj` — the hash is
    SHA-256 over the *parsed* block, so it needs the djot AST. Without this file
    a fresh agent can read the corpus but cannot cite it, which is the whole
    loop.
  * `pandig check` is a set difference over it.
  * At a few hundred blocks it is the entire corpus in one read, which is the
    context assembly mvp-design.md 8.1 assumes and needs no embeddings.

Authorship is *not* derived — nothing in a block implies it — so it comes from
the enclosing turn's `author` attribute, which lives in the `.dj` itself. If it
lived only here it would be destroyed by the next render.
"""
import json

from ..canonize import block_hash
from ..refs import citations


def _turn_authors(blocks: list) -> list:
    """
    Author per block, taken from the enclosing turn div.

    `contains` says how many following blocks a div owns, so a running set of
    open turns is enough — no tree needs building.
    """
    authors = [None] * len(blocks)
    for i, b in enumerate(blocks):
        if b["type"] == "div" and "turn" in (b["content"].get("classes") or []):
            who = (b["content"].get("attrs") or {}).get("author")
            for j in range(i, min(i + 1 + b["content"].get("contains", 0),
                                  len(blocks))):
                if authors[j] is None:
                    authors[j] = who
    return authors


def build(notes: list[dict]) -> list[dict]:
    """One record per block, in corpus order."""
    out = []
    for note in notes:
        blocks = note["blocks"]
        authors = _turn_authors(blocks)
        for i, b in enumerate(blocks):
            if not b.get("id"):
                continue
            c = b["content"]
            rec = {
                "handle": b["id"],
                "hash": block_hash(b)[:16],
                "type": b["type"],
                "source": note["path"].name,
                "kind": note["kind"],
                "text": c.get("text", ""),
            }
            for field in ("level", "depth", "contains", "checked", "style"):
                if c.get(field) is not None:
                    rec[field] = c[field]
            if authors[i]:
                rec["author"] = authors[i]
            cited = citations(b)
            if cited:
                rec["cites"] = cited
            out.append(rec)
    return out


def write(store, notes: list[dict]) -> list[dict]:
    records = build(notes)
    (store.site / "blocks.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    return records


def check(records: list[dict]) -> dict:
    """
    Dangling references and handle collisions.

    A dangling reference cannot be repaired in place — the note containing it
    is immutable — so the only defence is noticing. Handle collisions are the
    accepted cost of minting handles without reading the corpus (see refs.py);
    at 8 hex they are rare, and this is where they surface.
    """
    handles = {}
    for r in records:
        handles.setdefault(r["handle"], []).append(r)

    dangling = [
        {"from": r["handle"], "source": r["source"], "target": t,
         "text": r["text"][:60]}
        for r in records for t in r.get("cites", []) if t not in handles
    ]
    collisions = [
        {"handle": h, "blocks": [(x["source"], x["text"][:40]) for x in rs]}
        for h, rs in handles.items() if len(rs) > 1
    ]
    return {"blocks": len(records), "dangling": dangling,
            "collisions": collisions}

#!/usr/bin/env python3
"""
export_citations.py — pull every citation out of a frozen base, without compost.

    python3 tools/export_citations.py BASE [-o OUT.json]

`BASE` is a directory holding `graph/` and `storage/` — a live `.compost` or a
copy of one, archived years ago, on a machine where this project is not
installed.

**Deliberately standalone.** Nothing here imports `src/`, and it will not gain
an import later. A base outlives the tool that wrote it: `graph/*.jsonl` is one
self-describing JSON record per line, `storage/` holds the original bytes, and
the `contains`/`next` edges carry document order. That is a complete artifact,
readable with the standard library alone, and this script is the proof. If it
ever needs compost to run, the claim was false.

**Why an export exists at all.** Re-ingesting a base mints fresh guids for
everything, so every `[-](#guid)` written before the re-ingest points at a block
that no longer exists. The citations are the accumulated judgement of which
blocks mattered — the one thing in a base that cannot be rebuilt from the
sources — so they are captured before anything is discarded.

**Position, not content hash, is the matching key.** Measured on this project's
own base: of 32 cited blocks, **13 (41%) share a `record_hash` with another node**
— they are `Para`, `Header`, `Plain`, `ListItem`, all leaves, so the subtree
fold is the record hash and adds nothing. Duplicates in the base make content
matching ambiguous. Document order does not have that problem: walking two
digests of the same source in `contains`/`next` order matched **8,848 of 8,848
nodes, 100.0000%** (`docs/roadmap.md`, v0.2.13 guarantee 5). So each citation is
exported with `(source, index)` — the root's source name and the block's
position in a pre-order walk — and hashes are recorded only as corroboration.

**Every shape a citation arrives in.** Measured on the same base: 33 distinct
guids arrive as `tool_result` text, 2 in `tool_use` input, 1 as a parsed `Link`
in human prose. A scan that reads only parsed links finds one in thirty-five, so
this reads raw text *and* parsed links, and records which it was — a citation
found in tool output is weaker evidence than one a person typed, and the
distinction is preserved rather than flattened.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RAW = re.compile(r"\[-\]\(#([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                 r"[0-9a-f]{4}-[0-9a-f]{12})\)")
HREF = re.compile(r"^#([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                  r"[0-9a-f]{4}-[0-9a-f]{12})$")


def load(base: Path):
    """Every record under `graph/`. Load order cannot change the result."""
    gd = base / "graph"
    if not gd.is_dir():
        sys.exit(f"{base}: no graph/ — name a base directory")
    nodes, edges = {}, []
    for f in sorted(gd.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            (nodes.__setitem__(r["guid"], r) if r["record"] == "node"
             else edges.append(r))
    return nodes, edges


def tree(edges):
    """`contains` children and the `next` successor, as compost builds them."""
    kids, nxt = defaultdict(list), {}
    for e in edges:
        if e["type"] == "contains":
            kids[e["source"]].append(e["destination"])
        elif e["type"] == "next":
            nxt[e["source"]] = e["destination"]
    return kids, nxt


def ordered(guid, kids, nxt):
    """Children in `next` order — the same walk as `records.Graph.children`.

    Falls back to insertion order rather than raising: an export must still
    produce something from a base whose chain is broken, and it says so.
    """
    ks = kids.get(guid, [])
    if len(ks) < 2:
        return list(ks), True
    members, followed = set(ks), {nxt[k] for k in ks if k in nxt}
    heads = [k for k in ks if k not in followed]
    if len(heads) != 1:
        return list(ks), False
    out, seen, cur = [], set(), heads[0]
    while cur is not None and cur not in seen:
        seen.add(cur)
        out.append(cur)
        cur = nxt.get(cur)
        if cur is not None and cur not in members:
            break
    return (out, True) if len(out) == len(ks) else (list(ks), False)


def plain_text(node):
    """Readable text, for a human checking the export by eye."""
    out = []

    def walk(x):
        if isinstance(x, list):
            if len(x) == 2 and x[0] == "Str":
                out.append(x[1])
            elif len(x) == 2 and x[0] == "Space":
                out.append(" ")
            for y in x:
                walk(y)
        elif isinstance(x, dict):
            t = x.get("t")
            if t == "Str":
                out.append(str(x.get("c", "")))
            elif t in ("Space", "SoftBreak"):
                out.append(" ")
            for y in x.values():
                walk(y)
    walk(node.get("content"))
    if not out:
        for k in ("text", "value"):
            v = (node.get("params") or {}).get(k)
            if isinstance(v, str):
                return v
    return "".join(out)


def find_citations(nodes):
    """Every citation, and how it arrived. Raw text and parsed links both."""
    found = defaultdict(list)

    def links(x, acc):
        if isinstance(x, list):
            if len(x) == 2 and x[0] == "Link":
                try:
                    m = HREF.match(x[1][2][0])
                    if m:
                        acc.append(m.group(1))
                except Exception:
                    pass
            for y in x:
                links(y, acc)
        elif isinstance(x, dict):
            if x.get("t") == "Link":
                try:
                    m = HREF.match(x["c"][2][0])
                    if m:
                        acc.append(m.group(1))
                except Exception:
                    pass
            for y in x.values():
                links(y, acc)

    for guid, n in nodes.items():
        blob = json.dumps(n.get("params") or {}, ensure_ascii=False)
        for target in RAW.findall(blob):
            found[target].append({"in": guid, "in_type": n["type"],
                                  "how": "raw-text"})
        acc = []
        links(n.get("content"), acc)
        for target in acc:
            found[target].append({"in": guid, "in_type": n["type"],
                                  "how": "parsed-link"})
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("base")
    ap.add_argument("-o", "--out", default="citations-export.json")
    a = ap.parse_args()

    base = Path(a.base).resolve()
    nodes, edges = load(base)
    kids, nxt = tree(edges)
    parent = {e["destination"]: e["source"]
              for e in edges if e["type"] == "contains"}

    # pre-order index per root: the matching key a re-ingest can reproduce
    roots = [g for g, n in nodes.items() if g not in parent
             and n["type"] in ("document", "session")]
    index, root_of, broken = {}, {}, []

    def walk(root):
        i = 0
        stack = [root]
        while stack:
            g = stack.pop()
            index[g], root_of[g] = i, root
            i += 1
            kk, ok = ordered(g, kids, nxt)
            if not ok:
                broken.append(g)
            stack.extend(reversed(kk))
    for r in roots:
        walk(r)

    found = find_citations(nodes)
    out, missing = [], []
    for target, sites in sorted(found.items()):
        n = nodes.get(target)
        if n is None:
            missing.append({"guid": target, "sites": sites})
            continue
        root = nodes.get(root_of.get(target, ""), {})
        rp = root.get("params") or {}
        out.append({
            "guid": target,
            "type": n["type"],
            "text": plain_text(n)[:2000],
            "match_key": {"source": rp.get("source"),
                          "root_type": root.get("type"),
                          "root_guid": root_of.get(target),
                          "index": index.get(target)},
            "corroboration": {"record_hash": n.get("record_hash"),
                              "record_subtree_hash":
                                  n.get("record_subtree_hash")},
            "cited_by": sites,
        })

    doc = {"base": str(base), "schema": "compost-citation-export-1",
           "counts": {"nodes": len(nodes), "edges": len(edges),
                      "roots": len(roots), "cited": len(out),
                      "cited_but_absent": len(missing),
                      "broken_next_chains": len(set(broken))},
           "citations": out, "absent": missing}
    Path(a.out).write_text(json.dumps(doc, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    c = doc["counts"]
    print(f"{c['nodes']} nodes, {c['edges']} edges, {c['roots']} roots")
    print(f"exported {c['cited']} cited blocks "
          f"({c['cited_but_absent']} cited but not in this base)")
    if c["broken_next_chains"]:
        print(f"WARNING: {c['broken_next_chains']} broken next chains — "
              f"their indices fell back to insertion order")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()

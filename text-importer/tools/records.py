#!/usr/bin/env python3
"""
records.py — pandoc AST <-> compost records.

Two functions that must compose to the identity:

    records_to_ast(*ast_to_records(ast)) == ast

Everything else in this module is in service of that. The design is in
../record-format.md; the short version is that a node stores the pandoc
constructor tag and every non-block field verbatim, and block-valued fields
become child nodes joined by `contains` edges, with sibling order carried by a
`next` chain rather than an index.

Roles are recovered from node *types* rather than from a field on the edge:
pandoc already names Caption, TableHead, TableBody, TableFoot and Row, so a
table's children are told apart by what they are. Only the three places where
pandoc's grammar is anonymous need invented types — ListItem, DefinitionTerm
and DefinitionItem.
"""
import hashlib
import json
import uuid

LAYER = "pandoc-ast"

# Constructors whose own payload is text rather than inlines, and which
# therefore still deserve a content hash.
TEXT_IN_PARAMS = {"CodeBlock", "RawBlock"}


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


class Builder:
    """Accumulates records while walking an AST."""

    def __init__(self, mint=None):
        self.records: list[dict] = []
        self._mint = mint or (lambda: str(uuid.uuid4()))

    def node(self, type_, params=None, content=None) -> str:
        n = {"record": "node", "guid": self._mint(), "type": type_}
        if params:
            n["params"] = params
        if content is not None:
            n["content"] = content
        if content is not None or type_ in TEXT_IN_PARAMS:
            n["content_hash"] = hashlib.sha256(
                canonical([type_, params or {}, content])).hexdigest()
        self.records.append(n)
        return n["guid"]

    def edge(self, type_, src, dst):
        self.records.append({"record": "edge", "guid": self._mint(),
                             "layer": LAYER, "type": type_,
                             "source": src, "destination": dst})

    def children(self, parent: str, kids: list[str]):
        """`contains` for each child, plus the `next` chain between them."""
        for k in kids:
            self.edge("contains", parent, k)
        for a, b in zip(kids, kids[1:]):
            self.edge("next", a, b)


# --------------------------------------------------------------------------
# AST -> records
# --------------------------------------------------------------------------

def _c(block):
    return block.get("c")


def _list_item(b: Builder, item: list) -> str:
    """
    One `[Block]` from a bullet or ordered list.

    An item holding exactly one Plain or Para collapses into the ListItem
    itself — 89% of them do — carrying `wrap` so the expansion is exact.
    Without `wrap` the collapse would turn every tight list loose, because
    Plain-versus-Para is precisely how pandoc encodes list tightness.
    """
    if len(item) == 1 and item[0]["t"] in ("Plain", "Para"):
        return b.node("ListItem", {"wrap": item[0]["t"]}, _c(item[0]))
    guid = b.node("ListItem")
    b.children(guid, [_block(b, x) for x in item])
    return guid


def _caption(b: Builder, cap) -> str:
    short, blocks = cap
    guid = b.node("Caption", {"short": short} if short is not None else None)
    b.children(guid, [_block(b, x) for x in blocks])
    return guid


def _cell(b: Builder, cell) -> str:
    attr, align, rowspan, colspan, blocks = cell
    guid = b.node("Cell", {"attr": attr, "align": align,
                           "rowspan": rowspan, "colspan": colspan})
    b.children(guid, [_block(b, x) for x in blocks])
    return guid


def _row(b: Builder, row) -> str:
    attr, cells = row
    guid = b.node("Row", {"attr": attr})
    b.children(guid, [_cell(b, c) for c in cells])
    return guid


def _block(b: Builder, blk: dict) -> str:
    t = blk["t"]
    c = _c(blk)

    if t in ("Plain", "Para", "LineBlock"):
        return b.node(t, None, c)

    if t == "Header":
        return b.node(t, {"level": c[0], "attr": c[1]}, c[2])

    if t == "CodeBlock":
        return b.node(t, {"attr": c[0], "text": c[1]})

    if t == "RawBlock":
        return b.node(t, {"format": c[0], "text": c[1]})

    if t == "HorizontalRule":
        return b.node(t)

    if t == "BlockQuote":
        guid = b.node(t)
        b.children(guid, [_block(b, x) for x in c])
        return guid

    if t == "Div":
        guid = b.node(t, {"attr": c[0]})
        b.children(guid, [_block(b, x) for x in c[1]])
        return guid

    if t == "Figure":
        guid = b.node(t, {"attr": c[0]})
        b.children(guid, [_caption(b, c[1])] + [_block(b, x) for x in c[2]])
        return guid

    if t == "BulletList":
        guid = b.node(t)
        b.children(guid, [_list_item(b, item) for item in c])
        return guid

    if t == "OrderedList":
        guid = b.node(t, {"list_attributes": c[0]})
        b.children(guid, [_list_item(b, item) for item in c[1]])
        return guid

    if t == "DefinitionList":
        guid = b.node(t)
        terms = []
        for term_inlines, definitions in c:
            tg = b.node("DefinitionTerm", None, term_inlines)
            items = []
            for blocks in definitions:
                ig = b.node("DefinitionItem")
                b.children(ig, [_block(b, x) for x in blocks])
                items.append(ig)
            b.children(tg, items)
            terms.append(tg)
        b.children(guid, terms)
        return guid

    if t == "Table":
        attr, caption, colspecs, head, bodies, foot = c
        guid = b.node(t, {"attr": attr, "colspecs": colspecs})
        kids = [_caption(b, caption)]

        h_attr, h_rows = head
        hg = b.node("TableHead", {"attr": h_attr})
        b.children(hg, [_row(b, r) for r in h_rows])
        kids.append(hg)

        for body in bodies:
            b_attr, rhc, inter_rows, body_rows = body
            bg = b.node("TableBody", {"attr": b_attr, "row_head_columns": rhc,
                                      "intermediate_rows": len(inter_rows)})
            b.children(bg, [_row(b, r) for r in inter_rows + body_rows])
            kids.append(bg)

        f_attr, f_rows = foot
        fg = b.node("TableFoot", {"attr": f_attr})
        b.children(fg, [_row(b, r) for r in f_rows])
        kids.append(fg)

        b.children(guid, kids)
        return guid

    raise NotImplementedError(f"no mapping for block constructor {t!r}")


def ast_to_records(doc: dict, mint=None):
    """Return (records, root_guid) for a whole pandoc document."""
    b = Builder(mint)
    root = b.node("document", {
        "meta": doc.get("meta", {}),
        "pandoc_api_version": doc.get("pandoc-api-version"),
    })
    b.children(root, [_block(b, blk) for blk in doc["blocks"]])
    return b.records, root


# --------------------------------------------------------------------------
# records -> AST
# --------------------------------------------------------------------------

class Graph:
    def __init__(self, records):
        self.nodes = {r["guid"]: r for r in records if r["record"] == "node"}
        self._kids: dict[str, list[str]] = {}
        self._next: dict[str, str] = {}
        for r in records:
            if r["record"] != "edge":
                continue
            if r["type"] == "contains":
                self._kids.setdefault(r["source"], []).append(r["destination"])
            elif r["type"] == "next":
                self._next[r["source"]] = r["destination"]

    def children(self, guid: str) -> list[str]:
        """Children of `guid`, ordered by walking the next chain."""
        kids = self._kids.get(guid, [])
        if len(kids) < 2:
            return list(kids)
        members = set(kids)
        followed = {self._next[k] for k in kids if k in self._next}
        heads = [k for k in kids if k not in followed]
        if len(heads) != 1:
            raise ValueError(f"{guid}: expected one head, found {len(heads)}")
        out, seen, cur = [], set(), heads[0]
        while cur is not None:
            if cur in seen:
                raise ValueError(f"{guid}: cycle in next chain")
            seen.add(cur)
            out.append(cur)
            cur = self._next.get(cur)
            if cur is not None and cur not in members:
                raise ValueError(f"{guid}: next edge leaves the parent")
        if len(out) != len(kids):
            raise ValueError(f"{guid}: chain covers {len(out)} of {len(kids)}")
        return out


def _p(n, key, default=None):
    return n.get("params", {}).get(key, default)


def _blocks_of(g: Graph, guid: str) -> list:
    return [_to_block(g, k) for k in g.children(guid)]


def _to_caption(g: Graph, guid: str):
    n = g.nodes[guid]
    return [_p(n, "short"), _blocks_of(g, guid)]


def _to_cell(g: Graph, guid: str):
    n = g.nodes[guid]
    return [_p(n, "attr"), _p(n, "align"), _p(n, "rowspan"),
            _p(n, "colspan"), _blocks_of(g, guid)]


def _to_row(g: Graph, guid: str):
    n = g.nodes[guid]
    return [_p(n, "attr"), [_to_cell(g, k) for k in g.children(guid)]]


def _to_item(g: Graph, guid: str) -> list:
    """A ListItem back to `[Block]`, re-expanding a collapsed one."""
    n = g.nodes[guid]
    wrap = _p(n, "wrap")
    if wrap:
        return [{"t": wrap, "c": n["content"]}]
    return _blocks_of(g, guid)


def _to_block(g: Graph, guid: str) -> dict:
    n = g.nodes[guid]
    t = n["type"]

    if t in ("Plain", "Para", "LineBlock"):
        return {"t": t, "c": n["content"]}
    if t == "Header":
        return {"t": t, "c": [_p(n, "level"), _p(n, "attr"), n["content"]]}
    if t == "CodeBlock":
        return {"t": t, "c": [_p(n, "attr"), _p(n, "text")]}
    if t == "RawBlock":
        return {"t": t, "c": [_p(n, "format"), _p(n, "text")]}
    if t == "HorizontalRule":
        return {"t": t}
    if t == "BlockQuote":
        return {"t": t, "c": _blocks_of(g, guid)}
    if t == "Div":
        return {"t": t, "c": [_p(n, "attr"), _blocks_of(g, guid)]}
    if t == "Figure":
        kids = g.children(guid)
        return {"t": t, "c": [_p(n, "attr"), _to_caption(g, kids[0]),
                              [_to_block(g, k) for k in kids[1:]]]}
    if t == "BulletList":
        return {"t": t, "c": [_to_item(g, k) for k in g.children(guid)]}
    if t == "OrderedList":
        return {"t": t, "c": [_p(n, "list_attributes"),
                              [_to_item(g, k) for k in g.children(guid)]]}
    if t == "DefinitionList":
        pairs = []
        for tg in g.children(guid):
            term = g.nodes[tg]
            defs = [_blocks_of(g, ig) for ig in g.children(tg)]
            pairs.append([term["content"], defs])
        return {"t": t, "c": pairs}
    if t == "Table":
        kids = g.children(guid)
        caption = _to_caption(g, kids[0])
        head_g = kids[1]
        head = [_p(g.nodes[head_g], "attr"),
                [_to_row(g, r) for r in g.children(head_g)]]
        bodies = []
        for bg in kids[2:-1]:
            bn = g.nodes[bg]
            rows = [_to_row(g, r) for r in g.children(bg)]
            k = _p(bn, "intermediate_rows", 0)
            bodies.append([_p(bn, "attr"), _p(bn, "row_head_columns"),
                           rows[:k], rows[k:]])
        foot_g = kids[-1]
        foot = [_p(g.nodes[foot_g], "attr"),
                [_to_row(g, r) for r in g.children(foot_g)]]
        return {"t": t, "c": [_p(n, "attr"), caption, _p(n, "colspecs"),
                              head, bodies, foot]}

    raise NotImplementedError(f"no reverse mapping for node type {t!r}")


def records_to_ast(records: list, root: str) -> dict:
    g = Graph(records)
    n = g.nodes[root]
    return {
        "pandoc-api-version": _p(n, "pandoc_api_version"),
        "meta": _p(n, "meta", {}),
        "blocks": _blocks_of(g, root),
    }


# --------------------------------------------------------------------------

def to_jsonl(records: list) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                   for r in records)


def from_jsonl(text: str) -> list:
    return [json.loads(l) for l in text.splitlines() if l.strip()]

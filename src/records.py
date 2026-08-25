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
import datetime
import hashlib
import json
import re
import uuid

from . import __version__

LAYER = "pandoc-ast"

# The grammar version a record conforms to. See docs/record-grammar.md.
# Absent means 1 by definition: schema 1 is what compost has always written, so
# every record ever produced already conforms and nothing needs rewriting.
# Optional on read, required on write.
SCHEMA_VERSION = 1

# Nodes that sit at the top of a containment tree rather than inside one.
ROOT_TYPES = {"document", "session"}
# Nodes that are entities rather than content, and so belong to no tree. A
# `file` is *referenced* by the calls that touched it. A `blob` is the bytes
# of an ingested source, which a document is derived *from* rather than
# contained *by*. Both are pointed at; neither is inside anything.
UNCONTAINED = {"file", "blob", "alias", "unresolved_citation"}

# What a view shows, a human pastes, and a citation names: the whole guid.
# A prefix is not a handle. There was a resolver that accepted any unambiguous
# length, and it was removed: shortening handles is an optimisation nobody has
# yet felt the need for, and an abbreviation that silently stops resolving as
# the base grows is a worse failure than a long citation. When it is wanted it
# will be designed against a measured pain point, not left lying around.
HANDLE_LEN = 36
HANDLE_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

# Constructors whose own payload is text rather than inlines, and which
# therefore still deserve a content hash.
TEXT_IN_PARAMS = {"CodeBlock", "RawBlock"}


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _now() -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"))


# Provenance and identity are excluded on purpose. An edge's hash must say what
# it *claims* — type, layer, by, source, destination — and never when or by what
# it was written, or the same fact rebuilt tomorrow would not match the one
# written today, which is the entire use of the hash.
EDGE_HASH_SKIP = {"record", "guid", "schema_version", "content_hash",
                  "created_at", "tool_version"}


def edge_hash(e: dict) -> str:
    return hashlib.sha256(canonical(
        {k: v for k, v in e.items() if k not in EDGE_HASH_SKIP})).hexdigest()


class Builder:
    """Accumulates records while walking an AST."""

    def __init__(self, mint=None):
        self.records: list[dict] = []
        self._mint = mint or (lambda: str(uuid.uuid4()))

    def mint(self) -> str:
        """A fresh guid, not yet attached to anything.

        Needed whenever the name is used *outside* the record — a `blob` is
        named before it is described, because the guid is also the filename
        its bytes are stored under and the node has to carry that name.
        """
        return self._mint()

    def node(self, type_, params=None, content=None, guid=None) -> str:
        n = {"record": "node", "schema_version": SCHEMA_VERSION,
             "guid": guid or self._mint(), "type": type_}
        if params:
            n["params"] = params
        if content is not None:
            n["content"] = content
        if content is not None or type_ in TEXT_IN_PARAMS:
            n["content_hash"] = hashlib.sha256(
                canonical([type_, params or {}, content])).hexdigest()
        self.records.append(n)
        return n["guid"]

    def edge(self, type_, src, dst, layer: str = LAYER, **props):
        e = {"record": "edge", "schema_version": SCHEMA_VERSION,
             "guid": self._mint(), "layer": layer, "type": type_,
             "source": src, "destination": dst}
        e.update(props)                       # `by`, and anything a builder adds
        e["created_at"] = _now()
        e["tool_version"] = __version__
        e["content_hash"] = edge_hash(e)
        self.records.append(e)

    def children(self, parent: str, kids: list[str], layer: str = LAYER):
        """`contains` for each child, plus the `next` chain between them."""
        for k in kids:
            self.edge("contains", parent, k, layer)
        for a, b in zip(kids, kids[1:]):
            self.edge("next", a, b, layer)


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


def ast_to_records(doc: dict, mint=None, source: str | None = None,
                   route: str | None = None):
    """Return (records, root_guid) for a whole pandoc document."""
    b = Builder(mint)
    params = {
        "meta": doc.get("meta", {}),
        "pandoc_api_version": doc.get("pandoc-api-version"),
    }
    if source:
        params["source"] = source
    # How this document was read. Recorded on the root because that is the
    # only node that knows: every block below it looks the same whether it
    # came through `notes` or through `pandoc-ast`. Without it, "which of
    # these documents came in which way" is unanswerable after the fact,
    # which is exactly the question the pandoc-ast experiment needs to ask.
    if route:
        params["route"] = route
    root = b.node("document", params)
    b.children(root, [_block(b, blk) for blk in doc["blocks"]])
    return b.records, root


# --------------------------------------------------------------------------
# records -> AST
# --------------------------------------------------------------------------

class Graph:
    """
    The loaded records, addressable as a tree.

    `wrap` is an optional hook a *view* installs: given a node and the blocks
    it produced, it returns the blocks to emit in its place. That is how a
    handle gets into a rendered document without the translation knowing
    anything about views. Left unset, reconstruction is the exact identity.
    """

    def __init__(self, records):
        self.wrap = None
        self.nodes = {r["guid"]: r for r in records if r["record"] == "node"}
        self._kids: dict[str, list[str]] = {}
        self._next: dict[str, str] = {}
        # Every other edge type, by type then source. Until subagents arrived
        # no view had ever consulted an edge — `contains` and `next` rebuild
        # the tree and everything else was invisible here. Keeping this generic
        # rather than adding a `launched` field means the next relation a view
        # wants to draw needs no change to this class.
        self._rel: dict[str, dict[str, list[dict]]] = {}
        for r in records:
            if r["record"] != "edge":
                continue
            if r["type"] == "contains":
                self._kids.setdefault(r["source"], []).append(r["destination"])
            elif r["type"] == "next":
                self._next[r["source"]] = r["destination"]
            else:
                self._rel.setdefault(r["type"], {}).setdefault(
                    r["source"], []).append(r)

    def linked(self, guid, type_, by=None):
        """Edges of `type_` leaving `guid`, in record order."""
        out = self._rel.get(type_, {}).get(guid, [])
        return [e for e in out if by is None or e.get("by") == by]

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
    out = []
    for k in g.children(guid):
        blocks = [_to_block(g, k)]
        out.extend(g.wrap(g.nodes[k], blocks) if g.wrap else blocks)
    return out


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
    wrapper = _p(n, "wrap")
    blocks = ([{"t": wrapper, "c": n["content"]}] if wrapper
              else _blocks_of(g, guid))
    return g.wrap(n, blocks) if g.wrap else blocks


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


# --------------------------------------------------------------------------
# Whole-graph checks
# --------------------------------------------------------------------------

def check(records: list) -> list[str]:
    """
    Everything the format promises, over a whole loaded graph.

    Returns a list of problems, empty when the graph is sound. Kept here
    rather than in the test suite because the loader needs it too: a graph
    that fails these is not a graph we should serve a view from.
    """
    problems: list[str] = []
    nodes = {r["guid"]: r for r in records if r["record"] == "node"}
    edges = [r for r in records if r["record"] == "edge"]

    seen: dict[str, dict] = {}
    for r in records:
        g = r["guid"]
        if g in seen and canonical(seen[g]) != canonical(r):
            problems.append(f"guid {g} carries two different records")
        seen[g] = r

    for e in edges:
        for end in ("source", "destination"):
            if e[end] not in nodes:
                problems.append(f"edge {e['guid']} has a dangling {end}")

    kids: dict[str, list[str]] = {}
    parents: dict[str, int] = {}
    for e in edges:
        if e["type"] == "contains":
            kids.setdefault(e["source"], []).append(e["destination"])
            parents[e["destination"]] = parents.get(e["destination"], 0) + 1

    roots = {g for g, n in nodes.items() if n["type"] in ROOT_TYPES}
    for g, n in nodes.items():
        count = parents.get(g, 0)
        if n["type"] in UNCONTAINED:
            if count:
                problems.append(f"{n['type']} {g} is contained by something")
        elif g in roots:
            if count:
                problems.append(f"{n['type']} {g} has a parent")
        elif count != 1:
            problems.append(f"{n['type']} {g} has {count} parents, expected 1")

    # `launched` joins a subagent transcript to the tool call that ran it, and
    # a view renders the subagent *inside* that call. So it is a containment
    # relation as far as rendering is concerned, and it needs the same two
    # guarantees or a view will loop or double-print. `contains` is checked
    # above; this checks the pair together, since a cycle can run through both.
    launched: dict[str, list[str]] = {}
    launched_by: dict[str, int] = {}
    for e in edges:
        if e["type"] == "launched":
            launched.setdefault(e["source"], []).append(e["destination"])
            launched_by[e["destination"]] = launched_by.get(e["destination"], 0) + 1
    for g_, n_ in launched_by.items():
        if n_ > 1:
            problems.append(f"session {g_} is launched by {n_} tool calls")

    reach = {k: list(v) for k, v in kids.items()}
    for src, dsts in launched.items():
        reach.setdefault(src, []).extend(dsts)
    seen_l: dict[str, int] = {}

    def walk(g_):
        seen_l[g_] = 1
        for k in reach.get(g_, []):
            if seen_l.get(k) == 1:
                return True
            if not seen_l.get(k) and walk(k):
                return True
        seen_l[g_] = 2
        return False

    for g_ in list(nodes):
        if not seen_l.get(g_) and walk(g_):
            problems.append("cycle through contains and launched")
            break

    colour: dict[str, int] = {}

    def visit(g):
        colour[g] = 1
        for k in kids.get(g, []):
            if colour.get(k) == 1:
                return True
            if not colour.get(k) and visit(k):
                return True
        colour[g] = 2
        return False

    for r in roots:
        if visit(r):
            problems.append("cycle in the contains graph")
            break

    g = Graph(records)
    for parent in kids:
        try:
            g.children(parent)
        except ValueError as e:
            problems.append(str(e))

    short: dict[str, str] = {}
    for g_ in nodes:
        h = g_[:HANDLE_LEN]
        if h in short and short[h] != g_:
            problems.append(f"handle {h} is shared by two nodes")
        short[h] = g_

    for n in nodes.values():
        want = "content" in n or n["type"] in TEXT_IN_PARAMS
        if want != ("content_hash" in n):
            problems.append(
                f"{n['type']} {n['guid']}: content_hash should "
                f"{'be present' if want else 'be absent'}")

    for r in records:
        v = r.get("schema_version")
        if v is not None and v > SCHEMA_VERSION:
            problems.append(f"{r['guid']} is schema {v}; this tool writes "
                            f"{SCHEMA_VERSION}")

    return problems


def blob_of(records, root: str) -> dict | None:
    """
    The `blob` node a root was derived from, or None.

    This is the only supported way to get from a document back to its bytes.
    Storage filenames are minted guids, so the original name is *not* where
    the file lives — `blob.params["stored_as"]` is, and it is reachable only
    by following the `derived_from` edge. Anything that reconstructs a storage
    path from `params["source"]` is guessing, and will guess wrong.
    """
    nodes = {r["guid"]: r for r in records if r["record"] == "node"}
    for r in records:
        if (r["record"] == "edge" and r["type"] == "derived_from"
                and r["source"] == root):
            n = nodes.get(r["destination"])
            if n is not None and n["type"] == "blob":
                return n
    return None


# --------------------------------------------------------------------------
# Citations
# --------------------------------------------------------------------------

CITATION_TARGET = re.compile(r"^#(%s)$" % HANDLE_RE)
CITATION_LAYER = "citation"

# The v0.1 handle, in the four forms the corpus actually writes: bare, with the
# expansion marker `+++`, with a version pin `@ver`, and — not matched here —
# the metasyntactic ones the notes use when talking *about* handles. Those are
# excluded by the character class rather than by a rule: `{#xxxxxxxx}` is eight
# characters and none of them hex, `{#handle}` and `{#uuid:hash}` are neither.
# Exactly eight, never more: `{#a1b2c3d4e5}` is not a handle and must not match.
LEGACY_HANDLE = re.compile(r"\{#([0-9a-f]{8})(?:\+\+\+|@[^\s{}]+)?\}")


def plain_text(node: dict) -> str:
    """The node's own text, inlines flattened. Derived, never stored."""
    out: list[str] = []

    def go(x):
        if isinstance(x, dict):
            c = x.get("c")
            if x.get("t") == "Str" and isinstance(c, str):
                out.append(c)
            elif x.get("t") in ("Space", "SoftBreak", "LineBreak"):
                out.append(" ")
            else:
                go(c)
        elif isinstance(x, list):
            for v in x:
                go(v)

    go(node.get("content") or [])
    if node["type"] in TEXT_IN_PARAMS:
        out.append(node.get("params", {}).get("text", ""))
    return "".join(out)


def _links(node: dict) -> list[str]:
    """Link targets in a node's own inline content."""
    out: list[str] = []

    def go(x):
        if isinstance(x, dict):
            if x.get("t") == "Link":
                target = x["c"][2][0] if len(x["c"]) > 2 else ""
                out.append(target)
            go(x.get("c"))
        elif isinstance(x, list):
            for v in x:
                go(v)

    go(node.get("content") or [])
    return out


def citation_edges(records: list, mint=None) -> tuple[list, list[tuple[str, str]]]:
    """
    Read citations out of the *parsed* content and turn each into an edge.

    A citation is a link whose target is a handle: `[-](#<guid>)`. Reading
    `Link` nodes rather than regexing text is what makes "handles inside code
    are not citations" a property of the format instead of a rule to remember.
    A code block holds text with no inlines, so it contains no links and cannot
    contribute a citation however often it quotes the syntax — and this corpus
    quotes its own syntax constantly.

    The edges are **derived**, not asserted. The draft classed citations as
    asserted alongside `derived_from`, but the stated reason `derived_from`
    must be asserted is that no parser can recover it, and a citation is the
    exact opposite. So the text stays the source of truth, the edge is a
    projection, and a stale edge is a rebuild rather than a conflict.

    Returns (edges, unresolved (handle, source guid) pairs).
    """
    b = Builder(mint)
    nodes = [r for r in records if r["record"] == "node"]
    guids = {n["guid"] for n in nodes}

    edges, unresolved = [], []
    for n in nodes:
        for target in _links(n):
            m = CITATION_TARGET.match(target)
            if not m:
                continue                      # an ordinary link, not a citation
            handle = m.group(1)
            if handle not in guids:
                unresolved.append((handle, n["guid"]))
                continue
            edges.append({"record": "edge", "guid": b._mint(),
                          "layer": CITATION_LAYER, "type": "cites",
                          "source": n["guid"], "destination": handle})
    return edges, unresolved


def _strs(node: dict) -> list[str]:
    """Every `Str` in a node's own inline content, unflattened.

    The twin of `_links`, and written this way for the same reason.
    `plain_text()` folds `params["text"]` in, so scanning *it* would read a
    fenced example as prose — which is how the `{@x}` era mistook code for
    citations three times. Walking `content` for `Str` nodes cannot make that
    mistake: a `Code` node keeps its text as a bare string at `c[1]`, and a
    `CodeBlock`'s lives in `params["text"]`, which this never opens. Neither
    is ever a `Str`, so "handles inside code are not citations" is a property
    of the walk rather than an exclusion someone has to remember.
    """
    out: list[str] = []

    def go(x):
        if isinstance(x, dict):
            if x.get("t") == "Str":
                out.append(x.get("c") or "")
            go(x.get("c"))
        elif isinstance(x, list):
            for v in x:
                go(v)

    go(node.get("content") or [])
    return out


def legacy_handle_refs(records: list) -> list[tuple[str, str]]:
    """Every `{#8hex}` occurrence in prose, as (handle, citing node guid).

    `re.finditer` **within** each `Str`, never whole-`Str` equality. Measured
    over the v0.1-derived material in this repo, 135 handles are a whole `Str`
    and 98 are embedded in a larger one: whole-token recall is 57.9%, so an
    earlier draft specifying equality would have dropped 42% of occurrences
    without saying so. Real prose puts punctuation after a citation —
    `{#aa813aa9}.`, `({#b1c2d3e4}),` — and the pattern is self-delimiting, so
    there is nothing to reassemble.

    **There is no assignment rule and there does not need to be one.** Read as
    djot, a v0.1 block carries its own handle as an AST `id`, which never
    reaches a `Str`; only citations are text. Earlier drafts carried a rule to
    stop ~6,700 block labels becoming self-citations, and the reader retires it.
    """
    out = []
    for n in records:
        if n["record"] != "node":
            continue
        for s in _strs(n):
            for m in LEGACY_HANDLE.finditer(s):
                out.append((m.group(1), n["guid"]))
    return out

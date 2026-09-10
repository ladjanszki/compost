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
UNCONTAINED = {"file", "blob", "alias", "unresolved_citation", "display_name"}

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
EDGE_HASH_SKIP = {"record", "guid", "schema_version", "record_hash",
                  "created_at", "tool_version"}


def edge_hash(e: dict) -> str:
    return hashlib.sha256(canonical(
        {k: v for k, v in e.items() if k not in EDGE_HASH_SKIP})).hexdigest()


# --------------------------------------------------------------------------
# The fold: record_hash and record_subtree_hash
# --------------------------------------------------------------------------
#
# Both are top-level record fields, beside `guid`, `created_at` and
# `tool_version` — never inside `params`, which would put a hash inside its
# own input. docs/roadmap.md, "v0.2.13 — the fold".

def record_hash(rec: dict) -> str:
    """A node's own hash: SHA-256 over canonical `[type, params, content]`.

    Pure and total — every node gets one, whether or not it carries content,
    because "no content" and "content is None" are the same fact either way.
    This is the record minus `guid`, `created_at`, `tool_version`, and minus
    its children: two nodes with the same type/params/content hash the same
    regardless of where either sits, which is exactly what makes the fold
    below able to tell "same subtree" from "same node" apart.
    """
    return hashlib.sha256(canonical(
        [rec["type"], rec.get("params") or {}, rec.get("content")])
        ).hexdigest()


def stamp_hashes(records: list) -> list:
    """Stamp `record_hash` and `record_subtree_hash` on every node, in place.

    One post-order pass over the containment tree built from `contains` and
    `next` **only** — no other edge type may move a fold, so a `cites` edge
    minted later cannot change a node that was already folded. A leaf's fold
    is `H([record_hash, []])`; a leaf is any node with no `contains` children,
    which includes every `UNCONTAINED` type (`file`, `blob`, `alias`,
    `unresolved_citation`, `display_name`) as well as an ordinary childless
    block.

    Mutates the node dicts already in `records` (the same objects `Graph`
    indexes them by), so the return value is `records` itself — a convenience
    for chaining, not a copy.

    Called at the end of `ast_to_records` and `SessionImporter.run`, once the
    whole tree that batch will ever mint exists; and by `src/layers.py` for
    the nodes a layer mints, which are always leaves.
    """
    g = Graph(records)
    memo: dict[str, str] = {}

    def fold(guid: str) -> str:
        cached = memo.get(guid)
        if cached is not None:
            return cached
        n = g.nodes[guid]
        rh = record_hash(n)
        n["record_hash"] = rh
        kids = [fold(k) for k in g.children(guid)]
        sh = hashlib.sha256(canonical([rh, kids])).hexdigest()
        n["record_subtree_hash"] = sh
        memo[guid] = sh
        return sh

    for guid in list(g.nodes):
        fold(guid)
    return records


def refresh_fold(records: list, root: str) -> list:
    """Recompute `record_subtree_hash` (and, idempotently, `record_hash`)
    for a root's whole file, in place, after an append.

    This is the fix `docs/roadmap.md` ("AoTA") specifies for `check()`'s
    eleventh assertion failing on every append: appending mints new tail
    nodes with their own hashes already correct, but the root's own fold
    summarised only the *old* children, and nothing that reads the graph
    should have to know that a rewrite is due. `record_subtree_hash` is
    derived — recomputable from the graph at any time — so "fixing" it is
    refreshing a cache, not changing what any record claims: the root's own
    `record_hash` is untouched because its `params` never change, and this
    call recomputes to that identical value.

    In practice this is exactly the same post-order walk `stamp_hashes`
    already does, over the file that now includes the new tail — appending
    changes *which nodes* sit beneath the root, not *how* a fold is
    computed. Kept as its own name (rather than telling every append
    caller to call `stamp_hashes` directly) because the call site wants to
    say "refresh this root's fold", and `root` is checked against the
    records given so a caller that passes the wrong file's records fails
    loudly instead of silently folding nothing relevant.
    """
    g = Graph(records)
    if root not in g.nodes:
        raise ValueError(f"{root}: not a node in the given records")
    return stamp_hashes(records)


def align(old_recs: list, old_root: str, new_recs: list, new_root: str
          ) -> tuple[int, int]:
    """
    How much of `old_root`'s tree is an unchanged prefix of `new_root`'s.

    Pure — writes nothing, and never mutates either records list, so it can
    be called before any decision is made about what to mint. Walks both
    trees in the same deterministic order — a node, then its `contains`
    children in `next` order, then whatever it `delegates_to` — and compares
    `record_hash` pairwise (never `record_subtree_hash`, which would move
    the moment a tail is added and falsely report the *whole* ancestor chain
    as changed). `record_hash` never depends on children, so a node that
    matches at position *i* in both walks is the same content regardless of
    what was appended after it.

    Returns `(prefix, total)`, where `total` is the number of nodes the walk
    reaches in the **older** tree and `prefix` is how many of those matched,
    from the front, before the first mismatch or the shorter walk ran out.
    Report this pair, never a bare percentage — `docs/roadmap.md` names the
    exact failure this project has made four times: reporting `prefix` as a
    fraction of the *newer* tree, or of nodes reached by a narrower walk,
    reads as "100%" while covering half the graph.

    **Following `delegates_to` is not optional.** A transcript's turns
    delegate their markdown prose to a separate document tree each; a walk
    over `contains`/`next` alone never reaches any of it and silently
    measures half the graph while reporting the number as if it were whole
    (docs/roadmap.md, "AoTA", guarantee 8).
    """
    def walk(records, root):
        g = Graph(records)

        def visit(guid):
            order.append(guid)
            for k in g.children(guid):
                visit(k)
            for e in g.linked(guid, "delegates_to"):
                visit(e["destination"])

        order: list[str] = []
        visit(root)
        return order, g

    old_order, old_g = walk(old_recs, old_root)
    new_order, new_g = walk(new_recs, new_root)

    prefix = 0
    for a, b in zip(old_order, new_order):
        if old_g.nodes[a].get("record_hash") != new_g.nodes[b].get("record_hash"):
            break
        prefix += 1
    return prefix, len(old_order)


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
        # `record_hash` and `record_subtree_hash` are NOT stamped here: the
        # fold needs every node and every `contains`/`next` edge this batch
        # will ever mint, which does not exist yet mid-walk. `stamp_hashes`
        # does one post-order pass once the tree is whole — see the end of
        # `ast_to_records` and `SessionImporter.run`, and `src/layers.py` for
        # the nodes a layer mints.
        self.records.append(n)
        return n["guid"]

    def edge(self, type_, src, dst, layer: str = LAYER, **props):
        e = {"record": "edge", "schema_version": SCHEMA_VERSION,
             "guid": self._mint(), "layer": layer, "type": type_,
             "source": src, "destination": dst}
        e.update(props)                       # `by`, and anything a builder adds
        e["created_at"] = _now()
        e["tool_version"] = __version__
        e["record_hash"] = edge_hash(e)
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


# --------------------------------------------------------------------------
# Sections: hoisting `make_sections`' Div into its own Header
# --------------------------------------------------------------------------
#
# `make_sections` (applied in the reader, `src/markdown.py`) wraps every
# heading in a `Div(attr, [Header, ...rest])`. v0.2.16 does not keep that
# shape: the container is the `Header`, not the `Div` — decided by the human
# against this module's first draft, and measured afterwards (docs/roadmap.md,
# "TA"). `hoist` absorbs the Div into its own Header, which becomes the
# parent of `rest`; `unhoist` is its exact inverse. Neither function is the
# identity on its own input — a plain, unsectioned block list hoists to
# itself, but a sectioned one does not equal its own hoisted form — the
# guarantee is only that the PAIR composes to the identity, tested as a
# property over every corpus fixture rather than trusted
# (`tests/verify-0.2.16.sh`, guarantee 1).
#
# Both functions are pure and operate on raw pandoc block dicts (`{"t":...,
# "c":...}`), never on records — `ast_to_records` hoists on the way in and
# `records_to_ast` unhoists on the way out, so nothing else in the
# translation ever learns what a section is.
#
# The two keys `hoist` adds — `section_attr`, `section_blocks` — are not part
# of pandoc's grammar. They exist only on the boundary between these two
# functions and are never written to a record directly: `section_attr`
# becomes `params["section_attr"]` on the `Header` node (see `_block`,
# below), and `section_blocks` becomes the Header's `contains` children.

_SECTION_CLASS = "section"


def _is_section_div(blk: dict) -> bool:
    if blk.get("t") != "Div":
        return False
    attr, kids = blk["c"]
    return (_SECTION_CLASS in attr[1] and bool(kids)
            and kids[0].get("t") == "Header")


def hoist(blocks: list) -> list:
    """Fold every `make_sections` Div into its own Header. See module notes.

    Recurses into every block-list position pandoc's grammar has —
    `BlockQuote`, `Div`, `Figure`, list items, definitions, table cells and
    captions — because a section can appear, and nest, inside any of them.
    """
    return [_hoist_block(blk) for blk in blocks]


def _hoist_block(blk: dict) -> dict:
    t = blk["t"]

    if _is_section_div(blk):
        attr, kids = blk["c"]
        header, rest = kids[0], kids[1:]
        level, hattr, inlines = header["c"]
        return {"t": "Header", "c": [level, hattr, inlines],
               "section_attr": attr, "section_blocks": hoist(rest)}

    if t == "Div":
        attr, kids = blk["c"]
        return {"t": t, "c": [attr, hoist(kids)]}

    if t == "BlockQuote":
        return {"t": t, "c": hoist(blk["c"])}

    if t == "Figure":
        attr, (short, cap_blocks), kids = blk["c"]
        return {"t": t, "c": [attr, [short, hoist(cap_blocks)], hoist(kids)]}

    if t == "BulletList":
        return {"t": t, "c": [hoist(item) for item in blk["c"]]}

    if t == "OrderedList":
        list_attrs, items = blk["c"]
        return {"t": t, "c": [list_attrs, [hoist(item) for item in items]]}

    if t == "DefinitionList":
        return {"t": t, "c": [[term, [hoist(d) for d in defs]]
                              for term, defs in blk["c"]]}

    if t == "Table":
        attr, (short, cap_blocks), colspecs, head, bodies, foot = blk["c"]
        return {"t": t, "c": [attr, [short, hoist(cap_blocks)], colspecs,
                              _hoist_row_group(head),
                              [_hoist_body(body) for body in bodies],
                              _hoist_row_group(foot)]}

    return blk


def _hoist_row_group(rg):
    r_attr, rows = rg
    return [r_attr, [_hoist_row(r) for r in rows]]


def _hoist_row(row):
    r_attr, cells = row
    return [r_attr, [[c_attr, align, rowspan, colspan, hoist(cblocks)]
                     for c_attr, align, rowspan, colspan, cblocks in cells]]


def _hoist_body(body):
    b_attr, rhc, inter, main = body
    return [b_attr, rhc, [_hoist_row(r) for r in inter],
            [_hoist_row(r) for r in main]]


def unhoist(blocks: list) -> list:
    """The inverse of `hoist`. See module notes above `hoist`."""
    return [_unhoist_block(blk) for blk in blocks]


def _unhoist_block(blk: dict) -> dict:
    t = blk["t"]

    if t == "Header" and "section_attr" in blk:
        level, hattr, inlines = blk["c"]
        header = {"t": "Header", "c": [level, hattr, inlines]}
        rest = unhoist(blk.get("section_blocks") or [])
        return {"t": "Div", "c": [blk["section_attr"], [header] + rest]}

    if t == "Div":
        attr, kids = blk["c"]
        return {"t": t, "c": [attr, unhoist(kids)]}

    if t == "BlockQuote":
        return {"t": t, "c": unhoist(blk["c"])}

    if t == "Figure":
        attr, (short, cap_blocks), kids = blk["c"]
        return {"t": t, "c": [attr, [short, unhoist(cap_blocks)],
                              unhoist(kids)]}

    if t == "BulletList":
        return {"t": t, "c": [unhoist(item) for item in blk["c"]]}

    if t == "OrderedList":
        list_attrs, items = blk["c"]
        return {"t": t, "c": [list_attrs, [unhoist(item) for item in items]]}

    if t == "DefinitionList":
        return {"t": t, "c": [[term, [unhoist(d) for d in defs]]
                              for term, defs in blk["c"]]}

    if t == "Table":
        attr, (short, cap_blocks), colspecs, head, bodies, foot = blk["c"]
        return {"t": t, "c": [attr, [short, unhoist(cap_blocks)], colspecs,
                              _unhoist_row_group(head),
                              [_unhoist_body(body) for body in bodies],
                              _unhoist_row_group(foot)]}

    return blk


def _unhoist_row_group(rg):
    r_attr, rows = rg
    return [r_attr, [_unhoist_row(r) for r in rows]]


def _unhoist_row(row):
    r_attr, cells = row
    return [r_attr, [[c_attr, align, rowspan, colspan, unhoist(cblocks)]
                     for c_attr, align, rowspan, colspan, cblocks in cells]]


def _unhoist_body(body):
    b_attr, rhc, inter, main = body
    return [b_attr, rhc, [_unhoist_row(r) for r in inter],
            [_unhoist_row(r) for r in main]]


def _block(b: Builder, blk: dict) -> str:
    t = blk["t"]
    c = _c(blk)

    if t in ("Plain", "Para", "LineBlock"):
        return b.node(t, None, c)

    if t == "Header":
        # `section_attr`/`section_blocks` are `hoist`'s doing, present only
        # when this Header absorbed a `make_sections` Div — never for a
        # `pandoc-ast` route's own raw AST, which is never hoisted at all
        # (nothing in it matches `_is_section_div`). `params["section_attr"]`
        # keeps the div's own attr, which `make_sections` moved the
        # identifier onto — losing it would make `unhoist` not an inverse
        # (docs/roadmap.md, "two facts").
        params = {"level": c[0], "attr": c[1]}
        section_attr = blk.get("section_attr")
        if section_attr is not None:
            params["section_attr"] = section_attr
        guid = b.node(t, params, c[2])
        section_blocks = blk.get("section_blocks")
        if section_blocks:
            b.children(guid, [_block(b, x) for x in section_blocks])
        return guid

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
    # Hoisted before any block is walked, v0.2.16: `ast_to_records` never
    # sees a `make_sections` Div at all, only the Header it becomes. A block
    # list with no section shape hoists to itself, so this is a no-op for
    # the `pandoc-ast` route's own raw AST and for any fixture read without
    # the sectioning filter. See `hoist`'s module notes, above.
    b.children(root, [_block(b, blk) for blk in hoist(doc["blocks"])])
    stamp_hashes(b.records)
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
        blk = {"t": t, "c": [_p(n, "level"), _p(n, "attr"), n["content"]]}
        section_attr = _p(n, "section_attr")
        if section_attr is not None:
            # The inverse of `_block`'s Header case: this Header carries a
            # section (it was hoisted on the way in), so its `contains`
            # children are the div's own former content and need to travel
            # back with it for `unhoist` — called once, over the whole tree,
            # at the bottom of `records_to_ast`, never here per-node.
            blk["section_attr"] = section_attr
            blk["section_blocks"] = _blocks_of(g, guid)
        return blk
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
        # `unhoist` once, over the whole reconstructed list, is the exact
        # inverse of `ast_to_records`'s `hoist` — restoring the
        # `make_sections` Div a hoisted Header stands in for. A no-op on a
        # tree with no sections, same as `hoist` was on the way in.
        "blocks": unhoist(_blocks_of(g, root)),
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
        if "record_hash" not in n or "record_subtree_hash" not in n:
            problems.append(
                f"{n['type']} {n['guid']}: missing record_hash or "
                f"record_subtree_hash")

    for r in records:
        v = r.get("schema_version")
        if v is not None and v > SCHEMA_VERSION:
            problems.append(f"{r['guid']} is schema {v}; this tool writes "
                            f"{SCHEMA_VERSION}")

    # Eleventh assertion, and the first that verifies content rather than
    # structure: both hashes recompute from the record and its children.
    # `record_hash` needs only the node itself; `record_subtree_hash` needs
    # the fold of its children in `next` order, so a node whose stored hash
    # was hand-edited — or whose child was, four levels down — is caught
    # here, one node/subtree hash mismatch at a time. Wrapped in a `try`
    # because a graph broken badly enough to fail the structural assertions
    # above (a cycle, a malformed `next` chain) can make the walk itself
    # raise, and a graph that already has a name for its problem does not
    # need a traceback standing in for one.
    # `mutability`'s AoTA/ImTA contract (docs/design-0.3.0.md §2) is "existing
    # content never changes" — which is exactly what a hash-recompute failure
    # already means. `root_of` attributes a mismatched node to its containing
    # root so the message can name the *contract* that was violated, rather
    # than leave the generic phrasing below to stand for both "this base is
    # corrupt" and "this append-only root's head moved" — the same wording a
    # hash mismatch always used, whether or not a mutability was ever
    # declared. This does not make the check more discriminating than it
    # already was: it is the same signal, better attributed, and it still
    # cannot tell "the head changed" apart from "unrelated corruption" — both
    # are "content that used to be true is no longer what its hash claims".
    parent_of: dict[str, str] = {}
    for e in edges:
        if e["type"] == "contains" and e["destination"] not in parent_of:
            parent_of[e["destination"]] = e["source"]

    def root_of(guid):
        seen = set()
        while guid in parent_of and guid not in seen:
            seen.add(guid)
            guid = parent_of[guid]
        n = nodes.get(guid)
        return guid if n is not None and n["type"] in ROOT_TYPES else None

    def _flag_contract(guid, n):
        rg = root_of(guid)
        if rg is None:
            return
        mut = (nodes[rg].get("params") or {}).get("mutability")
        if mut in ("append-only", "immutable"):
            problems.append(
                f"{n['type']} {guid}: this violates {rg}'s "
                f"mutability={mut!r} contract — existing content must never "
                f"change once recorded")

    try:
        memo: dict[str, str] = {}

        def _fold(guid):
            cached = memo.get(guid)
            if cached is not None:
                return cached
            n = nodes[guid]
            rh = record_hash(n)
            if n.get("record_hash") != rh:
                problems.append(
                    f"{n['type']} {guid}: record_hash does not recompute")
                _flag_contract(guid, n)
            kids = [_fold(k) for k in g.children(guid)]
            sh = hashlib.sha256(canonical([rh, kids])).hexdigest()
            if n.get("record_subtree_hash") != sh:
                problems.append(
                    f"{n['type']} {guid}: record_subtree_hash does not "
                    f"recompute")
                _flag_contract(guid, n)
            memo[guid] = sh
            return sh

        for guid in nodes:
            _fold(guid)
    except Exception as e:
        problems.append(f"could not verify record hashes: {e}")

    # Twelfth assertion: `derived_from` is irreflexive and acyclic — the two
    # of PROV-O's `wasDerivedFrom` binding constraints v0.2.14 holds
    # (`docs/roadmap.md`, "the recursion made explicit"; the third, that the
    # source pre-exists the target, is explicitly NOT enforced — `created_at`
    # is audit metadata, not a semantic clock, so there is nothing to order
    # by). Checked over every `derived_from` edge in the base, not only the
    # ones this release mints, because a hand-built or migrated record makes
    # the same claim and is held to the same two constraints.
    df: dict[str, list[str]] = {}
    for e in edges:
        if e["type"] != "derived_from":
            continue
        if e["source"] == e["destination"]:
            problems.append(f"derived_from {e['guid']} is reflexive: "
                            f"{e['source']} derived from itself")
        df.setdefault(e["source"], []).append(e["destination"])
    df_colour: dict[str, int] = {}

    def df_visit(g):
        df_colour[g] = 1
        for k in df.get(g, []):
            if df_colour.get(k) == 1:
                return True
            if not df_colour.get(k) and df_visit(k):
                return True
        df_colour[g] = 2
        return False

    for g_ in list(df):
        if not df_colour.get(g_) and df_visit(g_):
            problems.append("cycle in the derived_from graph")
            break

    # Thirteenth assertion, and the one `mutability` (v0.2.15, "AoTA") exists
    # to make checkable: an `immutable` root is refused a second `--updates`
    # ingest by the CLI, so nothing this tool's own writers can produce
    # should ever give one a second `derived_from` edge.
    #
    # This is a **proxy**, not the literal contract docs/design-0.3.0.md §2
    # states — "no edges added to this root after the ingest that created
    # it". That literal wording needs a clock this project has already
    # decided it does not have: `created_at` is audit metadata, never
    # semantics (CLAUDE.md; design-0.3.0.md §7), and `Store.load()`'s own
    # invariant is that shuffling file order must not change the graph's
    # meaning, which rules out inferring "before/after" from load order
    # either. What *is* checkable without a clock: every ingest path this
    # release builds mints exactly one `derived_from` edge from a root per
    # digest, so a second one on a root declared `immutable` is the
    # structural trace every such violation, made through this tool, leaves
    # behind. A hand-authored `contains` edge spliced straight onto an
    # immutable root's children, with no second blob to go with it, would
    # NOT be caught here — a real gap, named rather than silently treated as
    # covered.
    df_count: dict[str, int] = {}
    for e in edges:
        if e["type"] == "derived_from":
            df_count[e["source"]] = df_count.get(e["source"], 0) + 1
    for g_, n in nodes.items():
        if n["type"] not in ROOT_TYPES:
            continue
        if ((n.get("params") or {}).get("mutability") == "immutable"
                and df_count.get(g_, 0) > 1):
            problems.append(
                f"{n['type']} {g_}: immutable root has {df_count[g_]} "
                f"derived_from edges — its mutability contract permits "
                f"exactly one ingest")

    # Fourteenth assertion: `revision_of` is root-to-root, irreflexive,
    # acyclic, and at most one revision per root (v0.2.16, "TA";
    # docs/design-0.3.0.md §7, §9). A revision re-mints the whole tree and
    # chains only the two roots — never a block — so the only shape this
    # edge is ever allowed to have is document/session -> document/session,
    # the same treatment `derived_from` got in v0.2.14 (twelfth assertion,
    # above). "At most one revision per root" is checked the same way
    # `launched` already is: a destination named by two different
    # `revision_of` edges would mean two different trees both claim to
    # supersede the same predecessor, forking a history the design
    # (`design-0.3.0.md` §9) declares linear — one revision, one predecessor.
    rev: dict[str, list[str]] = {}
    rev_dest_count: dict[str, int] = {}
    for e in edges:
        if e["type"] != "revision_of":
            continue
        if e["source"] == e["destination"]:
            problems.append(f"revision_of {e['guid']} is reflexive: "
                            f"{e['source']} cannot be its own revision")
        src_n, dst_n = nodes.get(e["source"]), nodes.get(e["destination"])
        if src_n is None or src_n["type"] not in ROOT_TYPES:
            problems.append(
                f"revision_of {e['guid']}: source {e['source']} is not a "
                f"document or session root — revision_of chains roots only")
        if dst_n is None or dst_n["type"] not in ROOT_TYPES:
            problems.append(
                f"revision_of {e['guid']}: destination {e['destination']} "
                f"is not a document or session root — revision_of chains "
                f"roots only")
        rev.setdefault(e["source"], []).append(e["destination"])
        rev_dest_count[e["destination"]] = rev_dest_count.get(
            e["destination"], 0) + 1

    for dst, n_rev in rev_dest_count.items():
        if n_rev > 1:
            problems.append(
                f"{dst} is superseded by {n_rev} different revision_of "
                f"edges — at most one revision per root")

    rev_colour: dict[str, int] = {}

    def rev_visit(g_):
        rev_colour[g_] = 1
        for k in rev.get(g_, []):
            if rev_colour.get(k) == 1:
                return True
            if not rev_colour.get(k) and rev_visit(k):
                return True
        rev_colour[g_] = 2
        return False

    for g_ in list(rev):
        if not rev_colour.get(g_) and rev_visit(g_):
            problems.append("cycle in the revision_of graph")
            break

    return problems


def blobs_of(records, root: str) -> list:
    """
    Every `blob` node a root was derived from, oldest first by `imported_at`.

    An AoTA root accumulates one `derived_from` edge per re-ingest — storage
    does not deduplicate (docs/roadmap.md, "AoTA"): a second ingest stores the
    whole grown file again as a second blob, and the first stays exactly as
    reachable as it always was. `blob_of()`, below, is the common case —
    "which bytes are current" — and this is the general one, for a caller
    that wants the whole history rather than the current bytes.
    """
    nodes = {r["guid"]: r for r in records if r["record"] == "node"}
    out = []
    for r in records:
        if (r["record"] == "edge" and r["type"] == "derived_from"
                and r["source"] == root):
            n = nodes.get(r["destination"])
            if n is not None and n["type"] == "blob":
                out.append(n)
    out.sort(key=_blob_order)
    return out


def _blob_order(b: dict) -> tuple:
    """The order two blobs on one root are compared in: import time, then guid.

    The guid is there so the answer never depends on **load order**, which
    `Store.load()` guarantees carries no meaning — filenames are minted and a
    shuffled read must produce the same graph (CLAUDE.md). `_now()` records
    whole seconds, so two ingests inside one second carry the *same*
    `imported_at`, and a sort on that field alone leaves the winner decided by
    whichever `graph/*.jsonl` happened to be read first. Measured, both
    answers were reachable from the same records simply by reversing them.

    **On a tie the guid is arbitrary and means nothing.** It is not "the
    newer blob" — a uuid4 carries no recency — it is only a stable choice, so
    that the same base always answers the same way. That is the whole of what
    is being fixed here: determinism, not correctness.

    The reason it can only be arbitrary is worth naming, because it is the
    same missing clock that stopped `check` asserting the literal `immutable`
    contract: **the records do not record which ingest came last.**
    `imported_at` is audit metadata, of the same class as `created_at`, which
    this project has already refused to build a contract on (docs/design-
    0.3.0.md §7). Deriving "which bytes are current" from it is a proxy.

    The real answer is a claim the records would carry — a `supersedes` edge
    from a blob to the one it replaces, making "current" mean *the blob
    nothing supersedes*: order-independent, and no clock at all. That is a
    new edge type and a schema change, it belongs with the rest of the
    storage work, and it is deliberately not smuggled in here.
    See `TODO-storage-revamp.md`.
    """
    p = b.get("params") or {}
    return (p.get("imported_at") or "", b.get("guid") or "")


def blob_of(records, root: str) -> dict | None:
    """
    The `blob` node holding a root's *current* bytes, or None.

    This is the only supported way to get from a document back to its bytes.
    Storage filenames are minted guids, so the original name is *not* where
    the file lives — `blob.params["stored_as"]` is, and it is reachable only
    by following a `derived_from` edge. Anything that reconstructs a storage
    path from `params["source"]` is guessing, and will guess wrong.

    A never-appended root has exactly one `derived_from` edge, and this
    returns exactly what it always did — every existing caller (`views.py`,
    the test suite) keeps working unchanged. An AoTA root that has been
    re-ingested has several (`blobs_of()`, above), and "current" is the last
    by `_blob_order` — `imported_at`, then guid to break a tie.

    **Read `_blob_order` before relying on this on a re-ingested root.** The
    ordering is a proxy: `imported_at` is audit metadata, it records whole
    seconds so two ingests in one second tie, and the guid that breaks that
    tie is arbitrary. What this guarantees is that one base always gives one
    answer, never that the answer is the newer bytes.
    """
    blobs = blobs_of(records, root)
    if not blobs:
        return None
    return blobs[-1]


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

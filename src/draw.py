#!/usr/bin/env python3
"""
draw.py — compost draw.

A Graphviz picture of the base, drawn from records and from nothing else —
every node, every edge, the same waist the three views already sit on. v1 has
no collapsing policy: `docs/roadmap.md` ("v0.2.7 — a graph view") measured
that the design difficulty in a graph view was the collapsing policy, not the
drawing, so "draw everything" sidesteps it. A session transcript is thousands
of nodes, so the first picture of a real base is unreadable *as a picture* and
useful *as evidence* — the question this release answers is what compost
actually stores, and a filtered picture cannot answer it.

    compost draw [ROOT] [--engine dot|twopi|sfdp]

Whole base by default; one root's subgraph when ROOT — a whole guid — is
named.

**DOT is always written; SVG only when the chosen engine is on PATH.** That is
the property that keeps the graphviz binary optional at all: the DOT is a
deliverable on its own, readable by an agent and renderable later on any
machine that has graphviz, so the command must never make the SVG a
precondition for writing it.

Output goes to `.compost/graphviz/`, a peer of `graph/`, `storage/` and
`views/` — never inside `views/`. The dependency runs the other way: an HTML
view will eventually *embed* this SVG, so graphviz output is an input to
`render`, not one of its outputs.
"""
import re
import shutil
import subprocess

from . import __version__
from . import records as R
from . import store as S

# `dot` is the layered-hierarchy engine and, measured, the wrong default: it
# was killed at the 180s ceiling on a single 500-node graph shaped like
# compost's `contains` tree plus `next` chain, and again on a single
# 2,773-node document. `twopi` lays out a rooted tree radially, which is what
# this shape actually is, and was 7x faster than `sfdp` at 20,000 nodes.
# `sfdp` stays available for a citation-heavy graph that has stopped being
# tree-shaped; `dot` for a small scoped subgraph, where hierarchy is worth the
# wait. See docs/roadmap.md, "And `dot` cannot be the engine".
ENGINES = ("twopi", "sfdp", "dot")
DEFAULT_ENGINE = "twopi"

# The synthetic super-root a whole-base picture needs so a radial engine has
# one centre to lay the forest of `contains` trees out around. DOT-local:
# never a record, never written to graph/, never reaching `check` — the same
# relationship a view's handle has to the graph it decorates. A fixed sentinel
# rather than a minted guid, so a later two-phase layout (`twopi` for
# structure, `neato -n` for the citation overlay) can find it again in this
# file's own `pos` output. See docs/roadmap.md, "The synthetic root is a
# DOT-local name, never a record."
SYNTH_ROOT = "__root__"

# Measured on a real 12,632-node base: 4.52s and 16.9 MB of SVG for the whole
# thing with `twopi`. Output size, not layout time, is the ceiling — roughly
# 1.4 KB per node — and 17 MB is large but genuinely usable. So this warns
# and never refuses: the DOT is always complete regardless, and there is no
# node count at which withholding the SVG outright is more useful than
# saying so. See docs/roadmap.md, "The size threshold: warn, never refuse".
WARN_NODES = 5000


# -- labelling ---------------------------------------------------------------

def _clean(s, limit=60) -> str:
    """One line, no run of whitespace, short enough to stay a label and not
    a paragraph. `views.py` truncates tool-output summaries the same way."""
    s = " ".join(str(s).split())
    if len(s) > limit:
        s = s[:limit - 1] + "…"
    return s


def _label(n: dict) -> str:
    """A short, honest label — the node's own text if it has any, otherwise
    whatever field in `params` actually says what it is. Never invented:
    a node with neither gets its bare type, same as everywhere else a view
    has nothing to show (`views._render_session`'s `contentblock` case)."""
    text = R.plain_text(n).strip()
    if text:
        return _clean(f"{n['type']}: {text}")
    p = n.get("params") or {}
    for key in ("source", "value", "original_name", "author", "name",
                "session_id", "block_type", "tool_use_id"):
        if p.get(key):
            return _clean(f"{n['type']}: {p[key]}")
    return n["type"]


def _dot_str(s: str) -> str:
    """Escape for a DOT quoted string: backslash and double-quote, nothing
    else — a guid's hyphens go in verbatim. Graphviz escapes them again on
    the way *out* to SVG (`&#45;`, because `--` is illegal in an XML
    comment), which is a fact about graphviz's writer, not this one. See
    docs/roadmap.md, "the guid is not in the SVG bytes"."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


# -- DOT ----------------------------------------------------------------------

def _node_line(n: dict) -> str:
    # `id=` is what survives into the SVG as `<g id="…">` — the mechanism the
    # HTML view will need to make a picture click-to-copy the way the prose
    # views already do. `class=` carries the node's own type, so styling or
    # grouping by kind needs no `subgraph cluster_` — measured, `twopi`
    # ignores clusters entirely (0 cluster elements against 4 from `dot` on
    # the same file), and `twopi` is the default engine.
    guid = n["guid"]
    return (f'  "{guid}" [id="{guid}", label="{_dot_str(_label(n))}", '
            f'class="{_dot_str(n["type"])}"];')


def _edge_line(e: dict) -> str:
    # `class=` carries the edge's own record *layer*, not its type — the
    # field a two-phase layout needs to isolate the structural graph from
    # `citation` without hand-filtering a flat DOT file. See docs/roadmap.md,
    # "Every DOT edge carries its record `layer` as a `class` attribute."
    return (f'  "{e["source"]}" -> "{e["destination"]}" '
            f'[id="{e["guid"]}", class="{_dot_str(e["layer"])}", '
            f'label="{_dot_str(e["type"])}"];')


def _tree_reach(recs, root_guid: str) -> set:
    """Every node under `root_guid` in the containment tree — `contains` plus
    `launched`, the same pair `records.check` walks together for cycles,
    because a view renders a launched subagent *inside* the call that ran it.
    This is "one root's subgraph": the node set a view would show for this
    root, nothing pulled in from anywhere else in the base."""
    kids: dict[str, list[str]] = {}
    for r in recs:
        if r["record"] == "edge" and r["type"] in ("contains", "launched"):
            kids.setdefault(r["source"], []).append(r["destination"])
    out, stack = set(), [root_guid]
    while stack:
        g = stack.pop()
        if g in out:
            continue
        out.add(g)
        stack.extend(kids.get(g, []))
    return out


def _graphviz_version(engine: str) -> str | None:
    """The engine's own version string, or None if it is not on PATH.

    A second tool whose version silently changes its output is a trap this
    project already knows from pandoc (`CLAUDE.md`); graphviz gets the same
    treatment from day one — pinned in `environment.yml`, and the producing
    version recorded on every file this module writes.
    """
    exe = shutil.which(engine)
    if not exe:
        return None
    r = subprocess.run([exe, "-V"], capture_output=True, text=True)
    m = re.search(r"version ([\d.]+)", r.stderr or r.stdout)
    return m.group(1) if m else (r.stderr or r.stdout).strip()


def build_dot(recs: list, root: str | None, engine: str) -> tuple[str, int]:
    """The DOT text, and the count of real (non-synthetic) nodes it draws."""
    nodes = {r["guid"]: r for r in recs if r["record"] == "node"}
    edges = [r for r in recs if r["record"] == "edge"]

    if root is None:
        node_ids = set(nodes)
        kept_edges = edges
        # Every ROOT_TYPES node, launched or not: a launched subagent session
        # already has an incoming `launched` edge drawn below, but forcing an
        # edge from the synthetic root onto it too keeps the whole base one
        # connected component under one name, which is what lets `root=` mean
        # anything to a radial engine.
        synth_targets = [n["guid"] for n in nodes.values()
                          if n["type"] in R.ROOT_TYPES]
        root_attr = SYNTH_ROOT
    else:
        node_ids = _tree_reach(recs, root)
        kept_edges = [e for e in edges if e["source"] in node_ids
                      and e["destination"] in node_ids]
        synth_targets = []
        root_attr = root

    lines = [
        "digraph compost {",
        f'  // compost {__version__} -- graphviz '
        f'{_graphviz_version(engine) or "not on PATH; DOT only"}',
        f'  // engine {engine}, '
        f'{"whole base" if root is None else "root " + root}',
        f'  root="{_dot_str(root_attr)}";',
        "",
    ]
    if synth_targets:
        lines.append(f'  "{SYNTH_ROOT}" [id="{SYNTH_ROOT}", '
                     f'label="{SYNTH_ROOT}", class="synthetic"];')
        for g in sorted(synth_targets):
            lines.append(f'  "{SYNTH_ROOT}" -> "{g}" [class="synthetic"];')
        lines.append("")

    for g in sorted(node_ids):
        lines.append(_node_line(nodes[g]))
    lines.append("")
    for e in sorted(kept_edges, key=lambda e: (e["source"], e["type"],
                                               e["destination"])):
        lines.append(_edge_line(e))
    lines.append("}")
    return "\n".join(lines) + "\n", len(node_ids)


def render_svg(dot_text: str, engine: str) -> str | None:
    """The engine's SVG for `dot_text`, or None if `engine` is not on PATH.

    Absence is not an error — that is the whole point of "SVG is optional".
    A *present* engine that fails is a different thing and is left to raise,
    the same distinction `_digest` draws between a missing referral and a
    broken one.
    """
    exe = shutil.which(engine)
    if not exe:
        return None
    r = subprocess.run([exe, "-Tsvg"], input=dot_text,
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


# -- driver -------------------------------------------------------------------

def draw(st: S.Store, root: str | None, engine: str) -> dict:
    """Generate the picture and write it under `.compost/graphviz/`.

    Refuses when `check` fails, exactly as `render` does: a picture of a
    broken graph asserts something the base does not support, and a wrong
    picture is worse than none.
    """
    recs, _ = st.load()
    problems = R.check(recs)
    if problems:
        raise RuntimeError(f"graph has {len(problems)} problems; "
                           f"first: {problems[0]}")

    if root is not None:
        nodes = {r["guid"] for r in recs if r["record"] == "node"}
        if root not in nodes:
            raise ValueError(f"no node with guid {root!r}")

    dot_text, n_nodes = build_dot(recs, root, engine)

    d = st.graphviz
    d.mkdir(parents=True, exist_ok=True)
    dot_path = d / "graph.dot"
    dot_path.write_text(dot_text, encoding="utf-8")
    written = {dot_path}

    svg_path = None
    svg_text = render_svg(dot_text, engine)
    if svg_text is not None:
        svg_path = d / "graph.svg"
        svg_path.write_text(svg_text, encoding="utf-8")
        written.add(svg_path)

    # `draw` owns its whole directory, the way `render_all` owns the three
    # view directories — what is on disk after a run is exactly that run's
    # output, so a deleted document, or a switch from one root to another,
    # cannot leave a stale picture of something the base no longer holds.
    removed = []
    for f in d.iterdir():
        if f.is_file() and f not in written:
            f.unlink()
            removed.append(f)

    return {"dot": dot_path, "svg": svg_path, "nodes": n_nodes,
            "engine": engine, "removed": removed}


def main(argv):
    """Called as `draw.main(argv[1:])` from `cli.main`, so `argv[0]` is the
    subcommand name itself — `"draw"` — exactly like `layers.main`."""
    try:
        st = S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1

    root, engine = None, DEFAULT_ENGINE
    rest = argv[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--engine":
            if i + 1 >= len(rest):
                print("--engine needs one of: " + ", ".join(ENGINES))
                return 2
            engine = rest[i + 1]
            i += 2
        elif a.startswith("--engine="):
            engine = a.split("=", 1)[1]
            i += 1
        elif a.startswith("-"):
            print(f"unknown option {a!r}")
            return 2
        elif root is not None:
            print(f"usage: compost draw [ROOT] [--engine {'|'.join(ENGINES)}]")
            return 2
        else:
            root = a
            i += 1

    if engine not in ENGINES:
        print(f"unknown engine {engine!r}; choices: {', '.join(ENGINES)}")
        return 2

    try:
        r = draw(st, root, engine)
    except RuntimeError as e:
        # A refusal, not a crash — same shape as `render`'s.
        print(f"  refusing to draw: {e}")
        return 1
    except ValueError as e:
        print(f"  {e}")
        return 1

    print(f"  {r['nodes']:,} nodes  |  engine {r['engine']}"
          f"{' (root ' + root + ')' if root else ' (whole base)'}")
    if r["nodes"] > WARN_NODES:
        print(f"  warning: {r['nodes']:,} nodes is past the ~{WARN_NODES:,} "
              f"where the SVG gets large; the DOT is still complete")
    print(f"  wrote {r['dot'].relative_to(st.root)}")
    if r["svg"] is not None:
        mb = r["svg"].stat().st_size / 1_000_000
        print(f"  wrote {r['svg'].relative_to(st.root)}  ({mb:.1f} MB)")
    else:
        print(f"  no {r['engine']} on PATH — SVG skipped, the DOT is "
              f"complete on its own")
    if r["removed"]:
        print(f"  removed {len(r['removed'])} stale file(s)")
    return 0

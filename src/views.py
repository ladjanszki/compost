#!/usr/bin/env python3
"""
views.py — generate the three default views from the graph.

    .compost/views/default-djot/   what an agent reads, handles on every block
    .compost/views/default-html/   what a human reads and clicks
    .compost/views/default-md/     clean markdown, for regenerating README & co

All three are produced from *records* and from nothing else. That is the whole
point of the waist: a missing edge is a visibly broken page the same day, not a
silent wrong answer months later. None of them is a source — `views/` is
generated and disposable, and deleting it costs a rebuild.

The djot and html views carry handles; the markdown view deliberately does
not, because its output is meant to be committed as README.md and a handle in
there would be noise a reader never asked for.

Handles are the first 8 hex characters of the node guid. `records.check`
rejects a base where two nodes share one, because a short handle that resolves
to the wrong block is exactly the silent-citation failure the format exists to
prevent.
"""
import html as _html
import json
import re
import subprocess
import sys
from pathlib import Path

from . import records as R
from . import store as S

# Handles belong on what a person would cite, which is prose and the items of
# a list — not on the machinery holding them. A BulletList is not a thought; the
# items are. Marking every container produced a view with more handles than
# words in it, which is worse than none: it hides the citable thing in noise.
#
# Everything still *has* a guid and is still addressable from the graph. This
# is only about what the rendered page shows.
# DefinitionTerm is deliberately absent: a term is inline content, and a
# handle is a block-level marker. It is the same wall inlines hit everywhere —
# addressable in the graph, not markable in a rendered document.
CITABLE = {"Para", "Plain", "Header", "CodeBlock", "RawBlock", "LineBlock",
           "HorizontalRule", "ListItem", "BlockQuote", "Table"}

# Node types that came from a transcript rather than from pandoc. Each one
# needs its own view rendering, because there is no pandoc constructor to fall
# back on — this is the dispatch that replaces "reuse records_to_ast".
SESSION_TYPES = {"session", "turn", "toolcall", "tooloutput", "thinking",
                 "file", "logline", "contentblock"}

# Session containers carry their handle in their own Attr rather than in a
# wrapper, which is both tidier and what the previous renderer did:
#   {#376c3ce7 .turn author="human" turn="019ff17b-..."}
SELF_LABELLING = {"turn", "toolcall", "tooloutput", "session", "thinking"}


# A line that is nothing but a handle, optionally behind a list marker. Matched
# narrowly on purpose: a paragraph of prose may legitimately *end* with a
# handle, and joining that to the block below would change what the document
# says.
HANDLE_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\{#%s\}$" % R.HANDLE_RE)


def handle(guid: str) -> str:
    return guid[:R.HANDLE_LEN]


def _attr(guid, classes, kv):
    return [guid, classes, [[k, str(v)] for k, v in kv if v is not None]]


def _code(text, classes, guid=""):
    return {"t": "CodeBlock", "c": [_attr(guid, classes, []), text]}


def _details(summary, blocks):
    """HTML-only collapse. Djot has none, so the djot view shows everything."""
    return [{"t": "RawBlock", "c": ["html",
             f"<details><summary>{_html.escape(summary)}</summary>"]},
            *blocks,
            {"t": "RawBlock", "c": ["html", "</details>"]}]


def _render_session(g, n, mode):
    """A transcript node as pandoc blocks. None means deliberately not shown."""
    t, guid, p = n["type"], n["guid"], n.get("params", {})

    if t == "file":
        return None          # uncontained by design; listed separately

    if t == "logline":
        # Every line of the transcript is in the graph; most of them are
        # harness machinery — mode changes, title updates, file snapshots —
        # and none of it is prose anybody would cite. Stored and addressable,
        # deliberately not rendered. Being in the graph and being on the page
        # are different things, and the importer no longer gets to decide the
        # second one by refusing the first.
        return None

    if t == "contentblock":
        # A message block this importer has no reading for. Shown, not hidden:
        # the whole point of storing it was to notice it exists.
        body = json.dumps(p.get("block"), indent=1, ensure_ascii=False)
        label = p.get("block_type") or "unknown"
        return [_code(body, ["content-block", f"block-{label}"], guid)]

    if t == "thinking":
        # Kept as a node in the graph regardless. Shown only when it carries
        # text, because rendering 491 empty markers would be inventing content
        # the log never had — the same mistake as pandoc's callout titles.
        if not p.get("text"):
            return None
        return [{"t": "Div", "c": [_attr(guid, ["thinking"], []),
                                   [_code(p["text"], ["thinking"])]]}]

    if t == "tooloutput":
        body = [_code(p.get("text", ""), ["tool-output"], guid)]
        if mode == "html":
            n_lines = p.get("text", "").count("\n") + 1
            err = " (error)" if p.get("is_error") else ""
            return _details(f"output — {n_lines} lines{err}", body)
        return body

    if t == "toolcall":
        inp = json.dumps(p.get("input", {}), indent=1, ensure_ascii=False)
        blocks = [_code(inp, ["tool-input"])]
        blocks += _session_children(g, guid, mode)
        # A subagent transcript is the output of this call — it just happens to
        # have arrived in another file. Rendering it here is what stops a
        # conversation fragmenting into six unreadable `agent-<hex>` pages, and
        # it is why `render_all` gives it no page of its own.
        for e in g.linked(guid, "launched"):
            n_sub = g.nodes[e["destination"]]
            ag = n_sub.get("params", {}).get("agent", {})
            body = _render_session(g, n_sub, mode) or []
            if mode == "html":
                turns = sum(1 for k in g.children(e["destination"])
                            if g.nodes[k]["type"] == "turn")
                label = (f"subagent — {ag.get('agentType', 'unknown')}, "
                         f"{turns} turns")
                if ag.get("description"):
                    label += f": {ag['description']}"
                blocks += _details(label, body)
            else:
                blocks += body
        return [{"t": "Div", "c": [_attr(guid, ["tool-call"],
                                         [("name", p.get("name"))]),
                                   blocks]}]

    if t == "turn":
        # An envelope carrying nothing but tool results has no prose of its
        # own — its `tool_result` was folded into the call that produced it.
        # The node exists and holds the whole log line; an empty Div on the
        # page would be 140 blank frames saying nothing.
        if p.get("author") == "envelope" and not g.children(guid):
            return None
        return [{"t": "Div", "c": [
            _attr(guid, ["turn"], [("author", p.get("author")),
                                   ("time", p.get("timestamp")),
                                   ("turn", p.get("uuid"))]),
            _session_children(g, guid, mode)]}]

    if t == "session":
        ag = p.get("agent") or {}
        return [{"t": "Div", "c": [
            _attr(guid, ["session"] + (["subagent"] if ag else []),
                  [("source", p.get("source")),
                   ("session", p.get("session_id")),
                   ("agent", ag.get("agentType")),
                   ("depth", ag.get("spawnDepth"))]),
            _session_children(g, guid, mode)]}]

    raise NotImplementedError(f"no view rendering for node type {t!r}")


def _session_children(g, guid, mode):
    """
    Children of a transcript node, each dispatched on what it is.

    Prose falls through to the ordinary block translation, so a paragraph of an
    answer renders exactly as a paragraph of a markdown file — same node types,
    same handles, one code path.
    """
    out = []
    for k in g.children(guid):
        n = g.nodes[k]
        if n["type"] in SESSION_TYPES:
            blocks = _render_session(g, n, mode)
            if blocks:
                out.extend(blocks)
        else:
            blocks = [R._to_block(g, k)]
            out.extend(g.wrap(n, blocks) if g.wrap else blocks)
    return out


def pandoc(to: str, ast: dict, *extra) -> str:
    r = subprocess.run(["pandoc", "-f", "json", "-t", to, "--wrap=preserve",
                        *extra], input=json.dumps(ast),
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


# A session carries no pandoc api version, having never come from pandoc. The
# view envelope still needs one, so the reconstruction default stands in.
API_VERSION = [1, 23, 1, 2]


def _ast(records, root, wrap=None, mode="djot") -> dict:
    g = R.Graph(records)
    g.wrap = wrap
    n = g.nodes[root]
    if n["type"] == "session":
        # The file *is* the session, so its turns sit at the top level rather
        # than inside one more wrapper.
        blocks = _session_children(g, root, mode)
    else:
        blocks = R._blocks_of(g, root)
    return {"pandoc-api-version": R._p(n, "pandoc_api_version") or API_VERSION,
            "meta": R._p(n, "meta", {}),
            "blocks": blocks}


# -- djot -------------------------------------------------------------------

def _is_handle(block) -> bool:
    return (block.get("t") == "RawBlock" and block["c"][0] == "djot"
            and block["c"][1].startswith("{#"))


def _djot_wrap(node, blocks):
    if node["type"] not in CITABLE:
        return blocks
    # A list item whose first block is a paragraph reads as one thing, so it
    # gets one handle. Two stacked handles on the same visual line is how the
    # view starts looking like machine output instead of a document.
    if node["type"] == "ListItem" and blocks and _is_handle(blocks[0]):
        blocks = blocks[1:]
    return [{"t": "RawBlock", "c": ["djot", "{#" + handle(node["guid"]) + "}"]},
            *blocks]


def render_djot(records, root) -> str:
    out = pandoc("djot", _ast(records, root, _djot_wrap, "djot"))
    # Pandoc puts a blank line between the raw block and what follows. Djot
    # binds an attribute only to the block immediately after it, so closing
    # that gap turns most handles into real djot ids rather than decoration.
    # Most, not all: a few positions djot cannot carry an attribute into stay
    # visible text. That is fine — views are read, never re-ingested, and the
    # requirement is that a human or an agent can see the handle and cite it.
    lines = out.split("\n")
    kept, skip = [], False
    for i, line in enumerate(lines):
        if skip:
            skip = False
            continue
        kept.append(line)
        if (HANDLE_LINE.match(line)
                and i + 1 < len(lines) and lines[i + 1].strip() == ""):
            skip = True
    return "\n".join(kept)


# -- markdown ---------------------------------------------------------------

def render_md(records, root) -> str:
    return pandoc("commonmark_x-smart", _ast(records, root, None, "md"))


# -- html -------------------------------------------------------------------

def _html_wrap(node, blocks):
    if node["type"] not in CITABLE:
        return blocks
    attr = [handle(node["guid"]), ["block"], [["data-type", node["type"]]]]
    return [{"t": "Div", "c": [attr, blocks]}]


CSS = """
:root { --bg:#fff; --fg:#1a1a1a; --dim:#6a6a6a; --line:#e3e3e3; --mark:#0b5fff; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16181c; --fg:#e6e6e6; --dim:#8b8b8b; --line:#2b2f36; --mark:#7aa2ff; }
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); margin: 0;
       font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { max-width: 46rem; margin: 0 auto; padding: 3rem 1.5rem 6rem; }
h1, h2, h3 { line-height: 1.25; margin: 2rem 0 .6rem; }
pre { background: color-mix(in srgb, var(--fg) 5%, transparent);
      padding: .8rem 1rem; border-radius: 6px; overflow-x: auto; }
code { font-size: .9em; }
table { border-collapse: collapse; width: 100%; overflow-x: auto; display: block; }
th, td { border: 1px solid var(--line); padding: .4rem .6rem; text-align: left; }
blockquote { border-left: 3px solid var(--line); margin: 1rem 0; padding-left: 1rem;
             color: var(--dim); }
.block { position: relative; }
.block > :first-child { margin-top: .35rem; }
.block::before {
  content: attr(id); position: absolute; left: -5.6rem; top: .35rem;
  font: 500 11px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--dim); opacity: 0; cursor: pointer; user-select: none;
  transition: opacity .12s; letter-spacing: .02em;
}
.block:hover::before { opacity: 1; }
.block.copied::before { content: "copied"; color: var(--mark); opacity: 1; }
@media (max-width: 62rem) {
  .block::before { position: static; display: block; opacity: .45; }
}
.turn { border-left: 3px solid var(--line); padding-left: 1rem; margin: 1.6rem 0; }
.turn[author="human"] { border-left-color: var(--mark); }
.tool-call { margin: .8rem 0; }
.tool-call > pre:first-child { background: color-mix(in srgb, var(--mark) 8%, transparent); }
details { margin: .4rem 0; }
summary { cursor: pointer; color: var(--dim); font-size: .85rem; }
.thinking pre { opacity: .7; font-style: italic; }
/* A citation's link text is a single dash, so the page shows the target. */
a[href^="#"]::after { content: attr(href); font: 500 11px/1 ui-monospace, Menlo, monospace;
                      color: var(--dim); }
a[href^="#"] { text-decoration: none; }
footer { color: var(--dim); font-size: .85rem; border-top: 1px solid var(--line);
         margin-top: 3rem; padding-top: 1rem; }
a { color: var(--mark); }
"""

JS = """
document.addEventListener('click', function (e) {
  var el = e.target.closest('.block');
  if (!el) return;
  var r = el.getBoundingClientRect();
  var onHandle = e.clientX < r.left || e.clientY < r.top + 24 && e.clientX < r.left + 90;
  if (!onHandle && window.innerWidth > 992) return;
  navigator.clipboard.writeText('[-](#' + el.id + ')');
  el.classList.add('copied');
  setTimeout(function () { el.classList.remove('copied'); }, 900);
});
"""


def render_html(records, root, title: str) -> str:
    body = pandoc("html", _ast(records, root, _html_wrap, "html"))
    return (f"<!doctype html>\n<html lang=\"en\">\n<head>\n"
            f"<meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{_html.escape(title)}</title>\n<style>{CSS}</style>\n"
            f"</head>\n<body>\n<main>\n{body}\n"
            f"<footer>{_html.escape(title)} — click a handle to copy it as a citation"
            f"</footer>\n</main>\n<script>{JS}</script>\n</body>\n</html>\n")


# -- driver -----------------------------------------------------------------

def view_names(docs) -> dict:
    """
    Root guid -> the filename stem its views are written under, unique.

    Two documents may now legitimately carry the same original name: storage
    names are minted guids, so nothing refuses a second `notes.md` the way the
    old name-keyed storage accidentally did. Without this, the second one's
    views silently overwrite the first's and `render` reports having written
    files that are not there — a view that is quietly the wrong document,
    which is the failure `render` exists to refuse.

    A collision is broken with the root's handle rather than a counter. A
    counter renumbers when an unrelated document arrives, so every URL in the
    browser moves; a handle is the document's own and never does. Names that
    do not collide are left clean, which is the common case.
    """
    from collections import Counter
    stems = {d["guid"]: Path(R._p(d, "source") or d["guid"]).stem for d in docs}
    clash = {s for s, n in Counter(stems.values()).items() if n > 1}
    return {g: (f"{s}-{handle(g)}" if s in clash else s)
            for g, s in stems.items()}


def render_all(st: S.Store):
    recs, files = st.load()
    problems = R.check(recs)
    if problems:
        raise RuntimeError(f"graph has {len(problems)} problems; "
                           f"first: {problems[0]}")
    g = R.Graph(recs)
    # A transcript gets a page unless something launched it, in which case it
    # is rendered where it was launched. One rule, and it handles the awkward
    # case for free: digest a subagent transcript on its own, with no parent in
    # the base, and it has no incoming `launched` edge — so it gets a page,
    # which is correct, because nothing else would show it.
    launched = {r["destination"] for r in recs
                if r["record"] == "edge" and r["type"] == "launched"}
    docs = [n for n in g.nodes.values()
            if n["type"] in ("document", "session")
            and n["guid"] not in launched]
    names = view_names(docs)
    written = []
    index = []
    for doc in sorted(docs, key=lambda d: R._p(d, "source") or d["guid"]):
        root = doc["guid"]
        name = names[root]
        for sub, ext, fn in (
            ("default-djot", ".dj", lambda: render_djot(recs, root)),
            ("default-md", ".md", lambda: render_md(recs, root)),
            ("default-html", ".html", lambda: render_html(recs, root, name)),
        ):
            d = st.views / sub
            d.mkdir(parents=True, exist_ok=True)
            (d / (name + ext)).write_text(fn(), encoding="utf-8")
            written.append(d / (name + ext))
        index.append(name)

    # Remove pages this render did not produce. `render` used to only ever
    # write, which was invisible while every document had a page forever — and
    # became wrong the moment a transcript could stop having one of its own,
    # because the stale page stays in the browser showing a document the graph
    # no longer presents that way. Views are generated and disposable, so the
    # rule is that what is on disk is exactly this render's output.
    kept = {f.resolve() for f in written}
    removed = []
    for sub in ("default-djot", "default-html", "default-md"):
        d = st.views / sub
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.name != "index.html" \
                    and f.resolve() not in kept:
                f.unlink()
                removed.append(f)

    idx = st.views / "default-html" / "index.html"
    links = "\n".join(f'<li><a href="{_html.escape(n)}.html">{_html.escape(n)}</a></li>'
                      for n in index)
    idx.write_text(
        f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>compost</title><style>{CSS}</style></head><body><main>"
        f"<h1>compost</h1><p>{len(index)} documents, "
        f"{sum(1 for r in recs if r['record'] == 'node')} nodes.</p>"
        f"<ul>{links}</ul></main></body></html>\n", encoding="utf-8")
    return written, len(index), files, removed


def main(argv):
    try:
        st = S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1
    try:
        written, ndocs, files, removed = render_all(st)
    except RuntimeError as e:
        # A refusal, not a crash. Rendering a broken graph would produce a page
        # that looks fine and is wrong, which is worse than no page.
        print(f"  refusing to render: {e}")
        return 1
    print(f"  loaded {len(files)} graph files")
    if removed:
        print(f"  removed {len(removed)} stale view files")
    print(f"  {ndocs} documents and sessions -> {len(written)} files under "
          f"{st.views.relative_to(st.root)}/")
    for sub in ("default-djot", "default-html", "default-md"):
        n = len(list((st.views / sub).glob("*")))
        print(f"    {sub:<16} {n} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

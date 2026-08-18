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

sys.path.insert(0, str(Path(__file__).parent))
import records as R    # noqa: E402
import store as S      # noqa: E402

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


# A line that is nothing but a handle, optionally behind a list marker. Matched
# narrowly on purpose: a paragraph of prose may legitimately *end* with a
# handle, and joining that to the block below would change what the document
# says.
HANDLE_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\{#[0-9a-f]{%d}\}$"
                         % R.HANDLE_LEN)


def handle(guid: str) -> str:
    return guid[:R.HANDLE_LEN]


def pandoc(to: str, ast: dict, *extra) -> str:
    r = subprocess.run(["pandoc", "-f", "json", "-t", to, "--wrap=preserve",
                        *extra], input=json.dumps(ast),
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def _ast(records, root, wrap=None) -> dict:
    g = R.Graph(records)
    g.wrap = wrap
    n = g.nodes[root]
    return {"pandoc-api-version": R._p(n, "pandoc_api_version"),
            "meta": R._p(n, "meta", {}),
            "blocks": R._blocks_of(g, root)}


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
    out = pandoc("djot", _ast(records, root, _djot_wrap))
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
    return pandoc("commonmark_x-smart", _ast(records, root))


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
  navigator.clipboard.writeText('{@' + el.id + '}');
  el.classList.add('copied');
  setTimeout(function () { el.classList.remove('copied'); }, 900);
});
"""


def render_html(records, root, title: str) -> str:
    body = pandoc("html", _ast(records, root, _html_wrap))
    return (f"<!doctype html>\n<html lang=\"en\">\n<head>\n"
            f"<meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{_html.escape(title)}</title>\n<style>{CSS}</style>\n"
            f"</head>\n<body>\n<main>\n{body}\n"
            f"<footer>{_html.escape(title)} — click a handle to copy it as a citation"
            f"</footer>\n</main>\n<script>{JS}</script>\n</body>\n</html>\n")


# -- driver -----------------------------------------------------------------

def render_all(st: S.Store):
    recs, files = st.load()
    problems = R.check(recs)
    if problems:
        raise RuntimeError(f"graph has {len(problems)} problems; "
                           f"first: {problems[0]}")
    g = R.Graph(recs)
    docs = [n for n in g.nodes.values() if n["type"] == "document"]
    written = []
    index = []
    for doc in sorted(docs, key=lambda d: R._p(d, "source") or d["guid"]):
        root = doc["guid"]
        name = Path(R._p(doc, "source") or root).stem
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
    return written, len(index), files


def main(argv):
    st = S.Store.find()
    written, ndocs, files = render_all(st)
    print(f"  loaded {len(files)} graph files")
    print(f"  {ndocs} documents -> {len(written)} files under "
          f"{st.views.relative_to(st.root)}/")
    for sub in ("default-djot", "default-html", "default-md"):
        n = len(list((st.views / sub).glob("*")))
        print(f"    {sub:<16} {n} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

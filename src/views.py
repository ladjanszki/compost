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

A handle is the **whole guid**. `records.HANDLE_LEN` is 36, so `handle()`
below is the identity function, and a prefix is not a shorter handle — it does
not match the citation syntax and `compost lookup` refuses it. `records.check`
still rejects a base where two nodes share a handle; that assertion is vacuous
while the handle is the guid, and it exists so that shortening handles later
cannot silently introduce the collision this format exists to prevent. See
`docs/decisions.md`, "Identifiers and citations, as settled".

This paragraph previously said handles were the first 8 hex characters, which
had been false since the guid became the handle, and the CSS carried the
damage until v0.2.9: the `.block::before` gutter was sized `left: -5.6rem`
and printed `attr(id)`, which fit an 8-character handle and spilled a
36-character one across the text it was meant to annotate. It now shows a
fixed hint instead of the id — see `docs/roadmap.md`, v0.2.9.
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

# The harness's own reserved tags, opening a Para. Recognised structurally —
# the node's first inline is a RawInline of format html whose text is exactly
# one of these — never by matching prose. That is the same standing as
# "never scan raw file text for citations": a paragraph that merely *mentions*
# one of these mid-sentence does not match. docs/roadmap.md, v0.2.9.
SLASH_CAVEAT = "<local-command-caveat>"
SLASH_COMMAND = "<command-name>"
SLASH_STDOUT = "<local-command-stdout>"
SLASH_TAGS = {SLASH_CAVEAT, SLASH_COMMAND, SLASH_STDOUT}

# A terminal's SGR sequences (colour, bold, ...), stripped from a slash
# command's stdout at view time only. The record keeps them; `lookup` still
# prints what the log held.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# A line that is nothing but a handle, optionally behind a list marker. Matched
# narrowly on purpose: a paragraph of prose may legitimately *end* with a
# handle, and joining that to the block below would change what the document
# says.
HANDLE_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\{#%s\}$" % R.HANDLE_RE)


# The display-name layer, and the node type it names — its own vocabulary,
# not a reuse of `alias`. An alias answers "what does this string resolve
# to" (input to node); a display name answers "what should be shown for
# this node" (node to string) — opposite directions, and overloading them
# would put display names in `lookup`'s resolver. docs/roadmap.md, v0.2.10.
DISPLAY_LAYER = "display"
DISPLAY_NAME_TYPE = "display_name"


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


def _lead_tag(node) -> str | None:
    """
    The text of `node`'s first inline, when that inline is a raw-html tag.

    `node["content"]` is the raw pandoc inline list a `Para`/`Plain` node
    carries. Returns None for anything else — no text, a different first
    inline, or a RawInline of a format other than html.
    """
    inlines = node.get("content") or []
    if not inlines:
        return None
    first = inlines[0]
    if (isinstance(first, dict) and first.get("t") == "RawInline"
            and (first.get("c") or [None])[0] == "html"):
        return first["c"][1]
    return None


def _command_line(text: str) -> str:
    """
    `/exit exit ` -> `/exit`; collapse whitespace, drop a redundant message.

    `text` is `R.plain_text(n)` on a slash-command Para — the RawInline tags
    around name/message/args are already gone, leaving bare words in order.
    When the word right after the name repeats it (message equals name, the
    common case), that word is noise and is dropped; anything after it (a
    real argument) is kept.
    """
    words = text.split()
    if not words:
        return ""
    name = words[0]
    if len(words) > 1 and words[1] == name.lstrip("/"):
        words.pop(1)
    return " ".join(words)


def _render_slash(g, n, mode):
    """
    A slash-command `Para` (see `_lead_tag`) -> the blocks to emit, or None.

    - the caveat is an instruction to the model; there is no reading of it
      that belongs inside an `author="human"` frame, so it renders as nothing.
    - the command becomes one plain line, still a `Para` so it keeps its
      handle through the ordinary wrap in `_session_children`.
    - the stdout folds in html (the `tooloutput` pattern), stays a bare code
      block in djot, and is skipped entirely when empty. ANSI SGR sequences
      are stripped here, in the view only — the record still holds them.
    """
    tag = _lead_tag(n)
    if tag == SLASH_CAVEAT:
        return None
    if tag == SLASH_COMMAND:
        line = _command_line(R.plain_text(n))
        if not line:
            return None
        return [{"t": "Para", "c": [{"t": "Str", "c": line}]}]
    if tag == SLASH_STDOUT:
        text = _ANSI_RE.sub("", R.plain_text(n)).strip()
        if not text:
            return None
        block = _code(text, ["command-output"])
        return _details("output", [block]) if mode == "html" else [block]
    return None


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
        # `params["text"]` is a string for the ordinary case, and — since
        # v0.2.13 stopped flattening a list-shaped `tool_result.content` to
        # joined text (design-total-mapping.md) — sometimes the list
        # itself, stored whole. A `CodeBlock`'s payload has to be a string
        # either way, so a list is shown as the same pretty JSON `contentblock`
        # already uses for a block this importer has no reading for.
        raw = p.get("text", "")
        text = (json.dumps(raw, indent=1, ensure_ascii=False)
               if isinstance(raw, list) else raw)
        body = [_code(text, ["tool-output"], guid)]
        if mode == "html":
            n_lines = text.count("\n") + 1
            err = " (error)" if p.get("is_error") else ""
            return _details(f"output — {n_lines} lines{err}", body)
        return body

    if t == "toolcall":
        raw_input = p.get("input") or {}
        inp = json.dumps(raw_input, indent=1, ensure_ascii=False)
        input_blocks = [_code(inp, ["tool-input"])]
        if mode == "html":
            # djot shows everything; html folds what is long. The summary is
            # the tool's name plus a taste of its first argument — the v0.1
            # style, ported: 12px monospace, dim.
            first = next(iter(raw_input.values()), "")
            first = first if isinstance(first, str) else \
                json.dumps(first, ensure_ascii=False)
            summary = p.get("name") or "tool call"
            if first:
                summary += f" — {first[:72]}"
            blocks = _details(summary, input_blocks)
        else:
            blocks = input_blocks
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
        # A turn whose children all render to nothing has nothing to show.
        # This subsumes the old check for an envelope turn specifically (its
        # `tool_result` was folded into the call that produced it) — the
        # general rule catches that case and any other, present or future,
        # without one special case per cause. The node exists and holds the
        # whole log line regardless; an empty Div on the page would be 140
        # blank frames saying nothing.
        kids = _session_children(g, guid, mode)
        if not kids:
            return None
        return [{"t": "Div", "c": [
            _attr(guid, ["turn"], [("author", p.get("author")),
                                   ("time", p.get("timestamp")),
                                   ("turn", p.get("uuid"))]),
            kids]}]

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
        elif _lead_tag(n) in SLASH_TAGS:
            # Structural, not a text scan: the node's first inline already
            # told us this is a harness-reserved tag, so it is routed here
            # instead of the ordinary R._to_block reconstruction path. That
            # path must keep returning the node exactly; this one may not
            # touch it — `_render_slash` reads the node, never rewrites it.
            blocks = _render_slash(g, n, mode)
            if blocks:
                out.extend(g.wrap(n, blocks) if g.wrap else blocks)
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
:root {
  --bg:#fff; --fg:#1a1a1a; --dim:#6a6a6a; --line:#e3e3e3;
  /* v0.1's single accent, verbatim — its links and its human-turn border
     were the same blue. docs/roadmap.md, v0.2.9, "the whole guid is printed". */
  --mark:#2b5fd9;
  --hl:#f2f6ff;          /* the one highlight colour: .hl and .hl-sub share it */
  --author:#9aa7bb;      /* v0.1's turn-label grey, verbatim */
  --agent:#d99b2b;       /* v0.1's claude/agent border colour, verbatim */
}
/* Forced light, deliberately: v0.1's Wikipedia-like page is what the palette
   above was restored for, and a dark-mode media query here undid exactly
   that on a machine set to dark. Every token above stays, so flexible
   theming later is a change of values rather than a rewrite.
   docs/roadmap.md, v0.2.10. */
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); margin: 0;
       font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { max-width: 46rem; margin: 0 auto; padding: 3rem 1.5rem 6rem; }
h1, h2, h3 { line-height: 1.25; margin: 2rem 0 .6rem; }
pre { background: color-mix(in srgb, var(--fg) 5%, transparent);
      padding: .8rem 1rem; border-radius: 6px; overflow-x: auto; }
code { font-size: .9em; }
/* Shared by every pandoc table and by the index page's own tables
   (render_index): `display: block` plus `overflow-x: auto` makes a wide
   table scroll inside its own box rather than widening the page, and
   reuses --line/--dim like everything else here — v0.2.10 added no
   second rule, because this one already does what an index table needs. */
table { border-collapse: collapse; width: 100%; overflow-x: auto; display: block; }
th, td { border: 1px solid var(--line); padding: .4rem .6rem; text-align: left; }
th { color: var(--dim); font-weight: 600; }
blockquote { border-left: 3px solid var(--line); margin: 1rem 0; padding-left: 1rem;
             color: var(--dim); }
.block { position: relative; }
.block > :first-child { margin-top: .35rem; }
/* A fixed hint, not the guid: the id is 36 characters now, not 8, and a
   36-character monospace string sized for 8 spills across the text it is
   meant to annotate. Shown only on `.hl` (JS, see below) rather than on
   `:hover` — blocks nest, and `:hover` matches every containing block at
   once. */
.block::before {
  content: "⧉ click to copy"; position: absolute; left: -9.5rem; top: .35rem;
  font: 500 11px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--dim); opacity: 0; white-space: nowrap; pointer-events: none;
  transition: opacity .12s; letter-spacing: .02em;
}
.block.hl::before { opacity: 1; }
.block.hl[data-subtree-hint]::before { content: "⧉ click · ⇧ subtree"; }
@media (max-width: 62rem) {
  .block::before { position: static; display: block; opacity: .45; }
}
/* One highlight, one meaning: this is what you are pointing at. Opaque, not
   translucent — `.block` divs nest, and a translucent wash would double-darken
   the inner ones. v0.1 painted the subtree amber as a warning that the
   clipboard was about to differ; v0.2 has no subtree citation syntax, so that
   warning would point at a difference that no longer exists. */
.hl, .hl-sub { background: var(--hl); border-radius: 3px; }
.turn { border-left: 3px solid var(--line); padding-left: 1rem; margin: 1.6rem 0; }
/* pandoc's html writer data-prefixes a Div's non-standard attributes — "author"
   is not a global HTML attribute, so the node comes out as data-author, not
   author. v0.1 rendered through djot.js, which does not do this, so its plain
   `[author]` selector is not portable verbatim; this is the one v0.1 constant
   in this release that had to change to work at all, not merely to look right. */
.turn[data-author]::before {
  content: attr(data-author); display: block; font-size: 11px;
  text-transform: uppercase; letter-spacing: .07em; color: var(--author);
  margin-bottom: .4rem;
}
/* The values are the closed vocabulary in docs/record-grammar.md §6 —
   `human`, `assistant`, `envelope` — not v0.1's. Porting v0.1's
   `^="claude"` / `^="agent"` verbatim left both selectors matching nothing,
   which is the same dead-selector failure the data- prefix caused above, from
   the other direction: the attribute was right and the value was not.
   `envelope` is deliberately unstyled — it is machinery, and the few that
   render carry no prose of their own. */
.turn[data-author="human"] { border-left-color: var(--mark); }
.turn[data-author="assistant"] { border-left-color: var(--agent); }
.tool-call { margin: .8rem 0; }
.tool-call > pre:first-child { background: color-mix(in srgb, var(--mark) 8%, transparent); }
details { margin: .4rem 0; }
summary { cursor: pointer; color: var(--dim); font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; }
.thinking pre { opacity: .7; font-style: italic; }
/* A citation's link text is a single dash, so the page shows the target. */
a[href^="#"]::after { content: attr(href); font: 500 11px/1 ui-monospace, Menlo, monospace;
                      color: var(--dim); }
a[href^="#"] { text-decoration: none; }
footer { color: var(--dim); font-size: .85rem; border-top: 1px solid var(--line);
         margin-top: 3rem; padding-top: 1rem; }
a { color: var(--mark); }
/* v0.1's toast: fixed, bottom centre, dark pill, showing the reference it
   just copied, for 1.8s. This is the copy confirmation; `.copied` used to
   replace the gutter text, which is the one place on screen nobody is
   looking immediately after clicking. */
#toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
  background: #1a1a1a; color: #fff; padding: .5rem 1rem; border-radius: 6px;
  font: 13px monospace; opacity: 0; transition: opacity .15s;
  pointer-events: none; max-width: 90vw; overflow: hidden; }
#toast.show { opacity: 1; }
"""

JS = """
// closest() stops at the first match walking up — the smallest containing
// block. A mousemove handler, not :hover, so a Para inside a ListItem inside
// a BlockQuote lights up only the one block the cursor is actually over.
function headerLevel(el) {
  if (!el || el.dataset.type !== 'Header') return null;
  var h = el.querySelector('h1,h2,h3,h4,h5,h6');
  return h ? parseInt(h.tagName.slice(1), 10) : null;
}
// The heading subtree, computed here rather than from a pandoc --section-divs
// wrapper: a header's subtree is every following sibling block up to (not
// including) the next heading of equal or higher level. Any other container's
// subtree is simply the .block descendants it already contains — a list item,
// a blockquote, or anything else nesting, with no special case needed because
// a leaf block's querySelectorAll('.block') is already empty.
function subtreeOf(el) {
  var lvl = headerLevel(el);
  if (lvl === null) return Array.prototype.slice.call(el.querySelectorAll('.block'));
  var out = [], sib = el.nextElementSibling;
  while (sib) {
    var sLvl = headerLevel(sib);
    if (sLvl !== null && sLvl <= lvl) break;
    out.push(sib);
    sib = sib.nextElementSibling;
  }
  return out;
}

var current = null, shiftDown = false;
function paint() {
  document.querySelectorAll('.hl,.hl-sub').forEach(function (n) {
    n.classList.remove('hl', 'hl-sub');
    n.removeAttribute('data-subtree-hint');
  });
  if (!current) return;
  current.classList.add('hl');
  var sub = subtreeOf(current);
  if (sub.length) current.setAttribute('data-subtree-hint', '1');
  // Shift highlights the subtree; shift does not change what is copied. v0.1's
  // {#id+++} was that syntax, and v0.2 has no subtree citation to mint one in.
  if (shiftDown) sub.forEach(function (b) { b.classList.add('hl-sub'); });
}
document.addEventListener('mousemove', function (e) {
  var el = e.target.closest('.block');
  if (el !== current) { current = el; paint(); }
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Shift' && !shiftDown) { shiftDown = true; paint(); }
});
document.addEventListener('keyup', function (e) {
  if (e.key === 'Shift') { shiftDown = false; paint(); }
});
// No geometry test, no width gate: click anywhere in the block. Shift is not
// read here at all — the clipboard gets '[-](#guid)' whether or not it is
// down, byte-identical, and it never contains '+'.
document.addEventListener('click', function (e) {
  var el = e.target.closest('.block');
  if (!el) return;
  var ref = '[-](#' + el.id + ')';
  navigator.clipboard.writeText(ref).then(function () {
    var t = document.getElementById('toast');
    t.textContent = ref;
    t.classList.add('show');
    clearTimeout(window._tt);
    window._tt = setTimeout(function () { t.classList.remove('show'); }, 1800);
  });
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
            f"</footer>\n<div id=\"toast\"></div>\n</main>\n<script>{JS}</script>\n"
            f"</body>\n</html>\n")


# -- the index ----------------------------------------------------------

def _display_name(g: R.Graph, root: str) -> str | None:
    """The most recent display name naming `root`, or None.

    A display-name edge points *at* the root (`display_name -> names ->
    root`), the opposite direction from what `Graph.linked` indexes edges
    by (source), so answering this per row would be a scan over every
    `names` edge in the base once per row. Built once instead, on first
    call, and cached on `g` itself — the same pattern `g.wrap` already uses
    for a view to carry state a bare `Graph` has no field for.

    Several display names may name one root, the same way two builds mint
    two aliases for one value: nothing collapses them in the records. The
    most recent by the naming edge's `created_at` wins; ties — same
    timestamp, or no display name at all — are broken by the display_name
    node's own guid, so the choice is stable across repeated renders.
    """
    idx = getattr(g, "_display_name_index", None)
    if idx is None:
        idx = {}
        for edges in g._rel.get("names", {}).values():
            for e in edges:
                if e.get("layer") != DISPLAY_LAYER:
                    continue          # the citation layer's own `names` use
                n = g.nodes.get(e["source"])
                if n is None or n["type"] != DISPLAY_NAME_TYPE:
                    continue
                key = (e.get("created_at", ""), n["guid"])
                cur = idx.get(e["destination"])
                if cur is None or key > cur[0]:
                    idx[e["destination"]] = (key, R._p(n, "value"))
        g._display_name_index = idx
    hit = idx.get(root)
    return hit[1] if hit else None


def _when(ts):
    """An ISO timestamp trimmed to what a person scans: `2026-08-25 16:13`.

    Display only — the record keeps whatever the source wrote, to the
    millisecond and with its own offset. This drops the seconds, the
    subseconds and the `Z`, because a table of `2003-08-05T16:30:57.370Z` is
    a column nobody reads across. Anything that is not an ISO-looking string
    is passed through untouched rather than guessed at (v0.2.10; the roadmap
    asked for date columns and did not say what a date looks like, which is
    how the raw form shipped in the first place).
    """
    if not ts or len(ts) < 16 or ts[10] not in "T ":
        return ts or "\u2014"
    return ts[:10] + " " + ts[11:16]


def _row_facts(g: R.Graph, recs: list, root: str) -> dict:
    """What one index row needs, computed once so the two renderers below
    stay presentational.

    `name` falls back to the source filename's stem — never to a heading
    read out of the document, which v0.2.10 rejected outright (a name that
    changes when the prose changes is a reminder pretending to be an
    identifier). Everything date-shaped is read from a record, never
    guessed from a path: a session's turns each carry their own timestamp,
    and a document's only reachable date is its blob's `imported_at`,
    through `derived_from` — `CLAUDE.md` is explicit that nothing else
    turns a filename into a storage fact.
    """
    n = g.nodes[root]
    source = R._p(n, "source")
    stem = Path(source).stem if source else root
    out = {"name": _display_name(g, root) or stem, "source": source}
    if n["type"] == "session":
        turns = [g.nodes[k] for k in g.children(root)
                 if g.nodes[k]["type"] == "turn"]
        times = sorted(t for t in (R._p(t, "timestamp") for t in turns) if t)
        out["session_id"] = R._p(n, "session_id")
        out["first_turn"] = times[0] if times else None
        out["last_turn"] = times[-1] if times else None
    else:
        def walk(guid):
            yield guid
            for k in g.children(guid):
                yield from walk(k)
        out["words"] = sum(len(R.plain_text(g.nodes[k]).split())
                           for k in walk(root))
        blob = R.blob_of(recs, root)
        out["imported_at"] = R._p(blob, "imported_at") if blob else None
    return out


def render_index(g: R.Graph, recs: list, docs: list, names: dict) -> str:
    """The `default-html/index.html` page: one section per member of
    `records.ROOT_TYPES`, generated rather than hardcoded (docs/roadmap.md,
    v0.2.10 — "the sections are generated from ROOT_TYPES, never
    hardcoded"). `names` is `view_names(docs)`, the filename-stem map, not
    the display-name index above — the same word means two different
    things one function apart, on purpose, following the driver that
    already used it that way.
    """
    total_nodes = sum(1 for r in recs if r["record"] == "node")
    sections = []
    for t in sorted(R.ROOT_TYPES):
        rows = [d for d in docs if d["type"] == t]
        facts = {d["guid"]: _row_facts(g, recs, d["guid"]) for d in rows}
        heading = t[:1].upper() + t[1:] + "s"
        sort_key = "last_turn" if t == "session" else "imported_at"
        rows = sorted(rows, key=lambda d: facts[d["guid"]].get(sort_key) or "",
                      reverse=True)
        if not rows:
            sections.append(f"<h2>{_html.escape(heading)}</h2>\n"
                            f"<p>no {_html.escape(t)}s yet</p>")
            continue
        if t == "session":
            cols = ["first turn", "last turn", "session id", "source"]

            def cells(f):
                return [_when(f.get("first_turn")),
                        _when(f.get("last_turn")),
                        f.get("session_id") or "—",
                        f.get("source") or "—"]
        elif t == "document":
            cols = ["words", "imported"]

            def cells(f):
                return [str(f.get("words", 0)),
                        _when(f.get("imported_at"))]
        else:
            # A root type this index has no dedicated columns for yet —
            # reached only by adding a member to ROOT_TYPES, which is
            # exactly the case this fallback exists to not crash on.
            cols = ["source"]

            def cells(f):
                return [f.get("source") or "—"]
        thead = "".join(f"<th>{_html.escape(c)}</th>" for c in cols)
        trs = []
        for d in rows:
            f = facts[d["guid"]]
            href = _html.escape(names[d["guid"]] + ".html")
            row_cells = "".join(f"<td>{_html.escape(str(c))}</td>"
                                for c in cells(f))
            trs.append(f'<tr><td><a href="{href}">'
                       f'{_html.escape(f["name"])}</a></td>{row_cells}</tr>')
        sections.append(
            f"<h2>{_html.escape(heading)}</h2>\n"
            f"<table><thead><tr><th>name</th>{thead}</tr></thead>"
            f"<tbody>{''.join(trs)}</tbody></table>")
    body = "\n".join(sections)
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>compost</title><style>{CSS}</style></head><body><main>"
            f"<h1>compost</h1><p>{len(docs)} documents and sessions, "
            f"{total_nodes} nodes.</p>{body}</main></body></html>\n")


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
            if n["type"] in R.ROOT_TYPES
            and n["guid"] not in launched]
    names = view_names(docs)
    written = []
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
    idx.write_text(render_index(g, recs, docs, names), encoding="utf-8")
    return written, len(docs), files, removed


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

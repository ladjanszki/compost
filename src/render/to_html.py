"""
to_html.py — render a knowledge base to a static, clickable site.

Every block carries its uuid as an HTML id and its content hash as data-hash,
so the page's JavaScript can build a pinned reference without a server. Click
copies `{#uuid:hash}`; shift-click copies `{#uuid:hash+++}` for the subtree.

Two djot behaviours this has to work around, both found by testing:

  * A heading's `{#id}` attaches to the enclosing <section>, not the heading.
    The page script moves it onto the heading and treats the section as that
    heading's subtree container.
  * A list item's id is dropped in HTML unless the list is loose. Canonization
    handles that (see canonize/inject_ids.loosen); if it ever regresses, the
    per-page addressability count reports it.
"""
import datetime
import html as html_mod
import re
import subprocess
from pathlib import Path

from ..canonize import block_hash
from ..ingest.ast_walker import walk
from ..ingest.djot_ast import get_ast_from_text
from ..refs import HANDLE, ID_ATTR, REF as REF_RE
from . import index as index_mod
from ..store import Store

_ID_IN_HTML = re.compile(r'id="' + HANDLE + r'"')


def djot_to_html(djot: str) -> str:
    r = subprocess.run(
        ["npx", "@djot/djot", "--to", "html"],
        input=djot, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"djot.js failed:\n{r.stderr.strip()}")
    return r.stdout


def has_subtree(blocks: list, i: int) -> bool:
    """
    Whether block i owns anything beneath it.

    A heading owns everything until the next heading of equal or higher level;
    a list item owns the immediately following items of greater depth.
    """
    b = blocks[i]
    c = b.get("content", {})
    if b["type"] == "heading":
        nxt = blocks[i + 1:]
        if not nxt:
            return False
        lvl = c.get("level", 1)
        return not (nxt[0]["type"] == "heading"
                    and nxt[0]["content"].get("level", 1) <= lvl)
    if b["type"] == "div":
        # A turn (or any div) owns the blocks flattened out of it, so shift-click
        # copies a whole turn.
        return c.get("contains", 0) > 0
    if b["type"] in ("list_item", "task_item"):
        d = c.get("depth", 0)
        nxt = blocks[i + 1:]
        return bool(nxt) and nxt[0]["type"] in ("list_item", "task_item") \
            and nxt[0]["content"].get("depth", 0) > d
    return False


def annotate(djot: str, blocks: list) -> str:
    """Add data-hash / data-subtree to each block's attribute in the djot."""
    meta = {}
    for i, b in enumerate(blocks):
        if b.get("id"):
            meta[b["id"]] = (block_hash(b)[:16], has_subtree(blocks, i))

    def sub(m):
        bid = m.group(1)
        if bid not in meta:
            return m.group(0)
        h, sub_ok = meta[bid]
        return f'{{#{bid} data-hash="{h}"{" data-subtree=\"1\"" if sub_ok else ""}}}'

    return ID_ATTR.sub(sub, djot)


# ---------------------------------------------------------------- corpus ---

def load_notes(store: Store) -> list[dict]:
    """Every conversation and artifact, with its parsed blocks."""
    notes = []
    for path in store.source_paths():
        kind = "artifact" if path.parent == store.artifacts else "conversation"
        djot = path.read_text(encoding="utf-8")
        blocks = walk(get_ast_from_text(djot))
        # An artifact is named, so its filename is its title. A conversation is
        # a uuid, so the first heading — or failing that the first block — is
        # the only human-readable handle on it.
        # A link should say what it points at. Prefer the document's own first
        # heading; fall back to the filename for an artifact (which is chosen,
        # so it means something) and to the opening words for a conversation
        # (whose name is a uuid, which means nothing).
        heading = next((b["content"]["text"] for b in blocks
                        if b["type"] == "heading"), "")
        if heading:
            title = heading
        elif kind == "artifact":
            title = path.stem.replace("-", " ")
        else:
            title = next((b["content"].get("text", "") for b in blocks
                          if b["content"].get("text")), "") or path.stem

        turn_blocks = [b for b in blocks if b["type"] == "div"
                       and "turn" in (b["content"].get("classes") or [])]
        turns = len(turn_blocks)
        # An imported conversation carries the real time of its first turn;
        # its filename cannot supply one.
        stamp = next((((b["content"].get("attrs") or {}).get("time") or "")[:16]
                      for b in turn_blocks
                      if (b["content"].get("attrs") or {}).get("time")), "")
        who = []
        for b in turn_blocks:
            a = (b["content"].get("attrs") or {}).get("author")
            if a and a not in who:
                who.append(a)
        notes.append({
            "id": path.stem,
            "kind": kind,
            "path": path,
            "djot": djot,
            "blocks": blocks,
            "turns": turns,
            "authors": who,
            "when": stamp.replace("T", " ") or _when(path.stem)
                    or datetime.datetime.fromtimestamp(
                        path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "words": sum(len(b["content"].get("text", "").split()) for b in blocks),
            "title": " ".join(title.split())[:80],
        })
    return notes


def backlink_index(notes: list[dict]) -> dict[str, list[dict]]:
    """
    Map block id -> notes referencing it.

    Computed at render time from the text, so it applies retroactively to notes
    written before backlinks existed. Nothing is stored.
    """
    index: dict[str, list[dict]] = {}
    for note in notes:
        # Scan parsed block text, not the raw file: pandoc escapes references
        # on disk as "\{#uuid:hash\}", and parsing is what unescapes them.
        for block in note["blocks"]:
            for m in REF_RE.finditer(block["content"].get("text", "")):
                target = m.group(1)
                if target == block.get("id"):
                    continue  # a block referencing itself is not a backlink
                entries = index.setdefault(target, [])
                if not any(e["note"] is note for e in entries):
                    entries.append({"note": note, "subtree": bool(m.group(3))})
    return index


# ------------------------------------------------------------------ page ---

CSS = """
  body {font: 16px/1.6 -apple-system, system-ui, sans-serif; max-width: 46rem;
        margin: 0 auto; padding: 2rem 1rem 6rem; color: #1a1a1a;}
  a {color: #2b5fd9;}
  nav {font-size: 13px; margin-bottom: 2rem; color: #7a8ba6;}
  h1,h2,h3 {line-height: 1.25;}
  [data-hash] {position: relative; border-radius: 3px; padding: 2px 4px;
        margin-left: -4px; cursor: pointer;}
  .hl {background: #f2f6ff;}
  .hl-sub {background: #fff3d6; border-radius: 3px;}
  .hl::after {content: "⧉ click to copy"; position: absolute; right: -9.5rem;
        top: 2px; font-size: 11px; color: #7a8ba6; white-space: nowrap;}
  .hl[data-subtree]::after {content: "⧉ click · ⇧ subtree";}
  li > p[data-hash] {margin: 0;}
  .task-list {list-style: none; padding-left: 1.2rem;}
  .backlinks {margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #e4e8ef;
        font-size: 14px;}
  .backlinks h2 {font-size: 14px; text-transform: uppercase; letter-spacing: .05em;
        color: #7a8ba6;}
  .noteindex {list-style: none; padding: 0;}
  .noteindex li {padding: .5rem 0; border-bottom: 1px solid #f0f2f6;}
  .noteindex .meta {display: block; color: #9aa7bb; font-size: 12px;
        font-family: monospace; margin-top: .1rem;}
  .noteindex .when {color: #9aa7bb; font-size: 12px; font-family: monospace;}
  .kind {font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
        color: #9aa7bb;}
  /* A turn is fenced in its own div so appends cannot corrupt the seam; the
     author attribute rides along in the djot, so the label needs no JS. */
  .turn {border-left: 3px solid #e4e8ef; padding: .2rem 0 .2rem 1rem;
        margin: 1.6rem 0;}
  .turn[author]::before {content: attr(author); display: block; font-size: 11px;
        text-transform: uppercase; letter-spacing: .07em; color: #9aa7bb;
        margin-bottom: .4rem;}
  .turn[author="human"] {border-left-color: #2b5fd9;}
  .turn[author^="claude"], .turn[author^="agent"] {border-left-color: #d99b2b;}
  details.tool-call {margin: .6rem 0; font-size: 13px;}
  details.tool-call > summary {cursor: pointer; color: #7a8ba6; font-size: 12px;
        font-family: monospace;}
  details.tool-call[open] {border-left: 2px solid #f0f2f6; padding-left: .8rem;}
  #toast {position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
        background: #1a1a1a; color: #fff; padding: .5rem 1rem; border-radius: 6px;
        font: 13px monospace; opacity: 0; transition: opacity .15s;
        pointer-events: none; max-width: 90vw; overflow: hidden;}
  #toast.show {opacity: 1;}
"""

SCRIPT = """
// Tool traffic is the bulk of an imported session and almost none of its value.
// Fold it: the whole transcript stays in the page and stays addressable, but
// what you read by default is the conversation.
document.querySelectorAll('div.tool-call').forEach(function (div) {
  const d = document.createElement('details');
  d.className = 'tool-call';
  const s = document.createElement('summary');
  const first = div.querySelector('p,pre,li');
  s.textContent = '⊞ ' + ((first && first.textContent.trim().slice(0, 72)) || 'tool call');
  d.appendChild(s);
  while (div.firstChild) d.appendChild(div.firstChild);
  div.replaceWith(d);
});

// A heading's id lands on the wrapping <section>. Move it to the heading so the
// heading is one block, and mark the section as that block's subtree container.
document.querySelectorAll('section[data-hash]').forEach(function (sec) {
  const h = sec.querySelector('h1,h2,h3,h4,h5,h6');
  if (!h) return;
  h.id = sec.id; h.dataset.hash = sec.dataset.hash;
  if (sec.hasAttribute('data-subtree')) h.dataset.subtree = '1';
  sec.removeAttribute('id'); sec.removeAttribute('data-hash');
  sec.removeAttribute('data-subtree');
  sec.dataset.subtreeFor = h.id;
});
document.querySelectorAll('li > p[data-hash]').forEach(function (p) {
  p.parentElement.dataset.subtreeFor = p.id;
});

let current = null, shift = false;
function paint() {
  document.querySelectorAll('.hl,.hl-sub').forEach(function (n) {
    n.classList.remove('hl', 'hl-sub');
  });
  if (!current) return;
  current.classList.add('hl');
  if (shift && current.hasAttribute('data-subtree')) {
    const box = document.querySelector('[data-subtree-for="' + current.id + '"]');
    if (box) box.classList.add('hl-sub');
  }
}
// closest() stops at the first match walking up — the smallest containing block.
document.addEventListener('mousemove', function (e) {
  const el = e.target.closest('[data-hash]');
  if (el !== current) { current = el; paint(); }
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Shift' && !shift) { shift = true; paint(); }
});
document.addEventListener('keyup', function (e) {
  if (e.key === 'Shift') { shift = false; paint(); }
});
document.addEventListener('click', function (e) {
  const el = e.target.closest('[data-hash]');
  if (!el) return;
  const sub = e.shiftKey && el.hasAttribute('data-subtree') ? '+++' : '';
  // No version pin: conversation blocks are immutable, so the handle already
  // pins the content. Artifacts are mutable and will copy '@' + hash.
  const ref = '{#' + el.id + sub + '}';
  navigator.clipboard.writeText(ref).then(function () {
    const t = document.getElementById('toast');
    t.textContent = ref;
    t.classList.add('show');
    clearTimeout(window._tt);
    window._tt = setTimeout(function () { t.classList.remove('show'); }, 1800);
  });
});
"""

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{css}</style></head><body>
<nav><a href="{home}">← all notes</a></nav>
{body}
<div id="toast"></div>
<script>{script}</script></body></html>
"""


def _when(note_id: str) -> str:
    """
    UUIDv7 embeds a millisecond timestamp — no separate date field needed.

    The version nibble is checked. An imported session is named after its own
    log, which is a UUIDv4, and decoding its first 12 hex digits as a timestamp
    produced a date in the year 4527 before this guard existed.
    """
    import datetime
    parts = note_id.split("-")
    if len(parts) != 5 or not parts[2].startswith("7"):
        return ""
    try:
        ms = int(note_id.replace("-", "")[:12], 16)
        return datetime.datetime.fromtimestamp(
            ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ""


def render(store: Store) -> dict:
    notes = load_notes(store)
    backlinks = backlink_index(notes)
    store.site.mkdir(parents=True, exist_ok=True)

    total_blocks = clickable = 0

    for note in notes:
        body = djot_to_html(annotate(note["djot"], note["blocks"]))
        ids_in_html = len(_ID_IN_HTML.findall(body))
        total_blocks += sum(1 for b in note["blocks"] if b.get("id"))
        clickable += ids_in_html

        refs = []
        for b in note["blocks"]:
            for src in backlinks.get(b.get("id") or "", []):
                refs.append(
                    f'<li><a href="{src["note"]["id"]}.html">'
                    f'{html_mod.escape(src["note"]["title"])}</a>'
                    f'{" <em>(subtree)</em>" if src["subtree"] else ""}</li>'
                )
        if refs:
            body += ('<div class="backlinks"><h2>Referenced by</h2><ul>'
                     + "".join(refs) + "</ul></div>")

        (store.site / f"{note['id']}.html").write_text(
            PAGE.format(title=html_mod.escape(note["title"]), css=CSS,
                        script=SCRIPT, body=body, home="index.html"),
            encoding="utf-8")

    def listing(rows):
        out = []
        for n in rows:
            facts = []
            if n["turns"]:
                facts.append(f'{n["turns"]} turns')
            if n["authors"]:
                facts.append(" · ".join(n["authors"]))
            facts.append(f'{len(n["blocks"])} blocks')
            facts.append(f'{n["words"]:,} words'.replace(",", " "))
            when = n["when"]
            out.append(
                f'<li><a href="{n["id"]}.html">'
                f'{html_mod.escape(n["title"]) or n["id"]}</a>'
                f'<span class="meta">{when + " · " if when else ""}'
                f'{" · ".join(facts)}</span></li>')
        return "".join(out)

    convs = [n for n in notes if n["kind"] == "conversation"]
    arts = [n for n in notes if n["kind"] == "artifact"]
    index_body = (f"<h1>{store.root.name}</h1><p>{len(convs)} conversations, "
                  f"{len(arts)} artifacts, {total_blocks} addressable blocks.</p>")
    if convs:
        index_body += ('<p class="kind">Conversations</p>'
                       f'<ul class="noteindex">{listing(list(reversed(convs)))}</ul>')
    if arts:
        index_body += ('<p class="kind">Artifacts</p>'
                       f'<ul class="noteindex">{listing(arts)}</ul>')
    (store.site / "index.html").write_text(
        PAGE.format(title=store.root.name, css=CSS, script=SCRIPT,
                    body=index_body, home="index.html"),
        encoding="utf-8")

    index_mod.write(store, notes)

    return {"conversations": sum(1 for n in notes if n["kind"] == "conversation"),
            "artifacts": sum(1 for n in notes if n["kind"] == "artifact"),
            "blocks": total_blocks, "clickable": clickable,
            "backlinks": len(backlinks)}

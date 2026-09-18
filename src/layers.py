#!/usr/bin/env python3
"""
layers.py — compost layer.

The tool's second writer to graph/ — not the base's. Anything emitting valid
JSONL under graph/ writes records on the same terms; `check` is the gate, not
authorship (docs/decisions.md, "Anything may write records").

Unlike `digest`, which reads bytes nobody has seen before, a layer reads the
base itself and derives new records from what is already there — a citation resolved against every earlier import, not just
the batch it arrived in.

    compost layer                        list what can be built
    compost layer NAME [--by SCHEME]     build it

Bare `compost layer` is static help: the registry of what *can* be built, not
a report on the base. There is no `drop`, no bookkeeping of what has been
built, and no declaration written into the graph — running a builder twice
produces two complete sets of records and removes neither, which is the
governing decision this whole release is built on (docs/roadmap.md).
"""
import re
import uuid
from pathlib import Path

from . import __version__          # NOT `import src`; that fails inside the package
from . import records as R
from . import store as S

# -- concept-map: block -> concept, the first layer that calls a model -----
#
# docs/roadmap.md, "v0.3.0 -- the talks-about layer". Everything below this
# banner and above `BUILDERS` belongs to `compost layer concept-map`.

# Query-time filter, not an import-time one -- digest keeps every block's
# text regardless (CLAUDE.md, "digest everything; filter at query time"),
# and widening this constant reclassifies without re-importing anything.
# Measured 2026-09-15 against the 520-document corpus: with CodeBlock and
# BlockQuote included, 14,298 blocks; without, 12,296 -- exactly the corpus's
# CodeBlock count, and BlockQuote is a no-op either way (0 of 159 carry their
# own text). CodeBlock is excluded on top of that measurement: a code block
# has no prose *about* a topic, so classifying one invites exactly the false
# positive the human's stated preference (false negatives over false
# positives) rules against, and code blocks are the largest blocks in the
# corpus, dominating the size cap while contributing the least judgement.
CLASSIFIABLE = {"Para", "Plain", "ListItem", "Header"}

# Measured 2026-09-15: 8,000 skips 0 of 14,298 corpus blocks (max 2,120,
# p99.9 1,072) -- 7.5x the corpus's own p99.9, ~2,000 estimated tokens (well
# under a third of a typical ~6,800-token batch), and 0.6% of the
# 1,350,840-character block the human's own base really holds. Do not re-pick
# this without a new measurement; see docs/roadmap.md.
SIZE_CAP = 8000

# Measured 2026-09-11 against the human's own notes: batch 100 is
# ~6,800 tokens typically and ~18,500 worst case -- comfortable in any
# current context window. A first-class, reportable parameter
# (`--batch-size`), not a hidden constant: a number that changes the call
# count by 46x between 1 and 100 is the number an operator most needs to see
# before committing (docs/roadmap.md, "batching is not an optimisation").
DEFAULT_BATCH_SIZE = 100

# Named in the prompt's own topic list and in every fixture response. Change
# this and the canned fixtures under tests/fixtures/concept-map/ change with
# it (tests/prompt-0.3.0.md).
ABSTAIN_LABEL = "none of these"

CONCEPT_MAP_LAYER = "concept-map"

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "concept-map.md"


class ConceptMapError(Exception):
    """A refusal specific to `compost layer concept-map`.

    Always means the same thing as every refusal in this tool: nothing was
    written. Raised for a root that is not a concept map, and for a batch
    response that fails one of the three cheap checks (docs/roadmap.md,
    decision 8) -- a short count, an unknown label, or an id nobody sent.
    """


def _concept_map_tree(recs, map_root) -> list:
    """The map's labels and sublabels, each with its grounding description.

    Frontmatter is a guard here, never a discovery mechanism (CLAUDE.md):
    this refuses a root whose `params["meta"]["concept_map"]` is not the
    typed `MetaBool` `true`, rather than going looking for one. A heading is
    a label; a heading nested one level inside it is a sublabel; a Para or
    Plain directly inside either is that concept's grounding description,
    joined if there is more than one. No mechanism beyond `contains`/`next`
    is needed -- v0.2.16 and v0.2.17 already made a heading contain its own
    section.
    """
    g = R.Graph(recs)
    if map_root not in g.nodes:
        raise ConceptMapError(f"{map_root} is not a node in this base")
    n = g.nodes[map_root]
    meta = (n.get("params") or {}).get("meta") or {}
    flag = meta.get("concept_map")
    if not (isinstance(flag, dict) and flag.get("t") == "MetaBool"
            and flag.get("c") is True):
        raise ConceptMapError(
            f"{map_root}: not a concept map -- params.meta.concept_map is "
            f"{flag!r}, not the typed MetaBool `true`. Digest the map with "
            f"`concept_map: true` in its frontmatter, or point --map at the "
            f"right root.")

    def description_of(guid):
        parts = [R.plain_text(g.nodes[k]) for k in g.children(guid)
                 if g.nodes[k]["type"] in ("Para", "Plain")]
        return " ".join(p for p in parts if p).strip()

    concepts = []
    for guid in g.children(map_root):
        if g.nodes[guid]["type"] != "Header":
            continue
        subs = []
        for kg in g.children(guid):
            if g.nodes[kg]["type"] == "Header":
                subs.append({"guid": kg, "label": R.plain_text(g.nodes[kg]),
                             "description": description_of(kg)})
        concepts.append({"guid": guid, "label": R.plain_text(g.nodes[guid]),
                         "description": description_of(guid),
                         "sublabels": subs})
    if not concepts:
        raise ConceptMapError(f"{map_root}: concept map has no labels "
                              f"(no top-level Header)")
    return concepts


def _label_index(concepts: list) -> dict:
    """`"Label"` or `"Label > Sublabel"` -> the Header guid it names.

    Case- and character-exact, matching the prompt's own instruction to
    "use only topics from the list, spelled exactly as given".

    **A repeated name is refused, not merged.** This is a flat dict, so until
    v0.3.0 a second label of the same name overwrote the first and every
    block the model put there was attributed to whichever happened to win --
    silently, and differently depending on document order. Refusing is the
    project default and it is the only honest answer: the map says two
    things are called `Storage` and nothing in the answer format can say
    which one is meant.

    Not a corner case. Measured 2026-09-17 over twelve real Wikipedia
    articles, **14 headings repeat** -- `Definition`, `History`, `Examples`,
    `Properties`. Those are safe *as sublabels*, because a sublabel key is
    qualified by its parent; it is two top-level labels, or two sublabels
    under one parent, that collide.
    """
    idx = {}
    seen: dict[str, str] = {}

    def put(key, guid):
        if key in seen:
            raise ConceptMapError(
                f"the concept map names {key!r} twice ({seen[key]} and "
                f"{guid}). Labels are how the model names a concept, so two "
                f"with one name cannot be told apart -- rename one, or nest "
                f"them under different parents.")
        seen[key] = guid
        idx[key] = guid

    for c in concepts:
        put(c["label"], c["guid"])
        for s in c["sublabels"]:
            put(f"{c['label']} > {s['label']}", s["guid"])
    return idx


def _parent_of(recs) -> dict:
    """`contains` destination -> its source, first edge wins.

    Same construction `records.check()`'s `root_of` uses; kept local here
    rather than exported, since nothing outside this module needs a bare
    parent pointer -- everywhere else reads the tree through `Graph`.
    """
    p = {}
    for e in recs:
        if (e.get("record") == "edge" and e["type"] == "contains"
                and e["destination"] not in p):
            p[e["destination"]] = e["source"]
    return p


def _ancestor_lines(nodes: dict, parent_of: dict, guid: str) -> tuple:
    """The heading/bullet chain above `guid`, root-most first, indented.

    "The block arrives with its ancestor path, rendered as the heading and
    bullet chain above it" (docs/roadmap.md) -- v0.2.16 and v0.2.17 made this
    a single walk, by making a heading contain its own section and a list
    item contain what follows it. Only `Header` and `ListItem` ancestors are
    shown; anything else in between (a `Div`, a `BulletList`) is walked
    through silently. Returned as a tuple, not a list, so two blocks with an
    identical path hash equal and can be grouped in one batch.
    """
    chain = []
    cur = parent_of.get(guid)
    seen = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        n = nodes.get(cur)
        if n is None:
            break
        if n["type"] in ("Header", "ListItem"):
            chain.append(n)
        cur = parent_of.get(cur)
    chain.reverse()
    lines = []
    for depth, n in enumerate(chain):
        text = (R.plain_text(n) or "").strip()
        if text:
            lines.append("  " * depth + text)
    return tuple(lines)


def _excluded_subtrees(recs, *roots) -> set:
    """Every guid under any of `roots`, `roots` themselves included.

    The concept map and the prompt are administrative documents, not
    material to classify -- their own headings and grounding prose would
    otherwise show up as fragments to be filed under themselves.
    """
    g = R.Graph(recs)
    out = set()

    def walk(guid):
        if guid in out:
            return
        out.add(guid)
        for k in g.children(guid):
            walk(k)

    for r in roots:
        if r:
            walk(r)
    return out


def _collect_fragments(recs, exclude: set) -> tuple:
    """Every classifiable, non-empty, in-cap block outside `exclude`.

    Returns `(fragments, oversize)`. A fragment is
    `{"guid", "text", "path"}"`; `oversize` is the guids skipped for being
    over `SIZE_CAP` -- reported, never truncated (guarantee 10). Walked in
    one deterministic order (sorted roots, then `next` order within each) so
    that batching -- and therefore which run id lands on which block -- does
    not depend on `graph/*.jsonl` load order, the same standing promise
    `Store.load()` already makes for everything else.
    """
    g = R.Graph(recs)
    nodes = g.nodes
    parent_of = _parent_of(recs)
    fragments, oversize = [], []
    roots = sorted(k for k, n in nodes.items()
                   if n["type"] in R.ROOT_TYPES and k not in exclude)

    def walk(guid):
        n = nodes[guid]
        if guid not in exclude and n["type"] in CLASSIFIABLE:
            text = (R.plain_text(n) or "").strip()
            if text:
                if len(text) > SIZE_CAP:
                    oversize.append(guid)
                else:
                    fragments.append({
                        "guid": guid, "text": text,
                        "path": _ancestor_lines(nodes, parent_of, guid)})
        for k in g.children(guid):
            walk(k)

    for r in roots:
        walk(r)
    return fragments, oversize


def _group_by_path(fragments: list) -> list:
    """Fragments sharing one ancestor path, in first-seen order.

    "Siblings batched together share one path, so a chain is sent once per
    group rather than once per fragment" -- this is the grouping that makes
    that true; `_build_user_prompt` sends the path once per group below.
    """
    groups: dict[tuple, list] = {}
    order: list[tuple] = []
    for f in fragments:
        if f["path"] not in groups:
            groups[f["path"]] = []
            order.append(f["path"])
        groups[f["path"]].append(f)
    return [(p, groups[p]) for p in order]


def _make_batches(groups: list, batch_size: int) -> list:
    """Pack path-groups into batches of at most `batch_size` fragments.

    A group is split only when it is larger than `batch_size` on its own.
    Splitting costs one repeat of that group's ancestor path per extra chunk,
    which is the cost this grouping exists to avoid -- but an unbounded call
    is worse, and until v0.3.0 that is what happened.

    **`batch_size` used to be a hint, not a bound.** The earlier version never
    split a group at all, so a single large group became one oversized batch.
    Its docstring claimed "nothing in any measured material reaches that
    case", and that was false when written: measured 2026-09-17, the test
    corpus holds one path-group of **1,140** fragments, and every fragment
    with no ancestor path shares the empty path, so context-free material
    collapses into one group of everything. A 948-fragment call made during
    that measurement returned 1,580 answer lines for 948 fragments and took
    the whole run down with it.
    """
    groups = [(path, frags[i:i + batch_size])
              for path, frags in groups
              for i in range(0, len(frags), batch_size)]
    batches, cur, cur_n = [], [], 0
    for path, frags in groups:
        if cur and cur_n + len(frags) > batch_size:
            batches.append(cur)
            cur, cur_n = [], 0
        cur.append((path, frags))
        cur_n += len(frags)
    if cur:
        batches.append(cur)
    return batches


def _load_prompt_sections(text: str) -> tuple:
    """The fenced code block under each `## Heading` in the prompt file, plus
    its frontmatter `version`.

    Reads the prompt's literal text rather than parsing it through pandoc:
    what is wanted here is the exact string to send a model, not a citable
    tree. `prompts/concept-map.md` is read from the checkout
    (`PROMPT_PATH`, resolved from `__file__` so it works from any cwd,
    including the throwaway bases this project's own CLAUDE.md requires
    every writing command run inside) -- never from the ingested document's
    own text, since a real run additionally requires the *already-ingested*
    revision via `--prompt=GUID`, whose only job is to be the audit trail
    named in "The records this mints", not the source of the words sent.
    """
    sections = {}
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        heading, body = m.group(1).strip(), m.group(2)
        code = re.search(r"```\n(.*?)```", body, re.S)
        if code:
            sections[heading] = code.group(1)
    version_m = re.search(r"^version:\s*(\S+)", text, re.M)
    return sections, (version_m.group(1) if version_m else "unknown")


def _build_system_prompt(sections: dict, concepts: list) -> str:
    lines = []
    for c in concepts:
        line = f"- {c['label']}"
        if c["description"]:
            line += f" — {c['description']}"
        lines.append(line)
        for s in c["sublabels"]:
            sline = f"  - {s['label']}"
            if s["description"]:
                sline += f" — {s['description']}"
            lines.append(sline)
    lines.append(f"- {ABSTAIN_LABEL} — none of the topics above fit "
                 f"this fragment")
    topics = "TOPICS\n\n" + "\n".join(lines)
    system = sections.get("System", "").strip().replace(
        "{{ABSTAIN_LABEL}}", ABSTAIN_LABEL)
    answer = sections.get("The answer", "").strip().replace(
        "{{ABSTAIN_LABEL}}", ABSTAIN_LABEL)
    return f"{system}\n\n{topics}\n\n{answer}"


def _build_user_prompt(batch: list, id_of: dict) -> str:
    parts = []
    for path, frags in batch:
        ctx = "\n".join(path) if path else "(no ancestor context)"
        frag_lines = "\n".join(f"[{id_of[f['guid']]}] {f['text']}"
                               for f in frags)
        parts.append(f"CONTEXT\n{ctx}\n\nFRAGMENTS\n{frag_lines}")
    return "\n\n".join(parts)


_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.+?)\s*$")


def _parse_response(text: str, sent_ids: list, label_index: dict) -> list:
    """The three cheap checks (docs/roadmap.md, decision 8), in order: the
    count matches, every label is one the map names, every id was sent.
    Raises `ConceptMapError` -- loudly, and before anything is written --
    the instant any one of them fails."""
    parsed = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if m:
            parsed.append((int(m.group(1)), m.group(2).strip()))
    if len(parsed) != len(sent_ids):
        raise ConceptMapError(
            f"batch response has {len(parsed)} lines, expected "
            f"{len(sent_ids)} -- one per fragment sent")
    sent = set(sent_ids)
    for bid, label in parsed:
        if label != ABSTAIN_LABEL and label not in label_index:
            raise ConceptMapError(
                f"batch response names label {label!r} for id {bid}, which "
                f"is not in the concept map")
        if bid not in sent:
            raise ConceptMapError(
                f"batch response names id {bid}, which was not sent in "
                f"this batch")
    return parsed


def plan_concept_map(st: S.Store, map_root: str, prompt_root: str | None,
                      batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Everything about a run that is deterministic and free: the concept
    tree, the fragments, the batches. Shared by `--cost-calculation` and the
    real run, so the two can never silently plan differently."""
    recs, _ = st.load()
    concepts = _concept_map_tree(recs, map_root)
    exclude = _excluded_subtrees(recs, map_root, prompt_root)
    fragments, oversize = _collect_fragments(recs, exclude)
    groups = _group_by_path(fragments)
    batches = _make_batches(groups, batch_size)
    return {"recs": recs, "concepts": concepts, "fragments": fragments,
            "oversize": oversize, "batches": batches}


def cost_calculation(st: S.Store, map_root: str, prompt_root: str | None = None,
                      model: str | None = None,
                      batch_size: int = DEFAULT_BATCH_SIZE) -> str:
    """`--cost-calculation`. No network call, with or without `model` --
    guarantee 1. Every exact number (blocks, characters, calls) is reported
    as exact; every estimated one (tokens, price) says so in the same line
    it appears on -- guarantee 4.

    `prompt_root` is optional here, unlike on a real run: this only affects
    whether an already-ingested prompt document's own blocks are excluded
    from the projected count, so it can be estimated before a prompt has
    ever been digested at all. Omitting it very slightly over-counts on a
    base that already carries one.
    """
    from . import llm as LLM
    plan = plan_concept_map(st, map_root, prompt_root, batch_size)
    concepts, fragments = plan["concepts"], plan["fragments"]
    oversize, batches = plan["oversize"], plan["batches"]
    total = len(fragments) + len(oversize)
    total_chars = sum(len(f["text"]) for f in fragments)

    sections, _ = _load_prompt_sections(
        PROMPT_PATH.read_text(encoding="utf-8"))
    system_prompt = _build_system_prompt(sections, concepts)
    system_tokens = LLM.estimate_tokens(system_prompt)
    input_tokens = 0
    for batch in batches:
        id_of, nid = {}, 1
        for _, frags in batch:
            for f in frags:
                id_of[f["guid"]] = nid
                nid += 1
        input_tokens += system_tokens + LLM.estimate_tokens(
            _build_user_prompt(batch, id_of))

    lines = [
        f"{len(fragments)} of {total} classifiable blocks would be sent "
        f"({len(oversize)} skipped over the {SIZE_CAP:,}-character cap)",
        f"{total_chars:,} characters of block text (exact)",
        f"{len(batches)} calls at batch size {batch_size} (exact)",
        f"~{input_tokens:,} input tokens total, including the topic list "
        f"resent with every call (estimate -- no offline exact tokenizer "
        f"exists for the model families this project targets)",
    ]
    if model:
        price = LLM.PRICE_TABLE.get(model)
        if price is None:
            lines.append(
                f"no local price for {model!r} -- --cost-calculation makes "
                f"no network call, so only a model in llm.PRICE_TABLE can "
                f"be priced")
        else:
            cost = input_tokens / 1_000_000 * price
            lines.append(f"~${cost:.4f} at ${price}/M input tokens for "
                        f"{model} (estimate)")
    return "\n".join(f"  {l}" for l in lines)


def build_concept_map(st: S.Store, map_root: str, prompt_root: str, ask,
                       model: str, batch_size: int = DEFAULT_BATCH_SIZE
                       ) -> dict:
    """One run: one `prov:Activity`, one abstention node, classifying
    against one map. `ask` is `(system, user, model) -> str`, injected --
    the suites never call `llm.ask` (guarantee 2). Raises before writing
    anything on any failure (`ConceptMapError` or whatever `ask` raises) --
    "a failed run writes nothing at all" (guarantee 6): every record this
    mints lives only in the returned dict, and nothing touches `graph/`
    until every batch in the plan has answered cleanly.
    """
    plan = plan_concept_map(st, map_root, prompt_root, batch_size)
    concepts, fragments = plan["concepts"], plan["fragments"]
    oversize, batches = plan["oversize"], plan["batches"]
    label_index = _label_index(concepts)

    sections, prompt_version = _load_prompt_sections(
        PROMPT_PATH.read_text(encoding="utf-8"))
    system_prompt = _build_system_prompt(sections, concepts)

    b = R.Builder()
    run = _entity(b, "concept_run",
                  {"model": model, "batch_size": batch_size,
                   "prompt_version": prompt_version})
    abstention = _entity(b, "abstention")
    b.edge("used", run, map_root, CONCEPT_MAP_LAYER)
    b.edge("used", run, prompt_root, CONCEPT_MAP_LAYER)

    next_id, n_abstain = 1, 0
    for batch in batches:
        id_of = {}
        for _, frags in batch:
            for f in frags:
                id_of[f["guid"]] = next_id
                next_id += 1
        raw = ask(system_prompt, _build_user_prompt(batch, id_of), model)
        parsed = _parse_response(raw, list(id_of.values()), label_index)
        by_id = dict(parsed)
        for _, frags in batch:
            for f in frags:
                label = by_id[id_of[f["guid"]]]
                if label == ABSTAIN_LABEL:
                    target = abstention
                    n_abstain += 1
                else:
                    target = label_index[label]
                b.edge("talks_about", f["guid"], target, CONCEPT_MAP_LAYER,
                      primary=True, run=run)

    R.stamp_hashes(b.records)
    return {"run": run, "records": b.records, "classified": len(fragments),
            "skipped_oversize": len(oversize), "batches": len(batches),
            "abstained": n_abstain}


def _entity(b, type_, params=None):
    """`b.node()`, plus provenance as top-level keys, never inside `params`.

    Only `alias` and `unresolved_citation` need this today. Both carry
    `record_hash`/`record_subtree_hash` like every other node since v0.2.13
    (they carried no hash at all before that), and that hash's input is
    `canonical([type, params, content])` — so it stays blind to whatever else
    a record carries. Putting created_at and tool_version in `params` would
    work for these two but set a precedent that breaks the first time a node
    type whose hash genuinely needs to see top-level fields comes along.
    Decided once, here, while it is free — general node types keep
    `Builder.node()`'s existing shape, since the grammar (record-grammar.md
    §2) already gives nodes no provenance fields and this release does not
    extend that.
    """
    guid = b.node(type_, params)
    n = b.records[-1]
    n["created_at"], n["tool_version"] = R._now(), __version__
    return guid


def _citation(recs, name, by):
    """Citation edges, plus a placeholder for every target that is not here.

    An unresolved target cannot become an edge — a dangling endpoint fails
    `check` and takes the whole graph down. Before this it had nowhere to live
    at all: not in the text, not in the graph, only in terminal output. Now the
    absence is a record.
    """
    b = R.Builder()
    edges, unresolved = R.citation_edges(recs)
    for e in edges:
        # schema_version is NOT optional here. citation_edges builds raw dict
        # literals rather than going through Builder.edge(), so nothing has
        # added it — and "required on write" would be violated by the very
        # release that introduces it.
        e["schema_version"] = R.SCHEMA_VERSION
        e["layer"], e["by"] = name, by
        e["created_at"], e["tool_version"] = R._now(), __version__
        e["record_hash"] = R.edge_hash(e)

    # One alias and one placeholder per *distinct* value in this build. Two
    # citations of the same missing handle share one placeholder.
    seen = {}
    for value, source in unresolved:
        if value not in seen:
            ph = _entity(b, "unresolved_citation")
            al = _entity(b, "alias", {"value": value, "scheme": by})
            b.edge("names", al, ph, name, by=by)
            seen[value] = ph
        b.edge("cites", source, seen[value], name, by=by)
    # A layer is a writer like any other, so the nodes it mints — here,
    # `unresolved_citation` and `alias` placeholders — get folded the same
    # way `digest` folds a document. Both are UNCONTAINED, so both are leaves:
    # a whole-graph walk is not needed, `b.records` alone is the tree.
    R.stamp_hashes(b.records)
    return {"cites": len(edges) + sum(1 for _ in unresolved),
            "placeholders": len(seen),
            "records": edges + b.records,
            "unresolved": sorted(seen),
            "ambiguous": {}}


def _alias_targets(recs, scheme) -> dict:
    """value -> the real nodes its aliases name. Placeholders excluded.

    **The rule that keeps this linear.** After one build with no dictionary
    present, every legacy handle already has an `alias` naming an
    `unresolved_citation`. A second build looking aliases up by value would
    find those beside the real target, and each pre-dictionary build would add
    another candidate — growth quadratic in build count rather than linear, and
    every handle permanently ambiguous. So a `names` edge whose destination is
    a placeholder is not followed. The placeholder itself is never retracted;
    it just stops being an answer.
    """
    placeholders = {r["guid"] for r in recs if r["record"] == "node"
                    and r["type"] == "unresolved_citation"}
    aliases = {r["guid"]: (r.get("params") or {}).get("value")
               for r in recs if r["record"] == "node" and r["type"] == "alias"
               and (r.get("params") or {}).get("scheme") == scheme}
    out: dict[str, set] = {}
    for e in recs:
        if e["record"] != "edge" or e["type"] != "names":
            continue
        value = aliases.get(e["source"])
        if value is None or e["destination"] in placeholders:
            continue
        out.setdefault(value, set()).add(e["destination"])
    return out


def _kg8hex(recs, name, by):
    """v0.1 `{#8hex}` citations, resolved through the alias dictionary.

    The second customer of v0.2.4's naming machinery, and the first scheme
    whose placeholders can actually resolve later: a `uuid-link` target is
    absent because the document is not in the base, but a `kg-8hex` target is
    absent because the *dictionary* is not, and the dictionary arrives from
    outside. Build before it lands and every handle gets a placeholder; add the
    file, rebuild, and the same handles mint real edges. Nothing is retracted —
    the old placeholder stays as the record of a moment when it did not resolve.

    Nothing here rewrites the corpus. The v0.1 syntax stays exactly as written,
    on disk and at render time; what this adds is a way to look it up.
    """
    b = R.Builder()
    targets = _alias_targets(recs, by)

    n_cites = 0
    ambiguous: dict[str, int] = {}
    unresolved: list[tuple[str, str]] = []
    for handle, source in R.legacy_handle_refs(recs):
        found = targets.get(handle) or set()
        if len(found) == 1:
            # Straight through Builder.edge, which is where schema_version,
            # created_at, tool_version and record_hash already live. The
            # uuid-link path decorates raw dicts only because citation_edges
            # predates all four.
            b.edge("cites", source, next(iter(found)), name, by=by)
            n_cites += 1
        elif found:
            ambiguous[handle] = len(found)   # mint nothing; say so instead
        else:
            unresolved.append((handle, source))

    seen: dict[str, str] = {}
    for value, source in unresolved:
        if value not in seen:
            ph = _entity(b, "unresolved_citation")
            al = _entity(b, "alias", {"value": value, "scheme": by})
            b.edge("names", al, ph, name, by=by)
            seen[value] = ph
        b.edge("cites", source, seen[value], name, by=by)
        n_cites += 1

    R.stamp_hashes(b.records)
    return {"cites": n_cites, "placeholders": len(seen),
            "records": b.records, "unresolved": sorted(seen),
            "ambiguous": ambiguous}


# name -> {by -> builder}. Named the way routes are named, and for the same
# reason: what produced a record is written down, never inferred.
# Defined AFTER _citation — a module-level dict that names a function defined
# below it raises NameError at import time, and the module would not load.
#
# `concept-map` is the odd one out: it is registered here so
# `"concept-map" in BUILDERS` is true and bare `compost layer` lists it, but
# it takes `--map=GUID` (and `--prompt=GUID`, `--cost-calculation`,
# `--model=`, `--batch-size=`) rather than `--by=SCHEME` — the first builder
# that takes an argument naming material already in the base (decision 3,
# 2026-09-11). `main()` special-cases it before the `--by` parsing below ever
# runs; the `None` value here is never called through.
BUILDERS = {
    "citation": {"uuid-link": _citation, "kg-8hex": _kg8hex},
    "concept-map": {"map": None},
}

# The default has to be *named*, not "the only one there is". Until v0.2.5
# `citation` had a single scheme and bare `compost layer citation` fell through
# to it; adding a second would have turned that into "--by is required" and
# broken every documented invocation. It also matters which one wins: the
# legacy scheme reads prose for eight hex characters, and a conversation that
# says in words "handles look like {#a3f2b1c4}" mints a real edge if that
# string is also a real handle. Nothing structural excludes it, so kg-8hex
# stays opt-in and is never what you get by not choosing.
DEFAULT_BY = {
    "citation": "uuid-link",
}


def build(st, name: str, by: str) -> dict:
    """Generate a layer. Reads the base; writes one new file. Nothing else.

    This does NOT look at what a previous run wrote. Running it twice produces
    two complete sets of records and removes neither. That is deliberate: see
    docs/roadmap.md, "the tool does not hold your hand".
    """
    recs, _ = st.load()
    r = BUILDERS[name][by](recs, name, by)
    st.write(f"{uuid.uuid4()}.jsonl", r["records"])
    return r


def _main_concept_map(st: S.Store, opts: list) -> int:
    """`compost layer concept-map --map=GUID [...]`.

    Parses its own options rather than sharing `main()`'s `--by` loop,
    because it takes a different shape of argument entirely — a root guid,
    not a scheme name (decision 3, 2026-09-11).
    """
    map_guid = prompt_guid = model = None
    batch_size = DEFAULT_BATCH_SIZE
    cost_calc = False
    i = 0
    while i < len(opts):
        a = opts[i]
        if a == "--cost-calculation":
            cost_calc = True
            i += 1
        elif a.startswith("--map="):
            map_guid = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--prompt="):
            prompt_guid = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--model="):
            model = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--batch-size="):
            try:
                batch_size = int(a.split("=", 1)[1])
            except ValueError:
                print(f"--batch-size wants an integer, got {a!r}")
                return 2
            i += 1
        else:
            print(f"unknown option {a!r}")
            return 2

    if not map_guid:
        print("--map=GUID is required (a document root with "
              "concept_map: true in its frontmatter)")
        return 2

    try:
        if cost_calc:
            print(cost_calculation(st, map_guid, prompt_root=prompt_guid,
                                    model=model, batch_size=batch_size))
            return 0

        if not prompt_guid:
            # docs/roadmap.md names a `used` edge from the run to a prompt
            # root but never specifies how the CLI learns which document
            # that is. --map is explicit for the same reason; --prompt is
            # made explicit here too, rather than guessed by filename or
            # auto-ingested as a side effect of a run that might still fail
            # — see this release's report, "what I disagreed with".
            print("--prompt=GUID is required for a real run: digest "
                  "prompts/concept-map.md as `--as=notes "
                  "--mutability=mutable` once, and pass its root here")
            return 2

        from . import llm as LLM
        result = build_concept_map(st, map_guid, prompt_guid, ask=LLM.ask,
                                    model=model or LLM.MODEL,
                                    batch_size=batch_size)
    except ConceptMapError as e:
        print(f"refusing: {e}")
        return 1
    except Exception as e:
        print(f"concept-map run failed, nothing written: {e}")
        return 1

    st.write(f"{result['run']}.jsonl", result["records"])
    total = result["classified"] + result["skipped_oversize"]
    print(f"  run {result['run']}")
    print(f"  {result['classified']:,} of {total:,} blocks classified, "
          f"{result['skipped_oversize']} skipped over the "
          f"{SIZE_CAP:,}-character cap")
    print(f"  {result['batches']} batches, {result['abstained']} of "
          f"{result['classified']} abstained ({ABSTAIN_LABEL!r})")
    return 0


def main(argv):
    """Called as `layers.main(argv[1:])` from `cli.main`, so `argv[0]` is the
    subcommand name itself — `"layer"` — exactly like `views.main`. NAME and
    `--by` are parsed from `argv[1:]`."""
    try:
        st = S.Store.find()
    except S.NotABase as e:
        print(e)
        return 1

    rest = argv[1:]
    if not rest:
        print("what can be built:")
        for name, bys in BUILDERS.items():
            if name == "concept-map":
                print(f"  {name} (--map=GUID [--prompt=GUID] "
                      f"[--cost-calculation] [--model=NAME] "
                      f"[--batch-size=N])")
            else:
                print(f"  {name} ({', '.join(bys)})")
        return 0

    name = rest[0]
    if name not in BUILDERS:
        print(f"unknown layer {name!r}")
        print("what can be built:")
        for n, bys in BUILDERS.items():
            print(f"  {n} ({', '.join(bys)})")
        return 2

    if name == "concept-map":
        return _main_concept_map(st, rest[1:])

    bys = BUILDERS[name]
    by = None
    opts = rest[1:]
    i = 0
    while i < len(opts):
        a = opts[i]
        if a == "--by":
            if i + 1 >= len(opts):
                print("--by needs a scheme")
                return 2
            by = opts[i + 1]
            i += 2
        elif a.startswith("--by="):
            by = a.split("=", 1)[1]
            i += 1
        else:
            print(f"unknown option {a!r}")
            return 2

    if by is None:
        by = DEFAULT_BY.get(name)
        if by is None:
            print(f"--by is required for {name!r}; choices: {', '.join(bys)}")
            return 2
    if by not in bys:
        print(f"unknown scheme {by!r} for {name!r}; choices: {', '.join(bys)}")
        return 2

    r = build(st, name, by)
    n_unresolved = len(r["unresolved"])
    n_placeholders = r["placeholders"]
    print(f"  {r['cites']:,} cites edges  |  {n_unresolved} unresolved -> "
          f"{n_placeholders} placeholder{'' if n_placeholders == 1 else 's'}")
    for v in r["unresolved"][:10]:
        print(f"    {v}")
    if n_unresolved > 10:
        print(f"    … and {n_unresolved - 10} more")

    # Ambiguity is not an error and does not stop the build: the resolvable
    # handles still mint edges. It is reported because nothing else would say
    # so — an ambiguous handle mints no record at all, so silence would look
    # exactly like a handle nobody cited.
    if r["ambiguous"]:
        print(f"  {len(r['ambiguous'])} ambiguous, minted nothing:")
        for h, count in sorted(r["ambiguous"].items())[:10]:
            print(f"    {h} -> {count} distinct targets")
        if len(r["ambiguous"]) > 10:
            print(f"    … and {len(r['ambiguous']) - 10} more")
    return 0

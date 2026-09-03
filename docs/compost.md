# compost

*A local-first knowledge base where a conversation and a document are the same
kind of thing, and every paragraph has a name.*

**Status: v0.2.11 draft.** This document is being assembled from `CLAUDE.md`,
`decisions.md`, `record-format.md`, `record-grammar.md` and the roadmap. Where
it disagrees with the code, the code is right and this is a bug. Sections marked
*(to write)* are outlined and not yet drafted.

---

## Abstract

compost turns conversations and notes into an addressable graph. Every
paragraph, list item, tool call and answer becomes a node with a permanent
identifier, so a person and an agent can point at the same sentence and disagree
about it. Nothing is summarised away: the conversation that produced a decision
stays readable beside the decision.

It is built for one situation — running several projects at once, and needing to
get back into one cheaply after weeks away. The design follows from that: keep
everything, decide later, and make every claim checkable.

> **Not yet true, and listed as v0.2.11 work:** this is *intended* to be the
> README's opening verbatim, with a test asserting the two match so neither can
> drift. Today the README says something close but not identical. The claim is
> written here in the form it will take, and marked, rather than asserted early
> — which is the failure mode this whole document exists to reduce.

---

## 1. The shape

Three parts, and the middle one is the point.

```
  digestors                    the records                    renderers
  ─────────                    ───────────                    ─────────
  --as=notes              ┐
  --as=pandoc-ast         ├──►  nodes + edges   ──►  views/default-djot   (agents)
  --as=claude-code-…      ┘     JSONL, flat          views/default-html   (people)
                                                     views/default-md     (README, …)
        ▲                            │                        ▲
        │                            ▼                        │
    storage/                  compost layer              graphviz/
   (immutable bytes)      (derives more records)      (drawn, then embedded)
```

**This is a waist.** Everything entering becomes nodes and edges; everything
leaving is generated from nodes and edges and from nothing else. A missing edge
is a visibly broken page the same day, not a silent wrong answer months later.

The waist is what makes the rest of the design possible to state at all. Any
number of digestors, any number of renderers, and neither has to know about the
other.

## 2. Principles

**These are not invariants, and the distinction matters.**

An **invariant** is a property of the graph that a program checks. `check()`
makes **ten** assertions and refuses a view when any fails. You cannot violate
an invariant and ship; you get an error. (Ten assertions, twelve call sites —
the parent-count rule reports three different ways. Counting `problems.append`
gives twelve and is the wrong number; `docs/record-grammar.md` §5 enumerates the
ten, and `tests/test_grammar.py` checks that enumeration against the code.)

A **principle** is a rule about how the system is built, enforced by attention.
You can violate one and everything still passes. Each of the fifteen below was
learned by violating it — several more than once — and each carries the incident
that produced it. Python's own list calls itself *aphorisms* (`import this`);
this is the same kind of thing. Calling them invariants would make them sound
stronger than they are, and the whole reason to write them down is that nothing
enforces them.

**Fifteen principles. Ten invariants. They are different lists, they live in
different documents, and only one of them is enforced by a program.**

### On what enters

**1. Digest everything the file holds; filter at query time, never at import.**
A field dropped while reading is dropped once, silently, and every base built
afterwards is missing it with nothing to show it was ever there. Filtering later
is free and reversible; filtering at import is neither. *Held by property:*
`records_to_session(session_to_records(lines)) == lines`, exact. *The incident:*
an audit found the transcript importer dropping 46% of a real transcript's lines
and seventeen log-line keys.

**2. Nothing about ingestion is inferred from a file extension.** The route is
named with `--as` or the command refuses. *The incident:* this was dispatch on
the suffix until v0.2.2, where the fallback was not "markdown" but *anything at
all*.

**3. Sources are immutable, and storage is a blob store.** Every file lands
under a freshly minted `GUID.EXT`; `storage/` never overwrites. The same bytes
may legitimately arrive twice — `digest` reports that and does not resolve it.

**4. Filter only when disk or compute requires it.** The operator's formulation,
and the general form of principle 1. A **view** may filter freely, because it is
a projection rebuilt on every render and its omissions are undone by editing the
projection. An **importer's** omissions are not. So when something should not be
on the page, the answer is always a view-time suppression that leaves the node
addressable.

### On what is stored

**5. Filenames carry no meaning, and load order cannot change the result.**
Graph files are minted uuids; records are concatenated from every matching file;
shuffling them must produce an identical graph. This is what keeps files freely
regroupable and a SQL glob honest.

**6. `graph/` is flat, by rule.** A subdirectory is meaning. `Store.write`
refuses one. *The incident:* subdirectories were permitted, read, and used by
nothing — until a read-only SQL view over the same directory had to glob it too,
and a file visible to one reader and not the other would have been a silent
disagreement about what the graph is.

**7. Guids are UUIDv4, everywhere, always. Nothing derives a guid from
content.** A content hash with a uuid-shaped output resolves duplicates at write
time by construction, which is the thing forbidden everywhere else. *Measured:*
content-addressed naming would merge 633 empty table cells into one node, and
every identical `Yes.` across every document. Identity is positional; equality
is content-derived; conflating them merges things that are only accidentally
alike.

**8. A handle is the whole guid.** A prefix is not a shorter handle. *The
incident:* a prefix resolver was written and removed — it resolved in the graph
while the HTML view emitted the href verbatim, so a shortened citation resolved
for a tool and was a dead anchor for a person clicking it.

**9. Anything may write records; `check` is the gate.** The records `digest`
writes are ordinary Python, and so are a script's, a migration's, an agent's.
`Store.load()` does not care who wrote a file. *Stated honestly:* this is a
trust model and the trust is currently unearned — `check` verifies structure,
not that a node's `type` is a known one, so a typo'd `"alais"` passes.

**10. Duplicates accumulate, on purpose.** Nothing is deduplicated,
no consistency is guaranteed, and no dependency is managed. *The incident:* an
architecture review of a design that *did* try to stay consistent found four
states a base could enter and never leave. Removing the goal removed all four.

### On what leaves

**11. A view of a broken graph is worse than no view.** `render` refuses when
`check` fails, and says so.

**12. The round-trip property is the acceptance test.** If
`records_to_ast(ast_to_records(ast)) == ast` fails on any fixture, the change is
wrong regardless of what else passes.

**13. Reconstruction and viewing are different functions.** `records_to_ast`
stays exactly reversible; handles, collapsing and decoration belong in the view.

**14. Never scan raw file text for citations.** A citation is a `Link` node, and
reading the parsed content is what makes *"handles inside code blocks are not
citations"* true by construction rather than by rule. *The incident:* violated
three times under the old text-based syntax, and it cost something every time.

**15. Do not repair pandoc's output, and do not tidy its flags.** Three defects
are known and documented; they sit outside the AST-to-AST property on purpose,
and patching them breaks the round-trip by construction. Every flag in the
pandoc invocations — `-smart`, `-attributes`, `-fancy_lists` — prevents a
specific, measured corruption.

### The one about working, not about the system

**Work on `main`, and tag each version.** One developer, no CI, nothing to
isolate from. Branch only for a genuine one-way door. *The incident:* the
standing candidate for a feature branch turned out to be render-time and shipped
on `main` in an afternoon.

## 3. Digestors *(to write)*

Outline: what a route is; the four that exist (`notes`,
`claude-code-transcript`, `pandoc-ast`, `claude-code-response`); that a route
may declare the file it read *names other files*, which is the one place
`digest` reads something it was not handed; that this makes ingestion recursive
and would need a queue if it became asynchronous; and the two-phase rule —
nothing is written until every input has parsed, which is what makes a batch
safe to re-run.

## 4. The records *(to write)*

Outline: node, edge, the `contains` tree and the `next` chain; layers as the
unit of provenance and deletion; `schema_version`; the two hash functions and
why they are not comparable. Much of this is `record-grammar.md`, which is
verified against the code by `tests/test_grammar.py` and keeps that property
wherever it ends up.

## 5. Renderers *(to write)*

Outline: three views from one set of records; that renderers depend on each
other — the HTML view will embed graphviz output, which is why `graphviz/` is a
peer of `views/` and not inside it; and that views are generated and disposable,
so deleting one costs a rebuild.

## 6. The symmetry, which is the thesis

**An agent and a person read the same text.** Not a summary for one and the
source for the other — the same blocks, the same handles, the same graph.

HTML for people because it is pleasant to read and click; markdown and djot for
agents because they carry less distraction; both openable in a browser, so any
claim about what an agent saw is auditable by looking. Both carry a handle on
every citable block, so either can point at a sentence and the other can resolve
it.

Everything else in this document exists to keep that true.

## 7. Decisions *(to write)*

Outline: each significant decision, the principle behind it, and the measurement
that settled it. `decisions.md` loses nothing in the move — where it goes, it
goes whole.

## 8. What this is not

- **Not multi-writer.** Single writer assumed. That assumption licenses most of
  the design and is written down so its removal is a decision rather than a
  discovery.
- **Not a dependency manager.** Nothing infers what must be rebuilt or in what
  order. The operator sequences `digest`, `layer` and `render`.
- **Not consistent.** See principle 10.
- **Not a place to hide personal material.** A base is gitignored and
  machine-local. This repository has had personal material purged from its
  history once, and that is the standard for rewriting history: material that
  should never have been committed, not material that is merely old.

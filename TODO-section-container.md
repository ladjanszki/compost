# TODO — a section container of our own

**Not scheduled. Decide before v0.2.16** — the TA release, renumbered from
v0.2.17 on 2026-09-09 when the ledger left the line. The TA release revises whole trees and
compares them by fold; if sections are going to exist, they should exist before
anything starts folding documents in anger. Nothing before v0.2.16 is blocked by
this.

**The human wants one.** This file exists so that the argument against can be
made properly, and it will need to be a good one.

---

## The observation this exists to settle

Two of the human's weekly braindumps. Each is one `# Braindump` heading followed
by a nested bullet list. Different weeks, different contents, same heading.

Under the fold, the two documents separate cleanly — different `document` roots,
different `BulletList` folds, different `ListItem` subtrees. But **the two
headings do not separate, and neither hash can separate them**, because in our
record model a `Header` has no children at all:

```python
if t == "Header":
    return b.node(t, {"level": c[0], "attr": c[1]}, c[2])   # src/records.py:182
```

Its inlines are `content`; no `b.children` is called. So a `Header`'s subtree
*is* itself, `record_subtree_hash == record_hash`, and "the same heading text"
and "the same section" are the same statement.

That is defensible — the headings genuinely are the same heading — but it means
**the structure a person sees in the document is not in the graph.** "What is
under this heading" is not a subtree walk; it is a scan forward until a heading
of equal or lower level, performed by whoever asks.

## Why pandoc is like this, and why that is not our reason

Pandoc's block list is flat because pandoc's job is to *emit* documents. A
heading is a thing you print, and print order is all a writer needs. That is a
good reason for a document converter and a bad one for a knowledge graph, where
the question asked most often is structural.

Measured, so the next person does not have to:

- **`--section-divs` does not reach the JSON writer.** It is an HTML writer
  option. `pandoc -t json --section-divs` returns a flat `[Header, Para, Header,
  Para]`, unchanged.
- **`pandoc.utils.make_sections` does, via a Lua filter**, and it produces
  exactly what is wanted — nested `Div`s classed `section`, each carrying its
  heading's identifier:

  ```
  Div ['a', ['section'], []]
    Header ; Para
    Div ['b', ['section'], []]
      Header ; Para
  Div ['c', ['section'], []]
  ```

**This matters more than it looks.** It means sectioning would be *pandoc's*
rule applied by pandoc's own code, not a rule we invent and then have to defend
against every markdown edge case — setext headings, headings inside block
quotes, a level-3 that follows a level-1. We would be adopting a definition, not
authoring one.

**One thing changed under it since it was written.** v0.2.14 introduces a
`document` node between a turn and its parsed prose, for delegation. That is a
second tree-shape change, landing *before* this one and independently of it —
so the argument below can no longer say "we only move the tree once". It can
still say the two are unrelated: delegation adds a level inside transcripts,
sections add one inside documents.

## The case for

1. **Structure becomes a subtree.** "Everything under this heading" is
   `g.children(guid)`, not a scan with a level comparison.
2. **A section becomes citable.** The human cites by clicking a block in the
   HTML view. There is currently no handle that means *this section*, and it is
   an obvious thing to want.
3. **`record_subtree_hash` on a section answers "has this section changed."**
   That is the natural unit for TA revisions (v0.2.16) — far more useful than
   "has this document changed," which is almost always yes.
4. **Views get the collapse for free.** Collapsing a section is a tree
   operation once the tree exists.
5. **It costs no new node type.** A section is a `Div` with class `section`,
   which the grammar already has. Nothing in the schema needs a new `$def`.

## The case against — what would have to be true to talk us out

Each of these is a real cost. None has been measured yet; measuring them is what
this TODO asks for.

1. **Every existing base must be re-digested**, and every record's shape and
   hash changes. Re-digesting already mints fresh guids, so citations into an
   old base already break — this is not a *new* class of pain, but it is a full
   re-ingest of everything, at a moment when v0.2.15 exists precisely to stop
   re-ingesting everything.
2. **The AoTA positional prefix property must be re-measured.** §6b's 100.00%
   prefix was measured on flat trees. A pre-order walk of a sectioned tree emits
   the same real blocks in the same order with `Div`s interleaved, so it
   *should* hold — but "should" is how the 88.7% denominator happened.
3. **It adds a Lua filter to the reader pipeline.** `docs/decisions.md` records
   that every flag in the pandoc invocations is load-bearing and measured. A
   filter is a heavier commitment than a flag, it must ship with the package,
   and it must be applied identically on every path that parses markdown —
   including `session.py:_md_blocks`, which parses assistant prose. Applying it
   on one path and not the other would produce two incompatible document shapes
   in one base, which is the worst available outcome.
4. **Section identifiers inherit the header's**, which under our reader
   (`-attributes`) pandoc generates from the heading text and disambiguates
   positionally — `notes`, `notes-1`, `notes-2`. Measured at 0.4% of corpus
   headings, so small, but it puts a positional artifact on a container whose
   whole purpose is to be structural.
5. **Trees get deeper.** `draw`, the HTML view's indentation, and `check`'s
   cycle and parent-count walks all get a longer `contains` chain. Cheap, but
   not free, and `check` runs on every render.

## Two implementations, and only one of them is safe

**Do this:** apply `make_sections` in the **reader**, before `ast_to_records`
ever sees the AST. The records then mirror a sectioned AST exactly, and the
round-trip property is unchanged in form — `records_to_ast(ast_to_records(ast))
== ast` still holds, against the sectioned `ast`. Nothing inside the translation
learns about sections.

**Do not do this:** mint a `section` node type that `records_to_ast` unwraps on
the way out. That puts a non-identity transform inside the one function
`CLAUDE.md` requires to stay exactly reversible, and it is the same mistake as
repairing pandoc's output — a fix that breaks the property by construction.

## What would decide it

- Re-measure the AoTA prefix on sectioned trees. If it is not 100.00%, this
  costs a release and the reason must be understood before proceeding.
- Count how many `.md` sources in the corpus contain more than one heading. If
  most documents are a single flat section, most of the benefit is theoretical.
- Ask whether the human actually wants to cite a *section* handle, or whether
  clicking the heading and meaning "this section" is enough. This is a workflow
  question and it belongs to them.

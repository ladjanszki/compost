All six markdown docs reach a fixed point — but only after three normalization rules, and the flags matter more than the spec assumes. Here's what I'd change.

## Milestone 1 tests the wrong property

`original → AST → original`, compared with `diff`, fails on essentially every real document. On your own `README.md`:

```
< # compost — conversations to an addressable wiki
> # compost --- conversations to an addressable wiki
```

Pandoc's AST deliberately doesn't record surface choices — where you wrapped lines, `*em*` vs `_em_`, setext vs ATX. A byte-diff measures your typing habits, not pandoc's fidelity. You'd conclude pandoc is lossy when it isn't, and the "some formats can't be byte-identical" exemption you were already reaching for is actually the normal case, markdown included.

The property you need is the **AST fixed point**:

```
doc → AST₁ → doc′ → AST₂ ,  assert AST₁ == AST₂
```

That's the one that matters, because the graph stores the AST. It's format-independent, so PDF and HTML need no special pleading — same test, same criterion. And it's achievable: with `-f markdown-smart` and `--wrap=none`, all six of your markdown docs converge, but only after normalizing three things away:

| AST artifact | why it drifts | rule |
|---|---|---|
| `SoftBreak` vs `Space` | where the author hit Enter | → `Space` |
| `AlignDefault` vs `AlignLeft` | table alignment, unset means left | → one value |
| `ColWidth 0.5` → `0.3796…` | writer computes widths from rendered content; re-reading yields different ones | → `ColWidthDefault` |

Without those, README drifts in 72 places. With them, every file is a fixed point on the first pass.

**So the real deliverable of milestone 1 isn't "roundtripping works" — it's the normalization rule set.** That list *is* your ingestion spec: the enumerated set of AST fields that carry surface noise rather than meaning. Every entry is a decision about what compost considers content. Building the corpus first and letting the diffs tell you what to add is the right method; just name the output correctly so you know when you're done.

One asymmetry to keep in view: the fixed-point test catches `AST → doc → AST` loss. It cannot catch `doc → AST` loss — whatever the *reader* discarded before the AST existed. HTML will pass this test brilliantly while pandoc's reader has silently dropped attributes, styles, scripts and comments. Necessary, not sufficient.

## Two facts that change the plan

**Pandoc has no PDF reader.** `pdf` is on the writer list only. Your "for a pdf I don't think it has to be byte-by-byte the same" question doesn't arise — you can't get in at all without a separate extractor. Drop it from milestone 1 rather than discovering it there.

**Djot is a pandoc reader *and* writer** (both lists, pandoc 3.10.1). So djot.js and the `npx` spawn can die today, not at v0.2 — {#2d875ce4} treats that as a consequence of the redesign, but it's available immediately and independently.

## The em dash argument in the base is wrong

{#676da0ab} claims pandoc's AST "holds `—`, `--` and `---` as three distinct correct values." Under default flags it does not — `smart` is on for markdown, and the reader collapses them:

```
input:   em dash — here, three hyphens --- here, two -- here
default: Str "—"    Str "—"      Str "–"      ← all merged
-smart:  Str "—"    Str "---"    Str "--"     ← preserved
```

The loss the base blames on the djot *writer* also exists in the pandoc *reader*, and reader-side loss is unrecoverable — it happens before anything is stored. This doesn't undermine moving to pandoc, but it means `-smart` on every read is load-bearing, not a stylistic flag, and it belongs in the spec as an invariant with a test. Worth correcting in `graph.dj` when you next rewrite it, since that paragraph is currently an argument resting on a false premise.

Related: now that pandoc writes the views too, the djot writer's lossiness returns — but as a *render-time* concern, which by your own rule is free and regenerable. One caveat keeps it from being entirely free: the djot view is what agents read and quote from. Mangled text copied out of a view and resubmitted becomes ingested truth. That's the path by which render-time loss turns into canonization-time loss, and it argues for running the fixed-point check through the djot writer too, not just markdown.

## The question the spec doesn't answer: are inlines nodes?

This is the biggest gap, and it decides whether step 2 is possible at all.

Your node record has `"text":"..."`. If a `Para` node stores only flattened text, **you cannot rebuild the pandoc AST from the graph** — bold, links, code spans and citations are gone. Step 2's roundtrip fails by construction, and `content-hash` over plain text makes `**foo**` and `foo` hash identically. {#ee1ef66d} gestures at this ("a table cell, an image" are nodes) but the spec's record doesn't reflect it.

My recommendation, and it's the same instinct you applied to identifiers — **store the block's pandoc inline array verbatim as nested JSON inside the block node, and defer the question:**

```json
{"record":"node","id":"d826c4dd-…","type":"Para",
 "content":[{"t":"Str","c":"An"},{"t":"Space"},{"t":"Emph","c":[…]}],
 "content_hash":"9935…"}
```

Roundtripping becomes mechanical, the hash covers real structure, and "is a link its own node with its own guid" stays open until a query actually needs it. Keep `text` only as an explicitly derived convenience field for search and display — or drop it and derive it at render. What you must not do is let `text` be the only representation, because that's a one-way conversion, and you don't get to change your mind later.

## Your named open questions

**`this-object`** — I'd push back. The complaint behind it is right (`kind` + `type` + `label` is three words for overlapping ideas) but renaming `kind` doesn't fix the overlap, it just makes the key hyphenated and awkward in every language: `d["this-object"]` everywhere, never `d.kind`. Use **`record`**: `"record":"node"` / `"record":"edge"`. One word, no collision with `type`, no hyphen.

**Casing** — snake_case throughout (`content_hash`), not kebab. JSON keys become Python identifiers constantly in this codebase; kebab forces string subscripting forever. Pick one and let `compost check` enforce it.

**`type: "text-block/paragraph"`** — don't concatenate. You've encoded a 2-tuple in a string that every consumer immediately splits back, and prefix queries become string operations instead of equality. Your own instinct in the edge section — *"the JSON is a nested structure itself so further complicating with `/` notation is a bad idea"* — is correct, and it applies identically to nodes.

The better fix removes the problem instead of naming around it: **use pandoc's own tag names verbatim as `type`** — `Para`, `Header`, `CodeBlock`, `BulletList`. No mapping table, no translation bugs, and the pandoc-types repo becomes your literal schema documentation rather than a reference you can't read Haskell to verify. Compost-native types (`turn`, `toolcall`, `session`, `file`, `document`) stay lowercase, so the two families are distinguishable by convention. `label` disappears entirely, and with it the `/` question. This also directly serves "I think we should support **all** pandoc AST blocks" — you get all of them for free, including the ones neither of us would have listed.

**`layer` + `type` on edges, "JSON-native way?"** — two sibling scalar keys *is* the JSON-native encoding of a two-level taxonomy. `{"layer":"pandoc_ast","type":"next"}` is exactly right; it's the same thing as two columns in a table. The alternative, `{"type":{"pandoc_ast":"next"}}`, is worse — variable key names are hostile to queries, to schema validation, and to every loader you'll write. You already had the right answer; you just doubted it.

**Edges without a guid** — your reasoning holds, and I'd commit to it. Two independent agents asserting the same citation produce byte-identical records that dedupe silently ({#9142929f}); a uuid would turn that convergence into a conflict. An edge whose endpoints or type changed *is* a different edge.

Two conditions make it safe, and both need writing down:

- **Define the hash input precisely** — field order, key sorting, UTF-8, separator, no whitespace. A content hash with an undefined serialization is a time bomb: regenerate it under a different JSON encoder and every edge in the base silently duplicates. This applies to node `content_hash` equally.
- **Call it `id`, not `content-hash`.** On a node, `content_hash` means "hash of the text"; on an edge it would mean "identity". Same name, two meanings — precisely the overlap you objected to in `kind`/`type`/`label`. Let `id` mean identity everywhere, and document that nodes assign it while edges derive it. That's {#53be2b2a}, and it survives your redesign intact.

**UUIDv4 for now** — agreed, and postponing it is the right call. One invariant makes the deferral genuinely reversible: **a uuid may live in an edge, never in stored text.** Handles that appear in immutable prose can't be rewritten later; endpoints inside edges can be remapped freely. Hold that line and swapping in the counter-plus-check-character scheme from {#bc520e2a} stays a migration rather than a rewrite. Note also that a 36-character uuid can't be the thing a human clicks and pastes — so the human-facing handle is a separate concern from node identity from day one, not something the later optimization introduces.

## Directory layout

`.compost/` as marker-plus-root is good, and it solves the real problem you named — being embeddable in another project without littering it.

One thing to weigh: `.compost/graph/` and `.compost/storage/` are committed and precious, `.compost/views/` is generated and disposable, and they'd live side by side in a hidden directory. That invites both an `rm -rf` you can't undo and a `.gitignore` mistake. It also means `rg` and `find` skip your primary corpus by default, and GitHub's UI hides it — for a base whose selling point is being readable, that's a real cost.

Since filenames carry no meaning and nothing there is hand-edited ({#f9b3907c}), hiding `graph/` is defensible. I'd think harder about `storage/`: that's the immutable archival record, the one thing that isn't a projection of something else ({#c1d71cf9}), and hiding it makes it easy to forget it's the most valuable directory in the repo.

## Same repo, not a new one — which you already did

Your instinct to put this in `text-importer/` rather than a fresh repo is right, and I committed it as `cb7ed1b`:

- "No code from the previous version" is a discipline, not a filesystem property. A subdirectory enforces it just as well, and `grep -r "from src" text-importer/` proves it mechanically in a way that "it's in another folder" never does.
- A fresh repo has no corpus — no `compost lookup`, no `{#f9b3907c}` to cite while designing. You'd lose the exact workflow that makes this project worth building, at the moment you most need it.
- Your own hard-won rule is work on `main`, tag each version ({#e3494cbb} plans the old files' deletion as its own commit). A separate repo is a feature branch with extra ceremony.

Two loose ends: the spec still says the directory is called `pandig-text-importer`, and the pandoc-types repo it says was added isn't there — `text-importer/` contains only `spec.md`. Worth deciding how that vendors in (submodule, or a pinned copy with the commit recorded) before it arrives by accident.

**Where I'd start:** the format corpus plus the fixed-point harness, with the normalization rule set as the written output. It's the cheapest thing that produces a real answer, and it settles the inline question empirically — you'll see immediately whether flattening to `text` can survive contact with your own documents.

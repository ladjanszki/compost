# Writing to the base

Short, and worth reading before you change anything.

## The shape

Sources are imported once and kept in `.compost/storage/`. Ingestion turns them
into nodes and edges under `.compost/graph/`, as JSONL. Every view is generated
from those records and from nothing else.

```
compost import FILE...   # markdown by any suffix, transcripts as *.jsonl
compost check            # must report 0 problems
compost render           # views/default-{djot,html,md}
```

## Reading the base

`.compost/graph/**/*.jsonl` is the corpus, one record per line, each saying
whether it is a `node` or an `edge`. Filenames carry no meaning and load order
cannot change the result.

To read it as prose, use `views/default-djot/` — it carries a handle on every
citable block. To cite one, write a link to it:

```
[-](#d826c4dd-eb36-4da9-acab-f6f424a90803)
```

The link text is a single dash by convention; nothing reads it. Any unambiguous
prefix of the guid also resolves.

## Rules

1. **Cite from parsed content, never from raw text.** A citation is a `Link`
   node. A handle appearing inside a code block is not a citation, and the
   format guarantees that only if you read the AST.
2. **Do not hand-edit `.compost/graph/`.** Write through the importer so the
   invariants hold and the records stay canonical.
3. **`check` before `render`, and believe it.** Zero problems or the view is a
   lie.
4. **Add a test with a property, not a snapshot.** Every suite in `tests/`
   states something that must be true and has been made to fail on purpose.
   `tests/test_sabotage.py` is the pattern.
5. **Do not repair pandoc's output.** Three defects are known and documented in
   `docs/decisions.md`; they sit outside the AST-to-AST property on purpose, and
   patching them breaks the round-trip by construction.
6. **Reconstruction and viewing are different functions.** `records_to_ast` must
   stay exactly reversible; anything a view needs — handles, collapsing,
   decoration — belongs in `src/views.py`.

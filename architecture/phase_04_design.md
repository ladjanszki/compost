# Phase 04 — Design Document

## 1. Purpose

This document describes the design for **Phase 04**: converting Markdown documents to Djot via Pandoc and verifying the conversion doesn't lose content that matters.

After Phase 04, the system can ingest real-world Markdown content (Wikipedia, library docs, wiki pages) by converting to Djot first, then running through the verified Phase 02+03 pipeline.

---

## 2. Background

### Separation of concerns

```
pandoc: markdown → djot  (this phase — preprocessing)
djot.js: djot → AST      (Phase 02 — our core parser)
our code: AST → blocks   (Phase 02 — ingestion)
our code: blocks → djot   (Phase 03 — verified renderer)
```

Pandoc is used ONLY as a preprocessor for non-djot source material. It converts markdown to djot, then our djot-native pipeline handles everything else.

### Verification strategy

Two comparisons:

1. **External roundtrip**: `md → html` vs `md → djot → html`. If both produce semantically equivalent HTML, the djot intermediate preserves content. (Same approach as your earlier experiment.)

2. **Internal roundtrip**: `md → djot → blocks → djot`. This confirms the converted djot ingests cleanly through Phase 02+03. If the Phase 03 roundtrip passes on the converted file, we know nothing was lost in ingestion.

---

## 3. Scope

### In scope

- Implement `src/convert/md_to_djot.py` — pandoc wrapper for `markdown → djot`.
- Implement `src/convert/html_roundtrip.py` — HTML comparison for external verification.
- Implement `src/convert/batch_convert.py` — directory-level conversion.
- Support CommonMark, GFM, and pandoc markdown flavors.
- Detect and warn about raw HTML blocks (known lossy case).
- Batch conversion of a directory of `.md` files.
- Integration test: converted files pass the Phase 03 internal roundtrip.

### Out of scope

- Acquiring real Wikipedia content (uses handcrafted fixtures).
- Content cleaning or preprocessing.
- Handling every exotic markdown extension.

---

## 4. Acceptable vs unacceptable differences

Same as previously defined: trailing whitespace, auto-generated heading IDs, and class attribute ordering are acceptable. Missing text, missing structural elements, and changed link targets are not.

Raw HTML blocks are a documented known loss — pandoc drops them during `md → djot`. The converter detects and warns about these.

---

## 5. Test fixtures

Three sets in `tests/test_04/fixtures/`:
- `clean/` — standard docs (headings, paragraphs, code, links, lists)
- `gfm/` — GitHub Flavored Markdown (task lists, strikethrough, autolinks)
- `edge_cases/` — raw HTML heavy, unicode, deeply nested structures

---

## 6. Integration with the pipeline

```
.md files → convert_directory() → .dj files → ingest_page() → blocks.jsonl → build_index() → Kuzu
```

The integration test confirms: converted files ingest without error AND pass the Phase 03 roundtrip test.

---

## 7. File layout after Phase 04

```
knowledge-graph/
  src/
    convert/
      __init__.py
      md_to_djot.py         ← pandoc wrapper
      html_roundtrip.py     ← HTML comparison
      batch_convert.py      ← directory conversion
  tests/
    test_04/
      fixtures/
        clean/
        gfm/
        edge_cases/
      output/               ← converted .dj files (generated, gitignored)
```

---

## 8. Environment update

Add `beautifulsoup4` for HTML normalization:

```yaml
- pip:
  - beautifulsoup4
```

---

## 9. Verification

Phase 04 is passing when:

1. All "clean" fixtures convert and pass both external (HTML) and internal (Phase 03) roundtrip.
2. GFM fixtures convert with documented warnings and pass after normalization.
3. Integration test: converted files ingest through Phase 02 pipeline into Kuzu without error.

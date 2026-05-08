# Phase 04 — Implementation Plan

## 1. Overview

This document is the step-by-step implementation plan for Phase 04. It assumes the reader has read `phase_04_design.md`.

The goal of Phase 04 is:

```
.md files  →  pandoc (md → djot)  →  .dj files  →  Phase 02+03 pipeline (verified)
```

---

## 2. Prerequisites

- [ ] Phase 02 (djot.js parser, full ingestion) is complete.
- [ ] Phase 03 (renderer + roundtrip test) is complete and passing.
- [ ] `pandoc` 3.x is available.

---

## 3. Steps

### Step 1 — Update environment, create directories

Add `beautifulsoup4`. Create `src/convert/` and `tests/test_04/fixtures/`.

### Step 2 — Create test fixtures

Same fixture files as the old Phase 03 implementation plan (clean, gfm, edge_cases). See that document for the exact file contents.

### Step 3 — Implement `md_to_djot.py`

Pandoc wrapper: `pandoc -f {flavor} -t djot`. Detect raw HTML blocks via AST inspection. Return conversion report with warnings.

### Step 4 — Implement `html_roundtrip.py`

Compare `md → html` vs `md → djot → html`. Normalize with BeautifulSoup. Return pass/fail with diff.

### Step 5 — Implement `batch_convert.py`

Directory-level conversion with optional verification per file.

### Step 6 — Integration test

Convert clean fixtures → ingest through Phase 02 → run Phase 03 roundtrip on the result → build Kuzu index → verify.

### Step 7 — GFM and edge case verification

Convert GFM/edge case fixtures. Confirm warnings are emitted for raw HTML. Confirm non-HTML content passes roundtrip.

---

## 4. Implementation order

```
Step 1  (setup)           — no dependencies
Step 2  (fixtures)        — no dependencies  
Step 3  (md_to_djot)      — depends on pandoc
Step 4  (html_roundtrip)  — depends on beautifulsoup4
Step 5  (batch_convert)   — depends on Steps 3, 4
Step 6  (integration)     — depends on Step 5 + Phases 02, 03
Step 7  (edge cases)      — depends on Step 5
```

---

## 5. What Phase 04 does NOT validate

- **Semantic enrichment**: Phase 05.
- **Pandoc correctness in general**: we test our specific fixtures, not all possible markdown.
- **Link rewriting**: `.md` extensions in link targets work as-is (stripped to derive page ID).

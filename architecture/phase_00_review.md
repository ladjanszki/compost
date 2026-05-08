# Test 00 — Design Review

Reviewer scope: high-risk issues and explicit contradictions only.

---

## 1. Block count contradiction (design doc, section 9)

The section opens with:

> the walker should produce **7 blocks** in this order

The table that immediately follows lists **9 rows** (positions 1–9), and the sentence below the table says:

> 9 blocks total.

The implementation plan consistently uses 9. The "7" is a stale number that was never updated. Low severity on its own, but if anyone implements from the prose rather than the table, they'll wire in the wrong assertion.

**Action**: fix the opening sentence to say 9.

---

## 2. Merged-header edge case — RESOLVED

~~Both documents acknowledge that Pandoc merges the heading and the first paragraph into a single `Header` node when no blank line separates them.~~

**Resolution**: the original test input was syntactically invalid Djot. In Djot, headings can be multi-line, so a blank line is *required* after a heading to terminate it. The corrected test file has blank lines after each heading, making the parse unambiguous — Pandoc will produce separate `Header` and `Para` nodes. No split heuristic is needed.

**Action**: update `test_00.dj` in both documents to use the corrected version (blank lines after headings). Remove or downgrade the merged-header note in section 9 of the design doc — it was describing a consequence of malformed input, not a real parser edge case.

---

## 3. Page ID: design vs. implementation plan disagree on format

Design doc section 7 shows:

```json
"id": "page-test_00"
```

Implementation plan step 9 says:

> Derive `page_id` from filename stem (e.g. `test_00`).

These produce different values (`page-test_00` vs `test_00`). The `make_page` function signature takes `page_id` as an argument, so if the caller passes the bare stem, the stored ID won't have the `page-` prefix unless `make_page` adds it internally — which is not specified anywhere.

**Action**: decide whether the prefix is the caller's responsibility or the schema builder's, and make the two documents consistent.

---

## Summary

| # | Severity | Status | Issue |
|---|----------|--------|-------|
| 1 | Low (typo) | Open | "7 blocks" vs actual 9 |
| 2 | ~~High~~ | Resolved | Merged-header was caused by invalid Djot input, not a parser edge case |
| 3 | Low-Medium | Open | Page ID format inconsistency between documents |

With the corrected test input, no high-risk issues remain. The pipeline structure, schema definitions, walker logic, and verification steps are internally consistent.

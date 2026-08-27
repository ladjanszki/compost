-- unresolved_citations.sql — how many distinct citation targets have never
-- landed in this base: one `unresolved_citation` node per distinct missing
-- handle, minted by `compost layer citation` (src/layers.py, `_citation` and
-- `_kg8hex`). Two builds of the layer mint two full sets, so this counts
-- placeholders, not citations — a handle cited five times in one build is
-- still one placeholder.
--
-- docs/queries.md, "starting queries"
SELECT COUNT(*) AS unresolved_citations
FROM records
WHERE record = 'node' AND type = 'unresolved_citation';

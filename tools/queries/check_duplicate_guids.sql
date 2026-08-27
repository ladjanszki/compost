-- check_duplicate_guids.sql — mirrors src/records.py `check()`'s
-- "guid {g} carries two different records".
--
-- `records` (see tools/graph_sql.py) is already `SELECT DISTINCT * FROM
-- raw_records` — the same rule `Store.load()` applies. So a guid appearing
-- more than once *here* means two rows that are not byte-identical share
-- one guid: a hard error, never resolved by picking a winner. Deliberately
-- not `count(DISTINCT guid)` over the raw glob — that would also hide this
-- exact conflict (docs/decisions.md, "load() deduplicates byte-identical
-- records").
SELECT guid, COUNT(*) AS distinct_records
FROM records
GROUP BY guid
HAVING COUNT(*) > 1;

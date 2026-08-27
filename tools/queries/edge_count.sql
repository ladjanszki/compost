-- edge_count.sql — how many edges are in the base.
--
-- docs/queries.md, "starting queries"
SELECT COUNT(*) AS edges
FROM records
WHERE record = 'edge';

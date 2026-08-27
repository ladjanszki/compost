-- node_count.sql — how many nodes are in the base.
--
-- docs/queries.md, "starting queries"
SELECT COUNT(*) AS nodes
FROM records
WHERE record = 'node';

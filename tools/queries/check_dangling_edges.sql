-- check_dangling_edges.sql — mirrors src/records.py `check()`'s
-- "edge {guid} has a dangling {source,destination}".
--
-- Every edge endpoint must resolve to a node guid actually present in the
-- base. Two halves, one per end, unioned rather than joined once against
-- both — an edge can be dangling on both ends at once and each end is its
-- own problem in the Python original.
SELECT e.guid AS edge, 'source' AS end, e.source AS missing
FROM records e
WHERE e.record = 'edge'
  AND NOT EXISTS (
    SELECT 1 FROM records n WHERE n.record = 'node' AND n.guid = e.source)
UNION ALL
SELECT e.guid, 'destination', e.destination
FROM records e
WHERE e.record = 'edge'
  AND NOT EXISTS (
    SELECT 1 FROM records n WHERE n.record = 'node' AND n.guid = e.destination);

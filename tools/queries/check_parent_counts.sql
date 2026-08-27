-- check_parent_counts.sql — mirrors three branches of src/records.py
-- `check()` that all read the same `contains` in-degree:
--
--   "{type} {guid} is contained by something"   -- UNCONTAINED, count > 0
--   "{type} {guid} has a parent"                -- ROOT_TYPES, count > 0
--   "{type} {guid} has {n} parents, expected 1" -- everything else, count != 1
--
-- The type lists below are a hand-kept copy of `records.py`'s UNCONTAINED
-- and ROOT_TYPES sets, not a shared source — if either set changes there and
-- not here, a fixture base built with the new type is exactly the
-- disagreement the twin-assertion test exists to catch.
WITH parent_counts AS (
  SELECT destination AS node, COUNT(*) AS n
  FROM records
  WHERE record = 'edge' AND type = 'contains'
  GROUP BY destination
)
SELECT n_.guid, n_.type, COALESCE(pc.n, 0) AS parents
FROM records n_
LEFT JOIN parent_counts pc ON pc.node = n_.guid
WHERE n_.record = 'node'
  AND (
    (n_.type IN ('file', 'blob', 'alias', 'unresolved_citation')
     AND COALESCE(pc.n, 0) > 0)
    OR (n_.type IN ('document', 'session') AND COALESCE(pc.n, 0) > 0)
    OR (n_.type NOT IN ('file', 'blob', 'alias', 'unresolved_citation',
                        'document', 'session')
        AND COALESCE(pc.n, 0) <> 1)
  );

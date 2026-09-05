-- check_record_hash.sql — mirrors src/records.py `check()`'s
-- "{type} {guid}: missing record_hash or record_subtree_hash".
--
-- Presence only, in both directions collapsed to one: v0.2.13 made the two
-- hashes unconditional on every node, so there is no longer a "should be
-- absent" branch the way the old per-node `content_hash` had one (present
-- only when a node carried `content`, or was CodeBlock/RawBlock). Whether a
-- present hash actually *recomputes* — check()'s eleventh assertion, and the
-- first that verifies content rather than structure — needs a fold over
-- `contains`/`next`, the same class of graph-path problem as the checks
-- below this one under "Not mirrored", and is not mirrored here for the same
-- reason.
SELECT guid, type
FROM records
WHERE record = 'node'
  AND (record_hash IS NULL OR record_subtree_hash IS NULL);

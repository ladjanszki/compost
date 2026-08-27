-- check_content_hash.sql — mirrors src/records.py `check()`'s
-- "{type} {guid}: content_hash should {be present,be absent}".
--
-- A node carries `content_hash` exactly when it has a `content` field, or is
-- one of the two constructors whose payload is text in `params` rather than
-- inlines (`records.py`'s TEXT_IN_PARAMS: CodeBlock, RawBlock — hand-kept
-- here, same caveat as check_parent_counts.sql). Anything else is wrong in
-- either direction: present when it should not be, or missing when it
-- should be there.
SELECT guid, type
FROM records
WHERE record = 'node'
  AND (content IS NOT NULL OR type IN ('CodeBlock', 'RawBlock'))
      <> (content_hash IS NOT NULL);

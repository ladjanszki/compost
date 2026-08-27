-- check_schema_version.sql — mirrors src/records.py `check()`'s
-- "{guid} is schema {v}; this tool writes {SCHEMA_VERSION}".
--
-- The `1` below is a hand-kept copy of `records.SCHEMA_VERSION`, not a
-- shared source — see check_parent_counts.sql for why that is accepted
-- rather than fixed.
SELECT guid, schema_version
FROM records
WHERE schema_version IS NOT NULL AND schema_version > 1;

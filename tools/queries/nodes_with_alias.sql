-- nodes_with_alias.sql — how many nodes are named by at least one `alias`.
--
-- An alias names its target through a `names` edge (src/layers.py,
-- `_entity`/`_citation`), so "has an alias connected" means: is the
-- destination of a `names` edge whose source is an `alias` node. Counted
-- DISTINCT because one target can be named by several aliases — two builds
-- of the citation layer mint two aliases for the same missing handle,
-- naming the same placeholder (docs/roadmap.md, "One alias value can name
-- several nodes").
--
-- docs/queries.md, "starting queries"
SELECT COUNT(DISTINCT names.destination) AS nodes_with_alias
FROM records AS names
JOIN records AS alias
  ON alias.record = 'node' AND alias.type = 'alias'
 AND alias.guid = names.source
WHERE names.record = 'edge' AND names.type = 'names';

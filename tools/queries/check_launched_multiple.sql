-- check_launched_multiple.sql — mirrors src/records.py `check()`'s
-- "session {guid} is launched by {n} tool calls".
--
-- `launched` joins a subagent transcript to the tool call that ran it
-- (src/store.py, `_link_agents`), and a view renders the subagent *inside*
-- that call — so, like `contains`, a session must have at most one launcher.
SELECT destination AS session, COUNT(*) AS launched_by
FROM records
WHERE record = 'edge' AND type = 'launched'
GROUP BY destination
HAVING COUNT(*) > 1;

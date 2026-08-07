# Archive — historical, not current

Nothing in this directory describes the system as it is. It is kept because the
*reasoning* is still worth reading, and because `CHANGELOG.md` refers to it.

**Do not treat any of it as a specification.** If it disagrees with `README.md`,
`DEVELOPMENT.md`, `TODO.md` or the knowledge base, they win.

| File | What it is | Why it is here |
|---|---|---|
| `mvp-design.md` | the v0.1 product spec | Superseded. It still calls itself authoritative, describes `notes/` and `wiki/`, UUID block ids, and "humans write notes, agents write the wiki" — all now false. Its invariants live in `DEVELOPMENT.md` (Mental model) and its open questions in `TODO.md`. Code comments cite its section numbers; those citations are historical. |
| `mvp-interview.md` | the workflow interview | Raw material the design came from. Never a spec. |
| `my-workflow.md` | how the author works | Same. Still the best statement of the problem. |
| `human-log.md` | session log | Personal notes. |
| `architecture/delta_ingestion_and_block_versioning.md` | the delta algorithm | Written for human-edited files, before this system existed. **The algorithm it describes is now implemented** in `src/artifact.py`, so the document is a rationale, not a plan. |

The reasoning that replaced these is in the knowledge base itself — the
conversations record why each decision was made, and unlike a spec they cannot
drift, because nothing in them is ever rewritten.

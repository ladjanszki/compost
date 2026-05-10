# Kuzu to LadybugDB Migration Plan
## Status
**Pending** — This plan has not been executed yet.
---
## 1. Context and Intention
Following the acquisition of Kuzu by Apple (October 2025) and the subsequent archiving of the Kuzu repository, the open-source community forked and continued the project under the name **LadybugDB**.
This document is the comprehensive, self-contained migration plan for switching the "Agentic Local Knowledge Store" from Kuzu to LadybugDB. It is designed to be executable by an agent with no prior knowledge of the codebase, using only this document and `README.md` as entry points.
**Key timing observation:** The project is early — Phase 02 (the first phase that actively uses the graph database) is still "Pending." Only four Python files reference `kuzu` (two directly import it, totaling ~84 lines of code). No Kuzu database exists on disk. This makes the migration low-risk and primarily a documentation + naming exercise.
---
## 2. Prerequisites
Before starting execution:
1. **No existing Kuzu database on disk.** The directory `workspace/store/` contains only JSONL files (`blocks.jsonl`, `pages.jsonl`) from the deprecated Phase 00/01. No `kuzu/` subdirectory exists. Therefore, **no data migration is needed.** If a Kuzu database existed, binary format compatibility with LadybugDB would need to be verified and likely rebuilt.
2. **LadybugDB version to install:** `real-ladybug==0.15.3` (latest stable as of May 2026, released April 2026). This is the PyPI package name. The Python import name is `real_ladybug`. LadybugDB v0.12.0 was the first release after the Kuzu fork (equivalent to Kuzu v0.11.3); v0.15.3 includes several releases of divergence. Verify at https://pypi.org/project/real-ladybug/ if a newer patch version exists.
3. **The conda environment must be active:** `conda activate knowledge-graph`
4. **Git must be clean:** Run `git status` and ensure there are no uncommitted changes before starting.
---
## 3. Scope Boundary
### In scope — MUST update
These are active project files that affect code execution, future implementation, or agent comprehension:
| Category | Files |
|----------|-------|
| Environment | `environment.yml` |
| Python source | `src/index/kuzu_schema.py`, `src/index/kuzu_loader.py`, `src/index/build_index.py`, `src/index/jsonl_to_parquet.py` |
| Project root docs | `README.md`, `TODO.md`, `CHANGELOG.md`, `cleanup.md`, `product-evolution.md` |
| Architecture docs | All 20 files in `architecture/` except this migration plan (see full inventory in Section 9) |
### Out of scope — Do NOT update
These are historical records. Modifying them would alter the factual record of what was discussed and decided:
| Category | Path pattern | Reason |
|----------|-------------|--------|
| Conversation transcripts | `context-harvest/**/*.md`, `context-harvest/**/*.txt` | Historical conversation logs |
| Harvesting utilities | `context-harvest/*.py`, `parse_conversations.py` | Utility scripts for historical data processing |
| Audit reports | `independent-audit/*.md` | Point-in-time assessments referencing Kuzu as it was |
| Raw research | `raw/*.md` | Reference material |
| Generated HTML | `product-evolution.html` | Generated render — leave as-is |
### Self-referential exception
`architecture/KUZU_TO_LADYBUG_MIGRATION.md` (this file) necessarily references "Kuzu" throughout, as it describes the migration *from* Kuzu. Do **NOT** apply global replacement to this file.
---
## 4. Replacement Rules
These rules apply throughout all in-scope files unless a step specifies otherwise.
### In prose / documentation
| Old | New | Context |
|-----|-----|---------|
| `Kuzu` (capitalized) | `LadybugDB` | When referring to the database product |
| `kuzu` (lowercase, in paths) | `ladybug` | Directory names, file path segments |
| `Kuzu Node` / `Kuzu Edge` | `LadybugDB Node` / `LadybugDB Edge` | Object kind tables in docs |
| `Kuzu type` | `LadybugDB type` | Schema column type tables |
| `### Kuzu / graph database` | `### LadybugDB / graph database` | README section header |
| `The Kuzu Pivot` | `The LadybugDB Pivot` | Architecture review section |
### In Python code
| Old | New |
|-----|-----|
| `import kuzu` | `import real_ladybug as lb` |
| `import os, kuzu, shutil` | `import os, shutil` (next line) `import real_ladybug as lb` |
| `import os, shutil, kuzu` | `import os, shutil` (next line) `import real_ladybug as lb` |
| `kuzu.Database(...)` | `lb.Database(...)` |
| `kuzu.Connection(...)` | `lb.Connection(...)` |
| `from .kuzu_loader import` | `from .ladybug_loader import` |
| `from .kuzu_schema import` | `from .ladybug_schema import` |
### In file / directory paths
| Old | New |
|-----|-----|
| `workspace/indexes/kuzu/db` | `workspace/indexes/ladybug/db` |
| `workspace/indexes/kuzu/parquet` | `workspace/indexes/ladybug/parquet` |
| `workspace/store/kuzu/db` | `workspace/store/ladybug/db` |
| `workspace/store/kuzu/` | `workspace/store/ladybug/` |
| `src/index/kuzu_schema.py` | `src/index/ladybug_schema.py` |
| `src/index/kuzu_loader.py` | `src/index/ladybug_loader.py` |
### In environment / dependencies
| Old | New |
|-----|-----|
| `- kuzu` | `- real-ladybug==0.15.3` |
| `python -c "import kuzu; print(kuzu.__version__)"` | `python -c "import real_ladybug as lb; print(lb.__version__)"` |
| `\| \`kuzu\` \| Embedded canonical graph database` | `\| \`real-ladybug\` \| Embedded canonical graph database (LadybugDB)` |
---
## 5. Execution Plan
Execute these steps **in order**. Each step has a verification check — do not proceed to the next step until verification passes. **Commit after each step.**
---
### Step 1 — Update environment dependency
**Files:** `environment.yml`
**Action:** Replace the `kuzu` dependency with a pinned `real-ladybug` version.
Old:
```yaml
  - pip:
    - uuid6
    - kuzu
    - pyarrow
```
New:
```yaml
  - pip:
    - uuid6
    - real-ladybug==0.15.3
    - pyarrow
```
**Verification:**
```bash
conda env update -f environment.yml
python -c "import real_ladybug as lb; print(lb.__version__)"
# Expected: prints "0.15.3"
```
**Commit:** `migration: step 1 — replace kuzu with real-ladybug==0.15.3 in environment.yml`
---
### Step 2 — Rename Python source files
**Files:** `src/index/kuzu_schema.py`, `src/index/kuzu_loader.py`
**Action:** Use `git mv` to preserve blame history:
```bash
git mv src/index/kuzu_schema.py src/index/ladybug_schema.py
git mv src/index/kuzu_loader.py src/index/ladybug_loader.py
```
**Verification:**
```bash
ls src/index/ladybug_schema.py src/index/ladybug_loader.py
# Both files should exist
ls src/index/kuzu_schema.py src/index/kuzu_loader.py 2>&1
# Both should report "No such file or directory"
```
**Commit:** `migration: step 2 — rename kuzu_schema.py and kuzu_loader.py to ladybug_*`
---
### Step 3 — Update Python source code
**Files:** `src/index/ladybug_schema.py`, `src/index/ladybug_loader.py`, `src/index/build_index.py`, `src/index/jsonl_to_parquet.py`
#### `ladybug_schema.py` (formerly `kuzu_schema.py`)
Apply these changes:
- Line 2 docstring: `kuzu_schema.py — create node and relationship tables in a Kuzu database.` → `ladybug_schema.py — create node and relationship tables in a LadybugDB database.`
- Line 4: `import kuzu` → `import real_ladybug as lb`
- Line 9 docstring: `Open (or create) a Kuzu database` → `Open (or create) a LadybugDB database`
- Line 15: `db = kuzu.Database(db_path)` → `db = lb.Database(db_path)`
- Line 16: `conn = kuzu.Connection(db)` → `conn = lb.Connection(db)`
The Cypher `CREATE TABLE` statements (lines 18-51) remain unchanged — they are Cypher syntax, not Python API.
#### `ladybug_loader.py` (formerly `kuzu_loader.py`)
Apply these changes:
- Line 2 docstring: `kuzu_loader.py — bulk load Parquet files into Kuzu using COPY FROM.` → `ladybug_loader.py — bulk load Parquet files into LadybugDB using COPY FROM.`
- Line 6: `import kuzu` → `import real_ladybug as lb`
- Line 16 docstring: `Run COPY FROM on all three Parquet files to load data into Kuzu.` → `...into LadybugDB.`
- Line 18 docstring: `Assumes the schema already exists (kuzu_schema.create_schema was called).` → `...ladybug_schema.create_schema was called).`
- Line 22 docstring: `Kuzu COPY FROM requires absolute paths.` → `LadybugDB COPY FROM requires absolute paths.`
- Line 28: `db   = kuzu.Database(db_path)` → `db   = lb.Database(db_path)`
- Line 29: `conn = kuzu.Connection(db)` → `conn = lb.Connection(db)`
The `COPY FROM` Cypher statements (lines 31-33) remain unchanged.
#### `build_index.py`
Apply these changes:
- Line 3 docstring: `JSONL store → Parquet → Kuzu index.` → `JSONL store → Parquet → LadybugDB index.`
- Line 8: `from .kuzu_loader import load_from_parquet` → `from .ladybug_loader import load_from_parquet`
- Line 9: `from .kuzu_schema import create_schema` → `from .ladybug_schema import create_schema`
- Line 13: `DEFAULT_DB_PATH      = "workspace/indexes/kuzu/db"` → `DEFAULT_DB_PATH      = "workspace/indexes/ladybug/db"`
- Line 14: `DEFAULT_PARQUET_DIR  = "workspace/indexes/kuzu/parquet"` → `DEFAULT_PARQUET_DIR  = "workspace/indexes/ladybug/parquet"`
- Line 24 docstring: `Full pipeline: JSONL files → Parquet intermediate files → Kuzu graph index.` → `...→ LadybugDB graph index.`
- Line 26 docstring: `Clears and rebuilds the Kuzu database on every run.` → `...LadybugDB database...`
- Line 29 comment: `# 1. Clear the Kuzu database directory for a clean rebuild.` → `...LadybugDB database...`
- Line 30 comment: `# Kuzu creates the directory itself` → `# LadybugDB creates the directory itself`
- Line 49 comment: `# 4. Load Parquet files into Kuzu.` → `...into LadybugDB.`
- Line 52: `print(f"Kuzu index built at: {db_path}")` → `print(f"LadybugDB index built at: {db_path}")`
#### `jsonl_to_parquet.py`
Apply one change:
- Line 2 docstring: `jsonl_to_parquet.py — flatten JSONL store files to Parquet for Kuzu COPY FROM.` → `...for LadybugDB COPY FROM.`
**Verification:**
```bash
# Verify imports resolve
python -c "from src.index.ladybug_schema import create_schema; print('ladybug_schema OK')"
python -c "from src.index.ladybug_loader import load_from_parquet; print('ladybug_loader OK')"
python -c "from src.index.build_index import build_index; print('build_index OK')"
# Verify no remaining kuzu references in source
grep -ri "kuzu" src/
# Expected: zero matches
```
**End-to-end verification** (run the existing Phase 01 pipeline):
```bash
python -c "
from src.index.build_index import build_index
build_index()
print('End-to-end pipeline: PASS')
"
```
This reads the existing `workspace/store/blocks.jsonl` and `workspace/store/pages.jsonl` and runs the full JSONL → Parquet → LadybugDB pipeline. Expected output: block/page/HAS_BLOCK counts and "LadybugDB index built at: workspace/indexes/ladybug/db".
**Commit:** `migration: step 3 — update all Python source to use real_ladybug`
---
### Step 4 — Update README.md
**File:** `README.md`
**Actions (apply in this order — most specific first, then global):**
**4a. Remove Risk #13** (OPTIONAL MATCH). LadybugDB supports `OPTIONAL MATCH`. Delete the entire table row:
```
| 13 | Low | **Kuzu does NOT support OPTIONAL MATCH** — Phase 07 Cypher generation must avoid this pattern. The LLM may generate it anyway since it's common in Neo4j examples on the internet. | Documented in Phase 07 prompt instructions. The retry loop should catch syntax errors. Add explicit "DO NOT use OPTIONAL MATCH" to the few-shot prompt. |
```
**4b. Rewrite Risk #4** (pre-1.0 / version pinning).
Old:
```
| 4 | Medium | **Kuzu is pre-1.0** — The `environment.yml` does not pin a Kuzu version. Kuzu has had breaking API changes between minor versions (connection API, COPY FROM syntax, Cypher dialect). | Pin in `environment.yml`: `kuzu==0.x.y`. Test against that specific version. |
```
New:
```
| 4 | Medium | **LadybugDB is a community fork (pre-1.0)** — LadybugDB was forked from Kuzu after Apple's acquisition (Oct 2025). As a community fork it may have less rigorous backward compatibility guarantees than the original. The API has already diverged (e.g., `SHOW_TABLES()` output, `OPTIONAL MATCH` support added). | Pinned in `environment.yml`: `real-ladybug==0.15.3`. Test against that specific version. Monitor LadybugDB release notes for breaking changes. |
```
**4c. Rewrite Risk #10** (concurrency).
Old:
```
| 10 | Medium | **Write concurrency limits** — Kuzu (embedded mode) enforces single-writer semantics. If multiple agents attempt simultaneous writes, they will block or error. | For the single-agent use case this is fine. For multi-agent: introduce a write queue (Python `asyncio.Lock` or a dedicated writer process). Document that concurrent writes are not supported out of the box. |
```
New:
```
| 10 | Medium | **Write concurrency limits** — LadybugDB (embedded mode) enforces strict object constraints: a process can have either **one `READ_WRITE` Database object** OR **multiple `READ_ONLY` Database objects**. Mixing them, or attempting multiple simultaneous writers across processes, will cause locks or errors. | For the single-agent use case this is fine. For multi-agent: introduce a write queue (Python `asyncio.Lock` or a dedicated writer process). Document that concurrent writes are not supported out of the box. See: https://docs.ladybugdb.com/concurrency/ |
```
**4d. Apply global replacement** to all remaining instances of "Kuzu" / "kuzu" in README.md using the rules in Section 4. This covers:
- The header descriptions, core loop diagram, design principles
- The phase table entries (lines 32-34)
- The storage layers diagram and canonical data path
- The object kinds table ("Kuzu Node", "Kuzu Edge")
- The graph schema section header
- The repository layout tree
- The environment verify command
- The design decisions log table
- The key dependencies table
- All remaining risk entries (#7, #8, #11, #12, #14)
**Verification:**
```bash
grep -i "kuzu" README.md
# Expected: zero matches
```
**Commit:** `migration: step 4 — update README.md for LadybugDB`
---
### Step 5 — Update project management files
**Files:** `TODO.md`, `CHANGELOG.md`, `cleanup.md`, `product-evolution.md`
**Action for `TODO.md`, `cleanup.md`, `product-evolution.md`:** Apply the global replacement rules from Section 4. Every instance of "Kuzu" becomes "LadybugDB", every path segment "kuzu" becomes "ladybug", every code reference follows the Python code rules.
Key locations in each file:
- **`TODO.md`:** Lines 17, 20, 36, 41, 69, 80, 81, 82, 102 (9 occurrences)
- **`cleanup.md`:** Lines 9, 13, 14 (3 occurrences)
- **`product-evolution.md`:** Lines 5, 22, 40, 47, 51, 59, 60, 67, 77, 80 (10 occurrences)
**Special action for `CHANGELOG.md`:**
1. Apply global replacement to existing content (lines 5, 7).
2. Add a new entry at the top (after the `# CHANGELOG` header), using today's date:
```markdown
## YYYY-MM-DD — Kuzu to LadybugDB Migration
Replaced Kuzu with LadybugDB (community fork) as the embedded graph database, following
Apple's acquisition and archiving of the Kuzu repository. Renamed `kuzu_schema.py` →
`ladybug_schema.py`, `kuzu_loader.py` → `ladybug_loader.py`. Updated all design docs,
implementation plans, and workspace paths. Python package changed from `kuzu` to
`real-ladybug==0.15.3`. Import alias: `import real_ladybug as lb`.
LadybugDB now supports `OPTIONAL MATCH` — constraint removed from Phase 07 design and
implementation plans. Added defensive parsing guidance for `SHOW_TABLES()` output change.
No data migration was needed (no existing database on disk).
```
(Replace `YYYY-MM-DD` with today's date. The mention of "Kuzu" here is acceptable — it's a historical record of the migration.)
**Verification:**
```bash
grep -i "kuzu" TODO.md cleanup.md product-evolution.md
# Expected: zero matches
grep -i "kuzu" CHANGELOG.md
# Expected: only matches within the new migration entry (historical context)
```
**Commit:** `migration: step 5 — update TODO, CHANGELOG, cleanup, product-evolution`
---
### Step 6 — Update architecture documents
**Files:** All files in `architecture/` listed below. **SKIP** `architecture/KUZU_TO_LADYBUG_MIGRATION.md` (this file).
#### General action for ALL files below
Apply the replacement rules from Section 4.  In code snippets within these docs, apply the Python code replacement rules (import, Database, Connection, module names). In path references, apply the path rules. In prose, apply the prose rules.
#### Files to update (ordered by change density)
| File | ~Occurrences |
|------|-------------|
| `phase_01_implementation_plan.md` | 36 |
| `phase_01_design.md` | 30 |
| `phase_02_implementation_plan.md` | 22 |
| `OVERALL_ARCHITECTURE_REVIEW_PRE_IMPLEMENTATION.md` | 17 |
| `phase_06_implementation_plan.md` | 12 |
| `phase_07_implementation_plan.md` | 11 |
| `phase_07_design.md` | 10 |
| `phase_06_design.md` | 8 |
| `phase_02_design.md` | 7 |
| `phase_05_design.md` | 6 |
| `phase_05_implementation_plan.md` | 4 |
| `phase_00_design.md` | 3 |
| `phase_01_review.md` | 2 |
| `phase_04_design.md` | 2 |
| `phase_03_implementation_plan.md` | 1 |
| `phase_04_implementation_plan.md` | 1 |
| `phase_00_implementation_plan.md` | 1 |
| `phase_03_design.md` | 1 |
Skip: `phase_00_review.md` (0 occurrences — no changes needed).
#### Specific actions beyond global replacement
**1. `phase_07_implementation_plan.md`:**
- **Remove** the line (approximately line 82): `parts.append("  - Kuzu does NOT support OPTIONAL MATCH")`
- **Remove** the prompt instruction (approximately line 262): `- Do NOT use OPTIONAL MATCH (Kuzu does not support it).`
- **Add** a warning near the `SHOW_TABLES()` / schema introspection code (approximately lines 89-128). Insert a comment or note: "LadybugDB's `SHOW_TABLES()` includes an additional `database name` column (for its attached-database feature). Do NOT use hardcoded tuple unpacking (e.g., `name, type, ... = row`). Access data defensively via dictionaries or column indices verified against the result headers."
**2. `phase_07_design.md`:**
- **Remove** the line (approximately line 144): `- Do NOT use OPTIONAL MATCH (Kuzu does not support it).`
- **Add** a retained-constraints note in the same section: "LadybugDB still differs from Neo4j in certain ways. Retain warnings about: variable-length path walk semantics, the default upper bound of 30 for variable paths, and the lack of `FOREACH` or inline pattern `WHERE` clauses. See: https://docs.ladybugdb.com/cypher/difference/"
**3. `OVERALL_ARCHITECTURE_REVIEW_PRE_IMPLEMENTATION.md`:**
- Change the section header (approximately line 11) from `The Kuzu Pivot` to `The LadybugDB Pivot`.
- Add a brief contextual note at or near the section: "LadybugDB is the community fork of Kuzu, continued after Apple's acquisition and archiving of the original Kuzu repository in October 2025."
**Verification:**
```bash
grep -ri "kuzu" architecture/ --include="*.md" | grep -v "KUZU_TO_LADYBUG_MIGRATION.md"
# Expected: zero matches
```
**Commit:** `migration: step 6 — update all architecture documents for LadybugDB`
---
### Step 7 — Final verification
Run all checks together to confirm the migration is complete:
```bash
# 1. Python import works
python -c "import real_ladybug as lb; print(f'LadybugDB version: {lb.__version__}')"
# 2. Module imports resolve
python -c "from src.index.ladybug_schema import create_schema; print('ladybug_schema OK')"
python -c "from src.index.ladybug_loader import load_from_parquet; print('ladybug_loader OK')"
python -c "from src.index.build_index import build_index; print('build_index OK')"
# 3. Old files no longer exist
test ! -f src/index/kuzu_schema.py && echo "kuzu_schema.py removed: OK" || echo "FAIL: kuzu_schema.py still exists"
test ! -f src/index/kuzu_loader.py && echo "kuzu_loader.py removed: OK" || echo "FAIL: kuzu_loader.py still exists"
# 4. No remaining "kuzu" references in any in-scope files
echo "--- Checking source files ---"
grep -ri "kuzu" src/
echo "--- Checking root docs ---"
grep -i "kuzu" README.md TODO.md cleanup.md product-evolution.md environment.yml
echo "--- Checking architecture docs (excluding this migration plan) ---"
grep -ri "kuzu" architecture/ --include="*.md" | grep -v "KUZU_TO_LADYBUG_MIGRATION.md"
echo "--- Checking CHANGELOG (historical mentions are OK) ---"
grep -i "kuzu" CHANGELOG.md
# All of the above (except CHANGELOG historical entry) should return zero matches.
# 5. End-to-end pipeline test
python -c "
from src.index.build_index import build_index
build_index()
print('End-to-end pipeline: PASS')
"
```
If all checks pass, update the **Status** section at the top of this file from "Pending" to "Completed — YYYY-MM-DD" and commit.
**Commit:** `migration: complete — verify Kuzu-to-LadybugDB migration`
---
## 6. Technical Edge Cases
These are API and behavioral differences between Kuzu and LadybugDB that affect specific phases. They are handled by the changes in Section 5, but documented here for reference.
### 6.1 SHOW_TABLES() output change (affects Phase 07)
LadybugDB's `SHOW_TABLES()` includes an additional `database name` column to support the attached-database feature. Code that unpacks results by position (e.g., `name, type = row`) will break.
**Fix:** Phase 07's `schema_describer.py` implementation must access data defensively via dictionaries or column indices verified against result headers. Addressed in Step 6 specific action #1.
> Reference: https://docs.ladybugdb.com/cypher/query-clauses/call/
### 6.2 OPTIONAL MATCH now supported (affects Phase 07)
LadybugDB supports `OPTIONAL MATCH`. The LLM prompts in Phase 07 that explicitly forbid its use should have this constraint removed.
**Fix:** Addressed in Step 6 specific actions #1 and #2.
> Reference: https://docs.ladybugdb.com/cypher/query-clauses/optional-match/
### 6.3 Concurrency model clarification
LadybugDB formalizes the embedded concurrency constraints: a process can have either **one `READ_WRITE` Database object** or **multiple `READ_ONLY` Database objects**.
**Fix:** Addressed in Step 4 (README Risk #10 rewrite).
> Reference: https://docs.ladybugdb.com/concurrency/
### 6.4 Parquet bulk load (COPY FROM)
LadybugDB completely preserves the Cypher `COPY FROM` capability for Parquet ingestion. No changes needed to ingestion logic or Cypher statements.
> Reference: https://docs.ladybugdb.com/import/parquet/
### 6.5 Path convention inconsistency (pre-existing, not introduced by migration)
The codebase has two competing path conventions:
- Phase 01 code (`build_index.py`): uses `workspace/indexes/kuzu/`
- Phase 02 design docs and README: use `workspace/store/kuzu/`
This migration preserves the existing convention in each context (replacing `kuzu` → `ladybug`), leaving path consolidation to the Phase 02 implementation.
### 6.6 Database binary format compatibility
LadybugDB's on-disk format may not be binary-compatible with Kuzu databases. **This is not a concern for this migration** because no Kuzu database exists on disk (`workspace/store/` contains only JSONL files from the deprecated Phase 00/01). If a Kuzu database existed, it would need to be deleted and rebuilt from source data.
### 6.7 Retained Cypher differences from Neo4j
Even though `OPTIONAL MATCH` is now supported, LadybugDB still differs from Neo4j in other ways. These constraints must remain in Phase 07 prompts:
- Variable-length path walk semantics differ
- Default upper bound of 30 for variable-length paths
- No `FOREACH` clause
- No inline pattern `WHERE` clauses
> Reference: https://docs.ladybugdb.com/cypher/difference/
---
## 7. Risks and Mitigations
| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | **LadybugDB API diverges further from Kuzu** | Medium | Pinned to `real-ladybug==0.15.3`. Future upgrades require explicit testing. |
| 2 | **Missed reference to "kuzu" in a file** | Low | Step 7 grep verification catches this across all in-scope files. |
| 3 | **Import name confusion** (`real_ladybug` vs `real-ladybug` vs `ladybug`) | Low | PyPI package: `real-ladybug`. Python import: `real_ladybug`. Alias: `lb`. Documented consistently in Section 4 replacement rules. |
| 4 | **`git mv` doesn't preserve full blame** | Low | `git mv` records the rename. `git log --follow` tracks history. |
| 5 | **End-to-end test fails due to API change in LadybugDB 0.15.3** | Medium | The code surface is tiny (84 lines across 2 files). If `build_index()` fails, debug the specific API difference. The Cypher DDL and COPY FROM statements are the most likely to be stable. |
| 6 | **Agent applies replacement to out-of-scope files** | Low | Scope boundary is explicitly defined in Section 3. Verification greps only check in-scope files. |
### Rollback strategy
If the migration fails partway through:
```bash
git stash   # or: git checkout .
```
Since each step is committed separately, you can also revert individual steps:
```bash
git revert HEAD    # revert the last step
```
The migration is purely additive to source control — no data files are destroyed, no database state is changed.
---
## 8. Replacement Rule Quick Reference for Code Snippets in Docs
Many architecture documents contain inline Python code snippets. Here is the complete mapping for code that appears within markdown code blocks:
```python
# BEFORE (in any architecture doc code snippet)
import kuzu
db = kuzu.Database('workspace/indexes/kuzu/db')
conn = kuzu.Connection(db)
# AFTER
import real_ladybug as lb
db = lb.Database('workspace/indexes/ladybug/db')
conn = lb.Connection(db)
```
```python
# BEFORE (Phase 02 code snippets use store/ path)
import kuzu
db = kuzu.Database('workspace/store/kuzu/db')
conn = kuzu.Connection(db)
# AFTER
import real_ladybug as lb
db = lb.Database('workspace/store/ladybug/db')
conn = lb.Connection(db)
```
```python
# BEFORE (multi-import variants)
import os, kuzu, shutil
import os, shutil, kuzu
# AFTER (split the import)
import os, shutil
import real_ladybug as lb
```
```bash
# BEFORE (verification commands)
conda run -n knowledge-graph python -c "import kuzu; print(kuzu.__version__)"
# AFTER
conda run -n knowledge-graph python -c "import real_ladybug as lb; print(lb.__version__)"
```
```bash
# BEFORE (directory creation)
mkdir -p workspace/indexes/kuzu/db
mkdir -p workspace/indexes/kuzu/parquet
# AFTER
mkdir -p workspace/indexes/ladybug/db
mkdir -p workspace/indexes/ladybug/parquet
```
```bash
# BEFORE (file creation)
touch src/index/kuzu_schema.py
touch src/index/kuzu_loader.py
# AFTER
touch src/index/ladybug_schema.py
touch src/index/ladybug_loader.py
```
---
## 9. Complete File Inventory
### Python source files (4 files)
| File | Action | Key changes |
|------|--------|-------------|
| `src/index/kuzu_schema.py` | Rename → `ladybug_schema.py` + edit | `import kuzu` → `import real_ladybug as lb`, docstring, API calls |
| `src/index/kuzu_loader.py` | Rename → `ladybug_loader.py` + edit | Same pattern as above |
| `src/index/build_index.py` | Edit | Import paths, default path constants, all docstrings, comments, print |
| `src/index/jsonl_to_parquet.py` | Edit | Docstring only (line 2) |
### Environment file (1 file)
| File | Action | Key changes |
|------|--------|-------------|
| `environment.yml` | Edit | `- kuzu` → `- real-ladybug==0.15.3` |
### Root documentation (5 files)
| File | Action | Key changes |
|------|--------|-------------|
| `README.md` | Edit | Global replacement + Risk #4/#10/#13 rewrites + verify command + deps table |
| `TODO.md` | Edit | Global replacement (9 occurrences) |
| `CHANGELOG.md` | Edit | Global replacement (2 occurrences) + new migration entry |
| `cleanup.md` | Edit | Global replacement (3 occurrences) |
| `product-evolution.md` | Edit | Global replacement (10 occurrences) |
### Architecture documents (18 files to edit, 1 to skip, 1 protected)
| File | Action | ~Occurrences | Special handling |
|------|--------|-------------|-----------------|
| `OVERALL_ARCHITECTURE_REVIEW_PRE_IMPLEMENTATION.md` | Edit | 17 | Section header rewrite + fork context note |
| `phase_00_design.md` | Edit | 3 | — |
| `phase_00_implementation_plan.md` | Edit | 1 | — |
| `phase_00_review.md` | **Skip** | 0 | No changes needed |
| `phase_01_design.md` | Edit | 30 | — |
| `phase_01_implementation_plan.md` | Edit | 36 | Heaviest file — many code snippets |
| `phase_01_review.md` | Edit | 2 | — |
| `phase_02_design.md` | Edit | 7 | — |
| `phase_02_implementation_plan.md` | Edit | 22 | — |
| `phase_03_design.md` | Edit | 1 | — |
| `phase_03_implementation_plan.md` | Edit | 1 | — |
| `phase_04_design.md` | Edit | 2 | — |
| `phase_04_implementation_plan.md` | Edit | 1 | — |
| `phase_05_design.md` | Edit | 6 | — |
| `phase_05_implementation_plan.md` | Edit | 4 | — |
| `phase_06_design.md` | Edit | 8 | — |
| `phase_06_implementation_plan.md` | Edit | 12 | — |
| `phase_07_design.md` | Edit | 10 | Remove OPTIONAL MATCH constraint + add retained constraints |
| `phase_07_implementation_plan.md` | Edit | 11 | Remove OPTIONAL MATCH + add SHOW_TABLES() warning |
| `KUZU_TO_LADYBUG_MIGRATION.md` | **Protected** | — | This file. Do not apply replacements. |
### Files explicitly excluded (historical records — do NOT modify)
| Path pattern | Reason |
|-------------|--------|
| `context-harvest/**` | Conversation transcripts and harvesting scripts |
| `independent-audit/**` | Point-in-time audit reports |
| `raw/**` | Research artifacts |
| `parse_conversations.py` | Utility for historical data |
| `product-evolution.html` | Generated HTML render — leave as-is |
---
The agent prompt
Here is the prompt to give to the executing agent:
You are executing a database dependency migration for the knowledge-graph project:
replacing the Kuzu graph database with LadybugDB (its community fork).
## Entry points
Read these two documents IN ORDER before making any changes:
1. `README.md` — Understand the project architecture, directory layout, storage
   layers, phase status, known risks, and key dependencies.
2. `architecture/KUZU_TO_LADYBUG_MIGRATION.md` — The complete, self-contained
   migration plan. Read it ENTIRELY before starting execution.
## Execution protocol
1. Execute the plan step by step (Step 1 through Step 7), in exact order.
   Do not skip steps. Do not reorder steps.
2. After each step, run the verification command specified in the plan.
   Do not proceed to the next step until verification passes.
3. Commit after each step using the commit message specified in the plan.
4. If a verification fails, stop, diagnose the issue, fix it, and re-verify
   before proceeding.
## Critical constraints
- Follow the Scope Boundary (Section 3) strictly: do NOT modify files listed
  as "out of scope" (context-harvest/, independent-audit/, raw/, historical
  records).
- Do NOT modify `architecture/KUZU_TO_LADYBUG_MIGRATION.md` itself until
  Step 7, where you update only its Status field.
- Use `git mv` (not manual rename + delete) for file renames in Step 2.
- Use the Replacement Rules table (Section 4) as the authoritative reference
  for all text substitutions.
- For README Risk #4, #10, and #13: follow the SPECIFIC rewrite instructions
  in Step 4 — do not just apply global find-replace on those entries.
- For Phase 07 documents: follow the SPECIFIC actions in Step 6 to remove
  OPTIONAL MATCH constraints and add the SHOW_TABLES() warning.
## Expected outcome
When complete:
- `grep -ri "kuzu"` across all in-scope files returns zero matches
  (except CHANGELOG historical migration entry)
- `python -c "from src.index.build_index import build_index; build_index()"`
  runs successfully end-to-end
- All changes are committed with descriptive per-step messages
- The migration plan Status is updated to "Completed"

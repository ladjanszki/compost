# TODO

Everything discussed. See `DEVELOPMENT.md` for how. The reasoning lives in the
v0.1 corpus rather than in a spec that can drift — and that corpus is no longer
in this repository, so entries below that cite it are pointing outside.

**Released versions and planning milestones are different things**, and this
file used to blur them. Versions are git tags on `main`. The headings that used
to read "v1" and "v2+" were never versions, only buckets meaning "the next big
milestone" and "later"; they are named now, so nothing implies a release that
does not exist.

**Development happens on `main`, with a tag per version.** No feature branches:
one developer, no remote, no CI, nothing to isolate from. Branch only for a
change that is genuinely a one-way door. The em-dash entry below was the
standing candidate and turned out not to be one at all: it was render-time, and
v0.1.2 shipped it on `main` in an afternoon.

Tags so far: `v0-graph-architecture`, `v0.1`, `v0.1.1`, `v0.1.2`, `v0.1.3`,
`v0.1.4`.

Before adding anything here, decide whether it is a **render-time** change
(backward compatible, works on old notes for free) or a **canonization-time**
change (baked into immutable `.dj` files, recoverable only via an explicit
migration). See DEVELOPMENT.md — it decides urgency more than anything else.

---

## v0 — cleanup and carry-over ✓

- [x] Tag the LadybugDB architecture as `v0-graph-architecture` before cleanup
- [x] Delete 47 superseded files; carry ~360 LOC of parsing and rendering
- [x] Audit carried-over code against real behaviour, not the design docs
- [x] Fix walker: `task_list` / `task_list_item` were silently dropped
- [x] Fix walker: nested items emitted before their parent, depth discarded
- [x] Strengthen roundtrip test with an AST-tag coverage check — a dropped
      element type passed by being absent from both sides of the comparison

## v0.1 — the mechanical loop ✓

- [x] Canonization: Markdown → Djot via pandoc, no hand-written normalizer
- [x] Establish pandoc flags by testing (`-smart`, `-auto_identifiers`,
      `--wrap=preserve`, checkbox restore)
- [x] Inject ids as text via `--sourcepos`, not an AST round-trip
- [x] Verifier that refuses to emit a note with unaddressable blocks
- [x] `loosen()` — list item ids are dropped in HTML unless the list is loose
- [x] Reference syntax: `{#uuid:hash}` / `{#uuid:hash+++}`, always pinned
- [x] `raw/` and `notes/` split, sharing a uuid
- [x] `kg` on PATH via `pip install -e .`
- [x] `kg init` — defers the tool/data split to a runtime choice
- [x] `kg new` / `submit` / `render` / `serve`
- [x] Base resolution: `--root`, `$KG_HOME`, or a `.kg` marker in any parent
- [x] Static site: click for a block, shift-click for its subtree
- [x] Shift-hover highlights the subtree before you commit to copying it
- [x] Backlinks — "Referenced by" on the target note
- [x] Reverse-chronological index, dated from the UUIDv7 timestamp
- [x] `README.md`, `DEVELOPMENT.md`, `CHANGELOG.md`
- [x] Sabotage-verify every guarantee

---

## v0.1.1 — conversations, and an agent in the loop ✓

- [x] **Fix the walker's div handling** — a div swallowed its children, so every
      block of every folded turn would have been unaddressable
- [x] **8-hex handles** replacing UUIDv7 block ids; id overhead 26.8% → 10.2%
- [x] Optional version pin: `{#handle}` immutable, `{#handle@ver}` artifacts
- [x] `conversations/` and `artifacts/` — the split is mutability, not authorship
- [x] Turns as `{.turn author=...}` divs; authorship in the djot, so in git
- [x] Append verification — earlier blocks must survive unchanged, structure
      included, since the seam failure changes no text
- [x] Thread inferred from the blocks a draft cites; no second handle to copy
- [x] `blocks.json` — the corpus an agent can actually cite from
- [x] `kg check` — dangling references and handle collisions
- [x] `kg import` — a closed Claude Code session becomes a conversation
- [x] Folded tool traffic; per-turn author labels
- [x] `AGENTS.md` — an agent needs the base and this file, not the repo
- [x] Migrate the test base: 248 blocks remapped, zero dangling
- [x] **Importer attribution** — a `user` line is not "the human typed this".
      Tool results, harness injections and slash-command echoes all appeared
      under the user's name; in one session only 1 turn of 18 was real
- [x] **`kg artifact`** with handle-preserving update, so a living document can
      be commented on more than once. This is the delta algorithm, and it is
      what makes commenting on a README survive the next edit
- [x] **A reference inside code is not a citation** — importing this project's
      own sessions took `kg check` from 6 dangling to 48, every one a shell
      command or a documented example. Now zero
- [x] **Honest index links** — the document's own heading, the artifact's
      filename so "where is the README?" has an answer, the real date,
      participants and size
- [x] **Conversations titled by what the human opened with** — the first
      heading is usually the agent's, and the first block can be harness output
- [x] Guard `_when()` against non-UUIDv7 ids — an imported session's id is a
      UUIDv4 and decoded to the year 4527
- [x] Import all four sessions for this project
- [x] **Re-importing a live session preserves handles** — a session is imported
      again and again as it grows, and a blind overwrite renumbered every block
      each time, which would orphan any comment made on it. Same content-hash
      mechanism as an artifact. Refuses when the conversation holds turns the
      log does not know about, since those were submitted by hand
- [x] **The repo is its own knowledge base** — base at the root, docs published
      as artifacts, all 3311 handles preserved through the move
- [x] Separate released versions from planning milestones; record that
      development happens on `main` with tags
- [x] **Cut the documentation surface in half.** `mvp-design.md`,
      `mvp-interview.md`, `my-workflow.md`, `human-log.md` and `architecture/`
      move to `archive/` — 1141 of 2195 root doc lines, and the contradictory
      half. `mvp-design.md` was the worst offender: it declared itself
      authoritative while describing `notes/`, `wiki/` and UUID block ids
- [x] `CLAUDE.md` — the bootstrap a fresh agent loads automatically, routing it
      to `blocks.json` and the base rather than to markdown
- [x] `artifacts/state-of-play.dj` — the handoff: what exists, what does not,
      the traps that already cost something, and what to do next

## v0.1.2 — punctuation, and a bug class closed ✓

Small and self-contained. It ships before the `graph/` work rather than inside
it, because phase 6 of that plan migrates block text into nodes that carry an
immutability invariant: migrate first and 1,567 holes become permanent, and
repairing them afterwards is a content change on nodes that already have an
identity, which the spec forbids. Fix first and the migration copies correct
text.

The defect: djot has smart punctuation **in the spec**, so `---` is how djot
spells an em dash and pandoc is right to write it that way — the `.dj` files on
disk are correct and the round trip is lossless. But `inline_reconstruct.py`
has no branch for djot's `smart_punctuation` node, so every em dash, en dash,
ellipsis and curly quote the author typed is **deleted** from the parsed text.
`readme.dj`'s own title reads `kg  conversations to an addressable wiki`. This
is render-time, not canonization-time, and it corrects the whole corpus with no
file rewritten: both sides of the `kg artifact` hash comparison change
symmetrically, so no handle moves and no citation breaks.

- [x] `smart_punctuation` branch, all types — 789 occurrences in the corpus
- [x] `url` branch — a bare autolink is dropped the same way. 1 occurrence
- [x] `double_quoted` and `single_quoted`, defensively. Unhandled *containers*
      drop their children, which is the catastrophic form of the same bug.
      Unreachable today only because pandoc escapes quotes as `\"`
- [x] **An unknown tag raises instead of emitting nothing.** This is the point
      of the release. The bug is never the missing branch, it is that a missing
      branch is silent: `task_list` dropped silently, a div swallowed its
      children silently, and now this. Three times, one cause. Same treatment
      for the block walker
- [x] Parse the whole corpus as the test, so an unhandled tag announces itself.
      Sabotage-verified by deleting a branch and confirming failure
- [x] Republish the artifacts so the served text is correct
- [x] `CHANGELOG.md`, tag `v0.1.2`

## v0.1.3 — the base keeps its own sources ✓

Found by trying to see where this conversation had been branched, and failing.
The `/branch` event is in the log as two `type: "system"` lines naming the
parent session; `SKIP_TYPES` drops every one of those. So does it drop
`turn_duration` and `away_summary`. And `sessionId` is on every line and was
never stored, so nothing in the base recorded that one conversation was a
branch of another.

The importer dropping things is fine. The importer dropping things from a file
the base does not keep is not: it made the loss permanent, since the source
lived only in `~/.claude/projects/`, outside git and owned by another tool's
layout.

Not fixed here, deliberately: modelling those fields is graph work. Fixed here:
the evidence is inside the base, so a later version can go back for it.

- [x] `kg import` copies the log to `raw/<conv>/<session>.jsonl` before
      deriving anything from it. 10 MB for seven sessions
- [x] **A refresh may only grow the copy.** A log is append-only upstream, so
      content that is not a continuation means it was rewritten underneath us,
      and the import refuses rather than overwriting the record of what was
      actually ingested
- [x] An unchanged log is a no-op, so the refresh loop stays cheap
- [x] `tests/test_preserve/` — storage, growth, idempotence, the rewrite
      refusal, and that the dropped fields are recoverable from the copy
- [x] Rejected: redirecting Claude Code's log output into the repo. There is no
      setting for it, `CLAUDE_CONFIG_DIR` moves credentials and plugins too,
      and it would tie the base's durability to another tool's layout while
      solving nothing for any other kind of source

## v0.1.4 — kgb, and a man page that cannot drift ✓

Everything here is cheaper now than after v0.2, and the rename is cheaper now
than after a remote exists, so it goes first.

- [x] **The tool is `kgb`.** `kg` stays as an alias that prints a notice.
      Renamed only in the docs where a wrong command breaks someone; the
      changelog, the completed sections here, and 501 immutable conversation
      blocks keep saying `kg`, correctly. Cost four handles, measured first
- [x] `kgb lookup HANDLE` — the block, and everything citing it. Absorbs
      `tools/kgb.sh`, now deleted
- [x] `kgb last` — recent turns as `{#handle}` plus text, so a turn can be
      pasted into an agent and cited back exactly
- [x] `kgb --version`
- [x] **One source for the version, and it is the code.** `__version__` in the
      package, `pyproject.toml` reads it with `dynamic`. The reverse is normal
      and failed here: editable installs only refresh metadata on reinstall, so
      `pip show` said 0.1.0 for three releases
- [x] **A man page**, `artifacts/man-kgb.dj`, in the index as *man kgb*. One
      long searchable document, not help by level
- [x] **Fix the behavioural expectation in every place it is stated.** An agent
      with its own interface answers there; it does not also submit a turn. The
      human imports the round, which is where the handles come from anyway.
      Corrected in `CLAUDE.md`, `AGENTS.md`, `README.md`, `man kgb` and
      `state-of-play`; `kgb submit --author` stays correct for an agent with
      nowhere else to write. The specification for *how a submitted note
      reaches the agent* is still open and still lands after v0.2
- [x] **A test that the man page cannot drift** — every subcommand and long
      option must appear in it, and anything deprecated must be marked.
      Sabotage-verified

Deferred out of this release on purpose:

- The rescan subcommand (`kgb import --all` or similar). The general shape is a
  *source*: a directory plus a matcher plus an importer, so the next kind of
  input is configuration rather than code. Written up in the field notes
- Hiding the scaffolding under `.kgb/`, superseding `.kg`. Its own patch
  release, after this one
- Crediting pandoc and djot properly somewhere visible. They do the heavy
  lifting — pandoc untangles whatever markdown was actually typed, djot
  supplies a real linear-time parser with native block attributes — and the
  man page's SEE ALSO says so in one paragraph, which is not enough

## Known gaps — found and named, not scheduled

**Nothing below has shipped.** This heading used to read `v0.2.1`, which was a
planning bucket wearing a version number — so when v0.2.1 was tagged it read as
a list of what that release contained, which was the opposite of the truth.
Buckets get names here; releases get numbers, and `CHANGELOG.md` says what is
in them.

As of v0.2.2 the tool digests by named route, checks, renders three views,
resolves a handle and serves the HTML. Everything below is a real gap, listed
because it was found and named rather than discovered later.

### The migration

The one thing that makes v0.2 replace v0.1 rather than sit beside it.

**Superseded — see `docs/roadmap.md`, v0.2.4–v0.2.6.** The plan below rewrites
the old `.dj` files, and that was rejected on two grounds: it deletes the only
record that the old handles ever existed, and step 3 is a *textual* pass
deciding which `{#x}` occurrences are citations, which is the operation
CLAUDE.md forbids. The replacement rewrites nothing and adds an opt-in alias
layer instead. The numbered steps stay because their measurements still hold
and the replacement reuses most of them.

1. **Build the handle dictionary first.** Parse `conversations/*.dj` and
   `artifacts/*.dj` textually: a line that is exactly `{#xxxxxxxx}` assigns the
   following block. 5839 assignments, recovered with certainty. This must happen
   before anything is rewritten, since the `.dj` files are the only record that
   the old handles ever existed.
   - Re-deriving them from `raw/` instead does **not** work: text matching
     recovers 103 of 217, because the old canonization normalised text on the way
     to `.dj`. Zero were wrong, half simply do not match.
2. **Ingest the `.dj` files**, not `raw/`, for the same reason.
3. **Rewrite citations in one pass**: `{#x}` alone on a line stays an
   assignment; every other occurrence becomes `[-](#<new-uuid>)`. This does the
   syntax change and the target change together, so no runtime side table is
   needed afterwards.
4. **Commit the dictionary.** Old handle to new uuid, no prose, so it survives
   any purge of the corpus and outlives any single backup.
5. **Verify:** every handle resolvable before the migration resolves after; zero
   dangling; the rendered corpus is equivalent.
6. Optionally update the archived copies so the readable backup stays internally
   consistent. The pristine bytes stay in `compost-full-history.bundle`.

### `ls` and `lookup` — discuss, then maybe move to `extras/`

Same category as the build-system entry below: not a big refactor, not small
enough to do without deciding. **Discuss before moving anything.**

The argument for moving them is that once v0.2.8 puts SQL over the records,
`ls` is a `count(*)` and `lookup` is a select plus a join, so both become thin
wrappers rather than functionality — and `extras/` is where a convenience
wrapper belongs.

Two arguments against, both concrete:

- **`lookup` is in the working agreement.** `CLAUDE.md` instructs every agent
  to run `compost lookup <guid>` before answering a pasted citation. Moving it
  breaks that line, the man page's subcommand-count sentence (enforced by
  `tests/test_manpage.py`), and every recorded instruction naming it.
- **It would make the innermost loop depend on an optional tool.** The roadmap
  already protects `check` on these grounds — *"the gate must stay
  dependency-light, since `render` refuses when it fails"* — and resolving a
  citation is run more often than `check` is. `ls` has the same shape: it is
  the only thing that answers "what is actually in this base" with nothing
  optional installed, which is exactly when the question matters.

`ls` is the weaker case and might genuinely go. Decide **after** the query
layer exists and it is clear what SQL actually replaces, rather than on the
prediction that it will.

### `extras/`: `compost-cite` and `compost-why`

The additive direction for `extras/` — wrappers that compose the subcommands
rather than replacing them, so the CLI keeps the primitives.

- **`compost-cite HANDLE`** — resolve a handle and print the citation ready to
  paste, `[-](#<guid>)`, instead of printing the block and leaving the human to
  assemble it. The daily loop is: click a block, copy a handle, write a
  citation; this is the step in the middle that is done by hand today.
- **`compost-why HANDLE`** — walk the citation chain rather than reporting one
  hop. `lookup` answers "what cites this"; this answers "how did this get
  here", following `cites` backwards until it stops. The first thing that
  treats the citation layer as a graph rather than a lookup table.

Both are strictly additive: no subcommand changes, nothing is removed, and
neither needs the query layer. Wanted soon.

### The clean-room installs everything, and that is getting expensive

`tests/clean-room.sh` builds a **fresh conda environment from
`environment.yml`** on every run — that is the point of it, since the thing it
tests is whether somebody else could start. As of v0.2.7 that file pins
`graphviz=14.1.2`, which is **231 MB and 51 packages**, and v0.2.8 adds duckdb
on top (a pip wheel, roughly an order of magnitude smaller, but not free).

**The gate is now paying a large download to test features most runs do not
touch**, and it will grow with every optional tool the project adopts.

**The shape of the fix is a tiered install, mirroring the tiered *tests* that
already exist.** `tests/tier.py` distinguishes the smoke set from the fetched
corpus and reports which guarantees were skipped; the environment wants the
same split:

- a **quick clean room** — pandoc and python only, exercising everything that
  does not need an optional binary, and *saying* which checks it skipped
- a **full clean room** — everything installed, run before a release

Two ways to get there, and the choice is not made:

1. **Two conda files.** `environment.yml` minimal, `environment-full.yml`
   adding the heavy tools. Smallest change; conda has no notion of optional
   dependencies, so the split has to be by file.
2. **Move to pip and venv**, where this is a solved problem:
   `[project.optional-dependencies]` and `pip install compost[query,draw]` are
   standard and universally understood. Larger change, and pandoc and graphviz
   are *system* binaries that pip cannot install — so conda or the OS packager
   is still needed for those, and the split would be partial.

**Interim, and it is a real cost either way:** either the clean room stays slow,
or it stops covering `draw` and the query layer. Nothing measures which is
worse yet — **how long a clean-room run actually takes now, with graphviz, is
not recorded**, and that number should decide it rather than intuition.

**Not scheduled.** Candidate for v0.2.8, after duckdb lands and the problem is
concrete rather than anticipated.

### Sidechains ✓ — followed, joined, and shipped in v0.2.3

The corpus contains **zero** sidechain lines, so log order and reply order are
indistinguishable in every fixture and subagent nesting has never been
exercised. That much was already known. What was assumed with it, and is wrong,
is *where the lines are*: a subagent's turns are **not** interleaved into the
parent transcript. Claude Code writes them to their own file.

```
<session-id>.jsonl                                  the parent, isSidechain:false
<session-id>/subagents/agent-<agentId>.jsonl        the subagent, isSidechain:true
```

Measured 2026-08-19 on a session with one `Agent` call, 618 parent lines and 22
sidechain lines:

| | |
|---|---|
| uuid overlap between the two files | **0** |
| sidechain `parentUuid` resolving inside its own file | 28 of 29 — the 29th is `null`, its root |
| sidechain `parentUuid` resolving into the parent file | **0** |
| `sessionId` | identical in both |
| keys the sidechain file carries and the parent does not | `agentId`, `attributionAgent` |

So the reply chain does not cross the file boundary, and importing the parent
alone yields what it always did: no sidechain, and log order equal to reply
order. **The importer has to be told to go and get the second file.**

This entry used to say the join was the `agentId` inside the parent's `Agent`
`tool_use`. **That was a guess and it is wrong** — see the measurements below.

#### Measured 2026-08-21 on purpose-made data — the join is settled

The earlier entries here were built on one session with one `Agent` call, and
guessed. Four subagents were launched deliberately to answer the rest: two of
the **same** `agentType`, one of a different type, and one instructed to spawn
its own. Five sidechain files resulted.

**A sidechain file is per *call*, not per agent type.** Three of the four
direct launches were `general-purpose` and each got its own file. Any design
keying on agent type is wrong.

**Every sidechain has a `.meta.json` sidecar, and that is the join.** Nothing
in this repo knew these existed:

```
<session-id>/subagents/agent-<agentId>.jsonl        the turns
<session-id>/subagents/agent-<agentId>.meta.json    the join
```

```json
{"agentType": "general-purpose", "description": "…",
 "toolUseId": "toolu_…", "spawnDepth": 1, "model": "haiku"}
```

`toolUseId` names the parent's `tool_use` **block** directly, and it resolved
for all four direct launches. **`session.py` already stores exactly that key**
as `tool_use_id` on every `toolcall` and `tooloutput` node.

**So nothing has been lost, and the previous entry saying otherwise was wrong.**
It concluded that dropping `toolUseResult` cost the link in every transcript
ingested so far. It does not: the sidecar carries the join, the target is
already in the graph, and no transcript needs re-reading. There is still a
reason to capture `toolUseResult` — it holds a second, independent join
(`agentId`, which matched a file for all four) plus `outputFile`,
`resolvedModel` and `status` — but it is corroboration, not the mechanism, and
it is not urgent.

**Nesting is real, flat on disk, and makes the join recursive.** The depth-2
agent got its own file in the *same* directory, with `spawnDepth: 2` and a
`parentAgentId`. Its `toolUseId` does **not** resolve in the root transcript —
it resolves in its parent *agent's* transcript. So resolution is: look up
`toolUseId` in the log named by `parentAgentId`, or in the root session when
`parentAgentId` is absent. "Hang the sidechain off the toolcall node" is
therefore correct and recursive, and `spawnDepth` says how deep before you
start.

**`isSidechain` is a reliable discriminator.** 0 of 756 parent lines carry it
true; 5 of 5 lines in each sidechain do.

**The subagent's answer comes back into the parent, so ingesting both
duplicates it.** The `tool_result`
at launch is *not* the answer — it is 1067 bytes of launch boilerplate, because
every launch is async (`status: "async_launched"`, `isAsync: true`). The answer
arrives later, in the completion notification, and each subagent's final message
appears on **six** parent lines. So the same prose lands in the base twice: once
as the subagent's own turn, once as notification text in the parent. Decide
which one is citable before building the import, because after it there will be
two handles for one sentence and no rule saying which to use.

Note all of this is measured with `isAsync: true`. Whether a synchronous launch
puts the answer in the `tool_result` itself was not exercised and may not be
reachable any more.

**This does not block the import, and it was wrong to say it did.** Two copies
of one answer is a *semantic* question, and it belongs with the `duplicates`
edge work rather than in front of it — digest both, assert the relationship
later. The same reasoning as everywhere else here: do not resolve at import
what can be described afterwards.

One thing the `duplicates` work needs to know: **these copies are not
byte-identical and `content_hash` will not find them.** The subagent's turn is
its own prose; the parent's copies sit nested inside notification wrappers, on
`user`, `assistant`, `attachment` and `queue-operation` lines. Hash equality
catches re-imports of the same file, not this. A `duplicates` edge here has to
be asserted, or derived by something cleverer than a hash.

#### Built 2026-08-21 — what shipped, and what is still open

A transcript now brings its subagents with it, recursively, and each is joined
to the `Agent` call that launched it by a `launched` edge in an `agent` layer.

**Discovery follows references; it does not glob.** The earlier plan said to
glob `<session-id>/subagents/`, which would have been an assumption about
layout. Every transcript names its own children in `toolUseResult.agentId` —
verified at depth 2, where a subagent names *its* child — so this reads only
what the file said, which is the same contract as digesting the file itself.
That distinction is what makes it acceptable as the one exception to "digest
reads exactly the file it was given". `--no-follow` turns it off.

**The join is an equality between two things already in the graph:** the
sidecar's `toolUseId` and a stored `toolcall.params.tool_use_id`. The sidecar
is stored on the sidechain's root either way, so digesting a sidechain alone
keeps the fact and leaves the edge derivable.

A referenced file that is absent is reported and skipped, not fatal — a
transcript copied away from its `subagents/` directory is ordinary.

Still open:

1. ~~No view joins them.~~ **Done.** A launched transcript gets no page; it
   renders inside its `Agent` call, folded in HTML. One conversation is one
   page. This is the first time a view has consulted an edge to decide what to
   draw — `Graph.linked()` exists for it, generically, so the next relation a
   view wants needs no change there.
2. **`next` versus `replies_to` is still undecided** — `docs/decisions.md:136`.
   Sidechains did not settle it: within either file the two agree, and across
   files there is no shared chain to disagree about.
3. **Whether a *synchronous* launch puts the answer in the `tool_result`
   itself.** Every launch observed is `isAsync: true`; a sync one may not be
   reachable any more.
4. **The duplicated answer** — see *Duplicates are described, not resolved*.
   Not a blocker, and deliberately not solved here.

### Duplicates are described, not resolved

Nothing here collapses two records into one. The base records that two things
exist and, later, that they are related — because merging is a judgement, and a
judgement made at import is made once and silently. This entry is the home for
the cases as they turn up; the edge type does not exist yet.

Known cases, in the order they were found:

1. **Re-digesting an unchanged file.** Fresh guids, identical `content_hash`
   values sitting beside the first set, plus a second `blob` with the same
   `bytes_sha256`. `digest` reports it and stops there. Hash equality *does*
   find this one.
2. **A subagent's answer, once in its own transcript and once in the parent's
   completion notification.** Six parent lines per agent. **Hash equality does
   not find this one** — the subagent's turn is bare prose while the parent's
   copies are nested inside notification wrappers on `user`, `assistant`,
   `attachment` and `queue-operation` lines. So `duplicates` here must be
   asserted, or derived by something cleverer than a hash, and the two
   mechanisms should not be confused.
3. **The same path as both a `file` and a `blob`** — a path a session touched
   that is later digested. That one has its own edge already named,
   `represents`, and is arguably a different relation: same *referent*, not
   same *content*. Worth deciding whether `represents` and `duplicates` are one
   idea or two before either is built.

The open design question is what a view does with a `duplicates` edge, and what
`lookup` says when a handle names one of a pair. Answer that before minting any.

**One dedup rule already ships, and it is load-bearing.** `Store.load()` drops
byte-identical records (`src/store.py:163-169`) — *"two writers asserting the
same fact is agreement, not conflict"*. It reads like a convenience and it is
not; **removing it breaks the base.** Measured on a base holding one duplicated
graph file:

```
with dedup     : 3 nodes, 2 edges, 0 problems
without dedup  : PROBLEM Para … has 2 parents, expected 1
                 PROBLEM … expected one head, found 2
                 render refuses; one suite fails
```

A duplicated `contains` edge counts twice against the one-parent invariant, so
an innocent copy of a graph file would take every view down. "Load everything
and collapse later" therefore cannot simply be applied here: getting it would
mean teaching `check` to count *distinct* parent edges, which is the same dedup
logic relocated rather than removed.

So this is **rule zero of the dedup design, already implemented**, and the
design when written should account for it rather than discover it. The
question it leaves open is whether a byte-identical duplicate is a non-event
(today's answer) or a reportable condition — today nothing can tell you a base
contains one.

**A squash rule for the migrated v0.1 corpus — wanted soon.** Now that the old
corpus is in a base (v0.2.5), the same material will eventually be re-imported
in a newer shape, and the collapse should not carry the old form forward.

> **Keep the alias only for handles that were actually cited. Do not keep the
> old record formats or the old record names.**

152 aliases out of 6,601 assigned handles, because the other 6,449 name blocks
nothing refers to and a v0.1 name is only worth preserving where something
still points at it. `tools/v01_dictionary.py` already builds the dictionary
this way, so the filtered set exists; what does not exist is the rule for what
happens to the *rest* of an old record when its newer twin arrives.

Two things make this narrower than it sounds, and both should be checked before
designing it:

- **The set of cited old handles is closed.** New writing cites with
  `[-](#guid)`; the only source of `{#8hex}` citations was the v0.1 corpus,
  which is now fully imported and will not grow. So 159 is final, not a moving
  target, and the 152 aliases will never need extending.
- **Nothing is lost by dropping the rest.** `digest` keeps every old handle on
  the block itself, in `params["attr"][0]`. The aliases are an index over data
  that stays in the base, so a squash that discards uncited aliases discards
  a lookup shortcut, not a fact.

**Blocked on content matching**, which is the hard half of this whole section:
there is no way to know which new record is the twin of which old one until
that is answered, and it is worse than it looks — only 1,054 of the 6,601
handle-carrying blocks have a `content_hash` at all, because `Builder.node()`
hashes only nodes with inline content and the handle sits on a contentless
`Div`. `aliases-and-citation-parsers.md` in the notes repo has the two
candidate approaches and why both were deferred past v0.2.8.

### The transcript importer filtered at import ✓ — fixed, and held by property

*Audited and fixed 2026-08-21.* The importer discarded 369 of 796 lines (46.4%)
by handling only `user` and `assistant`, seventeen log-line keys including
`toolUseResult`, `cwd` and `gitBranch`, and 140 whole `user` lines via the
envelope rule. Every one of those was a filtering decision taken silently at
read time.

It is now lossless, and the guarantee is a property rather than a promise:

```
records_to_session(session_to_records(lines)) == lines
```

Exact, on 8 fixture sessions and 4204 lines across 13 line types. Two things
now live in the graph, deliberately:

- **`params["log"]`** on every line node — the line exactly as it was.
- **the nodes and edges** — what compost understood of it, which may improve.

A line type with no reading becomes a `logline`, because *kept* and
*understood* are different claims. An unrecognised message block becomes a
`contentblock` and is **shown**, since the point of storing it is to notice it.
Envelope lines are nodes now — recognising an envelope is about what to call
it, never about whether to keep it — and stay off the page, like empty
`thinking` nodes.

The accepted cost: a message's text is held twice, raw inside `log` and again
as parsed blocks. Raw is the source, parsed is the derivation, which is the
relationship `storage/` already has with the graph.

### Every route must say what it drops — audit the other two, and each new one

The transcript importer filtered for months and nobody could see it, because
nothing ever asked the question. Asking it once is not the fix; asking it of
every route is. **A route is not finished until it states what it discards and
proves the statement.**

`--as=claude-code-transcript` now answers with an exact round-trip. The others
have never been asked:

- **`--as=notes`.** `records_to_ast(ast_to_records(ast)) == ast` covers
  records-versus-AST and says nothing about text-versus-AST. The question is
  what **pandoc's reader** drops between the file and the AST, which is a
  different boundary and an unmeasured one. Frontmatter is the known case
  (`docs/decisions.md`) — `-s` keeps it, we do not pass `-s`. Measure the rest:
  read a corpus document, write it back, diff against the source, and count
  what never survived the *reader*. Anything found is either recorded as a
  known limit with a number or fixed.
- **`--as=pandoc-ast`.** Should be exactly lossless — it does no reading at all
  — but "should be" is what was said about transcripts. Assert it: every
  top-level key of the input JSON is represented, not just `blocks` and `meta`.

**And for every route added after these.** The check belongs beside the route,
in `tests/test_digest.py`, phrased the same way each time: everything the
source said comes back. A route that cannot make that claim ships with the
exception written down and measured, not with silence.

Note the two boundaries are genuinely different and both matter:

| boundary | question | covered by |
|---|---|---|
| bytes → parsed | did the *reader* drop anything? | **nothing, for `notes`** |
| parsed → records | did *we* drop anything? | the round-trip properties |


### Output portability — accepted at *crawl*, with walk and run written down

`docs/decisions.md` has the measurements and the reasoning; this is the
schedule. **Nothing here is scheduled**, and that is the point: the limit was
accepted knowingly, so it must not quietly become an assumption.

**The limit.** Eight node types are compost's own invention and have no pandoc
equivalent, so `views.py` chooses how to represent them — currently as `Div`
attributes and `RawBlock`. Both are format-bound. A transcript reaches djot,
html and the markdown family with its handles, authorship and tool names
intact, and reaches **latex, plain, man, typst, rst, docx and odt as
unattributed prose**. PDF goes through LaTeX, so PDF is prose too.

- **Crawl (today).** Accept it. Every real reader is in the surviving column:
  agents read djot, the human reads HTML, markdown is committed to GitHub. A
  prose-soup PDF is expectation management, not a missing feature — which is
  why the man page says so out loud.
- **Walk.** A per-node-type fallback using *visible text* rather than
  attributes, so any writer carries the meaning. Legal: views are read and
  never re-ingested. Build it when a format is actually wanted.
- **Run.** Give the out-mapping the same modularity the in-mapping already
  has — a node type registering its own rendering beside its reader, instead
  of an `if t == …` chain plus two module-level sets. Do not start here; it is
  architecture for its own sake without a second format to serve.

**If there is capacity for work of this shape, spend it on input instead.**
Getting more *input* formats understood — *What pandoc actually gets us*, above
— returns more than making a transcript survive to LaTeX. Reading many kinds of
document into one addressable graph is the point; emitting many kinds is not.

### `file` and `blob` nodes have no view

Both are uncontained, so they appear in no document tree. Either the session
view grows a "files touched" section assembled from `touches` edges, or
entities get an index of their own — a blob index would also be the natural
place to show "these four documents came from the same bytes".

The two node types are settled and are **not** to be merged: a `file` is a
path a session touched, a `blob` is bytes in `storage/`. The prior art and the
reasoning are in `docs/record-format.md`. When one path is both, a `represents`
edge joins them; nothing mints one yet, and doing so means matching an
`original_name` against a `path`, which is a guess worth designing rather than
writing in passing.

### Provenance is on every edge and on only two node types

**Deferred until the planned work through v0.2.8 is finished**, then decided
deliberately rather than by omission. See `docs/roadmap.md`.

As of v0.2.4, `created_at` and `tool_version` are top-level on **every edge**,
ingest-time and built alike, and on exactly **two node types** — `alias` and
`unresolved_citation`. Every other node has neither.

| | `created_at` / `tool_version` |
|---|---|
| every edge | yes |
| `alias`, `unresolved_citation` | yes |
| `Para`, `document`, `blob`, every other node | no |

**Two defensible rules are in tension, and the shipped state follows neither
cleanly.**

- *Provenance belongs where nothing else records it.* Records written by
  `compost layer` have no other trace of when they were made; ingested nodes
  are reachable from a `blob` carrying `imported_at` and `route`. Under this
  rule the two node types are right and **ingest-time edges should not have it
  either** — and `docs/roadmap.md` says those are kept "for uniformity", which
  is the other rule wearing this one's clothes.
- *Uniformity: every record says when and by what it was written.* Simple to
  state, simple to query, nothing to remember. Under this rule **every node
  should carry it too**.

**Why it was not settled in v0.2.4.** The plan's text said `Builder.node()`
should set provenance on every node; the storage measurement published beside
it — `+27.1%` overall, `+78.8%` on edges — was computed with provenance on
edges only. The two contradicted, and the narrow reading is what shipped and
what the published number describes.

**What deciding it costs.** Widening to every node changes every record written
from then on, so a base spans both shapes — which `schema_version` exists to
make survivable, and which is a good first exercise of it. It does **not** move
any `content_hash`: node hashing is `canonical([type, params, content])` and
provenance is top-level, which is the whole reason it was put there. Re-measure
the storage figures either way, because the published ones stop being true.

Note the reverse direction is also open: dropping provenance from ingest-time
edges would shrink the largest category of record in any base.

### `check` does not verify `storage/`

It reads records and stops there, so a blob whose bytes were altered on disk
is not detected — even though `bytes_sha256` is precisely what would detect
it. Storage is meant to be verifiable and currently is only verifiable by
hand. Hashing every source on every `check` is the obvious objection; a
`--deep` flag, or folding it into the `query` work, is the obvious answer.

### Short handles

The measured cost of full uuids is 21.7% of a djot view, and 60–75% on small
structurally dense files. Collision is the trigger to watch: 0.5% at today's
~6,700 blocks, 17% at 40,000, 68% at 100,000, and `check` already rejects a
base where two nodes share a handle.

**This entry used to call the optimisation non-breaking**, because a resolver
already accepted any unambiguous length and had a test. That resolver has been
removed — see `docs/decisions.md`. It resolved prefixes in the graph while the
HTML view emitted the href verbatim, so a short citation was a dead anchor for
anyone clicking it, and uniqueness was recomputed per query, so a prefix could
stop resolving as the base grew with nothing to report it.

So this is **not** a free size win, and it is not a change to start from the
resolver. It needs a design that answers what a view does with an abbreviated
href and what `check` does when one stops resolving, and it should start from
someone actually finding long handles painful rather than from the 21.7%.

Note that shortening what is **stored** is a different question from shortening
what is **typed**, and the second is the one with obvious value. See *Handle
resolution as a separate tool* under Later: expanding a prefix before the
citation is written gets the convenience without putting an abbreviation
anywhere near the base.

### What pandoc actually gets us — a research programme, not a feature

The `pandoc-ast` route exists as of v0.2.2 and is the instrument for this; the
experiment itself has not been run. The north star: **if we push all kinds of
documents through pandoc, how reliable is the graph we get?**

That is not yet a question with an answer, and sharpening it is part of the
work. What is decided is the method, because the value is entirely in the
record-keeping:

- a curated set of documents pandoc claims to read — html, djot, man, LaTeX,
  org, rst, docx — chosen for variety rather than volume
- for each one, the **exact invocation**, recorded next to it, not remembered
- for each one, an **expert review** of where the AST diverged from what the
  document meant: not "did it parse" but "did it parse into the right thing"

These are curated and reviewed, so they cannot be fetched: they belong in
`tests/fixtures/` as a tracked set, alongside the notes that justify them —
one directory per case holding the source, the invocation, and the review.

The output is knowledge, not a feature. It may well conclude that no single
mechanical route can cover this class, which was the going assumption when the
route was built. `route` is recorded on every root node so the question stays
answerable after the fact.

### Subcommands v0.1 had and v0.2 does not

`submit`, `new`, `last`, `artifact`. Both daily-loop gaps are closed: `lookup`
resolves a pasted handle without grepping, and `serve` reads the HTML view
without a file manager. Nothing here is missed yet — `new`, `submit` and `last`
belonged to a submit path that v0.2 replaced, and `artifact` is its own
milestone below.

`serve` runs in the foreground. Detaching it — a `--daemon` flag, or a pid file
with `--stop` and `--status` — is deliberately not built: it is state living
outside the base, and a terminal tab has covered it so far. Build it when
leaving a tab open actually becomes the annoyance.

### Smaller, but named

- **Empty `thinking` nodes** are stored and not rendered. All 491 carry no text
  because Claude Code persists only a signature; other agents do emit text. The
  view will need to show them the day one does.
- **Re-import identity.** A second digest of an unchanged file mints fresh
  guids and produces matching `content_hash` values that sit beside the first
  set, plus a second `blob` with the same `bytes_sha256`. `digest` now says so
  rather than resolving it. Expected, tested, and still the unanswered
  identity question — the duplication is at least visible now, which is a
  precondition for answering it.
- **Immutable notes are a promise nothing enforces.** `--as=notes` is meant
  for the note that is added and never edited, but no mechanism distinguishes
  it from anything else: nodes are immutable in practice because guids are
  minted per import, not because anything refuses a change. Either it stays
  documentation or it becomes a param `check` acts on. Do not let the route
  name imply the second.
- **Citations attach to blocks, not to references.** A `{@}`-era limitation that
  survives the move to links: two citations in one paragraph are two edges from
  the same source node, and nothing distinguishes which reference is which.
- **`tests/corpus/` is fetched, not tracked.** A fresh checkout runs 6 of the
  526 round-trip documents until `./tests/fetch-corpus.sh` runs; the pins are
  in `tests/corpus.txt`. `vendor/pandoc-types` is a separate optional clone
  that no test reads — it is the AST grammar, kept for a human to consult.
- **One pandoc call per text block** on session import — 19s for 7 sessions.
  Batching is available if it ever matters.

### Three pandoc defects, recorded and not worked around

They live in pandoc's *writer*, downstream of an AST-to-AST property, so they
sit outside the boundary the tests check. Repairing them would pull them inside
it and break the round-trip by construction.

- a code block inside a **tight** list item is destroyed; a loose list survives
- `<!-- -->` injected between adjacent lists re-reads as a `RawBlock`
- inline code adjacent to raw inline HTML is merged into it

## Next — inherited from v0.1, mostly superseded

- [ ] **Are the root markdown files views, and should they be tracked?** If
      `artifacts/*.dj` is the source and the `.md` is generated, then
      `README.md` is a view and views are not tracked — but an untracked README
      is a strange thing for a repository, and GitHub renders the `.md`. Worth
      a conversation rather than a decision. One measured input: `graph.dj`
      through pandoc to markdown and back keeps only **79 of 99** block hashes,
      so "regenerate the markdown whenever we need it" is fine for reading and
      is *not* free for republishing — 20 blocks would take new handles

- [ ] **Decide the id scheme before node types land.** Handles are
      `secrets.token_hex(4)` — random, never derived from content, so identity
      is recorded only in the `.dj`. Random ids carry birthday risk (14% chance
      of a collision per render at 10x, certain at 100x) and cost more
      characters than they need to. A base36 counter over a single ingestion
      queue removes collisions outright and needs no fixed width: 3 characters
      today, 4 at 100x. Open: one check character or two, since a dense id
      space turns a mistyped handle from a dangling reference into a silent
      citation of the wrong block. Canonization-time, so it is one-way
- [ ] **Docs are still published twice** — `README.md` and `artifacts/readme.dj`
      hold the same words, and only `kg artifact` keeps them in step. The
      obvious end state is that the `.dj` is the source and any `.md` is
      generated for GitHub, but that inverts the pipeline and was not worth
      doing in a hurry. Until then: **republish after editing**
- [ ] **Em dashes become `---` on disk.** Pandoc's djot writer applies smart
      punctuation and `-t djot-smart` is rejected, so an em dash the author
      typed is stored as three hyphens and the README's title reads "kg ---
      conversations". A restore is possible because pandoc *escapes* a literal
      `--` as `\--` while writing a converted dash unescaped, so the two are
      distinguishable — but a naive substitution would also rewrite code
      blocks, so it needs fence tracking. Canonization-time, so it changes
      handles for any block containing one
- [ ] *Superseded by v0.1.2 above, and kept because it is cited.* The entry
      above is wrong on every count: the `.dj` is correct, `---` is djot's
      spelling of an em dash, the round trip is lossless, nothing needs fence
      tracking, and it is render-time rather than canonization-time. The damage
      is in `inline_reconstruct.py`, which drops the character entirely
- [ ] **Reply affordance in the HTML** — a button that puts you in a draft for
      the block you clicked. The handle is already copied; the missing half is
      not having to switch to a terminal
- [ ] **Open todos view** — "what was I in the middle of". Block type is already
      in `blocks.json`; render-time, so it works retroactively
- [ ] **Backlinks are per-note, not per-block** — a target citing eleven blocks
      shows the same link eleven times with no indication of which block each
      points at. Noise at exactly the moment it should be useful
- [ ] `pytest` wiring and one runner for all five suites; no CI yet
- [ ] Persistent djot worker — `npx` costs ~1 s per spawn and `kg render` parses
      every file twice. One-file-per-conversation keeps this tolerable, but it
      dominates render time
- [ ] Remove `src/ingest/block_schema.py` (legacy; canonize does its own)
- [ ] Restore a copy-confirmation flash outside the repaint cycle
- [ ] Decide whether `+++` should be the *default* on headings, with a
      modifier for the single block

## Milestone: artifact generation

The next release after v0.1.1. Previously labelled "v1", which suggested a
maturity nothing here has yet.

The point where an LLM writes rather than converses. Nothing below is
deterministic.

- [ ] Explicit generation: hand `blocks.json` to an agent, take an artifact
      back. No embeddings — a project corpus fits in context
- [ ] **README and TODO as generated artifacts**, in djot, read from the served
      pages. The bootstrap has to sit *outside* the base, since a guide living
      inside it is only findable after you know the base exists
- [ ] Record lineage on every generated block (`DERIVED_FROM` → source block)
- [ ] **Lineage validation** — a block that cites nothing is invalid. Open:
      reject at write time, or flag visibly at render time (§13 Q3b)
- [ ] **Id-preserving regeneration** — unchanged blocks must keep their ids or
      every note referring to them is orphaned. This is the delta algorithm in
      `archive/architecture/delta_ingestion_and_block_versioning.md`
- [ ] Render agent-written general knowledge differently from note-grounded
      blocks; they carry different trust
- [ ] Curated index pages (agent-written entry points, distinct from views)
- [ ] Cost control: which model, and what stops a large note cascading

## Later — agreed in principle, not scheduled

Previously labelled "v2+".

- [ ] **Semantic linking** (§13 Q1) — which page a note affects beyond the
      blocks it cites. Needs embeddings or LLM reading; its own initiative.
      Keep inferred edges in a distinct type from reference/lineage edges
- [ ] **Context assembly** — "everything about topic T", by walking the wiki
      hierarchy and pruning. Pruning strategy undesigned
- [ ] Import foreign markdown: chat exports (`.md` from a plugin, `.json` from
      captured API traffic). ~10–20 conversations for one publication topic.
      Needs file-level provenance — a different tier from hand-written notes
- [ ] Todo state store — flipping a checkbox must not regenerate the wiki.
      Note that a todo written in an immutable note cannot be marked done
      there; the state needs a mutable home
- [ ] "UI notes" — UI actions submitting notes on your behalf, as an event log
- [ ] Archiving source content (page, video, image), not just the URL
- [ ] Browser extension for capture
- [ ] nvim plugin — tag pickers, metadata. Premature until the plain workflow
      has been run for a while
- [ ] Sources view per topic — ships with context assembly
- [ ] Mobile / remote serving
- [ ] Tags — may never be needed; hierarchy plus agent-written index pages may
      cover it

### Handle resolution as a separate tool, not a feature of this one

The idea is good and is being kept. What was removed in v0.2.1 was one *place*
to put it, not the idea itself: typing a few characters instead of 36 and
getting the block you meant is worth having.

The thing to notice about the failure is where the resolution happened. A
resolver inside `compost` meant abbreviated handles reached stored text and
rendered views, and both inherited the ambiguity — an abbreviated href is a
dead anchor to anyone clicking it, and a prefix that stops being unique as the
base grows has no moment at which anyone is told. **Resolving at the keyboard
inverts all of that.** A separate tool that expands a prefix to a full guid
*before* the citation is written leaves the base entirely canonical: the view
gets a whole guid, `check` gets a whole guid, and a collision surfaces
immediately to a person who can simply type more characters, instead of
silently years later to nobody.

So the shape wanted is a small independent thing — `lookup`-adjacent, a shell
function, an nvim mapping, a separate binary — that reads a base and prints a
guid. Something a person or an editor calls; nothing the format knows about.

It is not scheduled, because prefixes are only the easiest case of a general
problem: a human-friendly name standing in for a canonical id. Aliases for
documents and sessions want the same machinery, and a frequently cited block
deserves a name rather than a shorter number. Designing it properly means
answering things that have not been thought through — where aliases live, given
that a base is immutable and an alias is by nature mutable and renameable;
whether they are records or a side table; who resolves them and at what moment;
what happens to an alias whose target is re-imported under a new guid; and what
the tool does with an ambiguous one. Those answers should come from an alias
system designed on purpose, not be back-derived from a prefix matcher.

---

## Dangling references

*Case 1 and case 3 are now reported by `kg check` (v0.1.1).* The rest stands.

Found by submitting this repo's own docs into a knowledge base: `kg render`
reported *"1 referenced"* for the example reference in `README.md`, whose
target uuid exists in no note. The backlink index happily created an entry for
a block that was never submitted. Nothing warned, nothing rendered, nothing
broke — the reference simply pointed nowhere, silently.

**Why it matters.** Notes are immutable, so a bad reference can never be
corrected in place; it stays in the corpus forever. Without detection you only
discover a typo by going to look for one, and the count can only grow.

### The four ways a reference can dangle

1. **Target never existed** — a typo, or a reference pasted from somewhere
   else. The uuid appears nowhere in the corpus. *Possible today.*
2. **Hash mismatch** — the uuid resolves but the content hash does not. Cannot
   happen while every block lives in an immutable note. *Becomes real in v1,
   when wiki pages are mutable.*
3. **Target file removed** — notes are immutable but a file can still be
   deleted from the repo. *Possible today.*
4. **Regeneration orphaned it** — a wiki page was rewritten and unchanged
   blocks were not given their old ids back. *v1; prevented by the
   id-preserving regeneration item above, and the reason it is not optional.*

### Options

- **`kg check`** — scan every note's references and report each dangling one
  with its kind, source note, and target. Render-time, so it works
  retroactively on the whole corpus. Report-only by default; an exit code for
  scripting. This is the cheap first move.
- **Show them while reading** — style dangling references distinctly in the
  HTML. Better than a separate command for the common case, because you notice
  without having to think to look. Both are worth having; they catch different
  moments.
- **Warn at submit** — check a note's references as it is canonized and print a
  warning. Must *not* block: notes are immutable, and refusing a submission
  over a typo would lose the writing. Warning only.
- **Resolve case 2 from history (v1)** — a hash that no longer matches the
  current block is not an error, it is a reference to an *earlier version*.
  Resolve it from git rather than reporting it broken. This is the annotation
  durability guarantee in
  `archive/architecture/delta_ingestion_and_block_versioning.md` §4.6, and the reason
  references are pinned in the first place.

Case 2 is the one to keep in mind: once the wiki is mutable, the *majority* of
"dangling" references will be perfectly good references to superseded content.
A checker that cannot tell the difference will be noise, and noise gets muted.

---

## Open questions

Carried from the archived v0.1 spec.

- [ ] **Q1** How does an agent know which wiki page a note affects?
      *Deferred as its own initiative — see v2+ semantic linking.*
- [ ] **Q2** What is the unit of regeneration — one page, a page and its index,
      a transitive neighbourhood? Interacts with Q1
- [ ] **Q3b** Lineage: reject at write, or flag at render?
- [x] **Q9** Where do agent replies live? *Resolved 2026-08-06: in conversations,
      which either party writes. The boundary moved from authorship to
      mutability.*
- [x] **Q10** Are chat logs citable sources? *Resolved 2026-08-06: yes,
      deliberately. Decided against the recommendation; reversible at render
      time because authorship is recorded, so no migration if it goes wrong.*
- [ ] **Q4** Is the paragraph the right block unit? Agreed as default, but
      prose sometimes packs several thoughts into one
- [ ] **Q5** Which model generates the wiki, and what caps the cost?
- [ ] **Q7** Link capture detail — assumed a source is a line inside a note,
      promotable to its own page
- [ ] **Q8** Where is this design over-engineered? *(never answered)*
- [x] **Q3** Reference syntax — resolved: `{#uuid:hash}`, always pinned
- [x] **Q6** Directory naming — resolved: `raw/`, `notes/`, `site/`

---

## Before artifact generation: use it for a week

Write real notes, react to them, see whether the loop holds. Everything after
this point is expensive to change and cheap to postpone, and the corpus you
build now is what tells us whether generation should work the way we assumed.

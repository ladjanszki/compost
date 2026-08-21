# CHANGELOG

This file overarches versions. Entries below the `v0` marker describe the
LadybugDB-centric architecture that `v0` closes out.

## Unreleased — transcripts stop filtering, and bring their subagents

`--as=claude-code-transcript` was discarding **46% of a real transcript** and
nobody could see it. It is now lossless, and the guarantee is a property:

```
records_to_session(session_to_records(lines)) == lines
```

Exact, over 8 fixture sessions and 4204 lines across 13 line types.

### What was being dropped

Audited against one real 796-line log:

- **369 of 796 lines (46.4%)** — only `user` and `assistant` reached the graph.
  `attachment` alone was 184 of them, the second most common line type in the
  file.
- **Seventeen log-line keys.** A turn kept `author`, `timestamp` and `uuid`;
  `isSidechain`, `userType`, `entrypoint`, `cwd`, `sessionId`, `version`,
  `gitBranch`, `session_id`, `requestId`, `effort`, `promptId`,
  `toolUseResult`, `sourceToolAssistantUUID`, `permissionMode`, `origin`,
  `promptSource` and `classifierMetaLines` did not.
- **140 whole `user` lines** via the envelope rule. Their content survived — a
  `tool_result` folds into its toolcall — but the line's identity went with it.
  Recognising an envelope is about what to *call* it, never about whether to
  keep it.

None of it was data loss in the strict sense: `storage/` had the bytes. It was
a base built on a filtered log, with nothing to show what was missing.

### What replaced it

Every line becomes a node carrying its own original JSON in `params["log"]`.
Two things now live in the graph and they are different on purpose: `log` is
the line as it was and never changes; the nodes and edges are what compost
understood of it and may improve.

A line type with no reading becomes a **`logline`** — *kept* and *understood*
are different claims, and an importer only gets to make the first. An
unrecognised message block becomes a **`contentblock`** and is **shown**, since
the point of storing it is to notice it exists; the old `else` was silence.

Accepted cost: a message's text is held twice, raw inside `log` and again as
parsed blocks. Raw is the source, parsed is the derivation — the relationship
`storage/` already has with the graph.

Views are unchanged. Loglines and empty envelope turns are stored, addressable
and deliberately not rendered, the same treatment empty `thinking` nodes
already had.

### A transcript brings its subagents with it

Digesting a Claude Code log now digests the subagent transcripts it names,
recursively, and joins each to the `Agent` call that launched it with a
`launched` edge in a new `agent` layer. `--no-follow` digests exactly the file
named and nothing else.

This is the only place `digest` reads a file it was not handed, and the reason
it is allowed is that **it is not a guess**. The plan had been to glob
`<session-id>/subagents/` — an assumption about layout. Measurement showed
every transcript names its own children in `toolUseResult.agentId`, including
at depth 2 where a subagent names *its* child, so discovery follows references
instead. Following a reference and globbing a directory are different acts, and
only the first has the same contract as digesting the file itself.

The join is an **equality between two things already in the graph**: the
`.meta.json` sidecar's `toolUseId` and a stored `toolcall.params.tool_use_id`.
The sidecar is stored on the sidechain's root regardless, so digesting a
sidechain alone keeps the fact and leaves the edge derivable when the other end
arrives — the same shape as citations being derived from stored links.

`toolUseResult` reaches the graph only because the importer stopped filtering,
so that change was a prerequisite rather than a coincidence.

A referenced file that is absent is reported and skipped, not fatal: a
transcript copied away from its `subagents/` directory is an ordinary thing to
digest.

Verified against a real session with four subagents including one nested two
deep, which is joined to a tool call inside *its parent agent's* transcript
rather than the root's.

### Tests

`test_session` 9 → 11: the round-trip, and that no line type is filtered.
Sabotage-verified twice, and the second one matters — dropping a single key
from a stored line still returns the right *number* of lines and fails anyway,
because the property compares content.

`test_session_views` 10 → 11, with the deliberate non-rendering of envelope
turns stated as its own guarantee rather than left as a silent exclusion.

`test_digest` 13 → 17 for the subagent behaviour, on a hand-built parent and
sidechain pair. Written rather than bleached from a real one: the join spans a
`.meta.json` sidecar the bleacher does not process, so its `toolUseId` would
stop matching the parent's remapped `tool_use.id` and the fixture would test
nothing.

Adding that fixture broke `test_records`, which rglobbed `*.json` across the
whole tree and swallowed the sidecar. Its sweep is narrowed to `ast/*.json` —
"a pandoc AST" is a claim about what is in a file, not about its extension,
which is the mistake `digest` itself stopped making this release.

## v0.2.2 — 2026-08-21 — ingestion is asked for by name

`compost import FILE...` is gone. Ingestion is `compost digest --as=ROUTE
FILE...`, the route is required, and **nothing about it is inferred from a file
extension**.

### The route is named

`import` chose its reader from the suffix. Two faults, and the second forced
the change: the fallback was not "markdown" but *anything at all*, so a PNG
reached pandoc's markdown reader and came back as a pandoc error rather than a
compost one; and `.jsonl` is a container, not a format, so the suffix stops
naming a reader the moment a second kind of JSONL exists. That moment is
close — `claude --print` will produce single text turns, a different material
from a session log with its tool calls.

| route | reads |
|---|---|
| `notes` | prose, as `commonmark_x` with the three extensions off |
| `claude-code-transcript` | a Claude Code session log, the whole `*.jsonl` |
| `pandoc-ast` | a pandoc JSON document somebody else already produced |

`notes` is not a new reader — it is the dialect `decisions.md` settled in v0.2,
flags unchanged. What changed is that it must now be asked for. `pandoc-ast`
is genuinely new, and it is the *narrowest* route rather than the broadest:
`ast_to_records` already takes that shape, so there is no reading step in it to
be wrong. Whatever pandoc invocation produced the file stays outside the tool,
where the person who wrote it can inspect it.

`src/routes.py` is now the only module that knows how to read anything.
`store.py` no longer invokes pandoc.

### Storage is a blob store

Every ingested file lands under a freshly minted `storage/GUID.EXT`, and a
`blob` node records `original_name`, `stored_as`, `bytes_sha256`,
`imported_at` and `route`. A `derived_from` edge in a new `ingestion` layer
joins the document root to it, and the root records the route it came by.

Content-addressed names were the alternative and were rejected: they are
verifiable and idempotent, but they cost the invariant that *every object has
a guid*, which is worth more here. The duplication that buys is closed by
reporting rather than by naming — `these bytes are already in N blobs` — since
deciding two copies are one thing is a later layer's call. The extension
survives so a file pulled back out of `storage/` is still usable by hand; it is
a decoration and nothing routes on it.

**The original name is no longer where the file lives.** `records.blob_of()`
follows the edge, and anything reconstructing a storage path from
`params["source"]` is guessing.

Storage and graph filenames are different uuids on purpose. If either were
derivable from the other, something would eventually derive it — which is
suffix routing wearing a different hat.

### A batch is all or nothing

Nothing is written until every input has been read and parsed. This falls out
of minted names: under content-addressed storage a half-finished batch was safe
to re-run, and now it is not — the files that had landed would come in again
under fresh guids. Validating first is what makes it safe to pass a glob.

Directories are refused rather than walked, pointing at the shell. `find` is
better at recursion than a flag would be, and the caller already has an opinion
about how deep to go.

### Two things this found

**View filenames collided silently.** `render` names view files from the
source name, so two documents called `notes.md` overwrote each other's pages
and `render` reported writing files that held the wrong document. Nothing had
noticed because the old name-keyed storage *accidentally* guarded it by
refusing a second file with the same name and different bytes; minted names
removed that guard. Colliding stems now take the root's handle. A counter was
rejected — it renumbers when an unrelated document arrives, moving every URL
in the browser, while a handle is the document's own.

**`file` and `blob` are different nodes.** A `file` is a path a session
touched — may not exist, no bytes held. A `blob` is bytes in `storage/`. Every
vocabulary that has faced this splits it the same way, and the shared answer is
that a path is a locator rather than a thing: PROV-O, NFO, FRBR and DCAT are
recorded in `docs/record-format.md` as the reason, with the distinctions
borrowed and the namespaces deliberately not. A `represents` edge will join
them when one path is both; nothing mints one yet.

### Deferred on purpose

**Sidechains are still not followed.** `--as=claude-code-transcript` reads
exactly the file it is given, so storage and graph stay 1:1. The join between
a parent and its subagent is a second kind of fact and belongs in its own layer,
asserted explicitly, rather than smuggled in as a side effect of reading a
file. `TODO.md` names one thing to check first: where `agentId` actually
appears on the parent side, since that decides whether the link is recoverable
from transcripts already ingested.

**The pandoc research programme is written down, not run.** The route is the
instrument; the experiment — a curated set of documents with the exact
invocation and an expert review of where each AST diverged from what the
document meant — is a `TODO.md` entry with a method and no schedule.

### A filename is only a filename

Found by probing the new command rather than by any suite. A relative path
beginning with a dash reached pandoc as a flag — `-dash.md` parsed as `-d
ash.md`, i.e. `--defaults ash.md` — and surfaced as a pandoc error about a
file nobody had named. Paths are resolved before pandoc sees them, and `--`
now ends the options so such a name can be given at all. Both halves are
sabotage-verified, and the test uses a *relative* path deliberately: an
absolute one already begins with a slash and cannot exercise the bug.

Also confirmed along the way: a source with no extension at all is stored
under a bare guid, which is correct — the extension is decoration and never a
fallback.

### Tests

`tests/test_digest.py`, thirteen ingestion guarantees, each sabotage-verified:
the route is never guessed, the extension decides nothing (checked by making it
lie — markdown named `.jsonl`), a batch is all or nothing, a document reaches
bytes that hash to what the graph claims, duplication is reported, storage and
graph names never coincide.

`test_views` now builds its base through the real ingestion path rather than by
hand, which is what surfaced the filename collision above: a view test that
builds its own records can only check the views against itself.

Twelve suites, up from eleven. View guarantees 5/5 → 6/6. Storage stays at
ten: two cases whose mechanism is gone were replaced, not added to.

## v0.2.1 — 2026-08-20 — the daily loop closes

### The man page cannot drift again

`tests/test_manpage.py` holds `docs/man-compost.md` against the dispatcher, in
both directions and down to the number spelled out in prose. Ground truth is the
program: every name is offered to `cli.main` in a scratch directory and has to be
routed somewhere. v0.1.4 shipped a test with this name, the rewrite dropped it
for a promise in a docstring, and what rotted first was the count — five above a
list of six, copied from there into `CLAUDE.md`. Six sabotages, all caught.

It found one thing on its first run: `-h` and `help` are accepted and were
documented nowhere.

### The acceptance test is visible again

`run.sh` reads each suite's last line, and `test_records` printed its coverage
histogram *after* its verdict — so the table reported node types and hid the
520/520 the whole record format rests on. The verdict prints last now, and
`run.sh` checks that the line it picked starts `N/M `, which makes the
convention enforced rather than remembered. Sabotage-verified with a suite made
to end on a stray line.

### `compost lookup HANDLE`

Print the node a handle names: guid, type, source file, and the node's own
text. This is the half of the daily loop that had no tool — `CLAUDE.md` told an
agent to "resolve it from the graph" and left it to write its own JSONL scan.

**The handle is the whole guid**, and `lookup` does not report what cites the
node. Both of those were built first and then deliberately removed before
release, which is worth recording because the reasons generalise.

*Prefix resolution.* `records.py` had grown a resolver taking any unambiguous
prefix of 8 characters or more, and `decisions.md` had leaned on it to argue
that short handles were a free future win. They are not. The resolver worked in
the graph while the HTML view emitted the href verbatim, so a shortened
citation resolved for a tool and was a **dead anchor for a person clicking
it**. Uniqueness was recomputed per query over whatever was loaded, so a prefix
unambiguous today collides as the base grows — and since `check` never looks at
citations, nothing would have said so. It was an optimisation built ahead of
any measured pain. `HANDLE_RE` now matches a whole uuid, so a prefix is not a
short handle, it is an ordinary link, by construction.

*Backlinks.* `lookup` briefly printed what cited a node, which meant calling
`citation_edges` on every query. That function had never been called by the
program before — only by its own tests — so the `cites` layer `decisions.md`
documents still exists nowhere in a real base. Deriving it at query time would
have been the citation layer arriving by accident, ahead of its design, and a
layer built that way is harder to replace than one that was never built.

What remains is exact, small, and does not gate on `check`: a view asserts the
whole graph is sound, a query answers one question from what is on disk, and
refusing because an unrelated file has a dangling edge makes a broken base
harder to debug rather than safer. Seven guarantees.

### `compost serve [-p PORT]`

The HTML view in a browser, on `http://127.0.0.1:7373`, foreground until
interrupted.

**It does not render**, and that is the difference from v0.1, where `serve`
meant "render, then serve". Keeping them apart is not only simpler, it puts the
guarantee in a better place: `render` is the only thing that writes views and it
already refuses on a graph that fails `check`, so every file being served was
produced from a graph that was sound. Delivery needs no opinion of its own,
`serve` is a directory and a port, and it cannot fail for graph reasons. It also
matches what `lookup` does — queries and views hand you what exists; only
`render` asserts soundness. Run `render` in another terminal, refresh the page.

Two choices worth their own lines. The socket binds **loopback only**: a
knowledge base is not something to put on the local network by accident, and
`0.0.0.0` is exactly that accident. And responses carry `Cache-Control:
no-store` while revalidation headers from the client are dropped rather than
answered — `Last-Modified` is accurate only to the second, so a `render` landing
in the same second as your last page load is otherwise answered `304 Not
Modified` and you refresh onto yesterday's page. That was reproduced, not
guessed, and the suite reproduces it: same mtime, different bytes, must serve
the new bytes.

The default port is 7373 rather than v0.1's 8000, which is `irdmi` in
`/etc/services` and the default for `python -m http.server` and Django both.
7373 is unassigned, outside the ephemeral range macOS allocates from, and not
the default of anything common. `-p` overrides it.

Nine guarantees, five sabotages, including that nothing outside the served
directory is reachable.

### Test material in two tiers

`tests/fixtures/` is an 80 KB **smoke set**: the documents the suites name
directly — the one markdown file that reaches every sabotage, a hand-built AST
no reader can produce, three notes, and one transcript trimmed to the shortest
prefix carrying text, tool_use, tool_result and thinking. Every suite runs on a
bare clone.

Everything else moved to a separate repository and is fetched at the commits
pinned in `tests/corpus.txt` by `./tests/fetch-corpus.sh`, alongside rust-book.
A commit SHA is already a hash over the tree, so the pin is the checksum. That
takes the round-trip from 5 documents to 525.

Four guarantees assert volume — over 1000 prose blocks, over 100 thinking
nodes, over 5000 nodes, over 100 tool calls. They report themselves **skipped**
when the corpus is absent rather than being weakened to fit the smaller set,
and `run.sh` ends with `corpus present` or `corpus ABSENT`, because 5/5 and
525/525 are the same shape.

The split happened now rather than later on purpose: this repository has had
material removed from its history retroactively, which is expensive and leaves
residue on any remote it was pushed to, and test data only grows.

### `tests/clean-room.sh`

What the suites cannot tell you: whether somebody else could start. It clones
what is actually pushed, builds an env from `environment.yml`, installs, runs
both tiers, and exercises every subcommand. `--with-agent` adds the one check
the rest of it structurally cannot make — every command in the script is the
*correct* sequence, hardcoded, so it passes whether or not `CLAUDE.md` mentions
any of it. So it asks a fresh Claude, in the clone, with only `CLAUDE.md` in
context, to name the fetch command, the runner, and what the runner's last line
means. Exactly one file is auto-loaded into a fresh session, measured.

Not wired into `run.sh` and not automated. `DEVELOPMENT.md` ties it to the one
moment the answer matters: before tagging.

### Smaller

- The v0.1 corpus and 85 MB of another project's material were removed from
  this repository's **history**, not merely deleted — they were personal notes.
  A clone is 3.9 MB now, was 56 MB. The bytes are kept privately, and
  `docs/migration.md` says so up front rather than describing files a reader
  will not find.
- `compost import` with no arguments printed `usage: store.py import <file>...`.
  The program name comes from `argv[0]` now, so it is right through the CLI and
  still right when the module is run directly.
- `AGENTS.md` is folded into `CLAUDE.md` and gone. It was written to travel with
  a base and teach an agent to read one without this repository, but `compost
  init` never shipped it and no base exists yet, so its only possible readers
  already had `CLAUDE.md`. The three rules it alone carried moved across:
  property tests over snapshots, do not repair pandoc's output, and
  reconstruction is not viewing.
- The development env is `compost`, built from `environment.yml` with the CLI
  installed by `pip install -e .`. The `knowledge-graph` env it had drifted into
  is deleted. `CLAUDE.md`, `DEVELOPMENT.md` and the man page name it now, along
  with the pandoc floor — the base conda env has 3.8 and the suites pass there
  anyway, so nothing warned you.

## v0.2 — 2026-08-18 — nodes and edges, and none of the old code

**Everything was rewritten.** Not a refactor: no line of the v0.1
implementation survives. `src/` is a different program with a different storage
format, and the v0.1 corpus is no longer readable by it.

### The waist

Storage is **nodes and edges as JSONL**, and every view is generated from those
records and from nothing else. Djot is gone as a storage format; `blocks.json`
is gone; the `.dj` files under `conversations/` and `artifacts/` are no longer
written or read.

One rule does the translation: a node stores the pandoc constructor tag and
every non-block field verbatim, and block-valued fields become children joined
by `contains` edges. So there is no per-constructor special casing and no
mapping table to drift. `records_to_ast(ast_to_records(ast)) == ast` holds
exactly over 520 documents, covering all fourteen `Block` constructors.

### Every read and every write goes through pandoc

djot.js and the `npx` spawn are gone; pandoc reads and writes djot natively.
Markdown is read as `commonmark_x` with `attributes`, `smart` and `fancy_lists`
disabled.

This deleted three repair passes rather than fixing them. The em dash is not
restored, because `-smart` means it was never corrupted. Checkboxes are not
patched, because `-fancy_lists` means they parse the first time. There is no
fence tracking. **The pipeline contains no repair code at all** — every fix is
a flag, chosen once against a measured corpus.

Choosing that corpus reversed a decision mid-flight. `gfm` and `commonmark_x`
score identically on this repo's 25 documents, so gfm won on having safe
defaults; across 152 including a real documentation site it is 71 against 140,
because the gfm writer drops code fence info strings containing a comma —
`rust,ignore` becomes nothing — which is how every mdBook and Docusaurus corpus
annotates its examples. Twenty-five documents could not see it.

### Transcripts

Session JSONL is imported directly. Prose in a turn goes through the same path
a markdown file takes, so a paragraph of an answer is a node like any other;
tool output is stored whole, because parsing 60 real tool outputs as markdown
invented a Header, a BulletList and a Div out of terminal text.

Tool results fold into the call that produced them, matched on `tool_use_id`
rather than order. Attribution has a number now: **161 human turns out of 1060
`user` lines** — the other 899 are the transcript's envelopes around tool
results, which is the bug the old importer shipped.

Both orderings are stored, because they diverge on sidechains and this corpus
has none to test with: `session`/`next` is log order, which regenerates the
file, and `claude-code`/`replies_to` is the reply chain.

### Identity and citations

A handle is a **UUIDv4**. That costs 21.7% of a djot view against 7.7% at eight
characters, and up to 75% on small dense files — accepted, because a resolver
takes any unambiguous length, so shortening later needs no pass over stored
text: long and short citations coexist as full and abbreviated SHAs do in a git
log.

**A citation is a link:** `[-](#<guid>)`. The old `{#x}` meant "this element
*has* id x" in every markup language that knows the notation, so using it for
"points at x" was backwards, and any reader with `attributes` on agreed with the
language rather than with us. `{@x}` fixed the meaning but not the mechanism —
it was still text, so a handle quoted inside a code block became a real edge, in
a corpus that quotes its own syntax constantly. A `Link` is a node and a code
block has no inlines, so the rule that had been broken three times is now a
property of the format.

### Views

Three, all generated from records: `default-djot` for agents, `default-html`
for people, `default-md` clean enough to commit as `README.md`. Handles go on
prose and list items, not on the containers holding them — marking everything
produced a page with more handles than words. Tool output is shown in full in
djot, which has no collapse, and wrapped in `<details>` in HTML.

### Storage

`.compost/` is both the layout and the marker, replacing the `.kg` file, so a
base cannot be half-configured. Writes go through a temp file and an atomic
rename; only `*.jsonl` is loaded; filenames carry no meaning and load order
cannot change the result; the loaded file list is printed rather than hidden.

### Tests, and what they caught

Eight suites, 74 stated guarantees, each made to fail on purpose. Findings worth
recording because they were all silent:

- a fenced code block inside a **tight** list item is destroyed by pandoc's
  writer — emitted with no preceding blank line, so it re-reads as paragraph
  text. A loose list survives. Writer-independent, documented, unfixed.
- pandoc **synthesises** callout titles: `> [!IMPORTANT]` produces a `Div`
  containing the word `Important`, which no author typed.
- pandoc injects `<!-- -->` between adjacent lists, which re-reads as a
  `RawBlock` nobody wrote.
- document metadata lives outside `blocks` and every writer drops it without
  `--standalone`.
- `importing thing.md` and `thing.jsonl` wrote the same graph file and the second
  silently discarded the first, while the summary reported both.
- all 491 `thinking` blocks in the corpus carry **no text**: Claude Code
  persists only a signature. The node type stays, because other agents emit
  text into it.

### Fixtures that outlive their sources

`tests/fixtures/` holds 19 bleached notes, 21 edge cases, 7 bleached session
transcripts and two hand-built ASTs. Bleaching replaces every word with a lorem
word of the same length and leaves every character markdown gives meaning to
exactly where it was; correctness is checkable rather than eyeballed, since the
result must parse to the same tree of block types as the original.

It caught two leaks of its own: 57 absolute paths surviving in *key* position
inside `file-history-snapshot`, and a git branch name on the preserved list. A
vocabulary diff now shows 71,893 distinct words reduced to 4,104, all of them
JSON schema keys, enum values or tool names.

### Gone

`src/` and `tests/` from v0.1, `tools/`, the `.kg` marker, `site/`, the
`compost`/`kg`/`kgb`/`pandig` egg-info directories, the `uuid6` dependency, and
the `new`, `submit`, `serve`, `lookup`, `last` and `artifact` subcommands.
`conversations/`, `artifacts/` and `raw/` remain on disk as the input for a
migration that is not written yet, and are not readable by this version.

## v0.1.6 — 2026-08-17 — pandig reverted, the tool is `compost`

**v0.1.5 never worked.** It renamed `kgb` to `pandig` and is reverted here in
full — one commit, cleanly undone, nothing else changed underneath it. Kept in
history rather than erased: `git log` still shows the attempt and that it
didn't pan out, which is the same reasoning that keeps every conversation in
this base immutable in the first place.

**The tool is `compost` now.** Conversations pile up append-only, get turned
into artifacts, and what's fully superseded settles into `archive/` — the name
finally matches the shape of the system instead of punning at it. `kgb` (and
`kg` before it, and `pandig` for its few days) are gone **without an alias**.
Every prior rename kept the old name working with a deprecation notice; this
one doesn't, on purpose — v0.2 is about to break the storage format and the
importer from nothing, so there is no reason to carry three dead names into it
for the sake of continuity that's about to end anyway.

Renamed only where a wrong command breaks someone, same rule as last time:
`README.md`, `AGENTS.md`, `CLAUDE.md`, `DEVELOPMENT.md`, `man compost`
(`raw/artifacts/man-compost.md`, moved from `man-kgb.md`), `state-of-play`, and
`src/cli.py`. `CHANGELOG.md`, the completed `v0.1.4` section of `TODO.md`, and
`field-notes`' account of the day two handles nearly broke all still say `kg`
or `kgb`, because that is what the tool was called when those things happened.
`.kg` and `$KG_HOME` are untouched — renaming an env var breaks a shell profile
silently, which is a worse kind of break than a stale command name.

Also removed: `archive/` (moved to a personal notes directory outside the
repo) and `sample_data/math/` (demo content superseded by the conversation
corpus as a source of real sample data).

## v0.1.4 — 2026-08-11 — kgb, and a man page that cannot drift

**The tool is called `kgb` now.** Knowledge graph blocks, and a system whose
premise is that it knows exactly who said what and when has earned the joke.
`kg` remains as an alias that prints a notice, so every note, doc and shell
history written before the rename still runs.

Renamed only where a wrong command breaks someone: `README.md`, `AGENTS.md`,
`CLAUDE.md`, `DEVELOPMENT.md`. `CHANGELOG.md` and the completed sections of
`TODO.md` keep saying `kg`, because they record what the tool was called at the
time, and 501 blocks across the conversations say it immutably and always will.
Measured before deciding: only 4 cited artifact blocks mention the name, so the
rename cost four handles rather than eighty.

**New commands**, both absorbed from shell scripts that had accumulated:

- `kgb lookup HANDLE` — resolve a handle to its block, and list everything that
  cites it. Accepts `{#handle+++}` as well as a bare handle. Replaces the
  `tools/kgb.sh` function, which is deleted.
- `kgb last` — print recent turns as `{#handle}` plus text, so a turn can be
  pasted into an agent's interface and the agent can cite exact blocks back. A
  conversation file can be half a megabyte; one turn is not. `-n`, `--author`
  and `--handle` select which.
- `kgb --version`.

**The version has one source, and it is the code.** `__version__` lives in
`src/__init__.py` and `pyproject.toml` reads it with `dynamic`. The usual
arrangement is the reverse, and it failed here in the ordinary way: with an
editable install, packaging metadata only refreshes on reinstall, so `pip show`
reported 0.1.0 through three releases while the code was current. Nothing
visible reported a version at all, which is why nobody noticed.

**The behavioural expectation is corrected everywhere it was stated.** An agent
with its own interface answers there and does not submit its reply as a turn;
the human imports the round, which makes the answer addressable anyway. Two
output channels for one answer is worse than one, and it is the human who has
to read both.

This came from days of use rather than from the design, and it does contradict
"everything is a turn" — knowingly. Nothing is lost, because the import is
where the handles came from in either case. What does not change: an agent
resolves every handle before answering and cites handles in its answer, so the
import produces real citations.

Corrected in `CLAUDE.md` (which an agent loads first, and which had been
carrying a marker saying its own instruction was wrong), `AGENTS.md`,
`README.md`, `man kgb`, and `state-of-play`. `kgb submit --author` remains
correct for an agent with nowhere else to write, and for when a turn is asked
for deliberately.

**A man page, verified against the CLI.** `artifacts/man-kgb.dj`, published from
`raw/artifacts/man-kgb.md` and readable in the index as *man kgb*. One long
searchable document rather than help by level: the concepts, every command,
files, environment and examples.

`tests/test_manpage/` walks `build_parser()` and requires every subcommand and
every long option to appear in the page, and anything whose help says it is
deprecated to be marked as such. Sabotage-verified with a parser carrying an
invented command and flag. A reference document nothing checks drifts the first
time a flag is added, and this project has already paid for that once with
`mvp-design.md`.

The argparse tree moved into `build_parser()` so the test can walk it.

## v0.1.3 — 2026-08-11 — the base keeps its own sources

`kg import` now copies the session log into `raw/<conv>/<session>.jsonl` before
deriving anything from it.

Until now an imported conversation's source lived only in
`~/.claude/projects/`: outside the base, outside git, and owned by another
tool's storage layout. The importer discards a great deal on purpose — every
`type: "system"` line — and none of it was recoverable, because the base had
never held the file it was discarded from.

Found by trying to locate where a conversation had been branched and failing.
The `/branch` event is in the log as two `type: "system"` lines carrying the
parent session id, and `SKIP_TYPES` drops them. Also dropped, per session: 34
`turn_duration` records, 10 `away_summary`, 8 `local_command`. And `sessionId`
sits on every line and was never stored, so the base held no record that one
conversation was a branch of another.

None of that is fixed here, and it is not meant to be — the graph milestone is
where those become nodes and edges. What is fixed is that the evidence now
lives inside the base, so a later version can go back and read it. 10 MB for
seven sessions.

- **A refresh may only grow the copy.** A log is append-only upstream, so if
  new content is not a continuation of the stored copy, the log was rewritten
  underneath us and the import refuses rather than overwriting. The stored copy
  is the only record of what was actually ingested.
- Re-importing an unchanged log is a no-op, so the refresh loop stays cheap.
- `tests/test_preserve/` — storage, growth, idempotence, the rewrite refusal,
  and that the dropped fields are recoverable from the copy.

## v0.1.2 — 2026-08-10 — punctuation, and a bug class closed

Every em dash, en dash, ellipsis and curly quote an author had typed was being
deleted from the stored text. `readme.dj`'s own title read
`kg  conversations to an addressable wiki`. 795 occurrences across the corpus.

**The `.dj` files were correct the whole time.** Djot has smart punctuation in
its specification: `---` in a source file *means* an em dash, and `\-\--` means
three literal hyphens. Pandoc was encoding it exactly right, and the round trip
through djot.js is lossless. An earlier TODO entry blamed pandoc's writer, said
the corruption was on disk, and estimated the repair as canonization-time work
needing fence tracking. All of that was wrong. That entry is kept, because it
is cited, with a superseding block beside it.

The defect was in `inline_reconstruct.py`, which had no branch for djot's
`smart_punctuation` node. Its fallback emitted nothing.

- **An unhandled tag now raises**, in the inline reconstructor and in the block
  walker. This is the actual subject of the release. A missing branch that says
  nothing has now produced three bugs: `task_list` silently dropped, a div
  silently swallowing its children, and this. Each was invisible to the tests
  because the element was absent from *both* sides of every comparison, so
  nothing could see the difference. A branch that raises cannot fail that way.
- `smart_punctuation` is resolved to the character it denotes rather than
  echoed as its source spelling, so that an em dash and three literal hyphens
  stay distinguishable in the stored text. Structural markup is still emitted
  as djot source, as it always has been.
- `url` and `email` autolinks were dropped by the same fallback. One occurrence
  in the corpus.
- `double_quoted` and `single_quoted` handled defensively. Unreachable today
  only because pandoc escapes quotes as `\"`, and an unhandled *container*
  loses its children rather than just its wrapper.
- `tests/test_inlines/` — the branches, the sabotage check, and a pass over
  every file in the corpus so an unhandled tag announces itself.

No handle moved. Both sides of the `kg artifact` hash comparison are parsed by
the same reconstructor, so the change is symmetric: all six republished
documents reported 0 new and 0 gone, and `kg check` stayed at 0 dangling.

Sequenced before the `graph/` work deliberately. That milestone migrates block
text into nodes carrying an immutability invariant, so a hole repaired
afterwards would be a content change on a node that already has an identity.

## v0.1.1 — 2026-08-07 — conversations, and an agent in the loop

The loop now runs with both parties in it. Either can write; neither can alter
what the other wrote.

Developed on `main` with a tag per version. A `conversations` feature branch
was created and fast-forwarded away: with one developer, no remote and no CI
there is nothing to isolate from, and the cost was a trunk whose documentation
described an architecture that no longer existed.

**Changed — the shape of the system**

- **The split is mutability, not authorship.** `notes/` and `wiki/` enforced
  "humans write notes, agents write the wiki" with the filesystem. That boundary
  is gone: `conversations/` is append-only and `artifacts/` is rewritten in
  place, and either party writes either kind. What protected anything was never
  the directory but immutability, and that is kept — no block already written
  ever changes, whoever wrote it. Revises invariant 3 and §3 of `mvp-design.md`,
  which called a conversation a view rather than a storage type.
- **A conversation is one append-only file**, not a directory of turns. Turns
  get concatenated for reading anyway, and one file is one djot parse: at the
  measured ~1 s per `npx` spawn, a 70-turn imported session costs about a second
  this way against roughly two minutes as separate files.
- **Turns are fenced divs carrying their author** —
  `{#handle .turn author="claude"}`. One native djot construct provides the
  container, the authorship, and the nesting that folded tool traffic needs. No
  frontmatter, no sidecar, nothing outside the reference implementation.
- **Block ids are 8 hex characters, not UUIDv7.** A UUID cost 39 bytes per block
  on disk and 56 per reference — measured at 26.8% of the corpus, and unreadable
  inline. Handles cost 10.2%. Nothing needed a per-block timestamp; note ids stay
  UUIDv7 so dates and ordering still work. Rejected the shorter registry-backed
  handle: a handle-to-block file cannot be rebuilt from the `.dj` files, so
  losing it would break every reference at once.
- **The version pin is now optional.** `{#handle}` for immutable conversation
  blocks, whose handle already pins their content; `{#handle@ver}` for artifacts.
  Both forms are defined now so the syntax never has to change again.
- **The thread is inferred from citations.** You reply by clicking a block, so
  the conversation is implied; `-c` is only needed when a draft cites nothing or
  cites two threads.

**New**

- `kg artifact` — publish a markdown document as an artifact. On update,
  unchanged blocks **keep their handles**, matched by content hash rather than
  position so an insertion does not renumber everything after it. Without this,
  regenerating a document orphans every comment ever written about it, and those
  comments live in immutable turns where they can never be corrected. This is
  the delta algorithm from `architecture/delta_ingestion_and_block_versioning.md`,
  and it turned out to be about thirty lines.
- `kg import` — a closed Claude Code session becomes a conversation. The whole
  log is turned into one markdown document and canonized in a single pass,
  because pandoc carries fenced divs and their attributes through to djot.
  Nothing is filtered: tool traffic and thinking are wrapped in `.tool-call`
  divs that the renderer folds away, so the transcript is complete and every
  block of it addressable. Subagent branches become `claude:sidechain` turns.
- `site/blocks.json` — every block with its handle, hash, type, source,
  structure, citations and author. An agent can read a `.dj` with grep but
  cannot *cite* one, because the hash is SHA-256 over the parsed block; this
  closes that gap and doubles as whole-corpus context assembly.
- `kg check` — dangling references and handle collisions, as a set difference
  over `blocks.json`. A dangling reference cannot be repaired in place, because
  the turn holding it is immutable, so noticing is the only defence.
- `AGENTS.md` — everything an agent needs to read and write a base, without
  reading this repository.
- Rendering: per-turn author labels straight from the djot attribute via
  `attr()`, no JavaScript; `.tool-call` divs folded into `<details>`; whole
  turns subtree-copyable.

**Fixed — correctness**

- **The importer attributed the harness to the human.** A `user` line in a
  session log is not the same thing as "the person typed this": tool results
  come back as user messages because that is the API protocol, the harness
  injects its own context, and a slash command echoes both its name and its
  output. In one 18-"user"-turn session **only 1 turn was genuinely typed**, so
  a reader saw directory listings above the user's name. Tool results are now
  folded into the call that produced them, matched on `tool_use_id`; harness
  messages are attributed to `system`; injected system-reminders are lifted out
  of real typing and kept, folded, rather than discarded.
- **A conversation's date was decoded from a UUIDv4.** An imported session is
  named after its log, whose id is not a UUIDv7, so reading its first twelve hex
  digits as a millisecond timestamp dated one conversation to the year 4527.
  `_when()` now checks the version nibble, and imported turns carry their real
  timestamp as an attribute.
- **A div swallowed its children.** `inject_ids` recursed into a div and gave
  every child an id; `ast_walker` nested those children inside the div's
  `content` instead of emitting them. Two halves of one pipeline held opposite
  beliefs, so canonization wrote ids into the file for blocks the block list did
  not contain — clickable in HTML, resolving to nothing, absent from every view.
  Neither the verifier nor the roundtrip test could see it, because the blocks
  were missing from both sides of every comparison; `test_roundtrip` even had a
  `_flatten()` helper written to accommodate the nesting. This blocked folds
  entirely, and would have made every block of every imported turn
  unaddressable.

- **A reference inside code is not a citation.** Importing this project's own
  sessions took `kg check` from 6 dangling references to 48 — every one a shell
  command from a throwaway experiment or a documented example. A checker that
  reports those is noise, and noise gets muted, which would cost the only thing
  the check is for. Code blocks and code spans are now excluded, and the count
  went to zero.
- **The repo is its own knowledge base.** `.kg`, `conversations/`, `artifacts/`
  and `raw/` at the root; the docs are published with `kg artifact`. Moving the
  corpus in preserved all 3311 handles exactly, verified by comparing a hash of
  the whole handle set before and after.
- Re-importing a session **preserves handles**. A live session is refreshed
  repeatedly as it grows, and the first implementation overwrote the file
  blindly, renumbering every block on each refresh — which would orphan every
  comment ever made on that conversation. It uses the same content-hash
  matching as an artifact, and refuses when the conversation contains turns the
  log does not know about, because those were submitted by hand and would be
  deleted.
- All four Claude Code sessions for this project are imported: 348, 311, 20 and
  3 turns.
- Index links show the document's own heading, the artifact's filename (so
  "where is the README?" has an answer), the real date, participants, and size.
  A conversation is titled by **what the human opened with** — its first heading
  is usually something the agent wrote, and its first block can be harness
  output, which titled one session "<local-command-caveat>Caveat: The...".

**Docs**

- The documentation surface is halved. `mvp-design.md`, `mvp-interview.md`,
  `my-workflow.md`, `human-log.md` and `architecture/` move to `archive/` —
  1141 of 2195 root doc lines, and the contradictory half. `mvp-design.md` was
  the worst of it: still declaring itself authoritative while describing
  `notes/`, `wiki/`, UUID block ids and "humans write notes, agents write the
  wiki", none of which survive. Its invariants are in `DEVELOPMENT.md` and its
  open questions in `TODO.md`. Code comments still cite its section numbers;
  those are historical now.
- `CLAUDE.md` is the bootstrap a fresh agent loads automatically. It routes to
  `site/blocks.json` and the base rather than to markdown, which is the point:
  the reasoning lives in immutable conversations that cannot drift, while a
  spec can and did.
- `artifacts/state-of-play.dj` is the handoff — what exists, what does not, the
  traps that already cost something, what to do next, and what nobody has
  answered.

**Measured, because it drove decisions**

- Appending a turn directly after a heading section merges it into the
  *previous* paragraph — an already-referenced block's text silently grows and
  the new turn's id attaches to nothing. A list appended after a paragraph is
  absorbed as continuation text and loses its id. A single blank line prevents
  every case found; the turn fence then makes merging structurally impossible.
- `npx @djot/djot` costs ~1 s per spawn, and `kg render` parses each file twice.

**Migration**

`tools/migrate_to_handles.py` remapped the test base: 248 blocks, 27 references
rewritten, zero dangling, including a cross-file subtree reference. Old-to-new
is positional — re-canonizing an immutable draft yields the same block sequence
— so nothing was guessed, and the script refuses to write if the sequences do
not correspond.

## v0.1 — 2026-08-04 — the mechanical loop

The write → submit → canonize → read → reference → submit loop works end to
end, with no LLM anywhere in it. Wiki generation is still unbuilt.

**New**

- `kg` on PATH via `pip install -e .`, working from any directory. The base is
  found via `--root`, `$KG_HOME`, or a `.kg` marker in any parent.
- `kg init` creates a base anywhere, which defers the tool/data split to a
  runtime choice rather than an architectural commitment.
- `kg new` opens `$EDITOR` and submits on exit — never on save, so saving
  mid-thought stays free.
- Static site with click-to-copy. Click a block for `{#uuid:hash}`,
  shift-click for `{#uuid:hash+++}`. Holding Shift while hovering highlights
  the subtree, so what will be copied is visible before committing.
- Backlinks: a note referencing a block appears as "Referenced by" on the note
  containing it. Computed at render time, so it works retroactively.
- Reverse-chronological index, dated from the UUIDv7 timestamp.

**Fixed — correctness**

- `loosen()` moved into canonization. Djot drops a list item's id in HTML
  unless the list is loose, so every list item and todo was unaddressable.
  Since notes are immutable this could not have been repaired later: notes
  canonized before the fix would have been permanently degraded.
- Backlink scanning reads parsed block text rather than the raw file. Pandoc
  escapes references on disk as `\{#uuid:hash\}`, so scanning the file found
  nothing.

**Docs**

- `README.md` restored — the repo had no entry point since the cleanup.
- `DEVELOPMENT.md` added: architecture, the non-obvious pandoc and djot
  behaviours, the sabotage-verification practice, and where the next work is.

## 2026-08-03 — Architecture pivot and repository cleanup

**Tagged `v0-graph-architecture`.** Everything removed in this cleanup remains
reachable there (`git show v0-graph-architecture:<path>`).

The product changed shape after a workflow interview (`my-workflow.md`,
`mvp-interview.md`). The new design is in `mvp-design.md`:

- **`.dj` files in git are the source of truth.** LadybugDB is no longer
  canonical storage. Any graph that returns will be a derived, disposable cache.
- **Notes are immutable and human-written; wiki pages are agent-written.** The
  human never writes the wiki, agents never write notes.
- **Lineage replaces semantic extraction.** Every wiki block cites the note or
  source block it derives from. Recorded at generation time rather than
  extracted afterwards — free, exact, and it doubles as the anti-slop
  mechanism: a block with nothing to cite is invalid.
- **Deleted, not deferred:** Phase 05 (entity/relation extraction), Phase 07
  (LLM-to-Cypher), temporal quadruplets, `Annotation` nodes, the Parquet event
  log (git supersedes it), and HITL diff approval.
- **Retained:** `architecture/delta_ingestion_and_block_versioning.md`. Its
  content-hash and delta mechanisms carry over unchanged; the subject moves
  from human-edited notes to agent-regenerated wiki pages.

Removed 47 files across two commits (superseded docs, then the LadybugDB
ingestion path). ~360 LOC of parsing and rendering carried forward.

**Defects found during the carry-over audit**, both on the MVP critical path
and neither caught by the existing roundtrip test:

1. `ast_walker.py` silently drops `task_list` / `task_list_item`. Djot supports
   them natively (`checkbox: checked|unchecked`); the walker has no branch, so
   todos vanish with no error.
2. Nested list items are emitted *before* their parent, and nesting depth is
   discarded, so `- a` / `- b` (nested) yields `[b, a]` flattened to one level.

*Correction:* an earlier version of this entry claimed nested items were
embedded as raw markup in the parent block. That was wrong. The confusion came
from a probe written without blank lines — **djot requires a blank line before
a nested list**; without one djot itself (not the walker) parses the child as
lazy continuation text of the parent paragraph. That is spec behaviour and a
*canonization* concern, since hand-written notes rarely include those blank
lines. The walker defect is the ordering and depth loss described above.

`test_roundtrip.py` detects none of it: a dropped element is absent from both
sides of the comparison, and reordering survives re-parsing unchanged. The
Phase 03 claim of "no data loss, 31 block types" holds only for the properties
the test actually compares.

---

## Phase 02 & 03 — 2026-05-16

Implemented Phase 02: Rewrote ingestion to bypass Pandoc and use native `djot.js`. Dropped JSONL intermediate representation to write blocks directly into Parquet files, which are immediately loaded into LadybugDB during `ingest_page()`. Extended Block schema with `language` field and added `LINKS_TO` relationships for explicit cross-links. Re-wrote `inline_reconstruct.py` and `ast_walker.py` against the native AST.

Implemented Phase 03: Built Djot rendering via `blocks_to_djot.py` that formats structured Block dictionaries back into raw Djot text. Added a roundtrip validation harness (`test_roundtrip.py`) validating `Djot -> Blocks -> Djot` without data loss (whitespace-normalized, structural fidelity). Passed verification for 31 block types. Achieved ~4.6x token reduction compared to raw JSON block representation.

## 2026-05-10 — Kuzu to LadybugDB Migration
Replaced Kuzu with LadybugDB (community fork) as the embedded graph database, following
Apple's acquisition and archiving of the Kuzu repository. Renamed `kuzu_schema.py` →
`ladybug_schema.py`, `kuzu_loader.py` → `ladybug_loader.py`. Updated all design docs,
implementation plans, and workspace paths. Python package changed from `kuzu` to
`real-ladybug==0.15.3`. Import alias: `import real_ladybug as lb`.
LadybugDB now supports `OPTIONAL MATCH` — constraint removed from Phase 07 design and
implementation plans. Added defensive parsing guidance for `SHOW_TABLES()` output change.
No data migration was needed (no existing database on disk).

## Phase 01 — 2026-05-08

JSONL → LadybugDB graph index. Implemented `src/index/` module: `ladybug_schema.py`, `jsonl_to_parquet.py`, `ladybug_loader.py`, `build_index.py`. Loads blocks and pages from JSONL into LadybugDB via Parquet COPY FROM. Full rebuild on each run. Verified: 47 Block nodes, 7 Page nodes, 47 HAS_BLOCK edges from the test corpus.

Dependencies added: `ladybug`, `pyarrow`.

## Phase 00 — 2026-05-08

Djot → JSONL ingestion pipeline. Implemented `src/ingest/` module: pandoc-based parser, AST walker, inline reconstructor, block schema builder, JSONL writer. Ingests a Djot file into `blocks.jsonl` + `pages.jsonl`. Handles heading, paragraph, list_item (ordered + unordered). Verified: 9 blocks from test file, 47 blocks from full test corpus (7 files).

Dependencies: `python 3.12`, `uuid6`, `pandoc` (system).

# TODO — do we parse tool output for citations?

**Not scheduled. A decision, not a task.** Measured 2026-09-08 against the real
base. Nothing here is urgent while the base is small; it gets worse every week.

---

## The situation

The human writes their replies in nvim. Often they do not paste the reply into
the conversation — they save it to a file and give the agent the filename. The
agent reads it with `Read`, and the file's text comes back as a `tool_result`.

`src/session.py` keeps tool output **verbatim and unparsed**, on purpose: it is
terminal text, not prose, and parsing it invents structure that was never there
— 60 real tool outputs produce a `Header`, a `BulletList` and a `Div`, and a
table of numbers splits into three blocks on indentation alone.

`compost layer citation` reads **`Link` nodes**. `CLAUDE.md`: *"Never scan raw
file text for citations. A citation is a `Link` node, and reading the parsed
content is what makes 'handles inside code blocks are not citations' true by
construction."* That rule was violated three times under the old text-based
syntax and cost something every time.

So a citation that arrives as tool output is never parsed, never becomes a
`Link`, and is invisible to the citation layer. **Both rules are right and the
result is wrong.**

## What it costs, measured

Across the whole base, 35 distinct citations exist and **one** of them is a
parsed `Link`:

| where the citation actually arrives | distinct guids |
|---|---|
| `tool_result` on an **envelope** turn — an agent read the file | **33** |
| `text` on a **human** turn — pasted directly | **1** |
| `tool_use` input (`Bash`, `Write`) | 2 |

`cites` edges in the base: **206, every one of them from the v0.1 `kg-8hex`
migration.** Not one edge from a citation the human wrote.

## The answer that looks right and is not

*"Digest the notes file with `--as=notes` and the citations become real
`Link`s."* No: **those citations are about the conversation, not about the
note.** The file is a workflow prop standing in for a turn — it exists only
because the helper that pipes a rendered answer back into the conversation has
not been written. Digesting it as a document would attach every citation to the
wrong thing and record a relationship that never existed.

Worth stating because it was proposed and it is plausible.

## The decision

**Do we parse some of a transcript's verbatim text for citations, and if so
which parts?** Candidates, narrowest first:

1. `tool_result` from a **`Read` of a markdown file** — the exact shape the
   human's workflow produces.
2. Any `tool_result` whose content parses as markdown.
3. `tool_use` **input** as well — `Write` and `Bash` heredocs carry citations
   too, measured at 2.
4. Everything verbatim in a transcript.

### For

- **It is where the citations are.** 33 of 35. Any answer that does not reach
  tool output recovers almost nothing.
- **The information is already stored.** Nothing needs re-ingesting; this is a
  layer over records that exist. It can be built, run, and deleted, and
  rerunning it is free.
- **It need not touch the importer.** A *layer* can parse what a view would
  parse, mint `cites` edges, and leave the `tooloutput` node exactly as it is.
  That keeps *digest everything, filter at query time* intact — the parsing is
  a query-time decision, which is the side of the line this project already
  says is free and reversible.

### Against

- **It reintroduces text scanning.** The rule exists because handles inside
  code fences became citations three times. Tool output is *full* of code
  fences — it is mostly `cat`, `grep` and diff output.
- **A citation quoted is not a citation made.** An agent that `cat`s a file
  containing citations would mint edges asserting *the agent* cited them. The
  same text can appear in a diff, a backup, a `grep -n` hit, and a heredoc that
  writes it somewhere else — potentially four edges for one act of citing.
- **Attribution is already known to be subtle here.** A `user` line carrying
  only a tool result is an *envelope*, not a person. All 33 arrive on envelope
  turns, so the naive reading attributes the human's citation to the harness.

### Risks

- **Duplicates that accumulate.** Principle 10 says duplicates accumulate on
  purpose and nothing is deduplicated. A layer that mints an edge per textual
  occurrence would multiply one citation into many, and there is no inverse
  except deleting the file the run wrote.
- **Silent wrongness.** A wrong `cites` edge looks exactly like a right one.
  `check` cannot tell them apart; it verifies structure, not intent.

## The alternative that removes the question

**Build the turn-piping helper.** If the human's reply reaches the conversation
as a real turn — the thing `docs/roadmap.md`'s conversation loop already
describes — the citation is parsed as prose, becomes a `Link`, and every rule
stays as it is. That is the *cause*; parsing tool output is treating the
symptom.

It is also not built, and the workaround has been running for months.

## What would decide it

- Count, in the base, how many of the 61 `tool_result` occurrences are the
  human's own answer versus a quote, a diff, or a re-read of the same file. If
  most are duplicates of one act, option 1 is worth little and the helper is the
  answer.
- Ask whether an edge minted from tool output should carry a different `by`
  value — `--by=tool-output-scan` rather than `uuid-link` — so the weaker
  provenance is visible in the record rather than assumed away.
- Decide whether this is a **layer** (rebuildable, deletable, no importer
  change) or an **importer** change. The first is reversible and the second is
  not; there is no reason yet for the second.

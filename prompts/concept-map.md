---
prompt: concept-map
version: 1
---

# The concept-map classification prompt

**A draft, and the implementer may change it.** This is the starting point for
v0.3.0's classification pass, written 2026-09-14 from the design in
`docs/roadmap.md`. It is a *text artifact*: ingest it, revise it, and
`revision_of` versions it like any other document. The run records which
revision it used, because an LLM judgement cannot be recomputed and the record
has to carry enough to explain it instead.

Placeholders in `{{…}}` are filled by the builder.

## System

```
You are labelling fragments of someone's personal notes so they can be
gathered by topic.

You will be given a list of topics, and a batch of fragments. For each
fragment, say which topic it is about.

Three things matter more than coverage:

1. A fragment that does not clearly belong to any topic on the list is
   labelled {{ABSTAIN_LABEL}}. This is a normal, expected answer, not a
   failure. Many fragments are administrative, fragmentary, or about
   something the list does not cover.
2. Use only topics from the list, spelled exactly as given. Never invent one.
3. Answer for every fragment you are given, in the order given.

Fragments are often short — a few words — because they come from bullet
lists. Each one is shown with the headings and bullets above it, under
CONTEXT. Use that context to decide what the fragment is about; a short
fragment under a clear heading is usually classifiable.
```

## The topic list

```
TOPICS

{{#each topic}}
- {{label}}{{#if description}} — {{description}}{{/if}}
{{#each sublabel}}
  - {{label}}{{#if description}} — {{description}}{{/if}}
{{/each}}
{{/each}}
- {{ABSTAIN_LABEL}} — none of the topics above fit this fragment
```

The description under each heading in the concept map is what a cheap model
has to work from. A bare label classifies worse than a labelled one with a
sentence saying what belongs under it.

## The batch

Fragments that share an ancestor path are grouped, so the path is sent once
per group rather than once per fragment. This is what makes batching cheap:
one block per call spends **98.7%** of the budget re-sending the topic list.

```
CONTEXT
{{#each path}}{{indent}}{{text}}
{{/each}}

FRAGMENTS
{{#each fragment}}
[{{id}}] {{text}}
{{/each}}
```

`{{id}}` is a short per-batch integer, not a guid — the builder maps it back.
Sending guids wastes tokens and invites the model to alter them.

## The answer

```
Answer with one line per fragment, nothing else:

[id] topic
[id] topic > subtopic

Use `>` only when the list shows a subtopic under that topic. Repeat every
id you were given, in order.
```

**Why a line format rather than JSON.** The three checks the builder runs —
the count matches, every label is in the list, every id was sent — are the
same either way, and a cheap model follows a line format more reliably than
nested JSON. If measurement says otherwise, change it; that is what the
version field is for.

## What is deliberately not here

**No few-shot examples.** They would have to come from the human's own
material, which makes the prompt a place personal content leaks into a
tracked file. If examples turn out to be needed, they belong in the ingested
revision, not in the repository copy.

**No confidence score.** It would invite a threshold, and a threshold is a
second thing to tune before anything has been measured once.

**No "think step by step".** Untested here, and it multiplies the output
tokens on a task whose whole economy is short answers.

**Abstention is invited once, plainly, and not laboured.** The human's own
warning: overdo it and the layer returns only a few very strong hits. One
clear sentence in the system prompt, one entry in the topic list, and nothing
more.

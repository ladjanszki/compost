# MVP Interview — Round 2

> Your long-form answer lives in `my-workflow.md`. This document is now only the follow-ups.
>
> **Format:** no code blocks. Write under each **Answer:** line, as much or as little as you want.
> Correct me where I'm wrong — most sections below are me *asserting* what I think you meant, so
> the cheapest useful thing you can do is disagree. Skipping a section means "you got it right
> or I don't care", and both are useful.

---

## What I took from `my-workflow.md`

So you can see where I'm starting from, and correct the frame rather than answer inside a wrong one:

1. **You write in neovim, in a new empty file, in flowing prose.** Not in a chat window. Not in a
   form. The blank file is the entry point, not an obstacle. This is a hard constraint, not a
   preference.
2. **"Submit" is the core verb.** You finish a note and hand it to the system. Everything else is
   downstream of that one action.
3. **The wiki is read-only.** You proposed dropping chat entirely and storing discussions as their
   own pages, threaded by ID references. I think this is the best idea in the document — it deletes
   an entire subsystem and makes conversation file-native.
4. **You restructure the wiki by commenting at it.** "IDxxx this belongs under another part
   because…" — meaning an *agent* edits the `.dj` files, with you directing by reference. The wiki
   isn't automagical; it's iteratively improved by an agent you're steering.
5. **Files are throwaway** (`random-uuid.dj`). Pages and blocks are real; filenames are not.
6. **Capture is already solved-ish** — you have a browser extension producing `[title](url)`, you
   paste it into a note and write why it mattered. No browser plugin needed for v1.
7. **Two reasons you come back:** something to ship, or a new idea. Plus ad-hoc recall
   ("why did the DCC locomotives need a square wave?").

If any of those six are wrong, say so here and skip the rest — it'd change everything below.

**Answer:**

1. Yes, exactly. And also interaction with my phone can be solved by my sending email to myself or telegream messages later on. 
   So these notes with anchors to the original system or outside information are the main ingestable

Yes to all other points as well.



---

## 1. Submit — the core verb

This is now the highest-value unknown in the whole project. Everything hinges on it.

**What does "submit" look like at the moment you do it?** You've just written `~/notes/scratch.md`
in nvim and you're done. What happens next — you run a command? Move the file somewhere? Hit a key
in nvim? Does something watch a directory?

**Answer:**
I have two idea in mind for this.
1. CLI tool where I have a create command. This creates the `rnd-uuid.dj` file which donw even have to be created at pwd. Moreove, shouldon't be created at pwd but in a separate location otherqwise I'll drown in `scratch.md` and `tmp_23.dj` files. Then the saving of the file submits it. I know I'm going to have a gazillion files open where I wait for a link or something. But I have to be pedantic with at least this submission thing I guess :)
2. A neovim plugin which opens a file, nicely adds the menus, etc. But this is deferred for later.


**Does submitting block you, or is it fire-and-forget?** i.e. do you wait for it to be processed
and look at the result, or do you close the file and move on?

**Answer:**
Depends on what I work on. Most of the time I picture myself actively working with the system.
At least on the conversation pages I need chat like response.
However we can later have an async system where I get notifications on the answers I got from agents.

**Does one submitted note become one wiki page, or does it get split/merged into existing pages?**
This is the big one. Option A: every note is its own page forever, and structure comes from links
and tags. Option B: notes are raw input, and an agent files their contents into existing pages.
Your "this belongs under another part" comment implies B, but B is much harder and can lose text.

**Answer:**
So this is where I thought the graph comes in:
the notoes I wrote gets submitted
They get their IDs by paragraph or line
Then agents generate wiki pages which cite back to notes or data from websites, text, video, etc.
then I can iteratively improve this wiki by commenting on the content and the structure (sections, subpages, etc)
This is also where a temporal dimension is required:
"I hate the new version, restore to the previous one" should be possible.
This is why we have block IDs and contect/version IDs as well

I'm not sure if this is added explicitly anywhere but I think about the content/version ID as an MD5 hash of the content
In this way the content ID is like an error flag as well: is this the whole content? does it give back the MD5 or SHA hash?
But I'm happy to debate this if this is a bad idea.


**If you submit a note and it goes somewhere you didn't expect, how do you find it again?**

**Answer:**
Preferably I don't have to argue the system on a note level.
But if I have to:
I add a comment to a wiki entry that this is wrong
Then the agent points out: no this is based on this note: filename/element ID.
now we are back to the note.
But I don't think I normally want my notes as they are.
However it is almost free to have an index page for all submitted notes by time or whatever.

---

## 2. Prose → referenceable blocks

You flagged this yourself: *"somehow the note turns into a djot file where the parts are
referenceable… I write mainly in these paragraphs."*

My read: this is the easy part, and it's mostly built. Each paragraph becomes a block, each gets a
UUID, IDs get written back into the file so they're stable. Headings and bullets work the same way.
Where it gets interesting is granularity.

**Is a paragraph the right unit?** In `my-workflow.md` your paragraphs are 1–8 lines and each holds
roughly one thought. But some of your lines are standalone thoughts that happen to sit in the same
block. Would you want to reference a *line*, or is a paragraph fine?

**Answer:**
I thought about a paragraph.
I tried to have one thought per paragraph but that might failed.
I'm not sure what is djots way? 
I don't want to extend it!
I use djot for its formal nature and quasi-human-radability.
We can reference lines if that is djots way but I thought using one paragraph as one unit.

Also I myself sometimes find that some parts are "pointing out" from the paragraph, it's still the same topic but maybe a link to something or a todo
In these cases I'm going to use bullet points to better format my notes
however I don't want to constraint myself too much because friction is something that can break the system
If it's too hard to take a note and add to the system I wont do it


**Do you want to see the IDs in your own file after submitting?** Two options: (a) the system
rewrites your file with `{#id}` lines inserted, so you see them and can hand-edit; (b) IDs live
only in the wiki, your source file stays clean. (a) makes references stable and greppable, but
puts machine noise in your prose.

**Answer:**
So I don't really see myself reading these djot files directly unless there is some debugging.
If we add an index for all notes submitted an one page per note then I can even go down to note level in the wiki.
But I think of this as debugging basically.
I guess rewriting my file on submission was what I called "canonization" in my initial message.
Yes this is where we do the linting because not all md files are valid dj files and we only use valid dj files with ids after submission
These ids and scaffolding will not be a problem in thw html wiki and can be easily stripped by pandoc in the command line to generate some really human readable from it.
And as a last straw we can still open up a dj file in nvim and check regardless of the ids.


**When you edit an existing note later, should its blocks keep their IDs?** Assume yes for
unchanged paragraphs — but if you split one paragraph into two, what should happen? (No right
answer; I want to know if you'd even notice.)

**Answer:**
On important thing:
A submitted not can't be edited! The note takes effect on a wiki page which can be referenced from a new note but submitted notes are read only.

Based on this I didn't really thought about text node evolution.
I think this is an important decision which I really want to discuss:
there are the submitted notes and other sources. 
these are read only
but there are the generated pages
I think of these as read/write 
and I thought the generator handles the node and content ids.

In your example:
the node gets splitted
then two new nodes created with new node ids and content ids
both new blocks reference the note which resulted in the splitting
and the original one block which was the ancestor of both.
In this case later an agent can argue based on the evolution of the page/understanding

---

## 3. Discussion pages — your read-only-wiki idea

Digging into this because I think it's the centerpiece and I want to build it right.

The model as I understand it: you read a wiki page, copy a block ID, write a note in nvim
referencing it, submit. An agent responds. The response becomes a page. You read it, reply by
copying *its* ID. A thread is a chain of ID references across files.

**Is the discussion a separate page per thread, or one long page that grows?**

**Answer:**
I'm thinking of one page per conversaion.
But not all submitted note should trigger a conversation.
If I submit a note about a wiki paragraph where I ask for some clarification or re-write and the agent can do it then the wiki page change as the side effect of my note.
the chnged parts reference the note and the earlier versions of the page for observability.
The note page only turns into a conversation if it is required.

However this is a very good question.
So basically if I submit a note (or other source) it gets its own page
I'm thinking of two solutions:
1. every page can have their own discussion page (as in wikipedia). so the discussion page is separate from the content/note page
2. Only the generated content pages have their own discussion pages and note pages are discussion pages by default but mybbe the only answer is: succeeded or acknowledged I guess.

But I think we can have some discussion here as well.

One thing is sure, it is **not** one long discussion, it is a discussion per thing to discuss.


**How does the agent get triggered?** Does submitting a note that contains an ID automatically kick
off an agent response, or do you explicitly ask for one? (i.e. is every note a question, or are
some notes just notes?)

**Answer:**
right now I thought of agent start on submission
but later this might have to be sophisticated (maybe by more cli subcommands) so we have more granular command on
what model, what node, async or promt, etc.


**Do you want the agent's answer to be a "reply", or should it also be allowed to edit the wiki?**
E.g. you write "this section is wrong because X" — does the agent (a) reply saying "you're right,
here's why", (b) go fix the page, or (c) both?

**Answer:**
Absolutely want the agents the generate the main wiki pages.
I don't want to write those, I write the notes and add the sources and the wiki is agent generated.
If something is not right or I want to ask or steer then I get the reference and write a new note.
But as I discussed above maybe my note requires clarification which can trigger a conversatino about a note before changing the wiki pages.
I'm not going to manually modify generated wiki files and my note files can only rewritten by linting and adding ids


**How do you write a reference in prose?** You said "copying the ID of the message". Concretely:
bare `{#019abc}` on its own line? Inline mid-sentence? Something like `@019abc`? What's least
annoying to type and paste?

**Answer:**
I thiought of these as inline IDs
Maybe we can use markdown links to beautify? Where the test is alway `Ref` or something like this.

**Do discussion pages show up in the wiki alongside knowledge pages, or in a separate area?**

**Answer:**
They can be accessed through an index page. 
The are also connected to all the pages the effected by ID connections between modified versions.
I want to write this explicitly here: this is a form of connection between nodes which I want to add from the beginning: what text (older blocks, sources and notes) went into writing **this** block


---

## 4. Structure — the one real open question

You mentioned **child pages** (hierarchy) and separately **tagging** (flat, many-to-many). These
are different systems and I don't want to build both for the MVP.

My instinct: hierarchy is what you *read* (navigating a wiki, drilling into child pages), tags are
what you *query* (assemble everything on topic T). You might genuinely need both. But if you only
get one for v1, which one makes the wiki usable?

**Answer:**
Lets go for hierarchy first

We might not need tags at all
I'm not sure about this we have to try this but:
if we need all information on topic T it might get a wiki page 
if that is the case we can collect that and all information referenced from that page (maybe recursively)
and assemble a context from that

I'm not sure how exactly we'll going to assembele context later on but I think it is doable by using the wiki graph and pruning

based on this: go for hierarchy and explicitly mark the context assembly problem as deferred
in v1 we are going for the readable wiki with clickable ids and note submitting

**When you say "child pages" — is that a real tree** (page A contains pages B and C) **or just
links** (page A happens to link to B and C, and the wiki renders that as a menu)?

**Answer:**
I thought of the latter if I described index pages when I used this expression/description
Is that the original context or I remeber wrong?


**Is "watchmaking" a page, a tag, or both?** And what about "knowledge-graph" — the project you're
working on right now? Same kind of thing, or different?

**Answer:**
Really good question.
So I think of this as: regardless of my adhd I **know** I have a special interest in watches.
This can be a topic which has its own wiki page.
Then I add sections for the brands, the models
Those can get their own pages at a point and I build the wiki graph.
I think watchmaking is an entry point through an index page
and if I want **all** the context belonging to watchmagint, I'd use the tree that the index page is referenceing (this'll need heavy pruning, I know)
Also I **know** I work on a knowledge graph so it can has its own page.
And then a page for **all** topics
A section for the 3-5 active I work on
And a section (or more if there is more structure) for all the inactive ones


**Roughly how many of these top-level things do you have live at once?** (You said ADHD and
parallel projects — I want the real number, not the tidy one.)

**Answer:**
I'm actively working on 3-5 at most.
I have hundreds of inactive or finished topics or projects.
This is something I'm quite strict about: active projects are the ones I **actually** work on
Putting a project to inactive doesn't cause any mental friction since we are creating the very system which makes it possible to easily switch back into context and do a task or add some new thought.


**Does a block belong to exactly one page, or can it appear in several?**

**Answer:**
I think it can belong to several.
But I'm not sure about the implications, I'm not educated enough to decide.
Is there something worth discussing here?

---

## 5. The agent as wiki editor

The thing that makes this work rather than rot: you comment, an agent restructures. This is also
the scariest part, because an agent editing your prose can destroy it.

**How much do you trust it?** (a) agent proposes a diff, you approve before it's written;
(b) agent writes freely and you rely on git to catch mistakes; (c) agent writes freely into a
branch and you merge.

**Answer:**
This is the point of the whole rigid read only parts and submitting system
and this is the point of the whole lineage system (which blocks directly affected the generation of this block)
so that we can have the agents write the wiki freely.
We can always revert
We can always ask: what made you write this? and it will be answerable and undoable.

**Is the agent allowed to rewrite your words, or only to move blocks around?** Big difference.
Moving preserves your voice and IDs; rewriting is where the value is but also where you lose
yourself.

**Answer:**
The agents only reference what I write and write their own generated pages.
Also I only read ther pages and refenrence them in my notes.

**Should the wiki visibly distinguish what you wrote from what an agent wrote?**

**Answer:**
I think it will be clear, all generated pages are agent written and all notes are written by me.
Sources are submitted by me in notes and can have their own page which is generated.
Do you think there are cases where this won't be enough?

---

## 6. Links, sources, tasks — quick ones

**Link capture:** you paste `[title](url)` plus a description of why it mattered. Is that its own
note/page, or a line inside a bigger note? And do you want a "sources" view per topic — "every URL
I ever saved about watchmaking"?

**Answer:**


**You're debating archiving page content.** Confirm for v1: link + your description only, no
fetching, no archiving. Yes?

**Answer:**
This is not for v1


**Tasks:** confirmed native in djot, so `- [ ] text` blocks are free and referenceable. Do you want
a cross-cutting "all open tasks" view, or is seeing them in context on their page enough?

**Answer:**
For v1 we are good with having them in place
- Also in reality when I work on a project I always check the pages

**However** this can become a huge friction point if stays the same
- When I manage projects where I work together with my agents I usuaally use one TODO.md file per project
- This is the state where it gets really useful
- Also I don't know if this is something worth deferring
   - If we are having some sort of database for all blocks (in mem or on disk), it should be straighforward to query by block type
      - im not sure about indentation and all but collecting all todo blocks is straighforward with almost all dbs

---

## 7. The corpus — still unanswered

**Existing markdown notes: roughly how many, where, written in what?**

**Answer:**
So I think we have to have two stages here.
I'll need to be able to import some old chat conversations but not now.
As we discussed earlier in this thread I have a problem of "creating knowledge from conversations"
Of course this is an oversimplification since I have other sources but I definitely have a lot of conversations which has very useful and important information
So now we can assume we are going to start small
Ill add some notes and some todos and we can test the system by building itself.

Then I have another topic which is a candidate for a scientific publication
Right now it is approx 10-20 conversations
and I have a story for it in my head (which can be pretty detailed and accurate as I demonstrated on this architecture topic)

So not now but eventually we have to input conversation exports which are in `.md` files (3rd party exporter plugin) or in `.json` format (where I was able to actually get the API trafic.



**`context-harvest/` — do you actually want those chat transcripts in the wiki, or was that an
experiment?** Honest answer please. They're long and low signal-density and could drown your own
writing in topic assembly.

**Answer:**
So, read the contents of that directory because I didn't remember.
It seems like at some points I collected all information fragemented into conversations
and vibe-coded some ad-hoc python scripts so I can save them
The good thing is that this is about the knowledge graph / LLM wiki topic which we are going to solve soon.
So I definitely don't need these right now
Furthermore if theis wiki we build works I'm not that much interested in old architectural conversations so context-harvest might get deleted all together
Lets just defer the faith of that for now
Do not export, do not delete, leave it there


**Is this one repo, or one repo per project?** You have ADHD and parallel projects — do you want
one big store where everything lives together, or isolation between projects?

**Answer:**
I thought of this as one big repo
I thought about some simple structure implemebnted with directoris
but all the djot files with ids are going on one level (root or one directory) there will be no separation in this storage layer based on semantics
All source of truth djot files in the same directory 
- I thought a lot about the name of the directoriy but all seems decieveing (src/, doc/, dj/), I'm not sure
- Another directory for the HTML versions
   - This will be served
   - this is generated deterministically from the djot files (pandoc + css + js)

---

## 8. Dealbreakers — the most useful question here

**What would make you abandon this in two weeks?** Be specific and pessimistic. I would rather
design around a real failure mode now than find it in September.

**Answer:**
1. If I'd feel that my notes are not represented in the wiki pages well.
If the agents can't be stirred this way and I just struggle with the system to display something useful.
That would be a deal breaker

2. Slop
I know this word is overused but it is applicable here
If the created wiki page is just pouring the useless unconnected information.
For example:
I'm taking notes about bands and their music. 
So at some point a wiki page will be created for the band.
If it is a 5 page long general slop which uses 3 lines of my original note, then i won't read it
Not because of pride but there will be a lot of thngs which are not in my focus currently when I take notes about a band and their music and I'll feel my thoughts diluted
If I write 3 sentences about that band we shouldn't have a more than 5 sentence wiki page
If I want general info added (e.g. create a section for the lineup with past memebers) then I'll **explicitly** say
The same is true for the one line intro, I'll write it or it is not needed


**What are you using today that this has to beat?** Even if the answer is "scattered files and my
memory".

**Answer:**
Nothing, I'm having scattered files a lot of projects and anxiety.
Right now I'm not really working on anything because I feel I lose my work if I just take notes and not have this system
This is partially true, partially emotional
however I'm not "using" anything per se.


**Where do you think I'm over-engineering?** You've read my critiques; now aim one at me.

**Answer:**


---

## 9. Free space

**Answer:**
This conversation/work already shows why I need this system.
I submitted a note and we already branched out the approximetely 20 conversations.
I can reference your questions by typing the answer underneeth but if you want to ask for clarification or continue that conversation with details you cant reallydo that
you can edit this file which is ad-hoc of you can cite the paragraph in a new file where ask more about this.
In case of the new system you generate your questions as djot documents
this gets converted to html deterministically by pandoc
I can refresh the page in the browser, read this and copy each ID into a new note or into one note but different paragraphs.
then add my answers there.
If we are starting a conversation about something it is just a page which shows these pargraphs/blocks that references each other.
But this is something I haven2t really thought throuh.

### Other sources
Look for other possible documentation in the repo.
I had a lot of discussion on several of these topics earlier and I'm sure if I let you read other docs besides README.md and the architecture docs you'll find a lot of infor
**However** I think it is valuable that I let the information settle in myself then I'm forced to write down it again because in this way the real valuable stuff remains.
Read other sources in the repo and try to collect the answers to some questions in this doc as well
**Important** there are a lot of deprecated and garbage notes in the repo as well, don't use the found information as fact
but surface it to me (if it's important for our system) and maybe discuss if there are some inconsistencies (there will be).


### Preserving the original
This is something I'm ready to discuss because maybe I'm overcautious
When I import a note (which basically will be a markdown file) we are going to use a deterministic linter to create a syntactically correct djot file 
This should be a determinisitic process
- This mainly will work because **most** markdown files are sanely formatted and easily converted to djot
- Later we can go for all md sources where an agent calls the linter and correts what is possible
What I'm trying to describe here is that we have to store the original but for the system to be able to reference back we have to have a djot file with ids
Since I'm not sure about the transformation process I'm leaning toward storing the original and in this case the origin of the block will be a whole file and not an ID
- This however brings the problem of different id types which is a problem again.
This is something we have to discuss


### Marking TODOs done
This is where my super pedantic system becomes a friction
For text and other elements we know we are going to copy its id and reference it
Lets call this an action for now
The above can restated: every block has a "copy-id" action build in
- if you want to see it implemented earlier check product-evolution.md and the generated html page (with in-file js I guess)

For a todo it would be really stupid to
- copy the id
- submit a note about this being done
- re-render the whole universe
- get a checkmark
- This is definitely a leave-it-dealbreaker

instead a todo block could have a mark-done and mark-undone actions

this seems to break the system because now the html pages write back to the system because for consystency the djots have to be updated

How i plan to avoid this breaking:
the copy action just puts some information on the clipboard
and this same UI action can also trigger an event which **submits a note** one my behalf (since I'm using the UI in v1 always) that the ID has been copied
This of couse has no real usage besides logging

but in case of a todo block
we can embed another action:
- when the tickmark is flipped we always send a note on my behalf: the `xy123` ID TODO is done.

The UI is refreshed by my action immediately
and the djots are refreshed when the UI note gets submitted

I'm open to debate this but I'm pretty sure this doesnt break the system and makes handling todos much simpler
also I think these "UI notes" will be very useful later

however I'm not sure if this is in the scope of v1 


### My comments on your last message

> And the graph's job is lineage: WikiBlock -[DERIVED_FROM]-> (Note block | Source | earlier version of itself).
> That's the answer to the question I opened this whole interview with — what pain does the graph actually solve? It isn't entity extraction. It's provenance. You wrote it yourself in §3: "what text (older blocks, sources and notes went into writing this block." Everything else in Phases 05–07 was a guess at what the graph was for. This isn't a guess.
> The insight I want you to check
> Your anti-slop dealbreaker and your lineage requirement are the same mechanism.
> You said a 3-sentence note must not become a 5-page wiki article, and that diluted thoughts would make you stop reading. That reads like a prompt-tuning problem, which would be unfixable — you'd be forever begging a model to be terse.
> But it isn't, because of the lineage rule. If every wiki block must cite at least one note or source block, the agent structurally cannot write slop — slop has no antecedent to cite. A validator rejects any block with an empty derived_from. General knowledge physically cannot leak in, because it came from the model's weights, not from your corpus.
> And your escape hatch already fits: when you do want general knowledge ("add a section for the lineup with past members"), that's an explicit instruction, and the generated blocks cite that note. The mechanism handles both cases with one rule.
> That converts your #1 dealbreaker from a vague quality worry into a testable invariant. It's the strongest argument I've seen for building lineage first, and it means lineage is not a nice-to-have for observability — it's the thing that makes the wiki readable.
> What the old docs confirm — and where you've changed your mind
> You were right that there's a lot in the repo. product-evolution.md §1–2 describes almost exactly the system you just re-derived: static HTML, click-to-copy block ID, async commenting, agent-applied edits. You reconstructed your own design from memory, which is a good sign it's the real one.

**Reaction** I really like this thinking and I haven't connected these dots. Let's keep this north star

> But you've genuinely changed position in four places, and you should know it:

> 1. HITL diff review is gone. The old design had the agent propose a diff that you approve before the wiki changes. You now say agents write freely and lineage + revert is the safety net. I think your new position is correct — approval gates are friction and friction kills this — but it's a reversal, and it makes lineage load-bearing rather than merely useful.
**Reaction** I also think this is a good change however I have to admit it was unintentional. This new way (let them write and review later) fits better my style by adding some comments and coming back some time later and start the "chat" with my wik/knowledge again 

> 2. Annotation nodes are gone. The old design made comments a first-class node type. Your model makes them just pages with ID references. Simpler; keep it.
**Reaction** I can't really recall what were these annotation nodes. However currently it is somewhat handwaving when we have a conversation page and when just a note which references something. There might be value in a separate questionnaire for this topic when do I submit a note and when do I start a conversation. I think copying the ID will be the same but maybe different submission so different pages are generated (note vs. conversation) OR it can be changed, every submission starts as a note then it can be converted to a conversation. I'm not sure about this. Or maybe we ONLY have conversations so no thinking required? Great rabbit hole.

> 3. Temporal quadruplets are gone. product-evolution.md §3 goes deep on RDF-star reification and valid-time modelling. Nothing in your workflow needs it. Delete.
**Reation** I'm not sure why? It seems to me that by having tasks and returning to projects and steer them definitely needs temporal abilities. "Show me the newest version of..." but maybe I don't understand quadrouplets.

> 4. Tags may be unnecessary. You raised tagging as the first step three messages ago and I agreed. Your new answers barely mention it — because agent-generated pages plus index pages do the organizing. Tagging was a manual solution to a problem you've now handed to an agent. I'm withdrawing my earlier recommendation unless you push back.
**Reaction** You are right we can get away with hierarchy right now

> One thing worth savouring: graphrag_design_review.md ranks "block ID stability under edits" as the #1 risk, the single biggest open decision, and the README calls it the biggest architectural debt (Risk #11). Your immutable-notes rule dissolves it. Note IDs never change because notes never change. Wiki block ancestry is explicit because a generator writes it. The hardest open problem in the repo was killed by a product decision, not a technical one.
**Reaction** No, I had a full delta update and idempotency plan figured out with another agent and documented. Did you find it? Or is this another topic and I just misunderstood you? I don't want to throw away the knowledge collected (and most likely documented) there.

> Also flagging: independent-audit/architectural_audit_response.md is stale — it insists the codebase uses Kuzu and that LadybugDB is "nowhere to be found." That was true on May 10; the migration landed the same day. Don't trust that file.
**Reaction** I know we have to have a clean start

> Three things I'd push back on

> 1. "Saving the file submits it" is a bug. You save reflexively in nvim — mid-sentence, mid-thought, whenever you pause. Combined with "agent starts on submission," every :w fires an LLM call against a half-written note. Make submit an explicit act: kg submit, or a command that closes the buffer. Keep saving free.
**Reaction** You are absolutely right I had in my head what you described (submit on exit) and then typed "save" instead. Absolutely, submit on buffer close (also nvim quit)

> 2. Use SHA-256, not MD5 — and note this is already designed. The delta doc §4.2 specifies exactly your idea: a content hash that doubles as an integrity check, 16-char prefix in the graph, full hash in the log. Your instinct was right and already written down. MD5 buys nothing in 2026.
**Reaction** This is the delta doc I'm talking about. The content hash and versioning based on an ID (separate from the block ID!) was worked out here. I want to keep that I really liked that solution. Or you think we superseeded that?

> 3. On blocks belonging to several pages — you asked if there's something to discuss. Yes, and my answer is no, one page each, for v1. If the same fact belongs on two pages, let it be two blocks that both cite the same note. Lineage already expresses "these are the same thing" without shared mutable state, and shared blocks would force you to answer "what happens when an agent edits a block that lives on three pages" — a question you don't need.
**Reaction** Ok, simplify here and have one block only to one page.










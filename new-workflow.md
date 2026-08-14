It is an interesting situation
I vibe coded myself into something which is not working right now becauswe I did so much back and forth with formats and definitions
But that's not a problem because I'm on a good track now

### Renaming
I think the right question:
- will this ever be public?
    - YES: In that case `kgb` is a name I'd have to change
    - NO: I won't giggle on it day by day but will get tiring really fast

Currently I'm thining it should be something short and not funny at all


### Module system


### Submission and import



### Conversation vs note vs session transscript
Now that I checked how can I use claude code as a cli agent I have better ideas about how to do conversations right

What we already imported into the system is the **session transscript**
This is the broadest set of information we have about or interaction with claude code
This is a long JSON document which has tool calls, subagent spawns, user space command calls
Basically everything anthropic lets us save

Up to this point I tried to make importing this full session transscript as frictionless as possible
However I didn't know which conversation I'm in
- I didn't know the session_id so I didn't know the uuid to look for
- Also the index page is currently showing session transscripts and conversations mixed which is definitely my bad
    - But now we are fixing it

I think at some point I made the rule "Everything is a conversations" and the the agent created an environment for this purpose

I created another section to untangle what is an import and what is a submission
- In the man file submission is for rounds of the conversation {#794b85fd+++}
- And import is for importing the session transscript {#1ff7d574+++}
    - Which I thought mistakenly is the conversation file
- This is definitely not the best categorisation and with the upcoming module system more and more importers are going to be needed

I was thinking about which word to use here
The function which we are going to implement: 

Here's some sort of information, 
- it can be a piece of text (conversation turn)
- another piece of text (just a note to work on later) 
- a JSON document (clade code transscript)
- or later
    - here's a youtube URL capture the video and make a transscript of it
    - here's a faphouse video page, download the video, extract the metadata information from the page

but now I want to concentrate on adding notes, adding conversation-turn adding the session transscript

So I was thinking of what name the subcommand should get
- **submit** Good for a note but awkward for a picture
- **import** Great for binary stuff but awkward for a conversation turn

I found myself that almost all words have some connotation on what we actually do and with what by using these so I landed on two "add or put"

1. Add
    - This is definitely general enough
    - short
    - simply by adding we are not really suggesting that we are doing anything

2. Put
    - well known from http
    - can be mixed up with http

3. Import
    - long and awkward for conversation turns
    - Still this represents the best what we are doing

Right now this is something I have to come up with

Lets assume I land on `xxx` (placeholder) for this subcommand

Then I think the current `import` and `submit` are going to get deleted
I think of the usage as 

```
kgb xxx --my-turn 
```

QUESTION: now that we are thinking about this 
I mostly use the system through `new`
I already thought about untangling this
- I don't really like to have the file in raw as starters
- I currently create draft files work on them on my own then submit them
    - I'm not sure if the draft should be handled by the system or not
    - But I definitely LOVE nameless files which I can just open up and pur my ideas into it

## Unique ID for every entity we work with
It is pretty self explanatory why do we have to give names to all entities we work with
- Files
    - Conversations with agents
        - Claude Code JSONL files
        - `agentic-bootstrap` repo agent
    - Own notes
    - Conversation turn
    - Scraped website as markdown
    - etc
- Nodes in the graph
- Edges in the graph

claude uses uuidv4 which is the fully random version
i should add a uuidv4 for all of these

then we can think of the optimization: how we can minimize the handle content percentage in the context window
    - By handle content percentage I mean: divide the tokens/characters used for 
        a. hangles
        b. useful payload
    - divide the two






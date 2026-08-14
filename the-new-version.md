Durin the implementation of the 0.1.x version of my knowledge graph I came across several usecases and new information 
Based on this I decided to crete a new version v0.2 where I'm willing to break previous conventions in data and code

# New simplified ID system

## Long unique ID
- I already spent a large amount of time to come up with good enough IDs (handles)
- These are central entities in the graph because these are closing the loop:
    - I'm able to cite agent text precisely
    - The agent is capable of referencing my text precisely

- I spent a lot of time trying to come up with the shortest possible unique handle
- A lot of sultions were thought through (fully or partially)
    - Base 32 instead of hex
    - Counter instead of random
    - Structured handles (file:block)
- These all have some problems and solve others
- For this I'm not going to chose a handle system right but make the system in a way that there can be multiple unique IDs for each entity

- Besides this decision (multiple IDs) we have to have one ID which we know always will be there
- To avoid problems we are not opting for size but reliability and go with UUIDv4
- This ID will always be present en every entity in the system and will be unique
    - Every file
    - Every block
    - Every node
    - Every edge
- This is definitely not an optimal handle because it makes notes and context windows crammed
- However it is reliable in scales that are unimaginable for this system
- Works paralell
- Used by several major software project
- We can later optimize for handle compactness or any other metric, the point is 
    - We have an ID to start the system and rely on
    - This question is not blocking us anymore

## Content ID
- This is basically an SHA256 hash of the actual content (text) of the block.
- This is an easy way to find duplicate nodes
    - However it can give false positives 
        - e.g. two headings called `Warning` will both give the same hash but might have very different purpose so clearly not duplicates)
- This can be a very handy tool if we are not overdoing it

## Structural ID
- This come up in an earlier design phase
- It connects to the question of delta update and idempotent ingestion
- I'm not sure about this right now
- This would serve the following purpose
    - There is a block where we are not deleting it or not moving it around in the document, just the text
    - In that case we created a new block (new LUID - long unique id) or do we do some sort of versioning
    - I'm not sure anymore what we would gain with having these versions
        - Maybe we have to modify less structure if allow mutations instead of block change
        - Maybe applying deltas or mutations can help us which edges to transfer to a modified node
            - This is going to be a HUGE problem
- This is definitely not a finished deal
- The good thing: we just decided to design the system so new IDs can be added later

---

# Workflows
- In the first version we are going to go for 
    - Add documents with pandoc
    - Add claude code session transscript JSON

## Adding a note
- A note is just a text document that sits in the system
- It does not start a conversation with agents (contrary to what we planned up to this point)
- It is written by me or it is form other source
    - Since we are going to leech on pandoc AST we can even import full ebooks

**There is a great question here**
- Will I still pump through all the incoming documents on the djot format?
- Would I get anything the AST can't give? It shouldn't! 
- It will be more elegant to just convert everything to AST then ingest that directly
- However I know there is at least the djot IDs which pandoc solves by hacking that on the AST instead of a nice representation
    - But still technically all the info is there the only thing a conversion issue might be: we can't convert pandoc AST to nodes and edges
- Now that I wrote this down it doesn't seem so impossible
- On the other hand it would me much more elegant to just use the AST instead of djot

1. I just want to add a quick something
    - In this case the `kg add --note` command can be used (no file name)
        - This was `kg new` up to this point which I used a lot
    - It is just like nameless funcions, sometimes I don't care about the container just want to add the text
    - Just like up to this 
2. I want to write something then think about then add
    - For this text files can be adde by the `kg add --note <filename>`
    - This helps us void having `kg draft` which would be just a very weird hybrid

### After submitting (adding) my nameless or named note it 
a. gets copied to raw
    - Here it gets it's own uuidv4
    - And the oriinal filename and other ingestion metadata gets stored
        - I think at this point the metadata already can go into JSONL format (graph)
    - the output will be something like `raw/48b1d829-48ef-47d2-a460-54b2658fabe4.md`
b. get transformed to graph format
    - `graph/93a01a34-e7fa-49d9-88ac-5e83ba41196e.json`
    - Again, not sure if through djot or pandoc AST, the AST way would be more elegant
c. misc
    - I'm not sure where these steps take place but I add them here
        - generating the json doc for the metadata
        - adding the edges that connect the metadata and the conversation

And since this is only a doc that is the end of it
- After we generated views from the internals 
    - by default 
        - the djot with IDs for the agents
        - the HTML to serve
        - markdown without IDs for github (have to be copied to place)
- Then I can pass the content to an agent or read it and write my notes on the material or anything else

Interesting question: do we need to connect the views to the original files?
- I think yes but I'm not sure
- And if yes I'm not sure in which step

### Edge layer involved
- Pandoc thinks about documents as a list of blocks
- We have to preserv this list in the graph
- We are going to have the pandoc blocks as nodes in the graph
- We have to add edges that represent the order between the blocks like in a linked list
    - The edge name will show this
- `document-structure` 


## Having an agent conversation
- This is more interesting then just submitting/adding a note
- To be able to mutually reference each others 



---

# Artifacts
We have to be very careful not to get seduced by directly editing an artifact becaus that would ruin the loop how the system is built up to this point
To be hones I haven't even thought about this, just handweavingly said: artifacts are mutable
But this can be a lot of things
And can differ based on the artifact itself
Maybe it would be more clever to think about this is parts

## Text artifact
This was the original idea, like a wiki page the agents and I work on thogether
Now here I never really specified what does mutability means
Just thought:
- I'm going to submit notes (e.g. exchange that to sections, add a new subsection under (handle) named "Example setion"

but an interesting question:
what if I open up 

---

# Connection to the pandoc AST
- This is I think one of the greatest strength this project can have: we are going to use one of the most used document transformers internal format as input and output.
- We are going to have out internal graph representation
    - This means we are not going to use the pandoc AST as our internal representation
        - Mainly because it is a list and we are using more general graph structure

- However we want to be able to easily convert our JSONL to pandoc's JSON
    - This would buy us so much for free after implementing this







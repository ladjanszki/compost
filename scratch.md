- Skolem (terminal 2)
    - re-digest the modified doc
    - try to understand what this means
    - I think I'm not interested in type classes I want to see pairwise equality?
        - I tell some usecases where I want to use this squashing


# Skolemization
- So this was very interesting to think about
- I have a lot of ideas and I want to discuss them
- You told several times that the hashes as an almost collision free way to distinguish two Skolem terms
- For us here the use-case is
    - I want to decide if we seen this information or not before
- This was the role of the hashes 
    - the node can be identified by the record hash
    - if two record hashes are identical due to chance (All sections called `# Appendix`) we distinguished them through the subtree hash (positions)


- Now you told me several times that the actual skolem term is the expression and the hash is an index.
- So I started to think about this 
- My first thought was: you are right!
    - In case of the claude code transcript we can match the trees and check for the same structure
    - In this way we would actually use the terms instead of the hash
- But this is not skolemization
- Because I'm expecting the transformation to be non changing implicitly
- We can't do this, the point of skolemizaiton is that I have the funciton as well
- Now we can save the transfomation that creates the internal blocks form the pandoc and claude code json blocks
    - I talked to an agent and we already found how this can be done in duckdb with SQL
    - This is even more self containing than having a python script saved (the current transformation from json to internal node)
- But then we talked some more about this and I realised we can save the actual terms we are transforming

## Claude Code Transcript
- We have a jsonl file which sits on a disk
- This is an append only log described in detail by this page [Claude Code JSONL transcript format explained](https://claude-dev.tools/docs/jsonl-format)
- Up to this point my main north star was: do not delete anything we are squashing/unifying these later
- Now this was my safeguard against having special solutions for special cases, I wanted to have general solutions
- But we are working on a claude code transcript ingestion which **should** use our knowledge on the file, the grammar and how it is written
- Since this is a guaranteed append only artifact we can absolutely dedup **at ingest time** with 100% certainty by walking the already digested tree.
- If there is no current tree -> ingest
- If there is a current tree -> add the newly appended part (if any) to the end
- This should be tested but I think a session_id is fully identifying a tree, then we can compare by walking it.
- Now the good question is: how early on we should do the dedup?
- Based on this the Claude Code transscript (based on it's properties) doesn't need any hash based comparison at all


### Skolemization here
- We have a jsonl file as raw input
- Here I'm describin skolemization as how can we exactly trace the function and the input (based on an index for example) to actually have the term for indexing

- In a JSONL file we have a JSON document in each line
- These documents can be canonized


---

### Review: TODO - a section container of our own
- The first part of the docs reads if the agent who wrote this wanted to 



---

# Last questions on 0.3.0

> 1. The prompt is unwritten. How the map is rendered, how a block and its path are rendered, and — critically — how abstention is invited rather than merely permitted. A model told "classify this" will not decline, which quietly defeats your false-negatives preference.

This question really got me thinking and I realised that for me to be able to answer these I have to clarify my workflow

- Configuration
    - As we already talked about this, this is the first layer building where there is a file input
    - We also agreed on using a markdown file where I add the tags/labels and subtags/sublabels
    - I think markdown is not the right format for this
    - Using this file directly by you adding blocks is a good idea first
    - But we also agreed on that the headings are going to be the labels/sublabels directly
    - I think this is good at first but leads to a fragile design where editing a heading acidentally can lead to a lot of trouble.
    - And even if we can track back because the file would be a mutable artifact it still feels fragile to me that part of the file is the query (heading) and part of the file is the result (section content)
    - Maybe it is just me but it feels hacky
    - Based on this I thought we should use a `.yaml` file instead of the `.md`
    - And even the first text artifact would be generated from the start
    - What happens in this system if change the title in the md file?
    - I guess because the titles are pre-configured we should give an error and do nothing
    - I think this is a much more intuitive behaviour than half query half result md files
    - Also the passing of a yaml file gives us a lot of possibility to configure this layer building **and** layer building in general if we use this elsewhere
    - I created an example yaml file in a local scratch directory outside the repo
        - I'm not sure if it's syntactically correct but shows how I imagine giving the tags and some description for them
- Rendering of the blocks
    - This build process creates 
- Is this really a layer build?
    - I mean I got that we are creating edges and nodes which was a layer building up to this point
    - but now we are assembling a text artifact from that blocks which makes me these somewhat differnt then creating an alias node
    - I don't want to change anything but we whould think through this vocabulary as well after 0.3.0 have been reached
- The prompt
    - I don't have any strong idea besides what we agreed on
    - Describe the situation what we are doing as good as you can
        - We have to remember that we are building the prompt for a less capable model which we can call cheap on openrouter
            - Or behind any OpenAI compatible API
    - I really liked the idea that each block that the have to be decided should bring the whole path with them
        - I imagene this as actually rendering **OR** passing the subgraph of markdown headers and parenting list elements down to the node we are categorising 
        - Then ask for a label and possibly sublabel from what can be found kin the configuration yaml file
            - Emphasising that config specific "non of the above" exists and is a very valid answer
        - If we are checking multiple children together we can pass on several siblings all at once 
            - So we don't have to pass all the path for every node on every level
        - If we don't have enough block for the batch of course we can pass on another section with enough children
    - As you can see I don't have a final prompt but I have some ideas as input
    - I think emphasising the possibility of "non of the above" is a prompt question and I don't know how else we could make it more prominent
        - I don't want to overdo this because then we will have very few and very strong hits


> 2. The response contract. A batch of 100 goes out; what if 97 come back? A missing or hallucinated identifier is the normal failure here, not an edge case.

- I think just as we did up to this point give a loud and clear error. I want to see how many pain this cases before we actually go into fixing it
- Later we can think about JSON reammar checking or even pydantic but not now
- What we should check from the beginning
    - Is the label (and optional sublabels) come from the configuration file?
    - The number check is cheap and a great catch
    - Lets see the severity and frequency of failures here

> 3. Failure mid-run. Forty-nine calls; if call thirty fails after twenty-nine succeeded, is a partial run written or nothing? This bites directly on one run, deletable whole — a half-run that looks complete is worse than no run.

- I'd say refuse which is the default for this project
- And I think this is good enough solution until my whole project folder can be categorised for a few cents
- We can think about some failsafe methods when this gets more expensive
    - Continuation of runs with incomplete batches only
    - Where to store until finished
    - Etc
    - This needs designing which I don't think we should now
    - But this will be a real question with volume
> 4. Prompt versioning has no home, though the design requires it.

- I think the prompt can be a text artifact which is versioned by default from now on
    - Am I right?

> 5. What a view shows for a block whose topic belongs to a superseded map revision.

- This question would be totally solved by the yaml file
- If the topic is not there we are not collecting (dropping) the blocks
- I already suggested to give error if the yaml diverges from this first collection 
    - Which will be rendered and served so I can comment and iteratively work on this
    - Maybe we are going to use more layers of generated text after this
        - e.g. from these collection pages we can write the actual wiki pages by feeding every block in a section (label section) and point to the soource of the claim in the rewrite

> [!note]
> I think this is apretty significant idea here
> This first semantical grouping will only create a collection page
> Then we can rewrite by topics to get the actual readable wiki file



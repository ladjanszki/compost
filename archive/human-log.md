## copied ID revamp
We already did a great job in reducing the ID overhead from 27% to 10%
We achieved this by going from composite id to 8character hex IDs
Let me ask an interesting question
the characters we are storing and you are reading are utf-8 I guess
So we can encode **much more** in a character than 16 varants (hex ID)
I get that using the full utf-8 character table migh cause ambiguities
but is there an extended alphabet over 16 so we can shorten the ids even more?
I think case sensitive is not a good idea here so Id go for case insensitive
but A-Z + 0-9 + (some specials) + (others from utf table)
I think we can go down to 4 character with this


## Conversations are almost breaking the djot format?
I feel that the conversations are almost toolong for the djot format
as you noted earlier in a conversation it is routine to emit the fencing characters (`:::` if i recall correctly) so it can't be made sure that a tool use output doesn1t break the system
regardloss of our effort?
If this is true (at least partially or there is a risk) maybe we should have one djot per turn and assemble only in HTML?
I don't want the shource of truth to be fragile


## Obsidian style frontmatter
I'm heavily debating this and I think I'm going to implement this
- Since we are going with JSONL files now this is no op I think


## Conversations don't have to be named automatically
- the user can have a chance to name them in the meta


## Pain point when accessing references
Now we are going back and forth with claude using the handles system and there is apin point where I have to understand what claude is referencing
In the djot view the agent has grep and able to fetch the reference pretty fast
I however read the HTML and only see the reference handle

> OK, since this keeps happening, in the meantime also I'd like you to modify the TODOs.
> I think this section {#845f1309+++} is not "Next" but morelike "Misc". These are mostly things which lef over from earler develpoments.
> And I'd like us to come up with a solution so I can easily see what the text is referencing

I wanted to write the quoted text above after I asked to resolve the IDs in {#5d5b69f1} for the second time in a conversation
And this is what started this request

On the HTML view I think a link would be the easiest
- I click on the reference to see the block (and the page around it if any)
- The block and its text appears for hover over
    - This seems like a good to have for later
Or at least a CLI tool here as well
- And this would be useful even for agents: `kg` cli subcommand for resolving IDs


## Differentiate djot IDs and pasted references
Currently the same format is used for the djot headers and when the copied ID is used as a reference in the text
This is currently not causing problems due to the stric parsability of djot
However this is not good
- Agents can misunderstand
- humans are even more prone to misundersstand
- However the parser seems to handle this fine it feels like an abuse which looks for trouble in the implementation (having the same id over and over again but syntactically just one is relevant... feels fragile)

Every time I write answer for a list of questions I afraid to put the handle in the list item because I'm afraid It'll parse as a djot id and breaks the system
references have to by different from djot IDs
Even full links in the HTML view


## Quick refresh conversation
I want to click a button on the HTML UI or at max run a cli command which re imports the claude conversations which have been appended
I know this can be done with the cli if I know the log file name which is in the `~/.claude` library
But that path has several friction 
Best would be UI (but that depends on the UI messages which was never implemented)
or an easier cli way (preferred right now) which updates all conversations that claude stores for the project `.claude/project` has a subdir structure for this


## unexpected automation
How come the system submitted my note as a conversation turn here?

> ❯ kg new
> appended to conversation 019fe816-e1ce-7a60-9643-edf50fdd80ee
>   turn   019fec26-11de-716b-8bd1-fb84471c153e  (15 blocks, author: human)
>   draft  /path/to/knowledge-graph/raw/019fe816-e1ce-7a60-9643-edf50fdd80ee/019fec26-11de-716b-8bd1-fb84471c153e.md
>   file   /path/to/knowledge-graph/conversations/019fe816-e1ce-7a60-9643-edf50fdd80ee.dj

I don't want the system to guess that I'm answering something because I'm using the handles from there
I want to explicitly discuss the rules
I thought about creating answer handles to make this explicit but I'm not sure about the details


## Re-ingest and delta
- What happens when we ingest something the same the second time
- What if something changed (e.g. turn appended)
    - Do we use delta?
    - Throw away everything?
    - I already thought about delta a lot with agents before


## Temporal data
Since we are debating back and forth on a given topic sometimes for weeks we have to keep track of time
I'm not saying that even the "superseeds" connection requires this but I'm sure we should involve time from the beginning
Even in the text version


## File metadata problem
Connecion to index page rendering problem
- What should be shown on the index page as file name
- starred conversation (to have TODO, CHANGELOG and README separately)

Original problem:
It was more then once when designing the system with claude that I havent find the file because I looked for the ingestion filename or something based on my logic
and the system used other defaults.

this has to be formalised
what metadata to store? We have to create nodes and edges respectively
etc. etc.




# 0. The renderer can't reuse records_to_ast

This is a new situation we are going to face mode and more as we add new types to the graph which are not originating from pandoc
I'm not sure how this will be translate to everything else.
For me the solution to this was something like a `to_string` method for objects
We can create a `to_pandoc_ast` like behaviour. 
If a node came from text then the pandoc representation is easy to build
If the node come from somewhere else (like a session JSONL) then we have to define the text representation 
In our case these are going to be text input and text output for files.

This already worked to some extent in the original version.
True that back then we haven't made this ourselves but djot to html carried the weight.

Can we do the `to_string` analogy here?


# 1. What "collapsed by default" means in a static file
Great catch!
This is a very important optimisation however this is optimisation.
Collapsed HTML is what I thought of so I can read the HTML version in the browser easily
In case of the djot files first lets just leave the tool text there (I think this is the div wrapping solution we had in the previous version) 

Later I think we are going to leave the handle for the whole block there so it can be queried (read from disk) in case it is required.
Maybe even on the fly parsing for better understanding.
But these are for later!
Right now all the information will be there
the djot just shows everything
and the HTML visually collapses those "sections"


# 2. What the stub says
Nothing right now, later a handle so the agent can get the whole information


# 3. Whether a call and its output are one citable thing or two
Lets use what is already there (two blocks) to be honest I'm not sure if I ever cited a tool block or not
But let's just use how it is actually
the later we can prettify


# 4. Which session nodes are citable at all
So this is a real issue which requires design
Right now do something simple.
Like we can cite the rounds and the calls and tool outputs.
Obviously the text inside turns can be cited but the text inside other types of node can't be referenced.
How about this?


# 5. The 491 empty thinking nodes
Claude doesn't emit them, other agents do, let's have the node for them!

# 6. file nodes have nowhere to go
Now this is very interesting if this is the same topic I was thinking about
So files have to be represented somehow
because we are going to create python files with agents and other files are read as well
So maybe we can create file nodes for the files in the repo we are contacting with
just as book-keeping first
Maybe we can note first that these are not the files representing the documents but outside files we are just talking about right now and not going into them further
(file representation node)

# 7. Escaping — the old problem, moved
Maybe we have to re-write the actualcitations again?
To be honest I never liked that there is a one character difference.
Can we use other types of parentheses maybe 
Or I thought about using actual markdown links for referencing?
Try a few version and argue for and against the link version


# 8. Turn order: file order or the parentUuid chain
This is a graph DB (in disguise) 
The edge value is there already
we have to have a layer for claude-code-session-transscript, parent (or contain or something)
and add this to edges
if there is an edge for this don't assume a wrong order first



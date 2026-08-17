# New v0.2 plans

At this point we are breaking backward compatibility furthermore also entirely scrape what we already have
Not the ideas (those are mostly restructured) but the code
I'm not just speking figuratively about scraping the code. 
I don't want us to use any code from the previous version and build this new importer and base functionality in an empty directory

What I'm debating is how to do it
Currently I created a new directory named `pandig-text-importer`
I want this first two steps of the development to take place in this new directory

We are going to work on the core functionality of the system which is the text importer

Contrary to previous plans the 0.2 implementation starts with creating a roboust connection to pandoc (later to pangraph)

Another change from the earlier versions is that we are only going to import pandoc ast first.
If we are capable of roundtripping pandoc ast to our internal JSONL format then we have gained access to  a very large corpus in the form of graph

For this I want us to work on a roundtripping for the first time.

## 1. Roundtripping with pandoc only
- Lets create a directory where we collect several documents that are in pandocs format list
    - then we are converting the document to pandoc AST save to file
    - then back to the original format
    - then we compare the two
- In case of a markdown or txt file I think diff is good enough to check the roundtripping
- In some other formats I'm not sure about the check
    - Like a pdf I don't think that have to be byte by byte the same as the original for the roundtrip to be considered succesfull
    - Also for HTML I'm not sure if it has to be character from character the same for the roundtrip to be considered successful
- But first we can go for the real text based formats
- It is important to save the pandoc AST as JSON file and start another transformation from there
- For starters we are collecting a few documents to use as samples where the original -> pandoc AST -> original works

### pandoc-types as the definition for pandoc AST JSON
- I'm also adding the pandoc-types github repo to the folder
- This is the ultimate source of truth when it comes to pandoc AST definition
- Since I can't read haskell I can't really check if the usually cited `Definitions` file is enough to have the JSON format derived
- This knowledge will be used when we read and write the pandoc AST
    - In this current effort I plan to use the pandoc AST as unified input for text documents
    - So all input we are going to receive as pandoc AST
    - And the rendering (view generation HTML, djot, md) will also goes through generating pandoc AST then using pandoc to create the actual documents

### pandig's (own) node and edge format**
- Since I want to start to store documents in this version we have to come up with our own node and edge schema
    - The good thing is that a lot of ideation went into this when writing the first 0.2 design draft.
    - The already existing draft can be found in `artifacts/graph.dj`


## 2. Roundtripping with own blocks
This is where we are heavily borrowing from the original `artifacts/graph.djot`

I copied {#1d7b3ce4+++} and {#24725730+++} below as subsections
I made a lot of changes on them compared to the `graphs.djot` draft

### The record format

- The paragraph {#f9b3907c} survives fully! 
- As you can see I have a lot of open questions in this section
    - I'm definitely open to suggestions on how to name the keys and the values
    - And what values to store for both node and edge 

#### Node

{#8bf4e663}
```
{
    "this-object":"node",
    "guid":"d826c4dd-eb36-4da9-acab-f6f424a90803",
    "type":"text-block/paragraph",
    "content-hash":"99355172b2735ba755232245ff002d8fe64742851cbb347f2862aff3a4be2fee",
    "text":"..."
}
```

- I find the description in {#2cce7317} quite handweavy
- Also I like to use bullet list and numbered lists more, it is easier to extend
- Some comments on your original table

- `kind` -> `this-object`
    - I'm not sure if this is a valid naming or not but makes so much more sense to me than having an object with "kind", "type" and label which is also a type
- `id` -> `guid`
    - The global unique ID we are going to use before optimising for context filling
    - This is a UUIDv4
    - Currently we are going to use only this until the system is functional
    - **Then** we optimise this
- `type` 
    - Concatenated label and type with a `/`
    - maybe not the best idea but at least in case of the text blocks it's much less confusing
- `hash`
    - added a real SHA256 hash as example
- `doc`
    - I'm not sure what is this and it's not in the table so I deleted it
- `prov`
    - Deferred to later steps in the 0.2 plan
    - Right now we are deling with `pandoc-ast` edges only
- `props` 
    - I'm not sure we should add a blanket key value storage before seeing the pain.
    - I don't think we should
- `label` 
    - I would need some more details before going for this list `block`, `turn`, `document`, `toolcall`, `session`, `file`
    - Most of this would be interesting later currently I think `text-block` is enough and the subtypes within
- `type`
    - block type for text-blocks: 
    - I thinkwe should support **all** pandoc AST blocks 


#### Edge

```
{
    "this-object":"edge",
    "content-hash":"6b4e5bfad8bfcdc5958170f8d38a2af9315c31fd3cb6203c64db1e7abf04ebeb",
    "layer":"pandoc-ast",
    "type":"next",
    "source":"1218c3a0-d84e-4900-92db-ed29a915d7bd",
    "destination":"1218c3a0-d84e-4900-92db-ed29a915d7bd",
}
```

{#5d1afabf}
An edge\'s `id` *is* its content hash, over `(layer, type, src, dst, props)`.

In case of the edge also a lot has changed
- I added the name `this-object` here as well but I'm still not sure if this is the right name and casing
    - I definitely don't want a `kind` and a `type` as well in the node object
- In case of the edge object `layer` and `type` has a type - subtype relationship just as type has subclasses in the node object as well
    - We can use `type : pandoc-ast/next` for example
    - However the JSON is a nested structure it self so further complicating with `/` notation is a bad idea
    - How should I store this relationship on a JSON native way?


### Identifiers
- Identifiers are simplified in the first two steps of the development
    - I let this topic block me for so long then I realised this is an optimization step so I postponed it
- We are going use uuidv4 identifiers for everything
    - And this is an interesting point here because it seems that edge won't have a guid
        - It is not so useful because if we connect the same two things in the same order with the same type of edge we don't add new info (so the content hash is enough)
        - However we had a uuid in mind for everything up to this point.
        - I'm open to debate this as well
- However (and this is very important)
    - the system is and will be designed in a way that adding new IDs are absolutely possible
    - I have a lot of ideas on how to do this technically and I'll add a writing on it
    - The point is: right now we are going for the surely wortking guid and later we can check dictionary or counting (base 10 or base 32) etc.


## New directory system
- We are going to use `.compost/` instead of .kb marker
    - The directories are hidden if this is used as a knowledge graph in the git project
    - Currently I use it as its own knowledge graph in development and it is really hard and would not be much simpler in another project

- Rename `raw/` -> `.compost/storage/`
    - The default storage for the load which is not stored on the graph directly
- New directory `.compost/graph/`
    - This is where we store the `.jsonl` files which build up the graph
- New directory for the generate views `.compost/views`
    - `.compost/views/default-html`
    - `.compost/views/default-djot`
    - `.compost/views/default-md`
    - These three views will be there by default
    - These are the current HTML view, the current djot files under `artifacts` and we are generating markdown pages like CHANGELOG and README as well (if I recall correctly)
    - These are going into these directories




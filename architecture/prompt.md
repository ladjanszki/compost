I had some great conversations lately with agents on how to design a knowledge base for my own workflo
We went through several itrerations of design and we solved many questions.
One of the problem was document storage and such.
Examining from several perspective we settled on using Kuzu as a graph database to store my block based documents.

The last conversation which puts into more "historical" context what we'll going to do can be found here.
`architecture/web-ui-conversations/Gemini-Block-Based Knowledge Graph Extraction.md`

Our first test:

We are going to use and example markdown file

```markdown
# Example heading - for the test file
I'm writing the first paragraph which has *bold* and _italic_
And maybe other text

Another paragaph about lorem ipsum
And the beauty of life

## This is a nested heading
And in this part we'll have a list as well

- just
- for
- the
- fun
```

This is both a valid markdown and djot file.
I'm bringing djot files here because they are going to be used as human and agent readable format instead of markdown
This decision is supported ba many facts.
I'm willing to discuss but the undersanding of this decision is not required for the test

## Test 00
1. Get the markdown snippet (see above) and save it as `test_00.dj`
    - Since this also passes as a djot file we are not going to start from here 
2. Use pandoc to transform to JSON
    - Pandoc can output Pandoc AST format which is our current target
3. Based in the discussion I linked above, the pandoc AST gets "flattened" and `COPY`-ed into Kuzu

Let's start here.

For this you
- Have to create a conda env called `knowledge-graph`
- Install Kuzu, Parquet, other stuff which is required
- Write the code for the above described `Test 00`

I know this is vague but I deliberately don't want to give too much context.
Ask clarification questions if required so I can see which part of the context have to be shared.
First we are just *planning*, not codeing.

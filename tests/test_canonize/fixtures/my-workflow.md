so how do I work.
In a lot of ways.

An empty page is not frightening to me, an empty page is the ONLY way I can start to work
On the questonnaire, I felt very bad about me having the put my long for answer into a code block
Not for pride but for lack of free formatting or syntax highlighting 
But maybe mostly emotionally.
So this is a high priority: I love to write my answer in a new file.
Also not in a chat window but in neovim where I feel I can write delte 
add newlines and move around with the cursor
Then I "submit" this not to the system

I think this note should have an ID in it if this is a reaction to the contents of the wiki
Or maybe the note doesn't have a reference to existing content and it is new

I thought about tagging here already
I try to talk myself out of the soulution that a neovim plugin is the best way
However I'll do most of my writing in nvim and adding tags is just an example
With a plugin I can pull up a list of tags and other metadata (person, urgency, etc)
But I feel this would be a rabbit hole og it's own

Then I submit this note and it gets ingested
This is weak part again:
Somehow the note tujrns into a djot file where the parts are referencable
this is great for an already markdown formatted text but as you can see I write mainly in these parsgraphs
If these are referenceable after a note like this transformed into djot then we are good.
Also sometimes I use headers and bullet lists in longer notes.

So these ideas are the base layer
Also I'm going to have a lot of chat conversations as "raw input" as well because one of the main modes how I do interact with the system is
"I just submitted a note about this paragraph or heading or list from the wiki, lets chat.

I also thought of going extreme with the read only wiki and not implementing a chat.
Instead there would be a separate set of pages where the discussions are stored.
I can answer to a given thread by copying the ID of the message
(maybe these pages are specially formatted so it is easier to see why I answer for)
Then I submit this note which I write in nvim and have all the IDs so the llm is able to understand which part of the wiki I'm talking about.

It also connects to browsing.
I have a grat plan with a browser plugin for easily adding content to the knowledge base.
But first I have to think of something simple.
i already use an extension which copies the URL and the title of a page as a markdown link
I'm going to add pages like this and I'll also want to be able to add some descrtiption
why this is important for me, connects to what topic, when
Also I'm debating if the link and the description is enough or not. 
It can be a good capability to actually save the content in question later (video, text, picture)not just the link but it is another rabbit hole on its own again.

I also want to be able to add tasks associated to the ideas here
This is part of standard djot so I don't want to extend on that.
Also as far as I understand all todos `- [ ] text` will be their own referenceable blocks so I can talk about a task directly as well.


Then I leave the project.
After a few weeks I come back

I want to be able to stsrt to read my own wiki which leads me back to the context in a way I already corrected and talked about.
Read the child pages and get into the part which I have to ship or have an idea for
These are the two main causes of revisiting a project.
OR when I have a question: "what was the case with the DCC locomotives? I remember they need a square wave but why and how?"

And then based on the ID I can pick up a task of a part I want to discuss or further extend and work in neovim by adding more text.

The part what is **automagical** in this user flow: I submit my notes and websites with descriptions and URLs. And I want to read a structured wiki which I interact with
But it is not automagical, I iteratively improve the wiki.
I might add a comment to a whole section: "IDxxx this belongs under another part because locomotives are blah blah" and in this way I can structure even the pages.

This I think is a full circly with minimal tooling.
Later we can ingest videos and websites and everything else 
But I have adhd and I need a reliable project and context store

Also as you can see files are these throwawy stuff in my idea so I'm thinking of having `random-uuid.dj` filenames.

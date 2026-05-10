It is really good that we are talking because what you reported to me shows that we lost track of the phases, version and steps.
Good news, I remember the intentions.

Let me tell you the current main idea with timeline then what we have to do to the repo so it gets clean
- the project is about building this graph based knowledge system
- in the beginning to reduce complexity we stored the ingested documents in jsonl files and this was the storage "backend"
- When this was the case it seemed like a sound future possibility that if we'll have so many jsonl files at least we have to index them for retrieval
- After discussing and weighing the situation with several agents we decided to make the first version work with JSONL files and as soon as possible we are switching to a graphdb which is basically a specified database for our use case
- After the initial version works with the files and LadybugDB gets implemented the workflow changes
- We take the djot files, then flatten tehem to parquiet for batch ingestions
    - This step MIGHT uses jsonl as an intermedier step but it is definitely just caching (and I think we dont even need this because we can easily write the parquet from a list flattened in the memory)
    - So no JSONL is justified bsides re-generation (which is in a later phase if I remember correctly)
- We feed the parser the djot documents -> parquet files -> LadybugDB -> jsonl -> djot render
    - This is the new workflow and in Phase 2 I think we only implement the pipeline until it ingest the files into LadybugDB by COPY

> [!warning] Based on the above mentioned we definitely don't need the jsonl in large quantities (debug and export only) and we wont use SQLite at all
> Based on this we have to clear out the timeline and the documentation

**Directory structure context and what have been already done**

1. I deleted the `djot` directory, we not used it anymore 
    - you can commit this
2. I also deleted the `data/` directory, test data is not living there anymore
    - This can also be committed
3. I removed some `.md` files which was clearly superseeded or temporal
4. `architecture/` - This is where the largest cleanup is required
    a. `web-ui-conversations` moved out of the repo - superseeded sources
    b. `open_questions_and_discussion_items.md` this should be moved into README.md
    c. design-docs - all files here have been moved to `architecture/` root
        - subfolder deleted
    d. new files in the root dir (from design-doc/)
        - agentic_local_knowledge_store_v1_design.md        -> [SUPERSEEDED] First written design document after initial agent conversation; not relevant anymore
        - agentic_local_knowledge_store_v1_design_v2.md     -> [SUPERSEEDED] Design afeter some more conversation; not relevant anymore 
        - agentic_local_knowledge_store_v1_design_v3.md     -> [SUPERSEEDED] Another iteration and I'm not sure why we kept all of them; not relevant anymore
        - agentic_local_knowledge_store_v1_design_v4.md     -> [SUPERSEEDED] Another iteration and I'm not sure why we kept all of them; not relevant anymore
        - agentic_local_knowledge_store_v1_design_v4.dj     -> [SUPERSEEDED] Just to show the same doc in djot format, can be deleted 
        - agentic_local_knowledge_store_v1_design_v4.html   -> [SUPERSEEDED] Same iteration in html format, can be deletd 
        - agentic_local_knowledge_store_v1_review.md        -> [SUPERSEEDED] First review, not relevant anymore 
        - phase_00_design.md                                -> [DONE] historical 
        - phase_00_implementation_plan.md                   -> [DONE] historical 
        - phase_00_review.md                                -> [DONE] historical 
        - phase_01_design.md                                -> [DONE] historical 
        - phase_01_implementation_plan.md                   -> [DONE] historical 
        - phase_01_review.md                                -> [DONE] implemented 
        - phase_02_design.md                                -> [TODO] 
        - phase_02_implementation_plan.md                   -> [TODO] 
        - phase_03_design.md                                -> [TODO] 
        - phase_03_implementation_plan.md                   -> [TODO] 
        - phase_04_design.md                                -> [TODO] 
        - phase_04_implementation_plan.md                   -> [TODO] 
        - phase_05_design.md                                -> [TODO] 
        - phase_05_implementation_plan.md                   -> [TODO] 
        - phase_06_design.md                                -> [TODO] 
        - phase_06_implementation_plan.md                   -> [TODO] 
        - phase_07_design.md                                -> [TODO] 
        - phase_07_implementation_plan.md                   -> [TODO] 
        - ARCHITECT_REVIEW.md                               -> [TO REVIEW] Your own review of the current state which will requoire it's own review after what I add here 




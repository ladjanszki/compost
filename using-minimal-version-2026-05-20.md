I have created a comprehensive "Cheat-sheet / Quickstart Guide" to help you understand querying the graph, along with a python script to run it directly!
Here is what was added:
1. docs/ladybugdb_quickstart.md: A detailed markdown guide that introduces the graph schema (Page -> HAS_BLOCK -> Block -> LINKS_TO -> Page). It walks through how nodes and edges connect and contains a Cypher query "Cookbook" explaining exactly how to think about structural graph querying using the data provided.
2. sample_data/math/*.dj: Created three interconnecting Wikipedia-style Djot files: probability.dj, stochastic_process.dj, and markov_chain.dj.
3. run_quickstart.py: An executable python script you can run immediately to wipe the database, ingest the sample data, and output the answers to the queries listed in the quickstart guide.
To try it out:
Simply run:
conda run -n knowledge-graph python run_quickstart.py
This script will output the actual query structures alongside the results (like Markov Chain blocks sequentially reconstructed, or a Page-to-Page Citation mapping). 
You can then open docs/ladybugdb_quickstart.md and read alongside the output to understand exactly how Cypher matches nodes and paths under the hood. Let me know if you want to explore any specific graph theory queries (like shortest paths or connected components)!

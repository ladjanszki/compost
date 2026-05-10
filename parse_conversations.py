import re

def extract_relevant_context(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by conversations or markdown headers if possible, or just look at paragraphs.
    paragraphs = content.split('\n\n')
    
    keywords = [
        "Agentic Local Knowledge Store", "LLM Wiki", "Kuzu", "JSONL", 
        "SQLite", "Pandoc", "djot", "BlockNote", "WYSIWYG", "LangGraph", 
        "LadybugDB", "Cypher", "Phase 05", "Phase 06", "Phase 07"
    ]
    
    keywords_lower = [k.lower() for k in keywords]
    
    relevant = []
    for p in paragraphs:
        p_lower = p.lower()
        if any(k in p_lower for k in keywords_lower):
            relevant.append(p)
            
    with open('extracted_facts.txt', 'w', encoding='utf-8') as out:
        out.write('\n\n---\n\n'.join(relevant))

extract_relevant_context('context-harvest/02_unified/ALL_CONVERSATIONS.txt')

import os
import shutil
import real_ladybug as lb
import warnings

# Suppress pyarrow warnings for cleaner output
warnings.filterwarnings("ignore", category=UserWarning)

from src.ingest.ingest_page import ingest_page

DB_PATH = 'workspace/store/ladybug/db'

def clear_db():
    if os.path.exists(DB_PATH):
        if os.path.isdir(DB_PATH):
            shutil.rmtree(DB_PATH)
        else:
            os.remove(DB_PATH)
    print(f"Cleared database at {DB_PATH}\n")

def run_ingestion():
    files = [
        'sample_data/math/probability.dj',
        'sample_data/math/stochastic_process.dj',
        'sample_data/math/markov_chain.dj'
    ]
    for f in files:
        page_id = ingest_page(f, author='quickstart:human', db_path=DB_PATH)
        print(f"Ingested: {f} -> {page_id}")
    print("\nIngestion complete!\n")

def execute_and_print(conn, title, query):
    print(f"=== {title} ===")
    print(f"Query: \n{query}\n")
    try:
        result = conn.execute(query)
        # Hack to get column names (Kuzu/Ladybug doesn't easily expose them on the python result object in older versions, we'll just print rows)
        count = 0
        while result.has_next():
            row = result.get_next()
            print(f"  -> {row}")
            count += 1
        if count == 0:
            print("  -> (No results)")
        print()
    except Exception as e:
        print(f"Error executing query: {e}\n")

def main():
    print("🚀 Starting LadybugDB Quickstart 🚀\n")
    clear_db()
    run_ingestion()

    db = lb.Database(DB_PATH)
    conn = lb.Connection(db)

    # Recipe 1
    execute_and_print(conn, 
        "Recipe 1: Retrieve all pages",
        "MATCH (p:Page) RETURN p.title, p.id"
    )

    # Recipe 2
    execute_and_print(conn,
        "Recipe 2: Reconstruct a page sequentially (Markov Chain)",
        "MATCH (p:Page {title: 'Markov Chain'})-[r:HAS_BLOCK]->(b:Block) RETURN b.type, b.text ORDER BY r.position"
    )

    # Recipe 4 (Modified slightly for output cleanliness)
    execute_and_print(conn,
        "Recipe 4: Page-to-Page Citation Map",
        "MATCH (p1:Page)-[:HAS_BLOCK]->(b:Block)-[:LINKS_TO]->(p2:Page) RETURN p1.title AS source, p2.title AS target"
    )

    # Recipe 5
    execute_and_print(conn,
        "Recipe 5: Finding Backlinks (What links to 'Probability Theory'?)",
        "MATCH (source_page:Page)-[:HAS_BLOCK]->(b:Block)-[:LINKS_TO]->(target:Page {title: 'Probability Theory'}) RETURN source_page.title"
    )

    print("✅ Quickstart complete! Check docs/ladybugdb_quickstart.md for explanations.")

if __name__ == "__main__":
    main()

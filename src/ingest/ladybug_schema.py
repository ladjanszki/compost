"""
ladybug_schema.py — create node and relationship tables in a LadybugDB database.
"""
import real_ladybug as lb

def create_schema(db_path: str = None, conn=None) -> None:
    """
    Create all node and relationship tables in the provided connection.
    If conn is not provided, opens the database at db_path.
    """
    if conn is None:
        db = lb.Database(db_path)
        conn = lb.Connection(db)

    # Use IF NOT EXISTS for tables
    try:
        conn.execute("""
            CREATE NODE TABLE Block(
                id STRING,
                version INT64,
                schema STRING,
                type STRING,
                text STRING,
                level INT64,
                style STRING,
                language STRING,
                created_by STRING,
                created_at STRING,
                hash STRING,
                PRIMARY KEY (id)
            )
        """)
    except Exception as e:
        if "already exists" not in str(e):
            raise
            
    try:
        conn.execute("""
            CREATE NODE TABLE Page(
                id STRING,
                schema STRING,
                title STRING,
                created_by STRING,
                created_at STRING,
                updated_at STRING,
                PRIMARY KEY (id)
            )
        """)
    except Exception as e:
        if "already exists" not in str(e):
            raise
            
    try:
        conn.execute("""
            CREATE REL TABLE HAS_BLOCK(
                FROM Page TO Block,
                position INT64
            )
        """)
    except Exception as e:
        if "already exists" not in str(e):
            raise
            
    try:
        conn.execute("""
            CREATE REL TABLE LINKS_TO(
                FROM Block TO Page,
                link_text STRING,
                url STRING
            )
        """)
    except Exception as e:
        if "already exists" not in str(e):
            raise

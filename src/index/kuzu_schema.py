"""
kuzu_schema.py — create node and relationship tables in a Kuzu database.
"""
import kuzu


def create_schema(db_path: str) -> None:
    """
    Open (or create) a Kuzu database at db_path and create all node and
    relationship tables.

    Safe to call on a freshly created empty database. The caller is
    responsible for clearing the database before rebuilding (see build_index).
    """
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)

    conn.execute("""
        CREATE NODE TABLE Block(
            id STRING,
            version INT64,
            schema STRING,
            type STRING,
            text STRING,
            level INT64,
            style STRING,
            created_by STRING,
            created_at STRING,
            hash STRING,
            PRIMARY KEY (id)
        )
    """)

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

    conn.execute("""
        CREATE REL TABLE HAS_BLOCK(
            FROM Page TO Block,
            position INT64
        )
    """)

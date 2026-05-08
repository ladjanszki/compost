"""
kuzu_loader.py — bulk load Parquet files into Kuzu using COPY FROM.
"""
import os

import kuzu


def load_from_parquet(
    db_path: str,
    blocks_parquet: str,
    pages_parquet: str,
    has_block_parquet: str,
) -> None:
    """
    Run COPY FROM on all three Parquet files to load data into Kuzu.

    Assumes the schema already exists (kuzu_schema.create_schema was called).
    Node tables (Block, Page) are loaded before the relationship table (HAS_BLOCK)
    because relationship endpoints must exist first.

    Kuzu COPY FROM requires absolute paths.
    """
    blocks_abs    = os.path.abspath(blocks_parquet)
    pages_abs     = os.path.abspath(pages_parquet)
    has_block_abs = os.path.abspath(has_block_parquet)

    db   = kuzu.Database(db_path)
    conn = kuzu.Connection(db)

    conn.execute(f"COPY Block FROM '{blocks_abs}'")
    conn.execute(f"COPY Page FROM '{pages_abs}'")
    conn.execute(f"COPY HAS_BLOCK FROM '{has_block_abs}'")

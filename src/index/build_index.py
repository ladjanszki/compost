"""
build_index.py — top-level pipeline: JSONL store → Parquet → Kuzu index.
"""
import os
import shutil

from .jsonl_to_parquet import blocks_to_parquet, has_block_to_parquet, pages_to_parquet
from .kuzu_loader import load_from_parquet
from .kuzu_schema import create_schema

DEFAULT_BLOCKS_JSONL = "workspace/store/blocks.jsonl"
DEFAULT_PAGES_JSONL  = "workspace/store/pages.jsonl"
DEFAULT_DB_PATH      = "workspace/indexes/kuzu/db"
DEFAULT_PARQUET_DIR  = "workspace/indexes/kuzu/parquet"


def build_index(
    blocks_jsonl: str = DEFAULT_BLOCKS_JSONL,
    pages_jsonl:  str = DEFAULT_PAGES_JSONL,
    db_path:      str = DEFAULT_DB_PATH,
    parquet_dir:  str = DEFAULT_PARQUET_DIR,
) -> None:
    """
    Full pipeline: JSONL files → Parquet intermediate files → Kuzu graph index.

    Clears and rebuilds the Kuzu database on every run.
    The JSONL source files are never modified.
    """
    # 1. Clear the Kuzu database directory for a clean rebuild.
    # Kuzu creates the directory itself — we must not pre-create it.
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    os.makedirs(parquet_dir, exist_ok=True)

    # 2. Create the schema.
    create_schema(db_path)

    # 3. Write Parquet intermediate files.
    blocks_parquet    = os.path.join(parquet_dir, "blocks.parquet")
    pages_parquet     = os.path.join(parquet_dir, "pages.parquet")
    has_block_parquet = os.path.join(parquet_dir, "has_block.parquet")

    n_blocks    = blocks_to_parquet(blocks_jsonl, blocks_parquet)
    n_pages     = pages_to_parquet(pages_jsonl, pages_parquet)
    n_has_block = has_block_to_parquet(pages_jsonl, has_block_parquet)

    print(f"Parquet written: {n_blocks} blocks, {n_pages} pages, {n_has_block} HAS_BLOCK rows")

    # 4. Load Parquet files into Kuzu.
    load_from_parquet(db_path, blocks_parquet, pages_parquet, has_block_parquet)

    print(f"Kuzu index built at: {db_path}")

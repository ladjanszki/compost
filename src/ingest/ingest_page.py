"""
ingest_page.py — top-level pipeline: .dj file → blocks.jsonl + pages.jsonl.
"""
from pathlib import Path

from .ast_walker import walk
from .block_schema import make_block, make_page
from .jsonl_writer import append_record
from .pandoc_ast import get_ast

DEFAULT_BLOCKS_JSONL = "workspace/store/blocks.jsonl"
DEFAULT_PAGES_JSONL = "workspace/store/pages.jsonl"


def ingest_page(
    djot_path: str,
    author: str,
    blocks_jsonl: str = DEFAULT_BLOCKS_JSONL,
    pages_jsonl: str = DEFAULT_PAGES_JSONL,
) -> str:
    """
    Full pipeline: parse a .dj file → walk AST → write blocks + page to JSONL.

    Returns the page ID.
    """
    # 1. Parse Djot → Pandoc AST
    ast = get_ast(djot_path)

    # 2. Walk AST → ordered list of {type, content} dicts
    raw_blocks = walk(ast)

    # 3. Build block.v1 records and write each to blocks.jsonl
    block_records = []
    for raw in raw_blocks:
        block = make_block(raw["type"], raw["content"], author)
        append_record(blocks_jsonl, block)
        block_records.append(block)

    # 4. Collect block IDs in document order
    block_ids = [b["id"] for b in block_records]

    # 5. Derive page ID from filename stem (caller owns the 'page-' prefix)
    stem = Path(djot_path).stem
    page_id = f"page-{stem}"

    # 6. Derive title from the first heading block, fallback to stem
    title = stem
    for b in block_records:
        if b["type"] == "heading":
            title = b["content"]["text"]
            break

    # 7. Build and write page.v1 record
    page = make_page(page_id, title, block_ids, author)
    append_record(pages_jsonl, page)

    return page_id

"""
ingest_page.py — top-level pipeline: .dj file → LadybugDB Graph Database
"""
import os
import tempfile
from pathlib import Path
import real_ladybug as lb

from .ast_walker import walk
from .block_schema import make_block, make_page
from .djot_ast import get_ast
from .parquet_writer import (
    write_blocks_to_parquet,
    write_pages_to_parquet,
    write_has_block_to_parquet,
    write_links_to_parquet,
)
from .ladybug_schema import create_schema

DEFAULT_DB_PATH = "workspace/store/ladybug/db"


def ingest_page(
    djot_path: str,
    author: str,
    db_path: str = DEFAULT_DB_PATH,
) -> str:
    """
    Full pipeline: parse a .dj file → walk AST → copy to LadybugDB.
    Returns the page ID.
    """
    ast = get_ast(djot_path)
    raw_blocks = walk(ast)

    block_records = []
    for raw in raw_blocks:
        block_id = raw.get("id")
        block = make_block(raw["type"], raw["content"], author)
        if block_id:
            block["id"] = block_id
        block_records.append(block)

    stem = Path(djot_path).stem
    page_id = f"page-{stem}"

    title = stem
    for b in block_records:
        if b["type"] == "heading":
            title = b["content"].get("text", stem)
            break

    block_ids = [b["id"] for b in block_records]
    page = make_page(page_id, title, block_ids, author)

    has_blocks = []
    for pos, bid in enumerate(block_ids):
        has_blocks.append({
            "from": page_id,
            "to": bid,
            "position": pos,
        })

    links_to = []
    for b in block_records:
        content = b.get("content", {})
        for link in content.get("links", []):
            url = link["url"]
            if not url.startswith(("http://", "https://", "#")):
                target_stem = Path(url).stem
                if target_stem:
                    target_page_id = f"page-{target_stem}"
                    links_to.append({
                        "from": b["id"],
                        "to": target_page_id,
                        "link_text": link["text"],
                        "url": url,
                    })

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = lb.Database(db_path)
    conn = lb.Connection(db)

    try:
        create_schema(conn=conn)
    except Exception as e:
        pass

    # Also need to create Page nodes for links_to if they don't exist, to avoid COPY failure?
    # Kùzu requires target nodes to exist. Let's create dummy pages for targets if they don't exist.
    # We can check existing pages. Or we can just insert dummy pages and ignore if they exist.
    # Actually, let's try to just insert the dummy pages now.
    dummy_pages = []
    for link in links_to:
        dummy_pages.append({
            "id": link["to"],
            "schema": "page.v1",
            "title": link["to"].replace("page-", ""),
            "created_by": "system",
            "created_at": page["created_at"],
            "updated_at": page["updated_at"],
        })

    with tempfile.TemporaryDirectory() as tmpdir:
        b_pq = os.path.join(tmpdir, "blocks.parquet")
        p_pq = os.path.join(tmpdir, "pages.parquet")
        dp_pq = os.path.join(tmpdir, "dummy_pages.parquet")
        hb_pq = os.path.join(tmpdir, "has_block.parquet")
        lt_pq = os.path.join(tmpdir, "links_to.parquet")

        write_blocks_to_parquet(block_records, b_pq)
        write_pages_to_parquet([page], p_pq)
        write_pages_to_parquet(dummy_pages, dp_pq)
        write_has_block_to_parquet(has_blocks, hb_pq)
        write_links_to_parquet(links_to, lt_pq)

        # Merge dummy pages if Kuzu doesn't support UPSERT, we can just do CREATE if not exists, but Kuzu's COPY is bulk.
        # Actually Kuzu's COPY will fail on duplicate primary keys. 
        # So we shouldn't use COPY for the current page if it already exists?
        # The design says "Not optimized for batch. single-file ingestion." and "Clear store" in tests.
        # "Wipe-and-rebuild specs" means we clear the DB before tests.
        # So we can just use COPY FROM directly.
        # Wait, if `links_to` targets are not in DB, COPY FROM LINKS_TO fails. Let's try it.
        # Actually, let me test how Kuzu handles it.
        
        # Load Blocks and current Page
        conn.execute(f"COPY Block FROM '{os.path.abspath(b_pq)}'")
        
        # Use MERGE for the Page node to handle dummy pages gracefully
        page_query = f"""
            MERGE (p:Page {{id: '{page["id"]}'}})
            SET p.schema = '{page["schema"]}',
                p.title = '{page["title"].replace("'", "''")}',
                p.created_by = '{page["created_by"]}',
                p.created_at = '{page["created_at"]}',
                p.updated_at = '{page["updated_at"]}'
        """
        conn.execute(page_query)
        
        if has_blocks:
            conn.execute(f"COPY HAS_BLOCK FROM '{os.path.abspath(hb_pq)}'")
            
        if links_to:
            # Create target pages one by one, ignoring errors if they exist
            for link in links_to:
                target_id = link["to"]
                try:
                    conn.execute(f"CREATE (p:Page {{id: '{target_id}', title: '{target_id}'}})")
                except Exception:
                    pass
            # Now we can safely copy LINKS_TO
            conn.execute(f"COPY LINKS_TO FROM '{os.path.abspath(lt_pq)}'")

    return page_id

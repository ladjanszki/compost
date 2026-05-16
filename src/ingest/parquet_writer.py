"""
parquet_writer.py — write memory records to Parquet files for LadybugDB COPY FROM.
"""
import os
import pyarrow as pa
import pyarrow.parquet as pq

def write_blocks_to_parquet(blocks: list[dict], output_path: str) -> int:
    rows = []
    for b in blocks:
        content = b.get("content", {})
        rows.append({
            "id":         b["id"],
            "version":    b["version"],
            "schema":     b["schema"],
            "type":       b["type"],
            "text":       content.get("text"),
            "level":      content.get("level"),
            "style":      content.get("style"),
            "language":   content.get("language"),
            "created_by": b["created_by"],
            "created_at": b["created_at"],
            "hash":       b["hash"],
        })

    table = pa.table({
        "id":         pa.array([r["id"]         for r in rows], type=pa.string()),
        "version":    pa.array([r["version"]     for r in rows], type=pa.int64()),
        "schema":     pa.array([r["schema"]      for r in rows], type=pa.string()),
        "type":       pa.array([r["type"]        for r in rows], type=pa.string()),
        "text":       pa.array([r["text"]        for r in rows], type=pa.string()),
        "level":      pa.array([r["level"]       for r in rows], type=pa.int64()),
        "style":      pa.array([r["style"]       for r in rows], type=pa.string()),
        "language":   pa.array([r["language"]    for r in rows], type=pa.string()),
        "created_by": pa.array([r["created_by"]  for r in rows], type=pa.string()),
        "created_at": pa.array([r["created_at"]  for r in rows], type=pa.string()),
        "hash":       pa.array([r["hash"]        for r in rows], type=pa.string()),
    })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pq.write_table(table, output_path)
    return len(rows)

def write_pages_to_parquet(pages: list[dict], output_path: str) -> int:
    table = pa.table({
        "id":         pa.array([p["id"]         for p in pages], type=pa.string()),
        "schema":     pa.array([p["schema"]      for p in pages], type=pa.string()),
        "title":      pa.array([p["title"]       for p in pages], type=pa.string()),
        "created_by": pa.array([p["created_by"]  for p in pages], type=pa.string()),
        "created_at": pa.array([p["created_at"]  for p in pages], type=pa.string()),
        "updated_at": pa.array([p["updated_at"]  for p in pages], type=pa.string()),
    })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pq.write_table(table, output_path)
    return len(pages)

def write_has_block_to_parquet(has_blocks: list[dict], output_path: str) -> int:
    table = pa.table({
        "from":     pa.array([r["from"]     for r in has_blocks], type=pa.string()),
        "to":       pa.array([r["to"]       for r in has_blocks], type=pa.string()),
        "position": pa.array([r["position"] for r in has_blocks], type=pa.int64()),
    })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pq.write_table(table, output_path)
    return len(has_blocks)

def write_links_to_parquet(links: list[dict], output_path: str) -> int:
    table = pa.table({
        "from":      pa.array([r["from"]      for r in links], type=pa.string()),
        "to":        pa.array([r["to"]        for r in links], type=pa.string()),
        "link_text": pa.array([r["link_text"] for r in links], type=pa.string()),
        "url":       pa.array([r["url"]       for r in links], type=pa.string()),
    })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pq.write_table(table, output_path)
    return len(links)

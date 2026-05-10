"""
jsonl_to_parquet.py — flatten JSONL store files to Parquet for LadybugDB COPY FROM.
"""
import json
import os

import pyarrow as pa
import pyarrow.parquet as pq


def blocks_to_parquet(blocks_jsonl: str, output_path: str) -> int:
    """
    Read blocks.jsonl and write a Parquet file with one row per block.

    Columns: id, version, schema, type, text, level, style,
             created_by, created_at, hash

    Content fields (text, level, style) are flattened from the nested
    content object. Missing fields are written as null.

    Returns the number of rows written.
    """
    rows = []
    with open(blocks_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            b = json.loads(line)
            content = b.get("content", {})
            rows.append({
                "id":         b["id"],
                "version":    b["version"],
                "schema":     b["schema"],
                "type":       b["type"],
                "text":       content.get("text"),
                "level":      content.get("level"),
                "style":      content.get("style"),
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
        "created_by": pa.array([r["created_by"]  for r in rows], type=pa.string()),
        "created_at": pa.array([r["created_at"]  for r in rows], type=pa.string()),
        "hash":       pa.array([r["hash"]        for r in rows], type=pa.string()),
    })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pq.write_table(table, output_path)
    return len(rows)


def pages_to_parquet(pages_jsonl: str, output_path: str) -> int:
    """
    Read pages.jsonl and write a Parquet file with one row per page.

    Columns: id, schema, title, created_by, created_at, updated_at

    Returns the number of rows written.
    """
    rows = []
    with open(pages_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            rows.append({
                "id":         p["id"],
                "schema":     p["schema"],
                "title":      p["title"],
                "created_by": p["created_by"],
                "created_at": p["created_at"],
                "updated_at": p["updated_at"],
            })

    table = pa.table({
        "id":         pa.array([r["id"]         for r in rows], type=pa.string()),
        "schema":     pa.array([r["schema"]      for r in rows], type=pa.string()),
        "title":      pa.array([r["title"]       for r in rows], type=pa.string()),
        "created_by": pa.array([r["created_by"]  for r in rows], type=pa.string()),
        "created_at": pa.array([r["created_at"]  for r in rows], type=pa.string()),
        "updated_at": pa.array([r["updated_at"]  for r in rows], type=pa.string()),
    })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pq.write_table(table, output_path)
    return len(rows)


def has_block_to_parquet(pages_jsonl: str, output_path: str) -> int:
    """
    Read pages.jsonl and write a Parquet file with one row per
    (page, block, position) triple derived from each page's root array.

    Columns: from, to, position

    Returns the number of rows written.
    """
    rows = []
    with open(pages_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            for position, block_id in enumerate(p["root"]):
                rows.append({
                    "from":     p["id"],
                    "to":       block_id,
                    "position": position,
                })

    table = pa.table({
        "from":     pa.array([r["from"]     for r in rows], type=pa.string()),
        "to":       pa.array([r["to"]       for r in rows], type=pa.string()),
        "position": pa.array([r["position"] for r in rows], type=pa.int64()),
    })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pq.write_table(table, output_path)
    return len(rows)

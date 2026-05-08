"""
block_schema.py — build block.v1 and page.v1 records.
"""
import hashlib
import json
from datetime import datetime, timezone

import uuid6


def _sha256(content: dict) -> str:
    """Return 'sha256:<hex>' of the JSON-serialized content object."""
    serialized = json.dumps(content, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    return f"sha256:{digest}"


def make_block(block_type: str, content: dict, author: str) -> dict:
    """
    Build a block.v1 record.

    Generates a UUIDv7 id, computes SHA-256 hash of content, sets version=1.
    """
    block_id = str(uuid6.uuid7())
    return {
        "id": block_id,
        "version": 1,
        "schema": "block.v1",
        "type": block_type,
        "content": content,
        "created_by": author,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hash": _sha256(content),
    }


def make_page(page_id: str, title: str, block_ids: list, author: str) -> dict:
    """
    Build a page.v1 record.

    The caller is responsible for constructing the full page_id
    (e.g. 'page-' + stem). make_page stores whatever id it receives.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": page_id,
        "schema": "page.v1",
        "title": title,
        "root": block_ids,
        "created_by": author,
        "created_at": now,
        "updated_at": now,
    }

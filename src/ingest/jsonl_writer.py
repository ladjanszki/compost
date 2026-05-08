"""
jsonl_writer.py — append JSON records to JSONL files with file locking.
"""
import fcntl
import json
import os


def append_record(jsonl_path: str, record: dict) -> None:
    """
    Append a single JSON record as one line to a JSONL file.

    Creates the file (and parent directories) if they do not exist.
    Uses fcntl.flock to serialize concurrent writes.
    """
    os.makedirs(os.path.dirname(os.path.abspath(jsonl_path)), exist_ok=True)
    with open(jsonl_path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

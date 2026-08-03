"""
Roundtrip: djot → blocks → render → re-parse → blocks. Compare.

Two independent checks, because they fail in different ways:

  1. Coverage — every block-producing tag in the source AST must yield at
     least one block. Without this, an element type the walker does not
     handle is silently dropped and still "passes" the roundtrip, because it
     is absent from both sides of the comparison. This is exactly how
     task_list went unnoticed.

  2. Roundtrip — parse, render, re-parse, and compare block for block.
"""
import json, os, sys, tempfile

sys.path.insert(0, ".")

from src.ingest.djot_ast import get_ast
from src.ingest.ast_walker import walk
from src.render.blocks_to_djot import render_blocks

# Maps a djot AST tag to the block type(s) the walker must produce for it.
# If a tag appears in the source, at least one block of a mapped type must
# come out. Container tags (bullet_list, task_list, section, ...) are absent
# because they emit nothing themselves — only their children do.
#
# `para` is deliberately excluded: paragraphs are absorbed into list items,
# block quotes, definition items and table cells, so their presence in the
# AST does not imply a `paragraph` block.
TAG_TO_BLOCK_TYPES = {
    "heading": {"heading"},
    "code_block": {"code_block", "raw_block"},  # `{=fmt}` becomes raw_block
    "block_quote": {"block_quote"},
    "list_item": {"list_item"},
    "task_list_item": {"task_item"},
    "definition_list_item": {"definition_item"},
    "table": {"table"},
    "thematic_break": {"thematic_break"},
    "div": {"div"},
    "raw_block": {"raw_block"},
}

# Content fields compared between the original and the re-parsed block.
COMPARED_FIELDS = ("level", "style", "language", "depth", "checked", "term")


def _ast_tags(node: dict, found: set) -> set:
    """Collect every tag present anywhere in the AST."""
    tag = node.get("tag")
    if tag:
        found.add(tag)
    for child in node.get("children", []) or []:
        _ast_tags(child, found)
    return found


def _flatten(blocks: list) -> list:
    """Top-level blocks plus any nested inside a div's content."""
    out = []
    for b in blocks:
        out.append(b)
        out.extend(_flatten(b.get("content", {}).get("children", []) or []))
    return out


def check_coverage(ast: dict, blocks: list) -> list[str]:
    """Every block-producing tag in the source must yield a block of a mapped type."""
    tags = _ast_tags(ast, set())
    emitted = {b["type"] for b in _flatten(blocks)}
    issues = []
    for tag in sorted(tags):
        wanted = TAG_TO_BLOCK_TYPES.get(tag)
        if wanted and not (wanted & emitted):
            issues.append(
                f"DROPPED: source contains {tag!r} but no block of type "
                f"{sorted(wanted)} was emitted"
            )
    return issues


def roundtrip_test(djot_path: str) -> list[str]:
    """Returns list of discrepancies (empty = pass)."""
    ast = get_ast(djot_path)
    original_blocks = walk(ast)

    issues = check_coverage(ast, original_blocks)

    # Render without IDs — they would add {#uuid} noise on re-parse.
    djot_text = render_blocks(original_blocks, {"include_ids": False})

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".dj", delete=False)
    tmp.write(djot_text)
    tmp.close()
    try:
        re_blocks = walk(get_ast(tmp.name))
    finally:
        os.unlink(tmp.name)

    # Per-type counts, so a type lost in rendering is reported precisely
    # rather than as a bare total mismatch.
    orig_counts, rt_counts = {}, {}
    for b in original_blocks:
        orig_counts[b["type"]] = orig_counts.get(b["type"], 0) + 1
    for b in re_blocks:
        rt_counts[b["type"]] = rt_counts.get(b["type"], 0) + 1

    for btype in sorted(set(orig_counts) | set(rt_counts)):
        a, b = orig_counts.get(btype, 0), rt_counts.get(btype, 0)
        if a != b:
            issues.append(f"count mismatch for {btype!r}: {a} → {b}")

    if len(original_blocks) != len(re_blocks):
        issues.append(f"total count: {len(original_blocks)} → {len(re_blocks)}")
        print("\n--- Original ---")
        print(json.dumps([b["type"] for b in original_blocks]))
        print("\n--- Re-parsed ---")
        print(json.dumps([b["type"] for b in re_blocks]))
        print("\n--- Djot output ---")
        print(djot_text)
        return issues

    for i, (orig, rt) in enumerate(zip(original_blocks, re_blocks)):
        if orig["type"] != rt["type"]:
            issues.append(f"block {i}: type {orig['type']} → {rt['type']}")
            continue

        orig_text = orig["content"].get("text", "").strip()
        rt_text = rt["content"].get("text", "").strip()
        if orig_text != rt_text:
            issues.append(
                f"block {i} ({orig['type']}): text differs\n"
                f"  orig: {orig_text[:80]!r}\n  rt:   {rt_text[:80]!r}"
            )

        for key in COMPARED_FIELDS:
            if orig["content"].get(key) != rt["content"].get(key):
                issues.append(
                    f"block {i} ({orig['type']}): {key} differs: "
                    f"{orig['content'].get(key)!r} → {rt['content'].get(key)!r}"
                )

    return issues


def main():
    test_files = [
        "tests/test_00/test_00.dj",
        "tests/test_02/all_elements.dj",
    ]
    import glob
    test_files.extend(sorted(glob.glob("tests/test_00/extra_inputs/*.dj")))
    test_files.extend(sorted(glob.glob("tests/test_03/fixtures/*.dj")))
    test_files.extend(sorted(glob.glob("sample_data/**/*.dj", recursive=True)))

    all_pass = True
    for path in test_files:
        if not os.path.exists(path):
            print(f"SKIP (not found): {path}")
            continue
        issues = roundtrip_test(path)
        if issues:
            print(f"FAIL: {path}")
            for issue in issues:
                print(f"  {issue}")
            all_pass = False
        else:
            blocks = walk(get_ast(path))
            types = sorted({b["type"] for b in blocks})
            print(f"PASS: {path} ({len(blocks)} blocks, {len(types)} types)")

    if all_pass:
        print("\nAll roundtrip tests PASSED.")
    else:
        print("\nSome tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Roundtrip: djot → blocks → render → re-parse → blocks. Compare."""
import json, os, sys, tempfile
sys.path.insert(0, ".")

from src.ingest.djot_ast import get_ast
from src.ingest.ast_walker import walk
from src.render.blocks_to_djot import render_blocks


def roundtrip_test(djot_path: str) -> list[str]:
    """Returns list of discrepancies (empty = pass)."""
    # Step 1: Original ingestion
    ast = get_ast(djot_path)
    original_blocks = walk(ast)
    
    # Step 2: Render to Djot (without IDs — they'd create {#uuid} noise)
    djot_text = render_blocks(original_blocks, {"include_ids": False})
    
    # Step 3: Re-parse the rendered Djot
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".dj", delete=False)
    tmp.write(djot_text)
    tmp.close()
    
    try:
        re_ast = get_ast(tmp.name)
        re_blocks = walk(re_ast)
    finally:
        os.unlink(tmp.name)
    
    # Step 4: Compare
    issues = []
    if len(original_blocks) != len(re_blocks):
        issues.append(f"Count mismatch: {len(original_blocks)} → {len(re_blocks)}")
        # If count mismatch, writing diff to help debug
        print("\n--- Original ---")
        print(json.dumps([b["type"] for b in original_blocks]))
        print("\n--- Re-parsed ---")
        print(json.dumps([b["type"] for b in re_blocks]))
        print("\n--- Djot output ---")
        print(djot_text)
        return issues
    
    for i, (orig, rt) in enumerate(zip(original_blocks, re_blocks)):
        if orig["type"] != rt["type"]:
            issues.append(f"Block {i}: type {orig['type']} → {rt['type']}")
            continue
        
        orig_text = orig["content"].get("text", "").strip()
        rt_text = rt["content"].get("text", "").strip()
        if orig_text != rt_text:
            issues.append(f"Block {i} ({orig['type']}): text differs\n  orig: {orig_text[:80]!r}\n  rt:   {rt_text[:80]!r}")
        
        for key in ("level", "style", "language"):
            if orig["content"].get(key) != rt["content"].get(key):
                issues.append(f"Block {i}: {key} differs: {orig['content'].get(key)} → {rt['content'].get(key)}")
    
    return issues


def main():
    test_files = [
        "tests/test_00/test_00.dj",
        "tests/test_02/all_elements.dj",
    ]
    import glob
    test_files.extend(sorted(glob.glob("tests/test_00/extra_inputs/*.dj")))
    
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
            ast = get_ast(path)
            blocks = walk(ast)
            print(f"PASS: {path} ({len(blocks)} blocks)")
    
    if all_pass:
        print("\nAll roundtrip tests PASSED.")
    else:
        print("\nSome tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()

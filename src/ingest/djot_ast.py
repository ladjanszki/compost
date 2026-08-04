"""
djot_ast.py — run djot.js on a .dj file and return the native AST as a dict.
"""
import json
import shutil
import subprocess


def _find_executable(name: str, fallbacks: list[str] = None) -> str:
    """Find an executable on PATH or in fallback locations."""
    path = shutil.which(name)
    if path:
        return path
    for fb in (fallbacks or []):
        if shutil.which(fb):
            return fb
    raise RuntimeError(f"{name} not found. Install Node.js and run: npm install -g @djot/djot")


def get_ast_from_text(source: str, sourcepos: bool = False, label: str = "<text>") -> dict:
    """
    Parse djot source text and return the native AST as a dict.

    With sourcepos=True every node carries a `pos` field with start/end
    line and column — required for injecting block ids as text.
    """
    npx = _find_executable("npx")

    cmd = [npx, "@djot/djot", "--to", "ast"]
    if sourcepos:
        cmd.append("--sourcepos")

    result = subprocess.run(cmd, input=source, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"djot.js failed for {label!r}:\n{result.stderr.strip()}")
    return json.loads(result.stdout)


def get_ast(djot_path: str, sourcepos: bool = False) -> dict:
    """
    Run djot.js on the given .dj file and return the parsed AST as a dict.
    Raises RuntimeError if djot.js exits non-zero.
    """
    with open(djot_path, "r", encoding="utf-8") as f:
        source = f.read()
    return get_ast_from_text(source, sourcepos=sourcepos, label=djot_path)

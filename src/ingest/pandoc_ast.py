"""
pandoc_ast.py — run pandoc on a .dj file and return the parsed AST as a dict.
"""
import json
import shutil
import subprocess


def _pandoc_executable() -> str:
    """Return the path to pandoc, searching PATH and common install locations."""
    pandoc = shutil.which("pandoc")
    if pandoc:
        return pandoc
    # Fallback: miniconda base env installs pandoc here on macOS
    fallbacks = [
        "/path/to/home/miniconda3/bin/pandoc",
        "/usr/local/bin/pandoc",
        "/opt/homebrew/bin/pandoc",
    ]
    for path in fallbacks:
        if shutil.which(path):
            return path
    raise RuntimeError(
        "pandoc not found. Install it with: conda install -c conda-forge pandoc"
    )


def get_ast(djot_path: str) -> dict:
    """
    Run pandoc on the given .dj file and return the parsed Pandoc AST as a
    Python dict.

    Raises RuntimeError if pandoc exits with a non-zero status.
    """
    pandoc = _pandoc_executable()
    result = subprocess.run(
        [pandoc, "-f", "djot", "-t", "json", djot_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pandoc failed for {djot_path!r}:\n{result.stderr.strip()}"
        )
    return json.loads(result.stdout)

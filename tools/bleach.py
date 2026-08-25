#!/usr/bin/env python3
"""
bleach.py — replace the prose in a markdown file, keep the formatting.

The point is a fixture corpus that can be committed and shared without
carrying the content of anybody's notes. Every word becomes a lorem word of
the same length and the same capitalisation; every character that markdown
gives meaning to is left exactly where it was — including indentation, blank
line runs, trailing whitespace and where the author pressed Enter.

Correctness is not "it looks similar". It is checkable: the bleached file must
parse to the same *shape* as the original — the same tree of block types in
the same order. `verify_shape` asserts it, and bleaching a file that fails is
a bug in this script, not an acceptable outcome.
"""
import hashlib
import re
import subprocess
import json

LOREM = """lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod
tempor incididunt ut labore et dolore magna aliqua enim ad minim veniam quis
nostrud exercitation ullamco laboris nisi aliquip ex ea commodo consequat duis
aute irure in reprehenderit voluptate velit esse cillum eu fugiat nulla
pariatur excepteur sint occaecat cupidatat non proident sunt culpa qui officia
deserunt mollit anim id est laborum curabitur pretium tincidunt lacus nulla
gravida orci a odio nullam varius turpis et commodo pharetra est vestibulum
integer nec urna libero tristique fermentum donec placerat mauris blandit
volutpat morbi rutrum tempus rhoncus vivamus sagittis lacinia purus""".split()

# Tokens markdown treats as structure even though they are made of letters.
PROTECT = [
    re.compile(r"\[[ xX]\]"),                                   # task markers
    re.compile(r"\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]"),  # gfm callouts
    re.compile(r"^[ \t]*(?:```+|~~~+)[ \t]*\S+", re.M),          # fence info string
]
HANDLE = re.compile(r"\{#([0-9a-f]{8})(\+*)\}")
WORD = re.compile(r"[A-Za-z]+")


def _pick(word: str, salt: str) -> str:
    """A lorem word of the same length, chosen deterministically."""
    n = len(word)
    seed = int(hashlib.sha256(f"{salt}:{word}".encode()).hexdigest()[:8], 16)
    pool = [w for w in LOREM if len(w) == n]
    if pool:
        out = pool[seed % len(pool)]
    else:                       # no lorem word that long: build one
        base = LOREM[seed % len(LOREM)]
        out = (base * (n // len(base) + 1))[:n]
    if word.isupper() and len(word) > 1:
        return out.upper()
    if word[0].isupper():
        return out.capitalize()
    return out


def bleach(text: str, salt: str = "") -> str:
    held: list[str] = []

    def hold(m):
        held.append(m.group(0))
        return f"\x00{len(held)-1}\x00"

    for pat in PROTECT:
        text = pat.sub(hold, text)

    # Handles keep their shape but stop pointing at real blocks. They are held
    # like the other protected tokens, or the word pass below would eat the
    # letters out of the hex and leave an unparseable handle behind.
    def rehandle(m):
        h = hashlib.sha256(f"{salt}:{m.group(1)}".encode()).hexdigest()[:8]
        held.append("{#" + h + m.group(2) + "}")
        return f"\x00{len(held)-1}\x00"
    text = HANDLE.sub(rehandle, text)

    text = WORD.sub(lambda m: _pick(m.group(0), salt), text)

    return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)


def shape(md: str, fmt: str = "gfm") -> list:
    """The tree of block types, with all text removed."""
    r = subprocess.run(["pandoc", "-f", fmt, "-t", "json"],
                       input=md, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    doc = json.loads(r.stdout)

    def walk(x):
        if isinstance(x, dict):
            t = x.get("t")
            kids = [walk(v) for v in (x.get("c") if isinstance(x.get("c"), list) else [])]
            kids = [k for k in kids if k]
            return [t, kids] if kids else [t]
        if isinstance(x, list):
            out = [walk(v) for v in x]
            return [o for o in out if o]
        return None
    return walk(doc["blocks"])


def verify_shape(original: str, bleached: str, fmt: str = "gfm"):
    a, b = shape(original, fmt), shape(bleached, fmt)
    return a == b, a, b

"""
Importing a Claude Code session.

The hazard is that tool output is arbitrary text. It routinely contains the
exact delimiters the importer uses to structure the document — `:::` and code
fences — because the tools are reading source files that use them. A fixed
fence would be closed early by the content it is supposed to contain, silently
reshaping the conversation.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.canonize import canonize_text
from src.importer import session_markdown, turns_from_session
from src.ingest.ast_walker import walk
from src.ingest.djot_ast import get_ast_from_text

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        FAILURES.append(name)
        if detail:
            print(f"          {detail}")


def session(lines: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for d in lines:
        f.write(json.dumps(d) + "\n")
    f.close()
    return Path(f.name)


def tc1_turns_and_authors():
    print("\nTC-1: user and assistant messages become authored turns")
    p = session([
        {"type": "mode", "mode": "normal"},
        {"type": "user", "uuid": "u1", "message": {"content": "A question."}},
        {"type": "assistant", "uuid": "a1", "message": {"content": [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "An answer."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "user", "uuid": "u2", "message": {"content": [
            {"type": "tool_result", "content": "file.txt"}]}},
        {"type": "assistant", "uuid": "a2", "isSidechain": True,
         "message": {"content": [{"type": "text", "text": "Subagent says hi."}]}},
    ])
    turns = turns_from_session(p)
    check("bookkeeping lines are skipped", len(turns) == 4, len(turns))
    check("authors are assigned",
          [t["author"] for t in turns] == ["human", "claude", "human",
                                           "claude:sidechain"],
          [t["author"] for t in turns])
    check("prose is separated from folded parts",
          turns[1]["prose"] == ["An answer."] and len(turns[1]["folded"]) == 2,
          turns[1])

    blocks = walk(get_ast_from_text(canonize_text(session_markdown(turns)).djot))
    authors = [(b["content"].get("attrs") or {}).get("author")
               for b in blocks if b["type"] == "div"
               and "turn" in (b["content"].get("classes") or [])]
    check("every turn survives canonization with its author",
          authors == ["human", "claude", "human", "claude:sidechain"], authors)
    check("the tool name is kept for the fold's summary",
          any((b["content"].get("attrs") or {}).get("name") == "Bash"
              for b in blocks if b["type"] == "div"))


def tc2_tool_output_cannot_break_the_document():
    print("\nTC-2: tool output containing our own delimiters is contained")
    hostile = (
        "::: {.turn author=\"attacker\"}\n"
        "This must not become a turn.\n"
        ":::\n"
        "~~~~\n"
        "nor must this escape a code fence\n"
        "~~~~\n"
        "```\nor this\n```\n"
    )
    p = session([
        {"type": "user", "uuid": "u1", "message": {"content": "Read the file."}},
        {"type": "assistant", "uuid": "a1", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file": "x"}}]}},
        {"type": "user", "uuid": "u2", "message": {"content": [
            {"type": "tool_result", "content": hostile}]}},
        {"type": "assistant", "uuid": "a2", "message": {"content": [
            {"type": "text", "text": "Done reading."}]}},
    ])
    turns = turns_from_session(p)
    blocks = walk(get_ast_from_text(canonize_text(session_markdown(turns)).djot))

    turn_divs = [b for b in blocks if b["type"] == "div"
                 and "turn" in (b["content"].get("classes") or [])]
    authors = [(b["content"].get("attrs") or {}).get("author") for b in turn_divs]
    check("the payload did not forge a turn", "attacker" not in authors, authors)
    check("turn count is exactly what the log contained",
          len(turn_divs) == 4, f"{len(turn_divs)} divs from 4 messages")
    check("the last turn's prose survived intact",
          any(b["content"].get("text") == "Done reading." for b in blocks),
          [b["content"].get("text", "")[:30] for b in blocks])
    check("the hostile payload is present, not dropped",
          any("must not become a turn" in b["content"].get("text", "")
              for b in blocks))
    check("every block is addressable", all(b.get("id") for b in blocks),
          [b["type"] for b in blocks if not b.get("id")])


def main():
    tc1_turns_and_authors()
    tc2_tool_output_cannot_break_the_document()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        sys.exit(1)
    print("All importer checks PASSED.")


if __name__ == "__main__":
    main()

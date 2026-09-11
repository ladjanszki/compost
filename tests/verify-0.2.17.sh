#!/usr/bin/env bash
# verify-0.2.17.sh — the list item as a container. Deleted when v0.2.17 ships.
#
#   NEW   — a v0.2.17 guarantee. MUST FAIL before the work, pass after.
#           A NEW check that passes at baseline is a bug in this script.
#   GUARD — an existing property. MUST PASS at both ends.
#
# Never runs a writing subcommand from inside this repository: `.compost` here
# is a symlink into the human's notes repository.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT=$PWD; W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
pass=0; fail=0
ok(){ printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1)); }
no(){ printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }
run(){ local k=$1 n=$2
  if python3 - >"$W/o" 2>&1; then ok "[$k] $n"; else no "[$k] $n"; sed 's/^/        /' "$W/o"|tail -3; fi; }
# `find`, not glob.glob: recursive glob silently skips dot-directories and so
# measures 518 of the 520 documents run.sh reports. Found by the v0.2.16 agent.
FIND='import subprocess as _sp
FS=[x for x in _sp.run(["find","'"$ROOT"'/tests/corpus","-name","*.md","-print0"],
    capture_output=True,text=True).stdout.split("\0") if x]'
echo

run NEW "a bullet with a sub-list carries its own text, like a plain bullet already does" <<PY
import sys,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
p=pathlib.Path(tempfile.mkdtemp())/"b.md"
p.write_text("- plain bullet\n- parent bullet\n    - child one\n")
recs,root=R.ast_to_records(MD.ast_of_file(str(p)))
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
g=R.Graph(recs)
items=[nodes[x] for x in nodes if nodes[x]["type"]=="ListItem"]
parent=[n for n in items if "parent bullet" in (R.plain_text(n) or "")]
assert parent, ("the bullet with a sub-list does not carry its own text; "
                "it is still a sibling Plain, unlike the collapsed single-block case")
n=parent[0]
assert (n.get("params") or {}).get("wrap") in ("Plain","Para"), \
    f"no wrap param on the hoisted item: {n.get('params')}"
PY

run NEW "everything under a bullet is a subtree walk, with no sibling scan" <<PY
import sys,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
p=pathlib.Path(tempfile.mkdtemp())/"b.md"
p.write_text("- parent bullet\n    - child one\n    - child two\n")
recs,root=R.ast_to_records(MD.ast_of_file(str(p)))
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
g=R.Graph(recs)
parent=[x for x in nodes if nodes[x]["type"]=="ListItem"
        and "parent bullet" in (R.plain_text(nodes[x]) or "")]
assert parent, "the parent bullet does not carry its text"
kids=[nodes[k]["type"] for k in g.children(parent[0])]
assert kids and all(t in ("BulletList","OrderedList") for t in kids), \
    f"children of the bullet are {kids}, expected only nested lists"
PY

run NEW "hoisting removes exactly one node per hoisted item — 19538 -> 19400" <<PY
import sys; sys.path.insert(0,"$ROOT")
$FIND
from src import records as R, markdown as MD
total=0
for f in FS:
    recs,_=R.ast_to_records(MD.ast_of_file(f))
    total+=sum(1 for r in recs if r["record"]=="node")
assert total==19400, f"corpus has {total} nodes; expected 19400 after hoisting 138 items"
PY

echo
run GUARD "two paragraphs in one bullet stay siblings — the conservative rule" <<PY
import sys,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
p=pathlib.Path(tempfile.mkdtemp())/"b.md"
p.write_text("- first para\n\n  second para\n")
recs,root=R.ast_to_records(MD.ast_of_file(str(p)))
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
g=R.Graph(recs)
item=[x for x in nodes if nodes[x]["type"]=="ListItem"]
assert item, "no ListItem at all"
kids=[nodes[k]["type"] for k in g.children(item[0])]
assert kids.count("Para")+kids.count("Plain") == 2, \
    (f"children are {kids}: two paragraphs in one bullet must stay siblings, "
     "because neither contains the other")
PY

run GUARD "hoist and unhoist still compose to the identity, over every corpus doc" <<PY
import sys; sys.path.insert(0,"$ROOT")
$FIND
from src import records as R, markdown as MD
bad=0
for f in FS:
    a=MD.ast_of_file(f)
    if R.unhoist(R.hoist(a["blocks"])) != a["blocks"]: bad+=1
assert bad==0, f"{bad} of {len(FS)} documents do not survive hoist->unhoist"
PY

run GUARD "the full round-trip holds through ast_to_records" <<PY
import sys; sys.path.insert(0,"$ROOT")
$FIND
from src import records as R, markdown as MD
bad=0
for f in FS:
    a=MD.ast_of_file(f)
    recs,root=R.ast_to_records(a)
    if R.records_to_ast(recs,root)!=a: bad+=1
assert bad==0, f"{bad} of {len(FS)} documents fail the round-trip"
PY

run GUARD "the transcript round-trip holds, byte for byte" <<PY
import sys,json,glob,pathlib; sys.path.insert(0,"$ROOT")
from src import session as S
for f in glob.glob("$ROOT/tests/fixtures/sessions/*.jsonl"):
    lines=[json.loads(l) for l in pathlib.Path(f).read_text().splitlines() if l.strip()]
    recs,root=S.session_to_records(f)
    assert S.records_to_session(recs,root)==lines, f
PY

run GUARD "the AoTA prefix property survives — 2379 of 2379, 473 of 473" <<PY
import sys,pathlib,tempfile; sys.path.insert(0,"$ROOT")
from src import records as R, session as S
for name,expect in (("session-04",2379),("session-02",473)):
    C=f"$ROOT/tests/corpus/compost-corpus/curated/sessions/{name}.jsonl"
    if not pathlib.Path(C).exists(): continue
    lines=[l for l in pathlib.Path(C).read_text().splitlines() if l.strip()]
    d1=pathlib.Path(tempfile.mkdtemp()); d2=pathlib.Path(tempfile.mkdtemp())
    (d1/"s.jsonl").write_text("\n".join(lines[:int(len(lines)*0.7)])+"\n")
    (d2/"s.jsonl").write_text("\n".join(lines)+"\n")
    ro,a=S.session_to_records(d1/"s.jsonl"); rn,b=S.session_to_records(d2/"s.jsonl")
    pre,tot=R.align(ro,a,rn,b)
    assert pre==tot, f"{name}: prefix broke, {pre} of {tot}"
    assert tot==expect, f"{name}: walk covers {tot}, expected {expect} — denominator moved"
PY

run GUARD "the views still render every citable block (v0.2.16's bug, as a standing check)" <<PY
import sys,re,pathlib; sys.path.insert(0,"$ROOT")
src=pathlib.Path("$ROOT/src/views.py").read_text()
assert re.search(r"^\s*blocks = R\.unhoist\(blocks\)", src, re.M), \
    "views.py no longer unhoists before handing blocks to pandoc; nested content will vanish"
PY

run GUARD "READER is still defined exactly once in src/" <<PY
import glob,re
hits=[f for f in glob.glob("$ROOT/src/*.py")
      if re.search(r'^READER\s*=', open(f).read(), re.M)]
assert len(hits)==1, f"READER defined in {hits}"
PY

echo
printf 'pass %d   fail %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

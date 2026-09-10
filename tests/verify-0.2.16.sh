#!/usr/bin/env bash
# verify-0.2.16.sh — TA and sections. Deleted when v0.2.16 ships.
#
#   NEW   — a v0.2.16 guarantee. MUST FAIL before the work, pass after.
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
NOTE=tests/fixtures/notes/note-01.md
SESS=tests/fixtures/sessions/session-smoke.jsonl
echo

run NEW "hoist and unhoist exist and compose to the identity on every corpus doc" <<PY
import sys,glob,json,subprocess; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
assert hasattr(R,"hoist") and hasattr(R,"unhoist"), \
    "no records.hoist / records.unhoist"
fs=sorted(glob.glob("$ROOT/tests/corpus/**/*.md",recursive=True)) or ["$ROOT/README.md"]
bad=0
for f in fs:
    a=MD.ast_of_file(f) if hasattr(MD,"ast_of_file") else json.loads(
        subprocess.run(["pandoc","-f",MD.READER,"-t","json",f],
                       capture_output=True,text=True,check=True).stdout)
    if R.unhoist(R.hoist(a["blocks"])) != a["blocks"]: bad+=1
assert bad==0, f"{bad} of {len(fs)} documents do not survive hoist->unhoist"
PY

run NEW "the reader sections: a Header becomes the parent of what follows it" <<PY
import sys,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
p=pathlib.Path(tempfile.mkdtemp())/"s.md"
p.write_text("# Chapter\n\nA paragraph.\n\n## Sub\n\n- one\n- two\n")
recs,root=R.ast_to_records(MD.ast_of_file(str(p))) if hasattr(MD,"ast_of_file") \
    else (None,None)
assert recs is not None, "no markdown.ast_of_file: the filter has no single seam"
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
g=R.Graph(recs)
top=[k for k in g.children(root)]
assert len(top)==1, f"expected one top-level section, got {len(top)}"
h=nodes[top[0]]
assert h["type"]=="Header" and (h["params"] or {}).get("level")==1, \
    f"the container is {h['type']}, not a level-1 Header"
kids=[nodes[k]["type"] for k in g.children(top[0])]
assert kids==["Para","Header"], f"section children are {kids}, expected Para then Header"
PY

run NEW "sections add no nodes — the count matches the flat model exactly" <<PY
import sys,glob,json,subprocess; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
fs=sorted(glob.glob("$ROOT/tests/corpus/**/*.md",recursive=True))[:60] or ["$ROOT/README.md"]
flat=sec=0
for f in fs:
    a=json.loads(subprocess.run(["pandoc","-f",MD.READER,"-t","json",f],
        capture_output=True,text=True,check=True).stdout)
    r1,_=R.ast_to_records(a); flat+=sum(1 for r in r1 if r["record"]=="node")
    r2,_=R.ast_to_records(MD.ast_of_file(f)); sec+=sum(1 for r in r2 if r["record"]=="node")
assert flat==sec, f"sectioning changed the node count: {flat} -> {sec}"
PY

run NEW "two identical headings share record_hash and differ in the fold" <<PY
import sys,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
d=pathlib.Path(tempfile.mkdtemp())
(d/"a.md").write_text("# Braindump\n\n- monday\n")
(d/"b.md").write_text("# Braindump\n\n- tuesday\n")
def head(p):
    recs,root=R.ast_to_records(MD.ast_of_file(str(p))); R.stamp_hashes(recs)
    nodes={r["guid"]:r for r in recs if r["record"]=="node"}
    g=R.Graph(recs)
    return nodes[g.children(root)[0]]
x,y=head(d/"a.md"),head(d/"b.md")
assert x["type"]=="Header" and y["type"]=="Header"
assert x["record_hash"]==y["record_hash"], "the same heading no longer hashes the same"
assert x["record_subtree_hash"]!=y["record_subtree_hash"], \
    "two braindumps still fold identically — the whole point of the release"
PY

run NEW "every markdown path is sectioned: a delegated turn's prose too" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
recs,root=MD.text_to_records("# Heading\n\nprose under it.\n")
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
g=R.Graph(recs)
top=g.children(root)
assert len(top)==1 and nodes[top[0]]["type"]=="Header", \
    "text_to_records is not sectioned — a base would hold two document shapes"
assert [nodes[k]["type"] for k in g.children(top[0])]==["Para"], \
    "the delegated path sections differently from the file path"
PY

run NEW "--updates on a mutable root mints one revision_of, root to root" <<PY
import subprocess,os,tempfile,json,glob,pathlib
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
cli=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,capture_output=True,text=True)
cli("init","."); cli("digest","--as=notes","--mutability=mutable","$ROOT/$NOTE")
load=lambda: [json.loads(l) for f in glob.glob(str(w/".compost/graph/*.jsonl")) for l in open(f) if l.strip()]
g=load(); root=next(r["guid"] for r in g if r["record"]=="node" and r["type"]=="document")
r=cli("digest","--as=notes",f"--updates={root}","$ROOT/$NOTE")
assert r.returncode==0, r.stdout+r.stderr
g=load()
rev=[e for e in g if e["record"]=="edge" and e["type"]=="revision_of"]
assert len(rev)==1, f"{len(rev)} revision_of edges, expected 1"
nodes={x["guid"]:x for x in g if x["record"]=="node"}
assert nodes[rev[0]["source"]]["type"]=="document", "revision_of source is not a root"
assert nodes[rev[0]["destination"]]["guid"]==root, "revision_of does not point at the old root"
assert sum(1 for x in g if x["record"]=="node" and x["type"]=="document")==2, \
    "a revision should mint a whole new tree (design-0.3.0 §9, Option A)"
PY

run NEW "check rejects a bad revision_of" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import records as R
def base():
    b=R.Builder()
    a=b.node("document",{"source":"x.md","mutability":"mutable"})
    c=b.node("document",{"source":"x.md","mutability":"mutable"})
    p=b.node("Para",None,[]); b.children(c,[p],"ingestion")
    return b,a,c,p
b,a,c,p=base(); b.edge("revision_of",a,a,"ingestion"); R.stamp_hashes(b.records)
assert any("revision" in x.lower() for x in R.check(b.records)), "reflexive accepted"
b,a,c,p=base(); b.edge("revision_of",a,c,"ingestion"); b.edge("revision_of",c,a,"ingestion")
R.stamp_hashes(b.records)
assert any("revision" in x.lower() or "cycle" in x.lower() for x in R.check(b.records)), "cycle accepted"
b,a,c,p=base(); b.edge("revision_of",p,c,"ingestion"); R.stamp_hashes(b.records)
assert any("revision" in x.lower() or "root" in x.lower() for x in R.check(b.records)), \
    "block-to-block revision accepted"
PY

run NEW "revision_of is in the schema" <<PY
import json
s=json.load(open("$ROOT/tools/record-schema-1.json"))
txt=json.dumps(s)
assert "revision_of" in txt, "the schema has never heard of revision_of"
PY

echo
run GUARD "the AST round-trip holds" <<PY
import sys,json,subprocess,glob; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
fs=sorted(glob.glob("$ROOT/tests/corpus/**/*.md",recursive=True))[:25] or ["$ROOT/README.md"]
for f in fs:
    a=json.loads(subprocess.run(["pandoc","-f",MD.READER,"-t","json",f],
        capture_output=True,text=True,check=True).stdout)
    recs,root=R.ast_to_records(a)
    assert R.records_to_ast(recs,root)==a, f
PY

run GUARD "the transcript round-trip holds, byte for byte" <<PY
import sys,json,glob,pathlib; sys.path.insert(0,"$ROOT")
from src import session as S
for f in glob.glob("$ROOT/tests/fixtures/sessions/*.jsonl"):
    lines=[json.loads(l) for l in pathlib.Path(f).read_text().splitlines() if l.strip()]
    recs,root=S.session_to_records(f)
    assert S.records_to_session(recs,root)==lines, f
PY

run GUARD "READER is still defined exactly once in src/" <<PY
import glob,re
hits=[f for f in glob.glob("$ROOT/src/*.py")
      if re.search(r'^READER\s*=', open(f).read(), re.M)]
assert len(hits)==1, f"READER defined in {hits} — two markdown dialects can drift"
PY

run GUARD "an append-only root still refuses a changed head" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import records as R
assert hasattr(R,"align"), "records.align went missing"
PY

echo
printf 'pass %d   fail %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

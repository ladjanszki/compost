#!/usr/bin/env bash
# verify-0.2.15.sh — AoTA. Deleted when v0.2.15 ships.
#
#   NEW   — a v0.2.15 guarantee. MUST FAIL before the work, pass after.
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
SESS=tests/fixtures/sessions/session-smoke.jsonl
CORP=tests/corpus/compost-corpus/curated/sessions/session-04.jsonl
[ -f "$ROOT/$CORP" ] || CORP=$SESS
echo

run NEW "digest refuses without --mutability, and names the three values" <<PY
import subprocess,os,tempfile,sys
w=tempfile.mkdtemp(); env={**os.environ,"PYTHONPATH":"$ROOT"}
cli=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,capture_output=True,text=True)
cli("init",".")
r=cli("digest","--as=claude-code-transcript","$ROOT/$SESS")
assert r.returncode!=0, "digest accepted a creation with no --mutability"
out=(r.stdout+r.stderr).lower()
for v in ("immutable","append-only","mutable"):
    assert v in out, f"the refusal does not name {v!r}"
PY

run NEW "--mutability together with --updates is refused" <<PY
import subprocess,os,tempfile,json,glob
w=tempfile.mkdtemp(); env={**os.environ,"PYTHONPATH":"$ROOT"}
cli=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,capture_output=True,text=True)
cli("init","."); cli("digest","--as=claude-code-transcript","--mutability=append-only","$ROOT/$SESS")
g=[json.loads(l) for f in glob.glob(w+"/.compost/graph/*.jsonl") for l in open(f) if l.strip()]
root=next(r["guid"] for r in g if r["record"]=="node" and r["type"]=="session")
r=cli("digest","--as=claude-code-transcript","--mutability=mutable",f"--updates={root}","$ROOT/$SESS")
assert r.returncode!=0, "mutability was allowed to change on an update"
PY

run NEW "an append keeps ONE root and mints only the tail" <<PY
import subprocess,os,tempfile,json,glob,pathlib
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
cli=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,capture_output=True,text=True)
lines=[l for l in pathlib.Path("$ROOT/$CORP").read_text().splitlines() if l.strip()]
d=w/"s.jsonl"; d.write_text("\n".join(lines[:int(len(lines)*0.7)])+"\n")
cli("init","."); cli("digest","--as=claude-code-transcript","--mutability=append-only",str(d))
load=lambda: [json.loads(l) for f in glob.glob(str(w/".compost/graph/*.jsonl")) for l in open(f) if l.strip()]
g=load(); n1=sum(1 for r in g if r["record"]=="node")
root=next(r["guid"] for r in g if r["record"]=="node" and r["type"]=="session")
d.write_text("\n".join(lines)+"\n")
r=cli("digest","--as=claude-code-transcript",f"--updates={root}",str(d))
assert r.returncode==0, r.stdout+r.stderr
g=load()
roots=[r["guid"] for r in g if r["record"]=="node" and r["type"]=="session"]
assert len(roots)==1, f"{len(roots)} session roots after an append; expected 1"
n2=sum(1 for r in g if r["record"]=="node")
assert n2 < n1*1.8, f"nodes went {n1}->{n2}: the head looks re-minted, not appended"
PY

run NEW "check is clean after an append — the root's fold is refreshed" <<PY
import subprocess,os,tempfile,json,glob,pathlib,sys
sys.path.insert(0,"$ROOT")
from src import records as R
assert hasattr(R,"refresh_fold"), "no records.refresh_fold: the append cannot fix the root"
# Through the CLI, not by calling refresh_fold directly. Calling it directly
# proves the function works and says nothing about whether the append USES
# it: with the call site removed this check passed while a real append left
# the base reporting "record_subtree_hash does not recompute", and a
# different check caught it. A check must fail for the reason it names.
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
cli=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,capture_output=True,text=True)
lines=[l for l in pathlib.Path("$ROOT/$CORP").read_text().splitlines() if l.strip()]
d=w/"s.jsonl"; d.write_text("\n".join(lines[:int(len(lines)*0.7)])+"\n")
cli("init","."); cli("digest","--as=claude-code-transcript","--mutability=append-only",str(d))
load=lambda: [json.loads(l) for f in glob.glob(str(w/".compost/graph/*.jsonl")) for l in open(f) if l.strip()]
root=next(r["guid"] for r in load() if r["record"]=="node" and r["type"]=="session")
d.write_text("\n".join(lines)+"\n")
r=cli("digest","--as=claude-code-transcript",f"--updates={root}",str(d))
assert r.returncode==0, r.stdout+r.stderr
p=R.check(load())
assert not p, f"check fails after a real append through the CLI: {p[:2]}"
PY

run NEW "appending a head-edited file is refused, and nothing is written" <<PY
import subprocess,os,tempfile,json,glob,pathlib
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
cli=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,capture_output=True,text=True)
lines=[l for l in pathlib.Path("$ROOT/$CORP").read_text().splitlines() if l.strip()]
d=w/"s.jsonl"; d.write_text("\n".join(lines[:int(len(lines)*0.7)])+"\n")
cli("init","."); cli("digest","--as=claude-code-transcript","--mutability=append-only",str(d))
load=lambda: [json.loads(l) for f in glob.glob(str(w/".compost/graph/*.jsonl")) for l in open(f) if l.strip()]
g=load(); n1=sum(1 for r in g if r["record"]=="node")
root=next(r["guid"] for r in g if r["record"]=="node" and r["type"]=="session")
t=list(lines); o=json.loads(t[3])
if isinstance(o.get("message"),dict): o["message"]["content"]="TAMPERED"
else: o["_tampered"]=True
t[3]=json.dumps(o); d.write_text("\n".join(t)+"\n")
r=cli("digest","--as=claude-code-transcript",f"--updates={root}",str(d))
assert r.returncode!=0, "a head-edited file was appended silently"
n2=sum(1 for x in load() if x["record"]=="node")
assert n1==n2, f"refused but still wrote: {n1} -> {n2} nodes"
PY

run NEW "check reports an append-only root whose head changed" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import records as R
b=R.Builder()
root=b.node("session",{"source":"s.jsonl","session_id":"x","version":None,
                       "mutability":"append-only"})
k=[b.node("turn",{"author":"human","uuid":f"u{i}","timestamp":"t","log":{}}) for i in (1,2)]
b.children(root,k,"session"); R.stamp_hashes(b.records)
# the head is edited in place, which append-only forbids
n=next(r for r in b.records if r["guid"]==k[0]); n["params"]["author"]="assistant"
p=R.check(b.records)
assert any("append" in x.lower() or "head" in x.lower() or "mutability" in x.lower()
           for x in p), f"an altered head was accepted: {p}"
PY

run NEW "the alignment walk exists, is pure, and follows delegates_to" <<PY
import sys,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import records as R, session as S
assert hasattr(R,"align"), "no records.align((old,new)) -> prefix length"
lines=[l for l in pathlib.Path("$ROOT/$CORP").read_text().splitlines() if l.strip()]
d1,d2=pathlib.Path(tempfile.mkdtemp()),pathlib.Path(tempfile.mkdtemp())
(d1/"s.jsonl").write_text("\n".join(lines[:int(len(lines)*0.7)])+"\n")
(d2/"s.jsonl").write_text("\n".join(lines)+"\n")
ro,a=S.session_to_records(d1/"s.jsonl"); rn,bb=S.session_to_records(d2/"s.jsonl")
before=len(ro)
pre,total=R.align(ro,a,rn,bb)
assert len(ro)==before, "align() wrote to the records it was given"
assert pre==total, f"prefix {pre} of {total}"
# a delegation-blind walk would see ~half; assert the walk is the wide one
n=sum(1 for r in ro if r["record"]=="node")
assert total > 0.75*n, f"walk covers {total} of {n} nodes — delegation is not followed"
PY

run NEW "blob_of copes with several blobs on one root" <<PY
import sys,inspect; sys.path.insert(0,"$ROOT")
from src import records as R
src=inspect.getsource(R.blob_of)
assert "list" in src.split("\n")[0] or hasattr(R,"blobs_of"), \
    "blob_of still returns a single blob; an AoTA root has several"
PY

run NEW "mutability is in the schema on root types" <<PY
import json
s=json.load(open("$ROOT/tools/record-schema-1.json"))
nt=s["\$defs"]["node_types"]
missing=[t for t in ("session","document")
         if "mutability" not in nt[t]["params"]["properties"]]
assert not missing, f"{missing} have no mutability param"
PY

echo
run GUARD "transcript round-trip holds" <<PY
import sys,json,glob,pathlib; sys.path.insert(0,"$ROOT")
from src import session as S
for f in glob.glob("$ROOT/tests/fixtures/sessions/*.jsonl"):
    lines=[json.loads(l) for l in pathlib.Path(f).read_text().splitlines() if l.strip()]
    recs,root=S.session_to_records(f)
    assert S.records_to_session(recs,root)==lines, f
PY

run GUARD "AST round-trip holds" <<PY
import sys,json,subprocess,glob; sys.path.insert(0,"$ROOT")
from src import records as R
fs=sorted(glob.glob("$ROOT/tests/corpus/**/*.md",recursive=True))[:25] or ["$ROOT/README.md"]
for f in fs:
    a=json.loads(subprocess.run(["pandoc","-f","commonmark_x-smart-attributes-fancy_lists",
        "-t","json",f],capture_output=True,text=True,check=True).stdout)
    recs,root=R.ast_to_records(a)
    assert R.records_to_ast(recs,root)==a, f
PY

run GUARD "a turn with two text blocks is still refused loudly" <<PY
import sys,json,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import session as S
d=pathlib.Path(tempfile.mkdtemp())/"two.jsonl"
d.write_text(json.dumps({"type":"user","uuid":"u","sessionId":"s","timestamp":"t",
 "message":{"role":"user","content":[{"type":"text","text":"a"},{"type":"text","text":"b"}]}})+"\n")
try:
    S.session_to_records(d); raise AssertionError("accepted two text blocks")
except NotImplementedError as e:
    assert "TODO-multiple-text-blocks" in str(e)
PY

echo
printf 'pass %d   fail %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

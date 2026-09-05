#!/usr/bin/env bash
# verify-0.2.13.sh — the fold. Deleted when v0.2.13 ships.
#
# Two classes of check, and the distinction matters:
#   NEW  — a v0.2.13 guarantee. MUST FAIL before the work and pass after.
#          A NEW check that passes at baseline proves nothing and is a bug
#          in this script.
#   GUARD — an existing property. MUST PASS at baseline and after.
#
# Run from the repo root, in the `compost` conda env. Writes only to a
# temp directory. It never runs a compost subcommand from inside this
# repository, because `.compost` here is a symlink to a private base.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT=$PWD
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
pass=0; fail=0
ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1)); }
no()   { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }
run()  { # run <NEW|GUARD> <name> <<< python
  local kind=$1 name=$2
  if python3 - >"$W/out" 2>&1; then ok "[$kind] $name"; else no "[$kind] $name"; sed 's/^/        /' "$W/out" | tail -4; fi
}

SESS=tests/corpus/compost-corpus/curated/sessions/session-04.jsonl
[ -f "$SESS" ] || SESS=tests/fixtures/sessions/session-smoke.jsonl
echo "corpus session: $SESS"
echo

# ---------------------------------------------------------------- NEW 1-3
run NEW "every node carries record_hash and record_subtree_hash" <<PY
import sys,glob,json; sys.path.insert(0,"$ROOT")
from src import session as S, records as R
recs,_=S.session_to_records("$ROOT/$SESS")
ast=json.loads(__import__("subprocess").run(["pandoc","-f","commonmark_x-smart-attributes-fancy_lists","-t","json","$ROOT/README.md"],capture_output=True,text=True,check=True).stdout)
recs+=R.ast_to_records(ast)[0]
miss=[r["guid"] for r in recs if r["record"]=="node" and not (r.get("record_hash") and r.get("record_subtree_hash"))]
assert not miss, f"{len(miss)} nodes missing a hash, e.g. {miss[:3]}"
PY

run NEW "record_hash == H([type, params, content]), canonical JSON" <<PY
import sys,hashlib,json; sys.path.insert(0,"$ROOT")
from src import session as S
def H(o): return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest()
recs,_=S.session_to_records("$ROOT/$SESS")
for r in recs:
    if r["record"]!="node": continue
    want=H([r["type"], r.get("params") or {}, r.get("content")])
    assert r["record_hash"]==want, f"{r['guid']} {r['type']}: stored != recomputed"
PY

run NEW "a leaf's fold is H([record_hash, []]); fold ignores non-tree edges" <<PY
import sys,hashlib,json; sys.path.insert(0,"$ROOT")
from src import session as S, records as R
def H(o): return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest()
recs,root=S.session_to_records("$ROOT/$SESS")
g=R.Graph(recs); leaves=[k for k in g.nodes if not g.children(k)]
assert leaves, "no leaves"
for k in leaves[:50]:
    n=g.nodes[k]
    assert n["record_subtree_hash"]==H([n["record_hash"],[]]), f"{k}: leaf fold wrong"
before={r["guid"]:r["record_subtree_hash"] for r in recs if r["record"]=="node"}
import copy
recs2=copy.deepcopy(recs)+[{"record":"edge","type":"cites","layer":"citation",
                            "source":leaves[0],"target":root,"guid":"x"}]
recs2=R.stamp_hashes(recs2)          # must re-derive, or this proves nothing
after={r["guid"]:r["record_subtree_hash"] for r in recs2 if r["record"]=="node"}
assert before==after, "a cites edge moved a fold"
PY

# ------------------------------------------------------------------ NEW 4
run NEW "mapping totality: signature, caller, list-shaped tool_result" <<PY
import sys,json,glob; sys.path.insert(0,"$ROOT")
from src import session as S
missing=[]
for f in glob.glob("$ROOT/tests/corpus/compost-corpus/curated/sessions/*.jsonl")+glob.glob("$ROOT/tests/fixtures/sessions/*.jsonl"):
    recs,_=S.session_to_records(f)
    nodes=[r for r in recs if r["record"]=="node"]
    srcsig=set(); srccal=set(); srclist=0
    for l in open(f):
        l=l.strip()
        if not l: continue
        c=(json.loads(l).get("message") or {}).get("content")
        if not isinstance(c,list): continue
        for b in c:
            if not isinstance(b,dict): continue
            if b.get("type")=="thinking" and b.get("signature"): srcsig.add(b["signature"])
            if b.get("type")=="tool_use" and "caller" in b: srccal.add(json.dumps(b["caller"]))
            if b.get("type")=="tool_result" and isinstance(b.get("content"),list): srclist+=1
    gotsig={n["params"].get("signature") for n in nodes if n["type"]=="thinking"}
    gotcal={json.dumps(n["params"].get("caller")) for n in nodes if n["type"]=="toolcall"}
    if srcsig-gotsig: missing.append(f"{f}: {len(srcsig-gotsig)} signatures dropped")
    if srccal-gotcal: missing.append(f"{f}: caller dropped")
    if srclist and not any(isinstance(n["params"].get("text"),list) for n in nodes if n["type"]=="tooloutput"):
        missing.append(f"{f}: list-shaped tool_result flattened")
assert not missing, "; ".join(missing[:3])
PY

# ------------------------------------------------------------------ NEW 5
run NEW "no derived param reads the subtree: 'lines' is gone" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import session as S
recs,root=S.session_to_records("$ROOT/$SESS")
p=[r for r in recs if r["guid"]==root][0]["params"]
assert "lines" not in p, f"session root still carries lines={p['lines']}"
PY

run NEW "alignment precondition: truncated tree is a clean 100% prefix" <<PY
import sys,itertools,tempfile,pathlib,glob; sys.path.insert(0,"$ROOT")
from src import session as S, records as R
bad=[]
srcs=glob.glob("$ROOT/tests/corpus/compost-corpus/curated/sessions/*.jsonl") or ["$ROOT/$SESS"]
for src in srcs:
    lines=[l for l in pathlib.Path(src).read_text().splitlines() if l.strip()]
    if len(lines)<10: continue
    d1,d2=pathlib.Path(tempfile.mkdtemp()),pathlib.Path(tempfile.mkdtemp())
    (d1/"s.jsonl").write_text("\n".join(lines[:int(len(lines)*0.7)])+"\n")
    (d2/"s.jsonl").write_text("\n".join(lines)+"\n")
    def walk(p):
        recs,root=S.session_to_records(p); g=R.Graph(recs); out=[]
        def go(k):
            out.append(g.nodes[k]["record_hash"])
            for c in g.children(k): go(c)
        go(root); return out
    a,b=walk(d1/"s.jsonl"),walk(d2/"s.jsonl")
    pre=len(list(itertools.takewhile(lambda t:t[0]==t[1],zip(a,b))))
    if pre!=len(a): bad.append(f"{pathlib.Path(src).name}: {pre}/{len(a)}")
assert not bad, "prefix not 100%: "+", ".join(bad)
PY

# ------------------------------------------------------------------ NEW 7
run NEW "check() recomputes hashes and rejects a tampered one" <<PY
import sys,subprocess,json,glob,os,tempfile,pathlib; sys.path.insert(0,"$ROOT")
w=pathlib.Path(tempfile.mkdtemp()); os.chdir(w)
env=dict(os.environ)
subprocess.run(["python3","-m","src.cli","init","."],cwd=w,env={**env,"PYTHONPATH":"$ROOT"},check=True,capture_output=True)
subprocess.run(["python3","-m","src.cli","digest","--as=claude-code-transcript","$ROOT/$SESS"],cwd=w,env={**env,"PYTHONPATH":"$ROOT"},check=True,capture_output=True)
f=glob.glob(str(w/".compost/graph/*.jsonl"))[0]
ls=pathlib.Path(f).read_text().splitlines()
for i,l in enumerate(ls):
    r=json.loads(l)
    if r.get("record")=="node": r["record_hash"]="0"*64; ls[i]=json.dumps(r); break
pathlib.Path(f).write_text("\n".join(ls)+"\n")
r=subprocess.run(["python3","-m","src.cli","check"],cwd=w,env={**env,"PYTHONPATH":"$ROOT"},capture_output=True,text=True)
assert r.returncode!=0 or "0 problems" not in r.stdout, "check accepted a tampered record_hash"
PY

echo
# ------------------------------------------------------------------- GUARDS
run GUARD "round-trip: records_to_session(session_to_records(f)) == lines" <<PY
import sys,json,glob,pathlib; sys.path.insert(0,"$ROOT")
from src import session as S
for f in (glob.glob("$ROOT/tests/fixtures/sessions/*.jsonl")+["$ROOT/$SESS"]):
    lines=[json.loads(l) for l in pathlib.Path(f).read_text().splitlines() if l.strip()]
    recs,root=S.session_to_records(f)
    assert S.records_to_session(recs,root)==lines, f
PY

run GUARD "round-trip: records_to_ast(ast_to_records(ast)) == ast" <<PY
import sys,json,subprocess,glob; sys.path.insert(0,"$ROOT")
from src import records as R
fs=sorted(glob.glob("$ROOT/tests/corpus/**/*.md",recursive=True))[:40] or ["$ROOT/README.md"]
for f in fs:
    a=json.loads(subprocess.run(["pandoc","-f","commonmark_x-smart-attributes-fancy_lists","-t","json",f],capture_output=True,text=True,check=True).stdout)
    recs,root=R.ast_to_records(a)
    assert R.records_to_ast(recs,root)==a, f
PY

echo
printf 'pass %d   fail %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

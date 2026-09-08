#!/usr/bin/env bash
# verify-0.2.14.sh — the recursion made explicit. Deleted when v0.2.14 ships.
#
#   NEW   — a v0.2.14 guarantee. MUST FAIL before the work, pass after.
#           A NEW check that passes at baseline is a bug in this script.
#   GUARD — an existing property. MUST PASS at both ends.
#
# Run from the repo root in the `compost` env. Writes only to a temp dir and
# never runs a writing subcommand from inside this repository, because
# `.compost` here is a symlink to the human's base.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT=$PWD
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
pass=0; fail=0
ok() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1)); }
no() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }
run() { local k=$1 n=$2
  if python3 - >"$W/o" 2>&1; then ok "[$k] $n"; else no "[$k] $n"; sed 's/^/        /' "$W/o" | tail -3; fi; }

SESS=tests/fixtures/sessions/session-smoke.jsonl
echo

run NEW "READER is defined exactly once in src/" <<PY
import re,glob
hits=[(f,l) for f in glob.glob("$ROOT/src/*.py")
      for l in open(f) if re.match(r"^READER\s*=", l)]
assert len(hits)==1, f"{len(hits)} definitions: {[h[0].split('/')[-1] for h in hits]}"
PY

run NEW "src/markdown.py exposes text_to_records; the two copies are gone" <<PY
import sys,os; sys.path.insert(0,"$ROOT")
assert os.path.exists("$ROOT/src/markdown.py"), "no src/markdown.py"
from src import markdown as M
assert hasattr(M,"text_to_records"), "no text_to_records"
from src import session as S, routes as RT
assert not hasattr(S,"_md_blocks"), "session._md_blocks still exists"
assert not hasattr(RT,"_ast_of_text"), "routes._ast_of_text still exists"
PY

run NEW "a digested turn reaches its prose through delegates_to" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import session as S, records as R
recs,root=S.session_to_records("$ROOT/$SESS")
d=[e for e in recs if e["record"]=="edge" and e["type"]=="delegates_to"]
assert d, "no delegates_to edges minted"
g=R.Graph(recs)
for e in d:
    assert g.nodes[e["source"]]["type"]=="turn", "delegates_to must start at a turn"
    assert g.nodes[e["destination"]]["type"]=="document", "must reach a document"
PY

run NEW "the delegated document is a root, and check is clean" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import session as S, records as R
recs,root=S.session_to_records("$ROOT/$SESS")
p=R.check(recs)
assert not p, f"{len(p)} problems, e.g. {p[:2]}"
kids={e["destination"] for e in recs if e["record"]=="edge" and e["type"]=="contains"}
docs=[r["guid"] for r in recs if r["record"]=="node" and r["type"]=="document"]
assert docs, "no delegated document"
bad=[d for d in docs if d in kids]
assert not bad, f"{len(bad)} documents are contained by something"
PY

run NEW "every delegated input is stored, and the derivation chain is two hops" <<PY
import sys,tempfile,os,subprocess,glob,json,pathlib; sys.path.insert(0,"$ROOT")
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
run=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,
                              capture_output=True,text=True,check=True)
run("init","."); run("digest","--as=claude-code-transcript","$ROOT/$SESS")
recs=[json.loads(l) for f in glob.glob(str(w/".compost/graph/*.jsonl"))
      for l in open(f) if l.strip()]
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
df={}
for e in recs:
    if e["record"]=="edge" and e["type"]=="derived_from":
        df.setdefault(e["source"],[]).append(e["destination"])
docs=[g for g,n in nodes.items() if n["type"]=="document"]
assert docs, "no delegated document"
for d in docs:
    b=df.get(d,[])
    assert len(b)==1, f"document has {len(b)} derived_from edges"
    blob=nodes[b[0]]
    assert blob["type"]=="blob", "derived_from must reach a blob"
    assert (blob["params"].get("stored_as") and
            (w/".compost/storage"/blob["params"]["stored_as"]).exists()), "blob not in storage"
    assert df.get(b[0]), "fragment blob has no derived_from to the transcript blob"
PY

run NEW "the stored fragment is byte-identical to the source text" <<PY
import sys,tempfile,os,subprocess,glob,json,pathlib; sys.path.insert(0,"$ROOT")
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
run=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,
                              capture_output=True,text=True,check=True)
run("init","."); run("digest","--as=claude-code-transcript","$ROOT/$SESS")
src=[json.loads(l) for l in open("$ROOT/$SESS") if l.strip()]
want=set()
for d in src:
    c=(d.get("message") or {}).get("content")
    for b in (c if isinstance(c,list) else []):
        if isinstance(b,dict) and b.get("type")=="text" and b.get("text","").strip():
            want.add(b["text"])
got=set()
for f in glob.glob(str(w/".compost/storage/*.json")):
    try: got.add(json.loads(open(f).read()).get("text"))
    except Exception: pass
missing=want-got
assert want, "fixture has no text blocks"
assert not missing, f"{len(missing)} text blocks not stored byte-identically"
PY

run NEW "the selector resolves to the stored fragment" <<PY
import sys,tempfile,os,subprocess,glob,json,pathlib; sys.path.insert(0,"$ROOT")
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
run=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,
                              capture_output=True,text=True,check=True)
run("init","."); run("digest","--as=claude-code-transcript","$ROOT/$SESS")
recs=[json.loads(l) for f in glob.glob(str(w/".compost/graph/*.jsonl"))
      for l in open(f) if l.strip()]
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
frag=[n for n in nodes.values() if n["type"]=="blob"
      and (n.get("params") or {}).get("selector_value")]
assert frag, "no blob carries selector_value"
df={e["source"]:e["destination"] for e in recs
    if e["record"]=="edge" and e["type"]=="derived_from"}
for b in frag:
    p=b["params"]
    assert p.get("selector_conforms_to")=="RFC 6901", "selector_conforms_to must name JSON Pointer"
    assert p.get("original_name") is None, "a fragment has no original_name"
    parent=nodes[df[b["guid"]]]
    lines=[json.loads(l) for l in
           open(w/".compost/storage"/parent["params"]["stored_as"]) if l.strip()]
    cur=lines
    for tok in p["selector_value"].split("/")[1:]:
        cur=cur[int(tok)] if isinstance(cur,list) else cur[tok.replace("~1","/").replace("~0","~")]
    stored=json.loads(open(w/".compost/storage"/p["stored_as"]).read())
    assert cur==stored, "selector does not resolve to the stored fragment"
PY

run NEW "check() rejects a derived_from cycle — the twelfth assertion" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import records as R
b=R.Builder()
d1=b.node("document",{"meta":{},"pandoc_api_version":[1,23]})
d2=b.node("document",{"meta":{},"pandoc_api_version":[1,23]})
b.edge("derived_from",d1,d2,"ingestion"); b.edge("derived_from",d2,d1,"ingestion")
R.stamp_hashes(b.records)
p=R.check(b.records)
assert any("derived" in x.lower() or "cycle" in x.lower() for x in p), \
    f"a derived_from cycle was accepted: {p}"
PY

run NEW "every schema alignment says what it enforces and what it does not" <<PY
import json
s=json.load(open("$ROOT/tools/record-schema-1.json"))
pairs=s["\$defs"]["edge_pairs"]
al=[p for p in pairs if "aligns_with" in p]
assert al, "no edge pair declares aligns_with"
bad=[p for p in al if not p.get("enforced") or "not_enforced" not in p]
assert not bad, f"{len(bad)} alignments do not name enforced/not_enforced"
PY

echo
run GUARD "lookup names the conversation, not '?'" <<PY
import sys,tempfile,os,subprocess,glob,json,pathlib,re; sys.path.insert(0,"$ROOT")
w=pathlib.Path(tempfile.mkdtemp()); env={**os.environ,"PYTHONPATH":"$ROOT"}
run=lambda *a: subprocess.run(["python3","-m","src.cli",*a],cwd=w,env=env,
                              capture_output=True,text=True)
run("init","."); run("digest","--as=claude-code-transcript","$ROOT/$SESS")
recs=[json.loads(l) for f in glob.glob(str(w/".compost/graph/*.jsonl"))
      for l in open(f) if l.strip()]
prose=[r["guid"] for r in recs if r["record"]=="node" and r["type"] in ("Para","Plain")]
assert prose, "fixture produced no prose blocks"
r=run("lookup",prose[0])
assert r.returncode==0, r.stderr
first=r.stdout.splitlines()[0]
assert " in ?" not in first, f"lookup lost the conversation: {first.strip()[:90]}"
PY

run GUARD "a turn with two text blocks is refused loudly" <<PY
import sys,json,tempfile,pathlib; sys.path.insert(0,"$ROOT")
from src import session as S
d=pathlib.Path(tempfile.mkdtemp())/"two.jsonl"
d.write_text(json.dumps({"type":"user","uuid":"u1","sessionId":"s","timestamp":"t",
 "message":{"role":"user","content":[{"type":"text","text":"a"},
                                     {"type":"text","text":"b"}]}})+"\n")
try:
    S.session_to_records(d); raise AssertionError("two text blocks were accepted")
except NotImplementedError as e:
    assert "TODO-multiple-text-blocks" in str(e), "error does not name the TODO"
PY

run GUARD "transcript round-trip: records_to_session(...) == lines" <<PY
import sys,json,glob,pathlib; sys.path.insert(0,"$ROOT")
from src import session as S
for f in glob.glob("$ROOT/tests/fixtures/sessions/*.jsonl"):
    lines=[json.loads(l) for l in pathlib.Path(f).read_text().splitlines() if l.strip()]
    recs,root=S.session_to_records(f)
    assert S.records_to_session(recs,root)==lines, f
PY

run GUARD "AST round-trip: records_to_ast(ast_to_records(ast)) == ast" <<PY
import sys,json,subprocess,glob; sys.path.insert(0,"$ROOT")
from src import records as R
fs=sorted(glob.glob("$ROOT/tests/corpus/**/*.md",recursive=True))[:30] or ["$ROOT/README.md"]
for f in fs:
    a=json.loads(subprocess.run(["pandoc","-f","commonmark_x-smart-attributes-fancy_lists",
                                 "-t","json",f],capture_output=True,text=True,check=True).stdout)
    recs,root=R.ast_to_records(a)
    assert R.records_to_ast(recs,root)==a, f
PY

run GUARD "alignment prefix is 100%, AND the walk still covers the graph" <<PY
# Two assertions, and the second is the one v0.2.14 nearly lost. Delegation
# moves prose out of a turn's `contains` children, so a walk that follows only
# `contains`/`next` reaches 52.5% of a digest — 100% of a prefix over half the
# graph, which reads as "unchanged" and is not. The walk must follow
# `delegates_to`, and the coverage is asserted so a future narrowing cannot
# pass silently.
import sys,itertools,tempfile,pathlib,glob; sys.path.insert(0,"$ROOT")
from src import session as S, records as R
bad=[]
for src in (glob.glob("$ROOT/tests/corpus/compost-corpus/curated/sessions/*.jsonl") or ["$ROOT/$SESS"]):
    lines=[l for l in pathlib.Path(src).read_text().splitlines() if l.strip()]
    if len(lines)<10: continue
    d1,d2=pathlib.Path(tempfile.mkdtemp()),pathlib.Path(tempfile.mkdtemp())
    (d1/"s.jsonl").write_text("\n".join(lines[:int(len(lines)*0.7)])+"\n")
    (d2/"s.jsonl").write_text("\n".join(lines)+"\n")
    def walk(p):
        recs,root=S.session_to_records(p); g=R.Graph(recs)
        deleg={}
        for e in recs:
            if e["record"]=="edge" and e["type"]=="delegates_to":
                deleg.setdefault(e["source"],[]).append(e["destination"])
        out=[]
        def go(k):
            out.append(g.nodes[k]["record_hash"])
            for c in g.children(k): go(c)
            for d in deleg.get(k,[]): go(d)
        go(root)
        total=sum(1 for r in recs if r["record"]=="node")
        return out, total
    (a,ta),(b,tb)=walk(d1/"s.jsonl"),walk(d2/"s.jsonl")
    pre=len(list(itertools.takewhile(lambda t:t[0]==t[1],zip(a,b))))
    name=pathlib.Path(src).name
    if pre!=len(a): bad.append(f"{name}: prefix {pre}/{len(a)}")
    # A walk that stops following delegation reaches ~52% of a digest, so a
    # floor well above that catches the narrowing while leaving room for the
    # UNCONTAINED types (blob, file, alias) that are never in the tree.
    if len(a) < 0.75*ta:
        bad.append(f"{name}: walk covers {len(a)}/{ta} nodes — the tree is being missed")
assert not bad, "; ".join(bad)
PY

echo
printf 'pass %d   fail %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

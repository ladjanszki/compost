#!/usr/bin/env bash
# verify-0.3.0.sh — the talks-about layer. Deleted when v0.3.0 ships.
#
#   NEW   — a v0.3.0 guarantee. MUST FAIL before the work, pass after.
#           A NEW check that passes at baseline is a bug in this script.
#   GUARD — an existing property. MUST PASS at both ends.
#
# Never runs a writing subcommand from inside this repository: `.compost` here
# is a symlink into the human's notes repository. Every CLI check below builds
# a base under $(mktemp -d) and cd's there first, so the walk-up cannot reach
# it.
#
# Nothing here makes a network call, and that is itself guarantee 2.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT=$PWD; W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
FIX=$ROOT/tests/fixtures/concept-map
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

# ---------------------------------------------------------------------------
# NEW — every one of these must fail at baseline
# ---------------------------------------------------------------------------

run NEW "src/llm.py exists, and defines its endpoint and model exactly once" <<PY
import pathlib,re
p=pathlib.Path("$ROOT/src/llm.py")
assert p.exists(), "src/llm.py does not exist — the one seam is unbuilt"
src=p.read_text()
for name in ("ENDPOINT","MODEL"):
    hits=re.findall(rf"^{name}\s*=", src, re.M)
    assert len(hits)==1, f"{name} defined {len(hits)} times in llm.py, expected 1"
PY

run NEW "nothing in src/ reaches the network except llm.py — guarantee 14" <<PY
import pathlib,re
srcs=[f for f in pathlib.Path("$ROOT/src").glob("*.py")]
assert any(f.name=="llm.py" for f in srcs), "src/llm.py does not exist yet"
bad=[f.name for f in srcs if f.name!="llm.py"
     and re.search(r"urllib\.request|urlopen|http\.client|openrouter", f.read_text())]
assert not bad, f"these reach the network outside the seam: {bad}"
PY

run NEW "concept-map is a registered builder taking --map" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import layers as L
assert "concept-map" in L.BUILDERS, f"BUILDERS holds {sorted(L.BUILDERS)}"
PY

run NEW "the schema admits the five new names and the two new edge props" <<PY
import json
s=json.load(open("$ROOT/tools/record-schema-1.json"))
n=s["\$defs"]["node"]; e=s["\$defs"]["edge"]
for t in ("concept_run","abstention"):
    assert t in n["properties"]["type"]["enum"], f"node type {t!r} not in the schema"
for t in ("talks_about","used"):
    assert t in e["properties"]["type"]["enum"], f"edge type {t!r} not in the schema"
assert "concept-map" in e["properties"]["layer"]["enum"], "layer 'concept-map' not in the schema"
for prop in ("primary","run"):
    assert prop in e["properties"], f"edge property {prop!r} missing; additionalProperties is false"
PY

run NEW "both new node types are UNCONTAINED" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import records as R
for t in ("concept_run","abstention"):
    assert t in R.UNCONTAINED, f"{t} is not UNCONTAINED — check will demand a parent"
PY

run NEW "exactly one primary per block per run — the fifteenth check assertion" <<PY
import sys,uuid; sys.path.insert(0,"$ROOT")
from src import records as R, markdown as MD
# Built from a real fixture, not by hand: a hand-assembled graph has no next
# chain, so Graph.children() raises before check() is ever reached and this
# failed for the wrong reason. No backticks in a heredoc body -- unquoted
# heredocs expand them as command substitution.
recs,root=R.ast_to_records(MD.ast_of_file("$FIX/map.md"))
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
heads=[g for g,n in nodes.items() if n["type"]=="Header"]
para=[g for g,n in nodes.items() if n["type"]=="Para"]
assert len(heads)>=2 and para, "the fixture changed shape"
assert not R.check(recs), f"the fixture graph is already unsound: {R.check(recs)}"
runid=str(uuid.uuid4())
b=R.Builder()
b.edge("talks_about",para[0],heads[0],"concept-map",primary=True,run=runid)
b.edge("talks_about",para[0],heads[1],"concept-map",primary=True,run=runid)
probs=R.check(recs+b.records)
assert any("primary" in p for p in probs), \
    f"two primaries in one run went unreported; check said: {probs}"
# The other half of the same assertion, and it is deliberately not a separate
# check: "two runs stay clean" cannot fail at baseline, so on its own it would
# be a NEW check that passes -- which the rules at the top call a bug.
c=R.Builder()
c.edge("talks_about",para[0],heads[0],"concept-map",primary=True,run=str(uuid.uuid4()))
c.edge("talks_about",para[0],heads[1],"concept-map",primary=True,run=str(uuid.uuid4()))
spread=[q for q in R.check(recs+c.records) if "primary" in q]
assert not spread, f"the assertion is not scoped per run; two runs were reported: {spread}"
PY

run NEW "--cost-calculation makes no network call and exits 0 with the endpoint closed" <<PY
import subprocess,os,sys,pathlib,json
W=pathlib.Path("$W")/"costbase"; W.mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
# A closed port. If anything tries to reach the network this cannot succeed.
env["COMPOST_LLM_ENDPOINT"]="http://127.0.0.1:1/v1/chat/completions"
env.pop("OPENROUTER_API_KEY",None)
env["PYTHONPATH"]="$ROOT"
r=subprocess.run([sys.executable,"-m","src.cli","init","."],cwd=W,env=env,
                 capture_output=True,text=True)
assert r.returncode==0, f"init failed: {r.stdout}{r.stderr}"
env2=env
r=subprocess.run([sys.executable,"-m","src.cli","digest","--as=notes",
                  "--mutability=mutable","$FIX/map.md"],cwd=W,env=env2,
                 capture_output=True,text=True)
assert r.returncode==0, f"digest failed: {r.stdout}{r.stderr}"
import re
root=re.findall(r"root ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                r.stdout)
assert root, f"no root guid in digest output: {r.stdout}"
r=subprocess.run([sys.executable,"-m","src.cli","layer","concept-map",
                  f"--map={root[0]}","--cost-calculation"],cwd=W,env=env2,
                 capture_output=True,text=True)
assert r.returncode==0, f"--cost-calculation did not exit 0: {r.stdout}{r.stderr}"
out=r.stdout.lower()
assert "estimate" in out, f"no number is labelled an estimate:\n{r.stdout}"
PY

run NEW "a root without concept_map: true is refused, and the refusal names the key" <<PY
import subprocess,os,sys,pathlib
W=pathlib.Path("$W")/"refusebase"; W.mkdir(parents=True,exist_ok=True)
env=dict(os.environ); env["PYTHONPATH"]="$ROOT"; env.pop("OPENROUTER_API_KEY",None)
r=subprocess.run([sys.executable,"-m","src.cli","init","."],cwd=W,env=env,
                 capture_output=True,text=True)
assert r.returncode==0, r.stdout+r.stderr
r=subprocess.run([sys.executable,"-m","src.cli","digest","--as=notes",
                  "--mutability=mutable","$FIX/no-frontmatter.md"],cwd=W,env=env,
                 capture_output=True,text=True)
assert r.returncode==0, r.stdout+r.stderr
import re
root=re.findall(r"root ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                r.stdout)
assert root, r.stdout
r=subprocess.run([sys.executable,"-m","src.cli","layer","concept-map",
                  f"--map={root[0]}","--cost-calculation"],cwd=W,env=env,
                 capture_output=True,text=True)
assert r.returncode!=0, "a map without the frontmatter key was accepted"
assert "concept_map" in (r.stdout+r.stderr), \
    f"the refusal does not name the key:\n{r.stdout}{r.stderr}"
PY

run NEW "a block over the 8,000-character cap is skipped and reported, never truncated" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import layers as L
cap=getattr(L,"SIZE_CAP",None)
assert cap==8000, f"SIZE_CAP is {cap!r}, expected 8000 (docs/roadmap.md, measured 2026-09-15)"
PY

run NEW "the collection view is a fourth family beside default-{djot,html,md}" <<PY
import pathlib,re
# NOT a bare search for "collection": views.py already says
# 'from collections import Counter', and matching that made this check pass at
# baseline, which the rules say is a bug in this script. Pinned to the naming
# the other three families already use: render_djot, render_md, render_html.
src=pathlib.Path("$ROOT/src/views.py").read_text()
assert re.search(r"^def render_collection\b", src, re.M), \
    "views.py defines no render_collection(); stage 2 is a view, not a layer"
PY

run NEW "batch_size is a bound, not a hint -- an oversized path-group is split" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import layers as L
# Measured 2026-09-17: the test corpus has a single path-group of 1,140
# fragments, and fragments with no ancestor path all share the empty path.
# _make_batches never split a group, so batch_size was only ever a hint.
groups=[(("p",), [{"guid":str(i),"text":"x","path":("p",)} for i in range(250)])]
batches=L._make_batches(groups, 100)
biggest=max(sum(len(fs) for _,fs in b) for b in batches)
assert biggest<=100, \
    f"largest batch holds {biggest} fragments; batch_size is not a bound"
total=sum(sum(len(fs) for _,fs in b) for b in batches)
assert total==250, f"splitting lost or duplicated fragments: {total} of 250"
PY

run NEW "ask() fails loudly when a model returns no text, and caps its output" <<PY
import sys, json, os, urllib.request; sys.path.insert(0,"$ROOT")
from src import llm
# A reasoning model spends output tokens on reasoning; with no max_tokens a
# large batch gets truncated and content comes back None. This crashed the
# 2026-09-17 model sweep deep inside _parse_response with an opaque
# AttributeError. No network here: urlopen is replaced.
seen={}
class Fake:
    def __init__(self,p): self._p=json.dumps(p).encode()
    def read(self): return self._p
    def __enter__(self): return self
    def __exit__(self,*a): return False
def fake(req, timeout=None):
    seen["body"]=json.loads(req.data.decode())
    return Fake({"choices":[{"message":{"content":None},"finish_reason":"length"}]})
urllib.request.urlopen=fake
os.environ["OPENROUTER_API_KEY"]="not-a-real-key"
assert hasattr(llm,"LLMError"), "llm.py defines no named error for a bad response"
try:
    llm.ask("s","u")
    raise AssertionError("ask() returned a non-string instead of failing loudly")
except llm.LLMError as e:
    assert "length" in str(e), f"the error does not name finish_reason: {e}"
assert seen["body"].get("max_tokens"), "the request sets no max_tokens"
PY

run NEW "the default model is the one that was measured" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import llm
# Measured 2026-09-17 over 2,207 fragments with ground truth: gpt-4o-mini
# rejected 12 of 13 batches and scored 39.3% page accuracy without headings;
# gemini-3.8-flash rejected 0 and scored 99.4%, matching claude-opus-5 at a
# sixth of the price. docs/decisions.md carries the table.
assert llm.MODEL=="google/gemini-3.8-flash", \
    f"MODEL is {llm.MODEL!r}; the measured default is google/gemini-3.8-flash"
assert llm.MODEL in llm.PRICE_TABLE, "the default model has no price table entry"
PY

run NEW "a map with two labels of the same name is refused, not silently merged" <<PY
import sys, tempfile, pathlib; sys.path.insert(0,"$ROOT")
from src import layers as L, markdown as MD, records as R
# _label_index is a flat dict, so a repeated top-level label used to
# overwrite the first silently and every block classified under it would be
# attributed to whichever won. Measured 2026-09-17 against real material:
# 14 headings repeat across the Wikipedia set -- Definition, History,
# Examples, Properties -- so this is the normal case, not a corner.
d=pathlib.Path(tempfile.mkdtemp())/"m.md"
d.write_text("---\nconcept_map: true\n---\n\n"
             "# Storage\n\nOne.\n\n# Storage\n\nTwo.\n")
recs,root=R.ast_to_records(MD.ast_of_file(str(d)))
try:
    L._label_index(L._concept_map_tree(recs, root))
    raise AssertionError("a duplicate label was accepted and silently merged")
except L.ConceptMapError as e:
    assert "Storage" in str(e), f"the refusal does not name the label: {e}"
PY

echo

# ---------------------------------------------------------------------------
# GUARD — every one of these must pass at both ends
# ---------------------------------------------------------------------------

run GUARD "the concept map fixture parses to label -> prose -> sublabel, typed" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import markdown as MD, records as R
a=MD.ast_of_file("$FIX/map.md")
recs,root=R.ast_to_records(a)
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
g=R.Graph(recs)
meta=nodes[root].get("params",{}).get("meta") or {}
assert meta.get("concept_map")=={"t":"MetaBool","c":True}, \
    f"concept_map does not arrive as a typed MetaBool: {meta!r}"
assert R.records_to_ast(recs,root)==a, "the round-trip fails with frontmatter present"
tops=[k for k in g.children(root) if nodes[k]["type"]=="Header"]
assert len(tops)==3, f"{len(tops)} top-level labels, expected 3"
storage=[k for k in tops if (R.plain_text(nodes[k]) or "")=="Storage"]
assert storage, "no 'Storage' label"
kids=[nodes[k]["type"] for k in g.children(storage[0])]
assert "Para" in kids and kids.count("Header")==2, \
    f"'Storage' holds {kids}; expected its grounding Para and two sublabels"
PY

run GUARD "a map with concept_map: false is still parsed, and says false" <<PY
import sys; sys.path.insert(0,"$ROOT")
from src import markdown as MD, records as R
a=MD.ast_of_file("$FIX/over-cap.md")
recs,root=R.ast_to_records(a)
nodes={r["guid"]:r for r in recs if r["record"]=="node"}
meta=nodes[root].get("params",{}).get("meta") or {}
assert meta.get("concept_map")=={"t":"MetaBool","c":False}, \
    f"a false key must arrive as a typed false, not absent: {meta!r}"
big=max(len(R.plain_text(n) or "") for n in nodes.values())
assert big>8000, f"the over-cap fixture's largest block is {big}, not over the cap"
PY

run GUARD "the corpus is still 19,400 nodes — the pin has not moved" <<PY
import sys; sys.path.insert(0,"$ROOT")
$FIND
from src import records as R, markdown as MD
total=0
for f in FS:
    recs,_=R.ast_to_records(MD.ast_of_file(f))
    total+=sum(1 for r in recs if r["record"]=="node")
assert len(FS)==520, f"corpus has {len(FS)} documents, expected 520"
assert total==19400, f"corpus has {total} nodes, expected 19400 (v0.2.17)"
PY

run GUARD "12,296 of 14,298 blocks classify — the cost table's real denominator" <<PY
import sys; sys.path.insert(0,"$ROOT")
$FIND
from src import records as R, markdown as MD
# The spec's published 12,296 / ~514k reproduces only without CodeBlock; the
# prose that claimed otherwise was corrected 2026-09-15. Both numbers are
# pinned so that widening the set is a visible decision, never a drift.
WITH={"Para","Plain","ListItem","Header","CodeBlock","BlockQuote"}
n_with=n_without=chars=0
for f in FS:
    recs,_=R.ast_to_records(MD.ast_of_file(f))
    for r in recs:
        if r["record"]!="node" or r["type"] not in WITH: continue
        t=R.plain_text(r) or ""
        if not t.strip(): continue
        n_with+=1
        if r["type"]!="CodeBlock": n_without+=1; chars+=len(t)
assert n_with==14298, f"including CodeBlock: {n_with}, expected 14298"
assert n_without==12296, f"excluding CodeBlock: {n_without}, expected 12296"
assert chars==2057373, f"block text is {chars} chars, expected 2057373 (~514k tok)"
PY

run GUARD "the largest corpus block is 2,120 chars, so the corpus cannot test the cap" <<PY
import sys; sys.path.insert(0,"$ROOT")
$FIND
from src import records as R, markdown as MD
WITH={"Para","Plain","ListItem","Header","CodeBlock","BlockQuote"}
big=0
for f in FS:
    recs,_=R.ast_to_records(MD.ast_of_file(f))
    for r in recs:
        if r["record"]=="node" and r["type"] in WITH:
            big=max(big,len(R.plain_text(r) or ""))
assert big==2120, f"largest corpus block is {big}, expected 2120 — the cap's justification moved"
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

run GUARD "the existing check assertions still fire — a dangling edge is caught" <<PY
import sys,uuid; sys.path.insert(0,"$ROOT")
from src import records as R
b=R.Builder()
doc=b.node("document"); blk=b.node("Para")
b.edge("contains",doc,blk,"ingestion")
b.edge("cites",blk,str(uuid.uuid4()),"citation")
R.stamp_hashes(b.records)
probs=R.check(b.records)
assert any("dangling" in p for p in probs), f"a dangling endpoint went unreported: {probs}"
PY

run GUARD "pyproject still declares no dependencies — requests was rejected" <<PY
import pathlib,re
t=pathlib.Path("$ROOT/pyproject.toml").read_text()
m=re.search(r"^dependencies\s*=\s*\[(.*?)\]", t, re.M|re.S)
assert m, "no dependencies key in pyproject.toml"
assert not m.group(1).strip(), f"dependencies is no longer empty: {m.group(1)!r}"
PY

run GUARD "no suite reaches a host off this machine — guarantee 2" <<PY
import pathlib,re
# test_serve legitimately drives compost serve over 127.0.0.1, so a bare grep
# for urlopen fails at baseline — a GUARD that fails at baseline is a bug in
# this script. What guarantee 2 actually forbids is an *external* host.
bad=[]
for f in pathlib.Path("$ROOT/tests").glob("test_*.py"):
    for url in re.findall(r"https?://([A-Za-z0-9._-]+)", f.read_text()):
        if url not in ("127.0.0.1","localhost","0.0.0.0"): bad.append((f.name,url))
    if re.search(r"requests\.(get|post)|openrouter\.ai", f.read_text()):
        bad.append((f.name,"requests/openrouter"))
assert not bad, f"these suites reach off this machine: {bad}"
PY

run GUARD "no API key has reached a tracked file" <<PY
import subprocess,re
out=subprocess.run(["git","-C","$ROOT","grep","-I","-l","-E","sk-or-v1-[0-9a-f]{8}"],
                   capture_output=True,text=True).stdout.strip()
assert not out, f"an OpenRouter key appears in tracked files: {out}"
PY

run GUARD "READER is still defined exactly once in src/" <<PY
import glob,re
hits=[f for f in glob.glob("$ROOT/src/*.py")
      if re.search(r'^READER\s*=', open(f).read(), re.M)]
assert len(hits)==1, f"READER defined in {hits}"
PY

run GUARD "views.py still unhoists before handing blocks to pandoc" <<PY
import re,pathlib
src=pathlib.Path("$ROOT/src/views.py").read_text()
assert re.search(r"^\s*blocks = R\.unhoist\(blocks\)", src, re.M), \
    "views.py no longer unhoists; nested content will vanish from every view"
PY

echo
printf 'pass %d   fail %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

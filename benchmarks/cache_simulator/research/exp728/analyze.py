#!/usr/bin/env python3
"""exp728 frozen analysis. Gates: REPRO (bug reproduces on unpatched), FIX (patched multi-GPU runs + output parity),
NOREGRESS (patched single-GPU == unpatched), secondary MIXED (exp725 question, uncontaminated cells only)."""
import json, statistics as st, sys
from pathlib import Path
D = Path(sys.argv[1]); cells = json.load(open(D.parent / "cells.json"))
rc = dict(l.strip().split(",") for l in open(D / "rc.csv")) if (D / "rc.csv").exists() else {}
def precell_mem(cid):
    f = D / "precell.csv"
    if not f.exists(): return None
    for l in open(f):
        if l.startswith(cid + ","):
            body, oll = l.strip().rsplit(",", 1)
            parts = body.split(",", 1)[1].strip(";").split(";")
            # nvidia-smi rows "idx, mem" joined by ';' -> after split(",",1) they look like "0, 2;1, 6694"
            return {int(r.split(",")[0]): int(r.split(",")[1]) for r in parts if r.strip()}, int(oll)
    return None
def flagged(c):
    gp = [int(g) for g in c["gpus"].split(",")]
    pm = precell_mem(c["id"])
    if pm is None: return True
    mem, oll = pm
    if oll > 0 or any(mem.get(g, 0) > 1024 for g in gp): return True
    f = D / "monitor.csv"
    if f.exists():
        for l in open(f):
            p = l.strip().split(",")
            if len(p) >= 3 and p[1] == c["id"] and p[-1].strip() not in ("", "0"): return True
    return False
R, miss, F, fail_msg = {}, [], {}, {}
for c in cells:
    j = D / f"{c['id']}.json"
    if j.exists():
        res = json.load(open(j)); R[c["id"]] = res
        F[c["id"]] = flagged(c)
    else:
        miss.append(c["id"])
        lg = D / f"{c['id']}.log"
        fail_msg[c["id"]] = "Expected all tensors to be on the same device" in lg.read_text(errors="replace") if lg.exists() else False
def arm(b, g, r): return [c for c in cells if c["build"] == b and c["gpus"] == g and abs(c["ratio"] - r) < 1e-9]
def shas(cid): return [x["out_sha"] for x in R[cid]["rows"]]
def tok(cid): return st.median(x["decode_tok_s"] for x in R[cid]["rows"])
def prov_ok(cid):
    p = D / f"{cid}.json.prov.json"
    return p.exists() and "/moei-fix728/" in json.load(open(p))["store_so"]
# REPRO
u01 = arm("U", "0,1", 0.2)
rep = sum(1 for c in u01 if c["id"] in miss and fail_msg.get(c["id"]))
REPRO = "REPRODUCED" if rep >= 2 else "NOT-REPRODUCED"
print(f"REPRO unpatched gpus=0,1 r=0.2: device-mismatch failures {rep}/{len(u01)} -> {REPRO}")
# reference outputs: unpatched single GPU
ref = [shas(c["id"]) for c in arm("U", "1", 0.2) if c["id"] in R]
ref_ok = len(ref) >= 1 and all(r == ref[0] for r in ref)
print(f"reference U g1 r0.2 outputs: {len(ref)} cells, self-identical={ref_ok}")
# FIX
pm = arm("P", "0,1", 0.2) + arm("P", "0,1", 0.1)
ran = [c for c in pm if c["id"] in R]
prov = all(prov_ok(c["id"]) for c in ran) and len(ran) > 0
agree = {c["id"]: sum(a == b for a, b in zip(shas(c["id"]), ref[0])) for c in ran} if ref_ok else {}
parity = ref_ok and all(v >= len(ref[0]) - 1 for v in agree.values())
print(f"  per-cell prompts identical to reference (of {len(ref[0]) if ref_ok else '?'}): {agree}")
if len(ran) == len(pm) and prov and parity: FIX = "FIXED"
elif len(ran) == len(pm) and prov: FIX = "RUNS-BUT-DIVERGES"
else: FIX = "PARTIAL" if ran else "NOT-FIXED"
print(f"FIX patched gpus=0,1: ran {len(ran)}/{len(pm)}, provenance={prov}, parity(>=n-1 per cell)={parity} -> {FIX}")
# NOREGRESS
pu = [(c, d) for c in arm("P", "1", 0.2) for d in arm("U", "1", 0.2) if c["block"] == d["block"] and c["id"] in R and d["id"] in R]
same = all(shas(c["id"]) == shas(d["id"]) for c, d in pu) and len(pu) == 3
clean = [(c, d) for c, d in pu if not F[c["id"]] and not F[d["id"]]]
ratio = st.median(tok(c["id"]) / tok(d["id"]) for c, d in clean) if clean else float("nan")
NR = "NOREGRESS" if same and clean and 0.95 <= ratio <= 1.05 else ("NOREGRESS-OUTPUTS-ONLY" if same and not clean else "REGRESSION?")
print(f"NOREGRESS patched vs unpatched g1 r0.2: outputs identical {same} ({len(pu)} blocks); clean pairs {len(clean)}; median tok/s ratio {ratio:.3f} -> {NR}")
# MIXED (secondary, exp725 question)
def m(b, g, r):
    v = [tok(c["id"]) for c in arm(b, g, r) if c["id"] in R and not F[c["id"]]]
    return (st.mean(v), len(v)) if v else (float("nan"), 0)
for k in (("P", "1", 0.2), ("P", "1", 0.4), ("P", "0,1", 0.2), ("P", "0,1", 0.1)):
    print(f"  {k[0]} gpus={k[1]:<3} r={k[2]}: tok/s {m(*k)[0]:6.2f} (clean n={m(*k)[1]})")
a, b_ = m("P", "0,1", 0.2), m("P", "1", 0.4)
if a[1] >= 2 and b_[1] >= 2:
    q = a[0] / b_[0]
    MIX = "MIXED-WINS" if q >= 1.05 else "MIXED-LOSES" if q <= 0.95 else "MIXED-TIE"
    print(f"MIXED equal-total-budget: (0,1 @0.2) / (1 @0.4) = {q:.3f} -> {MIX}")
else:
    MIX = "MIXED-UNDETERMINED"
print("flagged (contaminated) cells:", sorted(k for k, v in F.items() if v))
unexpected = [m for m in miss if not (m.split("_")[1] == "U" and "_g01_" in m)]
print(f"\nVERDICT {REPRO}|{FIX}|{NR}|{MIX} [{'COMPLETE' if not unexpected else f'INCOMPLETE({len(unexpected)} missing)'}]")

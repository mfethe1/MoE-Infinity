#!/usr/bin/env python3
"""exp725 frozen analysis. Usage: analyze.py <outdir>. Gates exactly as PREREG.md."""
import json, statistics as st, sys
from pathlib import Path
D = Path(sys.argv[1]); cells = json.load(open(D.parent / "cells.json"))
R, missing = {}, []
for c in cells:
    f = D / f"{c['id']}.json"
    (R.__setitem__(c["id"], (c, json.load(open(f)))) if f.exists() else missing.append(c["id"]))
arm = {}
for cid, (c, res) in R.items():
    v = st.median(r["decode_tok_s"] for r in res["rows"])
    h = sum(r["stats_delta"]["policy_routed_hits"] for r in res["rows"])
    m = sum(r["stats_delta"]["policy_routed_misses"] for r in res["rows"])
    arm.setdefault((c["gpus"], c["ratio"]), []).append((c["block"], v, m / max(h + m, 1)))
S = {}
for k, v in sorted(arm.items()):
    t = [x[1] for x in v]
    S[k] = {"n": len(t), "tok": st.mean(t), "cv": (st.pstdev(t) / st.mean(t)) if len(t) > 1 else float("nan"),
            "miss": st.mean(x[2] for x in v)}
    print(f"gpus={k[0]:<4} r={k[1]:<4} n={len(t)} tok/s={S[k]['tok']:6.2f} cv={S[k]['cv']:.3f} miss={S[k]['miss']:.4f} blocks={sorted(v)}")
ref = {}
for cid, (c, res) in R.items():
    for r in res["rows"]:
        ref.setdefault(r["i"], set()).add(r["out_sha"])
G0 = all(len(s) == 1 for s in ref.values())
print(f"G0 identical outputs: {G0} {[len(s) for _, s in sorted(ref.items())]}")
full = [s for s in S.values() if s["n"] == 3]
V = bool(full) and sum(s["cv"] <= 0.10 for s in full) / len(full) >= 0.75
print(f"V CV<=0.10 in >=75% of complete arms: {V}")
pairs = [(("0,1", 0.1), ("1", 0.2)), (("0,1", 0.2), ("1", 0.4))]
q = []
for a, b in pairs:
    if a in S and b in S:
        q.append(S[a]["tok"] / S[b]["tok"])
        print(f"equal-capacity both{a[1]} / gpu1@{b[1]} = x{q[-1]:.3f}")
if len(q) < 2: H = "INCOMPLETE"
elif max(q) <= 0.85: H = "RR-HARMS"
elif min(q) >= 1.05: H = "RR-HELPS"
elif all(0.95 <= x <= 1.05 for x in q): H = "RR-NEUTRAL"
else: H = "RR-MIXED"
pre = ("" if G0 else "CORRECTNESS-DIVERGE|") + ("" if V else "NOISY|")
print(f"\nVERDICT {pre}{H} [{'COMPLETE' if not missing else f'INCOMPLETE({len(missing)} missing)'}]")

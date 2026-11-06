#!/usr/bin/env python3
"""exp724 frozen analysis. Usage: analyze.py <outdir>. Stdlib only. Gates exactly as PREREG.md."""
import json, statistics as st, sys
from pathlib import Path

D = Path(sys.argv[1])
cells = json.load(open(D.parent / "cells.json"))
R, missing = {}, []
for c in cells:
    f = D / f"{c['id']}.json"
    if f.exists():
        R[c["id"]] = (c, json.load(open(f)))
    else:
        missing.append(c["id"])


def blockval(res):  # block statistic = median over prompts of decode tok/s
    return st.median(r["decode_tok_s"] for r in res["rows"])


def missrate(res):
    h = sum(r["stats_delta"]["policy_routed_hits"] for r in res["rows"])
    m = sum(r["stats_delta"]["policy_routed_misses"] for r in res["rows"])
    return m / max(h + m, 1)


groups = {}
for cid, (c, res) in R.items():
    groups.setdefault((c["gpu"], c["policy"], c["ratio"]), []).append((c["block"], blockval(res), missrate(res)))
summ = {}
for k, v in sorted(groups.items()):
    t = [x[1] for x in v]
    mr = [x[2] for x in v]
    cv = st.pstdev(t) / st.mean(t) if len(t) > 1 else float("nan")
    summ[k] = {"n": len(v), "tok_s": st.mean(t), "cv": cv, "miss": st.mean(mr), "blocks": sorted(v)}
    print(f"gpu{k[0]} {k[1]:<7} r={k[2]:<5} n={len(v)} tok/s={st.mean(t):6.2f} cv={cv:5.3f} miss={st.mean(mr):.4f}")

# G0 correctness: identical greedy outputs per prompt across every cell
ref = {}
diverge = 0
for cid, (c, res) in R.items():
    for r in res["rows"]:
        ref.setdefault(r["i"], set()).add(r["out_sha"])
G0 = all(len(s) == 1 for s in ref.values())
print(f"\nG0 correctness identical outputs: {G0} distinct-per-prompt={[len(s) for _, s in sorted(ref.items())]}")

# V validity: CV <= 0.10 in >= 80% of cells with n=3
full = [s for s in summ.values() if s["n"] == 3]
vfrac = sum(s["cv"] <= 0.10 for s in full) / max(len(full), 1)
V = bool(full) and vfrac >= 0.8
print(f"V validity: {vfrac:.2f} of {len(full)} complete cells CV<=0.10 -> {V}")

# H1 sim2real on GPU1: within-ratio demeaned miss-rate vs tok/s Pearson r, and best-miss == best-speed
g1 = {k: s for k, s in summ.items() if k[0] == 1}
ratios = sorted({k[2] for k in g1})
xs, ys, agree = [], [], 0
for rt in ratios:
    ks = [k for k in g1 if k[2] == rt]
    mm = st.mean(g1[k]["miss"] for k in ks)
    mt = st.mean(g1[k]["tok_s"] for k in ks)
    for k in ks:
        xs.append(g1[k]["miss"] - mm)
        ys.append((g1[k]["tok_s"] - mt) / mt)
    bm = min(ks, key=lambda k: g1[k]["miss"])
    bt = max(g1[k]["tok_s"] for k in ks)
    ok = g1[bm]["tok_s"] >= 0.98 * bt
    agree += ok
    print(f"  r={rt}: best-miss {bm[1]} tok/s {g1[bm]['tok_s']:.2f} vs best {bt:.2f} -> {'agree' if ok else 'DISAGREE'}")
r = st.correlation(xs, ys) if len(xs) > 2 and st.pstdev(xs) > 0 and st.pstdev(ys) > 0 else float("nan")
H1 = "CONFIRMED" if r <= -0.7 and agree >= 2 else "MARGINAL" if r <= -0.4 else "REJECTED"
print(f"H1 within-ratio pearson(miss, rel tok/s) = {r:.3f}, agree {agree}/{len(ratios)} -> {H1}")

# H2 link placement at r=0.2: GPU1/GPU0 tok/s for lcnu and s3fifo
lk = []
for p in ("lcnu", "s3fifo"):
    a, b = summ.get((1, p, 0.2)), summ.get((0, p, 0.2))
    if a and b:
        lk.append(a["tok_s"] / b["tok_s"])
        print(f"  {p}: gpu1 {a['tok_s']:.2f} / gpu0 {b['tok_s']:.2f} = x{lk[-1]:.2f}")
H2 = ("CONFIRMED" if lk and min(lk) >= 1.2 else "MARGINAL" if lk and min(lk) >= 1.05 else "REJECTED") if len(lk) == 2 else "INCOMPLETE"
print(f"H2 link placement min ratio {min(lk) if lk else float('nan'):.2f} -> {H2}")

# descriptive: seconds per miss per GPU from per-prompt OLS of decode time on misses
for g in (0, 1):
    pts = [((r["stats_delta"]["policy_routed_misses"]) / max(r["n_new"] - 1, 1), (r["t_full_s"] - r["t_1tok_s"]) / max(r["n_new"] - 1, 1))
           for cid, (c, res) in R.items() if c["gpu"] == g for r in res["rows"]]
    if len(pts) > 2:
        sl = st.linear_regression([p[0] for p in pts], [p[1] for p in pts])
        print(f"descriptive gpu{g}: s/token = {sl.intercept*1e3:.1f} ms + {sl.slope*1e3:.3f} ms per miss/token (n={len(pts)})")

status = "COMPLETE" if not missing else f"INCOMPLETE({len(missing)} missing)"
pre = "" if G0 else "CORRECTNESS-DIVERGE|"
pre += "" if V else "NOISY|"
print(f"\nVERDICT {pre}SIM2REAL:{H1}|LINK:{H2} [{status}]")

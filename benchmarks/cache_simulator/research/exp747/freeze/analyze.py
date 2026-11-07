#!/usr/bin/env python3
"""exp747 frozen analyzer. Usage: analyze.py OUTDIR. Never edits inputs.
Per cell: micro2.py results + mon2.sh samples (epoch load1 runner_workers psi spinners gpu_mib ollama)."""
import json, os, statistics as st, sys

O = sys.argv[1]
cells = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()

R = {}
for c in cells:
    cid, k = c["id"], c["spin"]; p = f"{O}/{cid}.json"
    if cid in fail or not os.path.exists(p):
        print(f"cell {cid}: MISSING/FAILED"); continue
    r = json.load(open(p))["results"]
    mon = []
    if os.path.exists(f"{O}/{cid}.mon"):
        for l in open(f"{O}/{cid}.mon"):
            f = l.split()
            try:
                mon.append((float(f[1]), int(f[2]), f[3], int(f[4]), int(f[5]), int(f[6])))
            except (ValueError, IndexError):
                pass
    why = ["gpu-prestart"] if cid in flag else []
    if len(mon) < 5:
        why.append(f"mon-samples={len(mon)}")
    else:
        if any(m[1] > 0 for m in mon):
            why.append("ci-runner-active")
        if any(m[5] != 0 for m in mon):
            why.append("ollama-loaded-or-probe-failed")
        if max(m[4] for m in mon) > 3000:
            why.append(f"gpu-mem-max={max(m[4] for m in mon)}")
        la = st.mean(m[0] for m in mon)
        if la > k + 4:
            why.append(f"load-mean={la:.2f}>{k + 4}")
        if st.median(m[3] for m in mon) != k:
            why.append(f"spinners-median={st.median(m[3] for m in mon)}!={k}")
    if r["gate_overrun_frac"]["frac_base_gt_50us"] > 0.05:
        why.append(f"gate-overrun={r['gate_overrun_frac']['frac_base_gt_50us']:.3f}")
    hs, ks = r["hostfn_stall"], r["kern_sync"]
    R[cid] = dict(k=k, hs=hs["median_us"], hs90=hs["p90_us"], hs1ms=hs["frac_gt_1ms"], ks=ks["median_us"], ks90=ks["p90_us"],
                  nt=r["mm_notify"]["median_us"], clean=not why)
    print(f"cell {cid}: spin={k} hostfn_stall med={hs['median_us']:.1f} p90={hs['p90_us']:.1f} >1ms={hs['frac_gt_1ms']:.3f} | "
          f"kern_sync med={ks['median_us']:.1f} p90={ks['p90_us']:.1f} | notify med={r['mm_notify']['median_us']:.1f} | "
          f"load_mean={round(st.mean(m[0] for m in mon), 2) if mon else None} "
          f"{'CLEAN' if not why else 'EXCLUDED:' + ';'.join(why)}")


def lvl(k):
    v = [x for x in R.values() if x["k"] == k and x["clean"]]
    return None if not v else {f: st.mean(x[f] for x in v) for f in ("hs", "hs90", "hs1ms", "ks", "ks90", "nt")} | {"n": len(v)}


L = {k: lvl(k) for k in (0, 6, 12, 18)}
for k, v in L.items():
    print(f"level spin={k}: {v if v is None else {a: round(b, 3) for a, b in v.items()}}")

q = L[0]
if not q:
    quiet = "QUIET:INCONCLUSIVE"
else:
    rq = q["hs"] / q["ks"]
    print(f"QUIET hostfn_stall/kern_sync = {rq:.2f}")
    quiet = "QUIET:HOSTFN-STALL-EXCEEDS-SYNC" if rq >= 2 else ("QUIET:HOSTFN-CHEAP" if rq <= 1 else "QUIET:COMPARABLE")

c12 = L[12]
if not (q and c12):
    cont = "CONTENTION:INCONCLUSIVE"
else:
    rh, rs = c12["hs"] / q["hs"], c12["ks"] / q["ks"]
    print(f"CONTENTION spin12/spin0 ratio: hostfn_stall {rh:.2f}, kern_sync {rs:.2f}")
    cont = ("CONTENTION:HOSTFN-FRAGILE" if rh >= 2 and rh >= 1.5 * rs
            else ("CONTENTION:HOSTFN-ROBUST" if rh < 1.3 else "CONTENTION:MIXED"))

for k in (0, 6, 12, 18):  # descriptive engine-scale projection: 16 route + 128 retirement callbacks per token, if serialized
    if L[k]:
        print(f"PROJ spin={k}: 144 serialized callbacks/token x {L[k]['hs']:.0f} us = {144 * L[k]['hs'] / 1000:.1f} ms/token (upper bound)")
print(f"VERDICT {quiet}|{cont}")

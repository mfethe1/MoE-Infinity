#!/usr/bin/env python3
"""exp738 frozen analyzer. Usage: analyze.py OUTDIR. Prints metrics then VERDICT lines. Never edits inputs."""
import json, os, statistics as st, sys

O = sys.argv[1]
cells = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()
R = {}
for c in cells:
    p = f"{O}/{c['id']}.json"
    if c["id"] in fail or not os.path.exists(p):
        print(f"cell {c['id']}: MISSING/FAILED"); continue
    d = json.load(open(p)); rows = d["rows"]
    ms = st.median(1000.0 / r["decode_tok_s"] for r in rows)
    grp = sum(r.get("routing_delta", {}).get("grouped_experts", 0) for r in rows)
    R[c["id"]] = {"arm": c["arm"], "threads": c["threads"], "ms": ms, "ids": [r["out_ids"] for r in rows],
                  "grouped_experts": grp, "thr_eff": d.get("threads_effective"), "routing": d.get("routing_getter"),
                  "clean": c["id"] not in flag}
    print(f"cell {c['id']}: arm={c['arm']} t={c['threads']} ms/tok={ms:.2f} grouped_experts={grp} "
          f"threads_eff={d.get('threads_effective')} routing_getter={d.get('routing_getter')} "
          f"{'CLEAN' if c['id'] not in flag else 'FLAGGED'}")

def arm(key):
    sel = [v for k, v in R.items() if key(k, v)]
    clean = [v["ms"] for v in sel if v["clean"]]
    return (st.mean(clean) if clean else None), clean, sel

def match(a, b):
    n = min(len(a), len(b)); fd = next((i for i in range(n) if a[i] != b[i]), n)
    return sum(x == y for x, y in zip(a, b)) / max(n, 1), fd

hf, hfc, hfs = arm(lambda k, v: v["arm"] == "hf")
base, bc, bs = arm(lambda k, v: v["arm"] == "eng" and v["threads"] == 4)
grp, gc, gs = arm(lambda k, v: v["arm"] == "grp")
t1, t1c, t1s = arm(lambda k, v: v["arm"] == "eng" and v["threads"] == 1)
t8, t8c, t8s = arm(lambda k, v: v["arm"] == "eng" and v["threads"] == 8)
spreads = [abs(c[0] - c[1]) / st.mean(c) for c in (bc, gc, t1c, t8c) if len(c) == 2]
noise = max(spreads) if spreads else None
thr = max(0.05, 2 * noise) if noise is not None else 0.05
print(f"arms ms/tok: hf={hf} base={base} grp={grp} t1={t1} t8={t8}")
print(f"noise(max within-arm rel spread)={noise} threshold={thr:.4f}")
if hf and base:
    print(f"engine gap base-hf = {base - hf:.2f} ms/tok")

# manipulation checks
thr_ok = all(v["thr_eff"] == v["threads"] for v in R.values() if v["arm"] != "hf")
print(f"MANIP threads_effective==requested: {thr_ok}")
base_g = sum(v["grouped_experts"] for v in bs + t1s + t8s)
grp_g = [v["grouped_experts"] for v in gs]
print(f"MANIP grouped_experts: base/t1/t8 total={base_g} grp per-cell={grp_g}")

# GROUPED
ref_hf = next((v["ids"] for v in hfs), None)
ref_base = next((v["ids"] for v in bs), None)
if not gs or not gc or base is None:
    gv = "GROUPED:INCONCLUSIVE(no clean grp/base cells)"
elif not all(g > 0 for g in grp_g) or not any(v["routing"] for v in gs):
    gv = "GROUPED:NOT-ENGAGED"
else:
    correct = True
    if ref_hf and ref_base:
        g_ids = gs[0]["ids"]
        mg = [match(g, h) for g, h in zip(g_ids, ref_hf)]
        mb = [match(b, h) for b, h in zip(ref_base, ref_hf)]
        mgv, mbv = st.mean(m for m, _ in mg), st.mean(m for m, _ in mb)
        early = [i for i, ((_, fg), (_, fb)) in enumerate(zip(mg, mb)) if fg < 8 and fb >= 8]
        gb = st.mean(match(g, b)[0] for g, b in zip(g_ids, ref_base))
        print(f"PARITY grp-vs-hf={mgv:.3f} base-vs-hf={mbv:.3f} grp-vs-base={gb:.3f} early-divergence-prompts={early}")
        correct = mgv >= mbv - 0.05 and not early
    rel = (base - grp) / base
    closed = (base - grp) / (base - hf) if hf and base > hf else None
    print(f"GROUPED rel speedup={rel:.4f} gap_closed={closed}")
    if not correct:
        gv = "GROUPED-INCORRECT"
    elif rel >= thr:
        gv = "GROUPED-WINS"
    elif rel <= -thr:
        gv = "GROUPED-SLOWER"
    else:
        gv = "GROUPED-FLAT"
# THREADS
if None in (base, t1, t8) or not thr_ok:
    tv = "THREADS:INCONCLUSIVE" + ("" if thr_ok else "(threads manipulation failed)")
else:
    r81, r41, r48 = (t1 - t8) / t1, (t1 - base) / t1, (base - t8) / base
    print(f"THREADS t1->t4 gain={r41:.4f} t4->t8 gain={r48:.4f} t1->t8 gain={r81:.4f}")
    if r41 >= thr or r48 >= thr:
        tv = "THREADS-HELP" if r41 > -thr and r48 > -thr else "THREADS-MIXED"
    elif r41 <= -thr or r48 <= -thr:
        tv = "THREADS-HURT"
    else:
        tv = "THREADS-FLAT"
print(f"VERDICT {gv}|{tv}")

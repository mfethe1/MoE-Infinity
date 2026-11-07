#!/usr/bin/env python3
"""exp744 frozen analyzer. Usage: analyze.py OUTDIR. Never edits inputs.
(1) micro cells: WSL CUDA primitive latencies (stability across micro_1/micro_2).
(2) engine cells: gpu_only_expert_routing on vs off (ms/token, NVML busy/idle split as in exp743)."""
import json, os, statistics as st, sys

O = sys.argv[1]
cells = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()


def util(cid):
    p = f"{O}/{cid}.util.csv"; out = []
    if os.path.exists(p):
        for l in open(p):
            try:
                t, u, m = l.strip().split(","); out.append((float(t), float(u)))
            except ValueError:
                pass
    return out


M, E = {}, {}
for c in cells:
    cid = c["id"]; p = f"{O}/{cid}.json"
    if cid in fail or not os.path.exists(p):
        print(f"cell {cid}: MISSING/FAILED"); continue
    d = json.load(open(p)); U = util(cid)
    base = [u for t, u in U if U and t < U[0][0] + 8]
    why = ["contamination"] if cid in flag else []
    if not base or st.mean(base) > 5:
        why.append(f"util-baseline={st.mean(base) if base else None}")
    if c["arm"] == "micro":
        r = d["results"]
        M[cid] = dict(kern_sync=r["kern_sync"]["median_us"], hostfn=r["hostfn_cost_us"],
                      hostfn_tail=r["kern_hostfn_sync"]["frac_gt_1ms"], notify=r["mm_sync"]["notify_median_us"],
                      launch=r["launch_tiny"]["median_us"], clean=not why)
        print(f"cell {cid}: micro kern_sync={M[cid]['kern_sync']:.1f}us hostfn_cost={M[cid]['hostfn']:.1f}us "
              f"hostfn_tail>1ms={M[cid]['hostfn_tail']:.3f} mm_notify={M[cid]['notify']:.1f}us "
              f"launch={M[cid]['launch']:.1f}us {'CLEAN' if not why else 'EXCLUDED:' + ';'.join(why)}")
        continue
    per = []
    for r in d["rows"]:
        a, b = r["win_full"]; s = [u for t, u in U if a <= t <= b]
        if len(s) < 10:
            why.append(f"row{r['i']}-samples={len(s)}"); continue
        ms = 1000.0 / r["decode_tok_s"]; bf = st.mean(s) / 100
        per.append((ms, ms * bf, ms * (1 - bf)))
    if not per:
        print(f"cell {cid}: NO-UTIL"); continue
    ms, busy, idle = (st.median(x[k] for x in per) for k in range(3))
    eff = d.get("gpu_route_effective"); req = d.get("gpu_route_requested")
    E[cid] = dict(arm=c["arm"], ms=ms, busy=busy, idle=idle, ok=(eff is True) == (req == "on") and eff is not None,
                  ids=[r.get("out_ids") for r in d["rows"]], clean=not why)
    print(f"cell {cid}: arm={c['arm']} ms/tok={ms:.2f} busy={busy:.2f} idle={idle:.2f} route_eff={eff} "
          f"{'CLEAN' if not why else 'EXCLUDED:' + ';'.join(why)}")

# (1) primitives
cm = [v for v in M.values() if v["clean"]]
if len(cm) < 2:
    prim = "PRIM:INCONCLUSIVE"
else:
    ks = [v["kern_sync"] for v in cm]
    stable = max(ks) <= 2 * min(ks)
    hf = st.mean(v["hostfn"] for v in cm); nt = st.mean(v["notify"] for v in cm)
    print(f"PRIM kern_sync={ks} stable={stable} hostfn_cost_mean={hf:.1f}us mm_notify_mean={nt:.1f}us")
    lvl = "HIGH" if nt > 200 else ("LOW" if nt < 100 else "MID")
    prim = f"PRIM:NOTIFY-{lvl}{'' if stable else '-UNSTABLE'}|HOSTFN:{'COSTLY' if hf > 50 else 'CHEAP'}"

# (2) routing A/B
on = [v for v in E.values() if v["arm"] == "on" and v["clean"]]
off = [v for v in E.values() if v["arm"] == "off" and v["clean"]]
manip = all(v["ok"] for v in E.values())
par_ids = [v["ids"] for v in E.values()]
parity = all(x == par_ids[0] for x in par_ids) if par_ids else False
print(f"MANIP gpu_route_effective matches request: {manip}; token-id parity across engine cells: {parity}")
if not (on and off) or not manip:
    route = "ROUTE:INCONCLUSIVE"
else:
    a = {k: st.mean(v[k] for v in on) for k in ("ms", "busy", "idle")}
    b = {k: st.mean(v[k] for v in off) for k in ("ms", "busy", "idle")}
    dm = b["ms"] - a["ms"]
    print(f"ROUTE on={a} off={b} d_ms(off-on)={dm:+.2f} d_idle={b['idle'] - a['idle']:+.2f} d_busy={b['busy'] - a['busy']:+.2f}")
    route = "ROUTE:NO-CHANGE" if abs(dm) < 3 else ("ROUTE:OFF-SLOWER" if dm > 0 else "ROUTE:OFF-FASTER")
    if not parity:
        route += "(PARITY-FAIL)"
print(f"VERDICT {prim}|{route}")

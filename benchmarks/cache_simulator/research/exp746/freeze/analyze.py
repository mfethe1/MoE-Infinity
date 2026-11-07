#!/usr/bin/env python3
"""exp746 frozen analyzer. Usage: analyze.py OUTDIR. Never edits inputs.
Arms: hf (transformers bf16), on/off (MoE-Infinity, gpu_only_expert_routing on/off). Stress: 0 or K spinner processes.
Per cell: median over prompts of ms/token, and NVML busy/idle split (as exp743). Load columns from mon.sh:
  HH:MM:SS loadavg1 runner_workers psi_some_avg10 own_spinners"""
import json, os, statistics as st, sys

O = sys.argv[1]
cells = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()
Q_LOAD_MAX, S_LOAD_MAX = 4.0, 18.0


def util(cid):
    p = f"{O}/{cid}.util.csv"; out = []
    if os.path.exists(p):
        for l in open(p):
            try:
                t, u, m = l.strip().split(","); out.append((float(t), float(u)))
            except ValueError:
                pass
    return out


def loads(cid):
    p = f"{O}/{cid}.load"; out = []
    if os.path.exists(p):
        for l in open(p):
            f = l.split()
            try:
                out.append((float(f[1]), int(f[2]), f[3] if len(f) > 3 else "NA", int(f[4]) if len(f) > 4 else 0))
            except (ValueError, IndexError):
                pass
    return out


R = {}
for c in cells:
    cid = c["id"]; p = f"{O}/{cid}.json"
    if cid in fail or not os.path.exists(p):
        print(f"cell {cid}: MISSING/FAILED"); continue
    d = json.load(open(p)); U = util(cid); L = loads(cid)
    why = ["gpu-contamination"] if cid in flag else []
    base = [u for t, u in U if U and t < U[0][0] + 8]
    if not base or st.mean(base) > 5:
        why.append(f"util-baseline={round(st.mean(base), 2) if base else None}")
    la = st.mean(x[0] for x in L) if L else None
    if not L:
        why.append("no-load-samples")
    else:
        if any(x[1] > 0 for x in L):
            why.append("ci-runner-active")
        lim = S_LOAD_MAX if c["stress"] else Q_LOAD_MAX
        if la > lim:
            why.append(f"load-mean={la:.2f}>{lim}")
        if c["stress"] and min(x[3] for x in L) < c["stress"] and st.median(x[3] for x in L) < c["stress"]:
            why.append("spinners-missing")
        if not c["stress"] and any(x[3] > 0 for x in L):
            why.append("spinners-in-quiet-cell")
    psi = [float(x[2]) for x in L if x[2] not in ("NA", "")]
    per = []
    for r in d["rows"]:
        a, b = r["win_full"]; s = [u for t, u in U if a <= t <= b]
        if len(s) < 10:
            why.append(f"row{r['i']}-samples={len(s)}"); continue
        ms = 1000.0 / r["decode_tok_s"]; bf = st.mean(s) / 100
        per.append((ms, ms * bf, ms * (1 - bf)))
    if not per:
        print(f"cell {cid}: NO-UTIL {why}"); continue
    ms, busy, idle = (st.median(x[k] for x in per) for k in range(3))
    ok = True
    if c["arm"] in ("on", "off"):
        ok = d.get("gpu_route_effective") is (c["arm"] == "on")
    R[cid] = dict(arm=c["arm"], stress=c["stress"], ms=ms, busy=busy, idle=idle, load=la, ok=ok,
                  ids=[r.get("out_ids") for r in d["rows"]], clean=not why)
    print(f"cell {cid}: arm={c['arm']} stress={c['stress']} ms/tok={ms:.2f} busy={busy:.2f} idle={idle:.2f} "
          f"load_mean={la if la is None else round(la, 2)} psi_mean={round(st.mean(psi), 2) if psi else None} "
          f"route_ok={ok} {'CLEAN' if not why else 'EXCLUDED:' + ';'.join(sorted(set(why)))}")


def arm(a, s):
    v = [x for x in R.values() if x["arm"] == a and x["stress"] == s and x["clean"]]
    if not v:
        return None
    return {k: st.mean(x[k] for x in v) for k in ("ms", "busy", "idle", "load")} | {"n": len(v)}


A = {(a, s): arm(a, s) for a in ("hf", "on", "off") for s in (0, 12)}
for k, v in A.items():
    print(f"arm {k[0]} stress={k[1]}: {v}")
manip = all(x["ok"] for x in R.values())
eng = [x["ids"] for x in R.values() if x["arm"] in ("on", "off")]
parity = bool(eng) and all(x == eng[0] for x in eng)
print(f"MANIP gpu_route_effective matches request (all engine cells): {manip}; engine token-id parity across all cells: {parity}")

# SPLIT (quiet): where does the on-vs-hf gap live (exp743 rule, re-run without host contention)
hq, oq = A[("hf", 0)], A[("on", 0)]
if not (hq and oq):
    split = "SPLIT:INCONCLUSIVE"
else:
    gap = oq["ms"] - hq["ms"]; di = oq["idle"] - hq["idle"]; db = oq["busy"] - hq["busy"]
    print(f"GAP on-hf (quiet) = {gap:.2f} = idle {di:.2f} + busy {db:.2f} (idle share {di / gap:.3f})")
    split = "SPLIT:GAP-IS-GPU-IDLE" if di >= 0.5 * gap else ("SPLIT:GAP-IS-GPU-BUSY" if db >= 0.5 * gap else "SPLIT:GAP-MIXED")


def route(s, tag):
    a, b = A[("on", s)], A[("off", s)]
    if not (a and b) or not manip:
        return f"{tag}:INCONCLUSIVE"
    dm = b["ms"] - a["ms"]
    print(f"{tag} off-on = {dm:+.2f} ms/tok (idle {b['idle'] - a['idle']:+.2f}, busy {b['busy'] - a['busy']:+.2f}); "
          f"n on={a['n']} off={b['n']}")
    v = "NO-CHANGE" if abs(dm) < 3 else ("OFF-FASTER" if dm < 0 else "OFF-SLOWER")
    return f"{tag}:{v}" + ("" if parity else "(PARITY-FAIL)")


rq, rs = route(0, "ROUTE-Q"), route(12, "ROUTE-S")

# SENS: relative slowdown under stress, engine (on) vs hf
hs, os_ = A[("hf", 12)], A[("on", 12)]
if not (hq and oq and hs and os_):
    sens = "SENS:INCONCLUSIVE"
else:
    eh, ee = hs["ms"] / hq["ms"] - 1, os_["ms"] / oq["ms"] - 1
    print(f"SENS slowdown under stress: hf {eh:+.3f}, engine(on) {ee:+.3f}; abs ms hf {hs['ms'] - hq['ms']:+.2f}, "
          f"engine {os_['ms'] - oq['ms']:+.2f}")
    if ee >= 0.10 and ee >= 2 * max(eh, 0.0):
        sens = "SENS:ENGINE-MORE-SENSITIVE"
    elif eh >= 0.10 and eh >= 2 * max(ee, 0.0):
        sens = "SENS:HF-MORE-SENSITIVE"
    elif max(ee, eh) < 0.10:
        sens = "SENS:BOTH-INSENSITIVE"
    else:
        sens = "SENS:SIMILAR"
print(f"VERDICT {split}|{rq}|{sens}|{rs}")

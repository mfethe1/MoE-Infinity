#!/usr/bin/env python3
"""exp751 frozen analyzer. Usage: analyze.py OUTDIR. Never edits inputs.
Native-Linux replication on a rented RTX 5060 Ti of exp747 (WSL host-callback stall) and exp746 (engine-vs-HF quiet gap).
Winnie (WSL2) references are the sealed values from exp747 ADDENDUM72 / exp746 ADDENDUM71 and are constants here."""
import json, os, statistics as st, sys

O = sys.argv[1]
cells = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()
WSL_HOSTFN_US, WSL_KSYNC_US = 521.968, 46.344          # exp747 spin=0 level means
WSL_GAP, WSL_IDLE, WSL_ON, WSL_HF = 60.14, 36.95, 94.67, 34.53   # exp746 quiet
Q_LOAD_MAX = 4.0
CGPSI_MAX = 20.0   # AMENDMENT1


def loads(cid):
    p = f"{O}/{cid}.load"; out = []
    if os.path.exists(p):
        for l in open(p):
            f = l.split()
            try:
                out.append((float(f[1]), int(f[4]), float(f[3]) if f[3] != "NA" else None))
            except (ValueError, IndexError):
                pass
    return out


def excl(c):
    cid = c["id"]; why = ["gpu-contamination"] if cid in flag else []
    L = loads(cid)
    if not L:
        return why + ["no-load-samples"], None
    la = st.mean(x[0] for x in L); k = c.get("spin", 0)   # AMENDMENT1: x[0] = container cgroup cores in use (not host loadavg)
    if not k and la > Q_LOAD_MAX:
        why.append(f"cores-mean={la:.2f}>{Q_LOAD_MAX}")
    ps = [x[2] for x in L if x[2] is not None]
    if not k and ps and st.mean(ps) > CGPSI_MAX:
        why.append(f"cgroup-cpu-psi-mean={st.mean(ps):.1f}>{CGPSI_MAX}")
    if k and st.median(x[1] for x in L) < k:
        why.append("spinners-missing")
    if not k and any(x[1] > 0 for x in L):
        why.append("spinners-in-quiet-cell")
    return why, la


MI, EN = {}, {}
for c in cells:
    cid = c["id"]; p = f"{O}/{cid}.json"
    if cid in fail or not os.path.exists(p):
        print(f"cell {cid}: MISSING/FAILED"); continue
    d = json.load(open(p)); why, la = excl(c)
    if c["arm"] == "micro":
        r = d["results"]
        if r["gate_overrun_frac"]["frac_base_gt_50us"] > 0.05:
            why.append("gate-overrun")
        MI[cid] = dict(spin=c["spin"], hs=r["hostfn_stall"]["median_us"], hs90=r["hostfn_stall"]["p90_us"],
                       hs1=r["hostfn_stall"]["frac_gt_1ms"], ks=r["kern_sync"]["median_us"], nt=r["mm_notify"]["median_us"],
                       clean=not why)
        m = MI[cid]
        print(f"cell {cid}: spin={c['spin']} hostfn_stall med={m['hs']:.1f} p90={m['hs90']:.1f} >1ms={m['hs1']:.3f} | kern_sync "
              f"med={m['ks']:.1f} | notify med={m['nt']:.1f} | load_mean={la if la is None else round(la, 2)} "
              f"{'CLEAN' if not why else 'EXCLUDED:' + ';'.join(why)}")
        continue
    U = []
    if os.path.exists(f"{O}/{cid}.util.csv"):
        for l in open(f"{O}/{cid}.util.csv"):
            try:
                t, u, _ = l.strip().split(","); U.append((float(t), float(u)))
            except ValueError:
                pass
    base = [u for t, u in U if U and t < U[0][0] + 8]
    if not base or st.mean(base) > 5:
        why.append(f"util-baseline={round(st.mean(base), 2) if base else None}")
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
    ok = True if c["arm"] == "hf" else d.get("gpu_route_effective") is (c["arm"] == "on")
    EN[cid] = dict(arm=c["arm"], ms=ms, busy=busy, idle=idle, ok=ok, ids=[r.get("out_ids") for r in d["rows"]], clean=not why)
    print(f"cell {cid}: arm={c['arm']} ms/tok={ms:.2f} busy={busy:.2f} idle={idle:.2f} load_mean={la if la is None else round(la, 2)} "
          f"route_ok={ok} {'CLEAN' if not why else 'EXCLUDED:' + ';'.join(sorted(set(why)))}")


def lvl(k):
    v = [x for x in MI.values() if x["spin"] == k and x["clean"]]
    return {q: st.mean(x[q] for x in v) for q in ("hs", "hs90", "hs1", "ks", "nt")} | {"n": len(v)} if v else None


A0, A6 = lvl(0), lvl(6)
print(f"level spin=0: {A0}\nlevel spin=6: {A6}")
if not A0:
    hv = "HOSTFN:INCONCLUSIVE"
else:
    print(f"HOSTFN native/WSL = {A0['hs'] / WSL_HOSTFN_US:.3f} (native {A0['hs']:.1f} us vs WSL {WSL_HOSTFN_US} us); "
          f"kern_sync native/WSL = {A0['ks'] / WSL_KSYNC_US:.3f}; native hostfn/kern_sync = {A0['hs'] / A0['ks']:.2f}")
    print(f"PROJ native: 144 serialized callbacks/token x {A0['hs']:.0f} us = {144 * A0['hs'] / 1000:.1f} ms/token (upper bound)")
    hv = ("HOSTFN:WSL-INFLATED" if A0["hs"] <= 150 else "HOSTFN:NATIVE-ALSO-SLOW" if A0["hs"] >= 350 else "HOSTFN:PARTIAL")


def arm(a):
    v = [x for x in EN.values() if x["arm"] == a and x["clean"]]
    return {q: st.mean(x[q] for x in v) for q in ("ms", "busy", "idle")} | {"n": len(v)} if v else None


H, ON, OFF = arm("hf"), arm("on"), arm("off")
print(f"arm hf: {H}\narm on: {ON}\narm off: {OFF}")
manip = all(x["ok"] for x in EN.values())
eng = [x["ids"] for x in EN.values() if x["arm"] in ("on", "off")]
parity = bool(eng) and all(x == eng[0] for x in eng)
hfids = [x["ids"] for x in EN.values() if x["arm"] == "hf"]
print(f"MANIP gpu_route_effective matches request: {manip}; engine token-id parity across engine cells: {parity}; "
      f"hf token-id parity: {bool(hfids) and all(x == hfids[0] for x in hfids)}")
if not (H and ON):
    gv = "GAP:INCONCLUSIVE"
else:
    gap = ON["ms"] - H["ms"]; di = ON["idle"] - H["idle"]
    print(f"GAP on-hf native = {gap:.2f} ms/tok = idle {di:.2f} + busy {ON['busy'] - H['busy']:.2f} (idle share {di / gap:.3f}); "
          f"WSL gap {WSL_GAP} (idle {WSL_IDLE}); native/WSL gap = {gap / WSL_GAP:.3f}; on/hf ratio native {ON['ms'] / H['ms']:.2f} "
          f"vs WSL {WSL_ON / WSL_HF:.2f}")
    gv = ("GAP:MOSTLY-ENV" if gap <= 0.5 * WSL_GAP else "GAP:PERSISTS-NATIVE" if gap >= 0.8 * WSL_GAP else "GAP:PARTIAL")
if not (ON and OFF) or not manip:
    rv = "ROUTE:INCONCLUSIVE"
else:
    dm = OFF["ms"] - ON["ms"]
    print(f"ROUTE off-on native = {dm:+.2f} ms/tok (idle {OFF['idle'] - ON['idle']:+.2f}, busy {OFF['busy'] - ON['busy']:+.2f})")
    rv = ("ROUTE:NO-CHANGE" if abs(dm) < 3 else "ROUTE:OFF-FASTER" if dm < 0 else "ROUTE:OFF-SLOWER") + ("" if parity else "(PARITY-FAIL)")
print(f"VERDICT {hv}|{gv}|{rv}")

#!/usr/bin/env python3
"""exp743 frozen analyzer. Usage: analyze.py OUTDIR. Never edits inputs.
Per decode window (row win_full) integrates NVML utilization.gpu samples -> GPU-busy fraction, then splits
ms/token into busy_ms (device executing >=1 kernel) and idle_ms (device idle: host-side / launch / sync gaps)."""
import json, os, statistics as st, sys

O = sys.argv[1]
cells = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()


def load_util(cid):
    p = f"{O}/{cid}.util.csv"
    if not os.path.exists(p):
        return []
    out = []
    for l in open(p):
        try:
            t, u, m = l.strip().split(","); out.append((float(t), float(u), float(m)))
        except ValueError:
            pass
    return out


def busy_frac(samples, a, b):
    s = [u for t, u, _ in samples if a <= t <= b]
    return (st.mean(s) / 100.0, len(s)) if s else (None, 0)


R = {}
for c in cells:
    cid = c["id"]; p = f"{O}/{cid}.json"
    if cid in fail or not os.path.exists(p):
        print(f"cell {cid}: MISSING/FAILED"); continue
    d = json.load(open(p)); rows = d["rows"]; U = load_util(cid)
    t_first = min(r["win_full"][0] for r in rows)
    base = [u for t, u, _ in U if t < (U[0][0] + 8 if U else 0)]
    base_u = st.mean(base) if base else None
    why = []
    if cid in flag:
        why.append("contamination")
    if base_u is None or base_u > 5:
        why.append(f"util-baseline={base_u}")
    per = []
    for r in rows:
        bf, n = busy_frac(U, *r["win_full"])
        if bf is None or n < 20:
            why.append(f"row{r['i']}-samples={n}"); continue
        ms = 1000.0 / r["decode_tok_s"]
        per.append((ms, ms * bf, ms * (1 - bf), bf))
    if not per:
        print(f"cell {cid}: NO-UTIL"); continue
    ms, busy, idle, bf = (st.median(x[k] for x in per) for k in range(4))
    grp = sum(r.get("routing_delta", {}).get("grouped_experts", 0) for r in rows)
    R[cid] = dict(arm=c["arm"], threads=c["threads"], ms=ms, busy=busy, idle=idle, bf=bf, clean=not why,
                  grp=grp, thr=d.get("threads_effective"))
    print(f"cell {cid}: arm={c['arm']} t={c['threads']} ms/tok={ms:.2f} busy_ms={busy:.2f} idle_ms={idle:.2f} "
          f"busy_frac={bf:.3f} base_util={base_u} grouped_experts={grp} threads_eff={d.get('threads_effective')} "
          f"{'CLEAN' if not why else 'EXCLUDED:' + ';'.join(why)}")


def arm(f):
    v = [x for x in R.values() if f(x) and x["clean"]]
    if not v:
        return None
    return {k: st.mean(x[k] for x in v) for k in ("ms", "busy", "idle", "bf")} | {"n": len(v)}


hf = arm(lambda x: x["arm"] == "hf")
t4 = arm(lambda x: x["arm"] == "eng" and x["threads"] == 4)
t1 = arm(lambda x: x["arm"] == "eng" and x["threads"] == 1)
gp = arm(lambda x: x["arm"] == "grp")
for n, a in (("hf", hf), ("t4", t4), ("t1", t1), ("grp", gp)):
    print(f"arm {n}: {a}")

ok_thr = all(x["thr"] == x["threads"] for x in R.values() if x["arm"] != "hf")
ok_grp = all(x["grp"] > 0 for x in R.values() if x["arm"] == "grp") and all(
    x["grp"] == 0 for x in R.values() if x["arm"] == "eng")
print(f"MANIP threads_effective==requested: {ok_thr}; grouped engaged only in grp: {ok_grp}")

# Primary: where does the engine-vs-HF gap live?
if not (hf and t4):
    v1 = "SPLIT:INCONCLUSIVE(no clean hf/t4)"
else:
    gap = t4["ms"] - hf["ms"]; d_idle = t4["idle"] - hf["idle"]; d_busy = t4["busy"] - hf["busy"]
    print(f"GAP t4-hf={gap:.2f} ms/tok = idle {d_idle:.2f} + busy {d_busy:.2f} "
          f"(idle share {d_idle / gap:.3f})")
    if d_idle >= 0.5 * gap:
        v1 = "GAP-IS-GPU-IDLE"
    elif d_busy >= 0.5 * gap:
        v1 = "GAP-IS-GPU-BUSY"
    else:
        v1 = "GAP-MIXED"


# Secondary: where did each manipulation's change land? (|delta ms| < 3 => no-change)
def landed(name, a, ok):
    if not (a and t4) or not ok:
        return f"{name}:INCONCLUSIVE"
    dm, di, db = a["ms"] - t4["ms"], a["idle"] - t4["idle"], a["busy"] - t4["busy"]
    print(f"{name} vs t4: d_ms={dm:+.2f} d_idle={di:+.2f} d_busy={db:+.2f}")
    if abs(dm) < 3:
        return f"{name}:NO-CHANGE"
    return f"{name}:{'IDLE' if abs(di) >= abs(db) else 'BUSY'}-{'UP' if dm > 0 else 'DOWN'}"


print(f"VERDICT {v1}|{landed('GRP', gp, ok_grp)}|{landed('T1', t1, ok_thr)}")

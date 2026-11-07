#!/usr/bin/env python3
"""exp752 frozen analyzer. Usage: analyze752.py OUTDIR. Never edits inputs.
Arms: hf (transformers bf16 reference), H / R / RC (patched MoE-Infinity build; MOEI_EXP752_MODE selects retirement path).
Per cell: median over prompts of ms/token and NVML busy/idle split (exp743/746 method). Exclusions as exp746 quiet cells plus
manipulation check (banner 'exp752 mode=N' must match the arm). Load columns (mon752.sh):
  HH:MM:SS loadavg1 runner_workers psi_some_avg10 0 foreign_other_gpu_procs"""
import json, os, re, statistics as st, sys

O = sys.argv[1]
cells = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()
Q_LOAD_MAX = 4.0
MODE = {"H": 0, "R": 1, "RC": 2}
THR = 3.0  # ms/token practical-effect bar


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
                out.append((float(f[1]), int(f[2]), f[3], int(f[5]) if len(f) > 5 and f[5] != "NA" else -1))
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
        if la > Q_LOAD_MAX:
            why.append(f"load-mean={la:.2f}>{Q_LOAD_MAX}")
    fo = max((x[3] for x in L), default=-1)
    manip = True
    if c["arm"] in MODE:
        log = open(f"{O}/{cid}.log", errors="replace").read() if os.path.exists(f"{O}/{cid}.log") else ""
        modes = set(int(m) for m in re.findall(r"exp752 mode=(\d)", log))
        manip = modes == {MODE[c["arm"]]} and d.get("gpu_route_effective") is True
        if not manip:
            why.append(f"manip-fail(modes={sorted(modes)},route={d.get('gpu_route_effective')})")
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
    R[cid] = dict(arm=c["arm"], ms=ms, busy=busy, idle=idle, load=la, foreign=fo, manip=manip,
                  ids=[r.get("out_ids") for r in d["rows"]], clean=not why)
    print(f"cell {cid}: arm={c['arm']} ms/tok={ms:.2f} busy={busy:.2f} idle={idle:.2f} load_mean="
          f"{la if la is None else round(la, 2)} foreign_other_gpu_max={fo} {'CLEAN' if not why else 'EXCLUDED:' + ';'.join(sorted(set(why)))}")


def arm(a):
    v = [x for x in R.values() if x["arm"] == a and x["clean"]]
    if not v:
        return None
    return {k: st.mean(x[k] for x in v) for k in ("ms", "busy", "idle", "load")} | {"n": len(v), "all": sorted(x["ms"] for x in v)}


A = {a: arm(a) for a in ("hf", "H", "R", "RC")}
for k, v in A.items():
    print(f"arm {k}: {v}")

# PARITY: greedy token ids must match the H arm. Control: H cells must agree with each other first.
ids = {a: [x["ids"] for x in R.values() if x["arm"] == a and x["manip"]] for a in ("H", "R", "RC")}  # all manip-valid cells, clean or not
h_ok = len(ids["H"]) >= 2 and all(x == ids["H"][0] for x in ids["H"])
par = {}
for a in ("R", "RC"):
    if not h_ok or not ids[a]:
        par[a] = "NA"
    else:
        par[a] = "OK" if all(x == ids["H"][0] for x in ids[a]) else "FAIL"
print(f"PARITY H-self-consistent={h_ok} R={par['R']} RC={par['RC']}")


def cmp(new, ref, tag):
    a, b = A[new], A[ref]
    if not (a and b) or a["n"] < 2 or b["n"] < 2:
        return f"{tag}:INCONCLUSIVE(n)"
    if par.get(new) == "FAIL":
        return f"{tag}:UNSAFE(PARITY-FAIL)"
    dm = a["ms"] - b["ms"]
    sep_fast = max(a["all"]) < min(b["all"]); sep_slow = min(a["all"]) > max(b["all"])
    print(f"{tag} {new}-{ref} = {dm:+.2f} ms/tok (idle {a['idle'] - b['idle']:+.2f}, busy {a['busy'] - b['busy']:+.2f}); "
          f"n {new}={a['n']} {ref}={b['n']}; separated_fast={sep_fast} separated_slow={sep_slow}")
    if abs(dm) < THR:
        v = "NO-CHANGE"
    elif dm <= -THR and sep_fast:
        v = "FASTER"
    elif dm >= THR and sep_slow:
        v = "SLOWER"
    else:
        v = "MIXED"
    return f"{tag}:{v}" + ("" if par.get(new) == "OK" else "(PARITY-NA)")


rv = cmp("R", "H", "RETIRE")
cv = cmp("RC", "R", "COMPL")
tv = cmp("RC", "H", "TOTAL")
if A["hf"] and A["H"]:
    gap = A["H"]["ms"] - A["hf"]["ms"]
    best = min((A[x]["ms"] for x in ("R", "RC") if A[x]), default=A["H"]["ms"])
    print(f"GAP H-hf = {gap:.2f} ms/tok; best patched arm closes {(A['H']['ms'] - best) / gap:.3f} of it (descriptive)")
fos = {x["foreign"] for x in R.values() if x["clean"]}
print(f"COVARIATE foreign_other_gpu_max across clean cells: {sorted(fos)}"
      + ("" if len(fos) <= 1 else " -> SENSITIVITY REQUIRED (see PREREG)"))
print(f"VERDICT {rv}|{cv}|{tv}")

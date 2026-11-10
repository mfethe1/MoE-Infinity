#!/usr/bin/env python3
"""exp759 frozen analyzer. Usage: analyze759.py OUTDIR. Never edits inputs.
Arms: hf (transformers bf16 reference), H (sealed exp752 build, MOEI_EXP752_MODE=H), RC (OUR PR #353 head b7f6ca4
fresh build, MOEI_EXP752_MODE=RC), P34 (upstream PR #354 head 827019db, MOEI_EXP752_MODE unset; banner ABSENT).
Per cell: median over prompts of ms/token and NVML busy/idle split (exp743/746 method). Exclusions as exp746/756
quiet cells. Parity computed on clean cells: every clean engine cell's out_ids must equal the sealed refs
(refs/RC_2.json, refs/RC_3.json) AND refs/H_2.json (all engine arms decode byte-identically). Any divergence =
PARITY-FAIL, no admitted timing claims.
Load columns (mon752.sh): HH:MM:SS loadavg1 runner_workers psi_some_avg10 0 foreign_other_gpu_procs"""
import json, os, re, statistics as st, sys

O = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
cells = json.load(open(os.path.join(HERE, "cells759.json")))
flag = set(open(f"{O}/FLAGGED").read().split()) if os.path.exists(f"{O}/FLAGGED") else set()
fail = {l.split()[0] for l in open(f"{O}/FAILED")} if os.path.exists(f"{O}/FAILED") else set()
Q_LOAD_MAX = 4.0
MODE = {"H": 0, "RC": 2}  # banner enum; P34 must print NO banner
THR = 3.0       # primary equivalence bar (exp752 continuity)
REPL_BAR = -4.10  # secondary: arm - H must be <= this to count as replicated in-envelope (0.5x sealed -8.20)
DRIFT_H = 4.0   # fresh H vs sealed 93.903 gates the envelope
SEAL_RC_TOL = 3.0
# Frozen sealed references (exp752 quiet-only clean medians; PREREG.md)
SEAL = {"H": 93.903, "RC": 85.699, "hf": 31.791, "P34": 83.750}  # P34 = exp756 fresh measurement (not a seal)


def refs_ids():
    """Canonical sealed out_ids; refs must agree with each other or the freeze itself is inconsistent."""
    ids = {}
    for r in ("RC_2", "RC_3", "H_2", "H_3"):
        p = os.path.join(HERE, "refs", r + ".json")
        v = out_ids_of(p)
        if v is None:
            return None, f"ref {r} invalid/missing"
        ids[r] = v
    canon = ids["RC_2"]
    for r, v in ids.items():
        if v != canon:
            return None, f"refs disagree: {r} != RC_2"
    return canon, None


def verdict(par_ok, env_ok, n_h, n_rc, n_p34, d, rc_h, p34_h, h_ms, rc_ms, p34_ms):
    """Frozen verdict rule (PREREG.md; comparisons rounded to 3 dp before bars).
    d = P34 - RC (medians of clean). Precedence: PARITY-FAIL > INCONCLUSIVE(n) > bars."""
    if not par_ok:
        return "PARITY-FAIL"
    if n_h < 2 or n_rc < 2 or n_p34 < 2:
        return "INCONCLUSIVE(n)"
    d, rc_h, p34_h = round(d, 3), round(rc_h, 3), round(p34_h, 3)
    if abs(d) <= THR:
        prim = "HEAD-TO-HEAD-EQUIVALENT"
    elif d > THR:
        prim = "P34-FASTER"
    else:
        prim = "RC-FASTER"
    sec = []
    sec.append(("RC-REPLICATED-IN-ENVELOPE" if rc_h <= REPL_BAR else "RC-NOT-REPLICATED") + f"[RC-H={rc_h:.2f}]")
    sec.append(("P34-REPLICATED-IN-ENVELOPE" if p34_h <= REPL_BAR else "P34-NOT-REPLICATED") + f"[P34-H={p34_h:.2f}]")
    seal = []
    for nm, v, s in (("H", h_ms, SEAL["H"]), ("RC", rc_ms, SEAL["RC"]), ("P34", p34_ms, SEAL["RC"])):
        mark = "ok" if abs(v - s) <= (DRIFT_H if nm == "H" else SEAL_RC_TOL) else "MISS"
        seal.append(f"{nm}={round(v,2)} vs seal {s} [{mark}]")
    out = f"{prim} d(P34-RC)={d:.3f} THR={THR} | " + " ".join(sec) + " | " + " ".join(seal)
    if not env_ok:
        out += " | ENV-DRIFT (timing labels descriptive)"
    return out


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


def out_ids_of(path):
    d = json.load(open(path))
    ids = [r.get("out_ids") for r in d["rows"]]
    if len(ids) != 6 or any(not isinstance(x, list) or not x for x in ids):
        return None  # invalid/missing out_ids fail closed
    return ids


canon, ref_err = refs_ids()
if canon is None:
    print(f"FREEZE-ERROR: {ref_err}"); sys.exit(3)

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
    log = open(f"{O}/{cid}.log", errors="replace").read() if os.path.exists(f"{O}/{cid}.log") else ""
    modes = set(int(m) for m in re.findall(r"exp752 mode=(\d)", log))
    if c["arm"] in MODE:
        manip = modes == {MODE[c["arm"]]} and d.get("gpu_route_effective") is True
        if not manip:
            why.append(f"manip-fail(modes={sorted(modes)},route={d.get('gpu_route_effective')})")
    elif c["arm"] == "P34":
        manip = modes == set() and d.get("gpu_route_effective") is True
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
                  ids=(out_ids_of(p) if os.path.exists(p) else None), clean=not why)
    print(f"cell {cid}: arm={c['arm']} ms/tok={ms:.2f} busy={busy:.2f} idle={idle:.2f} load_mean="
          f"{la if la is None else round(la, 2)} foreign_other_gpu_max={fo} {'CLEAN' if not why else 'EXCLUDED:' + ';'.join(sorted(set(why)))}")


def arm(a):
    v = [x for x in R.values() if x["arm"] == a and x["clean"]]
    if not v:
        return None, 0
    return st.median(x["ms"] for x in v), len(v)


h_ms, n_h = arm("H")
rc_ms, n_rc = arm("RC")
p34_ms, n_p34 = arm("P34")
hf_ms, n_hf = arm("hf")

# parity: every clean engine cell must byte-match the canonical sealed refs
diverge = []
for cid, x in sorted(R.items()):
    if x["arm"] in ("H", "RC", "P34") and x["clean"] and x["ids"] != canon:
        bad = [i for i in range(6) if x["ids"][i] != canon[i]]
        diverge.append(f"{cid}(arm={x['arm']},rows={bad})")
par_ok = not diverge
print(f"\nparity: {'OK all engine clean cells byte-identical to sealed refs' if par_ok else 'DIVERGED ' + '; '.join(diverge)}")
for nm, v, n in (("H", h_ms, n_h), ("RC", rc_ms, n_rc), ("P34", p34_ms, n_p34), ("hf", hf_ms, n_hf)):
    print(f"arm {nm}: median={None if v is None else round(v, 3)} clean n={n}")
if n_hf:
    print(f"drift hf: {round(hf_ms, 2)} vs seal {SEAL['hf']} [{ 'ok' if abs(hf_ms - SEAL['hf']) <= 3.0 else 'MISS' }] (informational n={n_hf})")
if None not in (h_ms, rc_ms, p34_ms):
    env_ok = abs(h_ms - SEAL["H"]) <= DRIFT_H
    v = verdict(par_ok, env_ok, n_h, n_rc, n_p34, p34_ms - rc_ms, rc_ms - h_ms, p34_ms - h_ms, h_ms, rc_ms, p34_ms)
    print(f"\nVERDICT {v}")
else:
    print(f"\nVERDICT INCONCLUSIVE(arms) H={h_ms} RC={rc_ms} P34={p34_ms}")

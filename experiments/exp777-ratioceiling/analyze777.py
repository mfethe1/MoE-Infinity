#!/usr/bin/env python3
"""exp777 analyzer: residency-ratio wall ceiling.

4 cells on src776 shipped path (PR #358 behavior): r in {0.75, 0.90, 0.975,
1.0}. r=0.75 covariate gate vs exp775 DB ref 182.66 +/- 25% -> [137.00,
228.33]. r* = max r with RC=0 (from CELL_RC.txt; cells may fail e.g. OOM at
r=1.0 — recorded, not fatal unless no r>0.75 runs).

Headroom = (W(0.75) - W(r*)) / W(0.75).

rc map:
  9 IDENTIFY-FAIL  src/env/markers/sha mismatch
  4 DATA-FAIL      BADIO, covariate gate fail, or no feasible r > 0.75
  1 LARGE-HEADROOM headroom >= 0.10
  2 MILD-HEADROOM  0.03 <= headroom < 0.10
  7 NO-HEADROOM    headroom < 0.03
Report-only: per-cell W/tok-per-s, monotonicity of W across r.
"""
import json, os, sys

REF = 182.66
TOL = 0.25
H1 = 0.10
H2 = 0.03
CELLS = [("PY_R075", "0.75"), ("PY_R090", "0.90"), ("PY_R0975", "0.975"), ("PY_R100", "1.0")]

def cellW(d, cid):
    p = os.path.join(d, "out", cid + ".json")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return None, None
    res = json.load(open(p))
    rr = res.get("rows") or res.get("results") or []
    if len(rr) < 20:
        return None, None
    W = sum(r["t_1tok_s"] + r["t_full_s"] for r in rr)
    tok = sum(r.get("n_new", 0) for r in rr) or None
    return W, (tok / W if tok else None)

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    env = open(os.path.join(out, "ENV.txt"), errors="replace").read() if os.path.exists(os.path.join(out, "ENV.txt")) else ""
    badio = open(os.path.join(out, "BADIO"), errors="replace").read().strip() if os.path.exists(os.path.join(out, "BADIO")) else ""
    rcs = {}
    rcp = os.path.join(out, "CELL_RC.txt")
    if os.path.exists(rcp):
        for ln in open(rcp, errors="replace"):
            parts = ln.split()
            if len(parts) >= 2 and "RC=" in ln:
                rcpart = [q for q in parts if q.startswith("RC=")][0]
                rcs[parts[0]] = int(rcpart[3:])
    sha = open(os.path.join(out, "SRC776_FILE_SHA.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC776_FILE_SHA.txt")) else ""
    L = ["exp777 residency-ratio wall ceiling (src776 shipped path)"]
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict777.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith("b7f6ca4") or "moei-776 /home/mfeth/exp776/src776" not in env or sha != "3571f714c811e1c7":
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r} sha={sha!r})"); return fin(9)
    if badio:
        L.append(f"DATA-FAIL BADIO non-empty: {badio[:80]}"); return fin(4)
    Ws = {}
    for cid, r in CELLS:
        W, tps = cellW(d, cid)
        Ws[cid] = W
        L.append(f"{cid} (r={r}): RC={rcs.get(cid,'?')} W={'MISSING' if W is None else f'{W:.2f}'}" + (f" tok/s={tps:.3f}" if tps else ""))
    if rcs.get("PY_R075") != 0 or Ws["PY_R075"] is None:
        L.append("DATA-FAIL: reference cell PY_R075 not clean"); return fin(4)
    wref = Ws["PY_R075"]
    lo, hi = REF * (1 - TOL), REF * (1 + TOL)
    L.append(f"covariate: W(R075)={wref:.2f} vs gate [{lo:.2f}, {hi:.2f}] (exp775 DB ref {REF} +/-25%)")
    if not (lo <= wref <= hi):
        L.append("DATA-FAIL: reference cell outside covariate gate"); return fin(4)
    feas = [(float(r), cid) for cid, r in CELLS if float(r) > 0.75 and rcs.get(cid) == 0 and Ws[cid] is not None]
    if not feas:
        L.append("DATA-FAIL: no feasible cell with r > 0.75"); return fin(4)
    rstar, cid = max(feas)
    head = (wref - Ws[cid]) / wref
    L.append(f"r* = {rstar} ({cid}); headroom = (W075 - W(r*)) / W075 = {head:+.4f}")
    seq = [(float(r), Ws[c]) for c, r in CELLS if Ws[c] is not None]
    mono = all(seq[i][1] >= seq[i + 1][1] for i in range(len(seq) - 1))
    L.append(f"monotone non-increasing W over r: {'yes' if mono else 'no'} (report-only)")
    if head >= H1:
        L.append(f"LARGE-HEADROOM: residency budget costs >=10% of decode wall — policy/budget lane has real room; successor exp778: attribute miss stalls (store instrumentation) and tune budget/policy"); return fin(1)
    if head >= H2:
        L.append(f"MILD-HEADROOM: residency budget costs {head:.1%} — bounded small; policy upside capped near this value"); return fin(2)
    L.append(f"NO-HEADROOM: residency budget costs <3% of decode wall — policy lane CLOSED; residual lives outside expert residency"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""exp779 analyzer: generation-loop overhead behavioral test.

Arms on src776 shipped path, identical flags/workload (24 prompts x 64 tok):
  PY_A engine_arm776.py  (HF generate baseline)     covariate gate vs
       exp775 DB ref 182.66 +/- 25% -> [137.00, 228.33]
  PY_B engine_arm779b.py (manual greedy + DynamicCache)
delta = (W_A - W_B) / W_A.

rc map:
  9 IDENTIFY-FAIL  src/env/src776-sha/engineB-sha mismatch
  4 DATA-FAIL      BADIO, A dirty/outside gate, B nonzero RC or missing
  1 LARGE-MOVE     delta >= 0.15  -> generation-loop overhead is real Python
                   cost; successor: productize manual/static decode path
  2 MILD-MOVE      0.05 <= delta < 0.15
  7 NO-MOVE        delta < 0.05   -> GENLOOP share was GPU-wait in disguise;
                   decode compute/attention-bound; lane redirects to ATTN
Report-only: out_sha agreement rate A vs B (greedy; kernel-shape changes may
diverge some tokens — not a gate), tok/s per arm, n_new check.
"""
import json, os, sys

REF = 182.66
TOL = 0.25
D1 = 0.15
D2 = 0.05

def loadW(d, cid):
    p = os.path.join(d, "out", cid + ".json")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return None, None
    res = json.load(open(p))
    rr = res.get("rows") or []
    if len(rr) < 20:
        return None, res
    W = sum(r["t_1tok_s"] + r["t_full_s"] for r in rr)
    return W, res

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    def rd(n):
        p = os.path.join(out, n)
        return open(p, errors="replace").read().strip() if os.path.exists(p) else ""
    src = rd("SRC_HEAD.txt"); env = rd("ENV.txt"); sha = rd("SRC776_FILE_SHA.txt"); engb = rd("ENGB_SHA.txt")
    badio = rd("BADIO")
    rcs = {}
    for ln in rd("CELL_RC.txt").splitlines():
        parts = ln.split()
        if len(parts) >= 2 and "RC=" in ln:
            rcpart = [q for q in parts if q.startswith("RC=")][0]
            rcs[parts[0]] = int(rcpart[3:])
    L = ["exp779 generation-loop overhead (A=HF generate, B=manual DynamicCache)"]
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict779.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith("b7f6ca4") or "moei-776 /home/mfeth/exp776/src776" not in env or sha != "3571f714c811e1c7" or not engb:
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r} sha={sha!r} engb={engb!r})"); return fin(9)
    if badio:
        L.append(f"DATA-FAIL BADIO non-empty: {badio[:80]}"); return fin(4)
    Wa, ra = loadW(d, "PY_A")
    Wb, rb = loadW(d, "PY_B")
    L.append(f"PY_A RC={rcs.get('PY_A','?')} W={'MISSING' if Wa is None else f'{Wa:.2f}'}")
    L.append(f"PY_B RC={rcs.get('PY_B','?')} W={'MISSING' if Wb is None else f'{Wb:.2f}'} arm={rb.get('arm') if rb else '?'}")
    if rcs.get("PY_A") != 0 or Wa is None:
        L.append("DATA-FAIL: baseline arm A not clean"); return fin(4)
    lo, hi = REF * (1 - TOL), REF * (1 + TOL)
    L.append(f"covariate: W(A)={Wa:.2f} vs gate [{lo:.2f}, {hi:.2f}] (exp775 DB ref {REF} +/-25%)")
    if not (lo <= Wa <= hi):
        L.append("DATA-FAIL: arm A outside covariate gate"); return fin(4)
    if rcs.get("PY_B") != 0 or Wb is None:
        L.append(f"DATA-FAIL: arm B not clean (rc={rcs.get('PY_B')})"); return fin(4)
    if rb.get("arm") != "B-manual-dynamic":
        L.append("IDENTIFY-FAIL: PY_B json is not arm B"); return fin(9)
    nnew_ok = all(r.get("n_new") == 64 for r in rb.get("rows", []))
    L.append(f"B n_new==64 all rows: {'yes' if nnew_ok else 'NO'}")
    if not nnew_ok:
        L.append("DATA-FAIL: B rows malformed length"); return fin(4)
    delta = (Wa - Wb) / Wa
    L.append(f"delta = (W_A - W_B)/W_A = {delta:+.4f}")
    try:
        shas_a = [r["out_sha"] for r in ra["rows"]]
        shas_b = [r["out_sha"] for r in rb["rows"]]
        agree = sum(1 for x, y in zip(shas_a, shas_b) if x == y)
        L.append(f"out_sha agreement A/B: {agree}/{len(shas_a)} (report-only)")
    except Exception as e:
        L.append(f"out_sha agreement unavailable: {e!r} (report-only)")
    tpsA = sum(r["n_new"] for r in ra["rows"]) / Wa
    tpsB = sum(r["n_new"] for r in rb["rows"]) / Wb
    L.append(f"tok/s A={tpsA:.3f} B={tpsB:.3f}")
    if delta >= D1:
        L.append(f"LARGE-MOVE: removing generate machinery saves >=15% decode wall — overhead is real Python cost; successor: manual/static decode path productization (then StaticCache step)"); return fin(1)
    if delta >= D2:
        L.append(f"MILD-MOVE: {delta:.1%} saved — machinery cost modest; static-cache follow-up may add more"); return fin(2)
    L.append("NO-MOVE: <5% wall change — GENLOOP 52% was GPU-wait under Python frames; decode is compute/attention-bound; redirect lane to ATTN"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

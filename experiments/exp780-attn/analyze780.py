#!/usr/bin/env python3
"""exp780 analyzer: attention-implementation wall test (sdpa vs eager).

Both arms: manual-loop decode (engine_arm780.py), identical envelope.
  PY_SDPA  --attn-impl sdpa ; PY_EAGER --attn-impl eager
  gain = (W_eager - W_sdpa) / W_eager   (wall saved by fused sdpa vs eager)

rc map (frozen in PREREG-780):
  9 IDENTIFY-FAIL   env/src/sha mismatch; attn_ok false or attn_impl field
                   wrong in either cell json; impl banner missing
  4 DATA-FAIL       BADIO non-empty; either cell RC!=0/missing/<20 rows;
                   SDPA arm outside covariate gate [142.50, 237.50]
                   (exp779 manual-loop ref W=190.00 +/-25%); n_new!=64
  1 KERNEL-MATTERS  gain >= 0.10   -> attention kernel is a real lever;
                   successor: FA2 / compiled attention path
  2 MILD            0.03 <= gain < 0.10
  7 NO-KERNEL-GAIN  gain < 0.03    -> attention is irreducible math at this
                   context length; redirect lane
  3 SDPA-REGRESSION gain <= -0.03  (eager faster): default impl is wrong;
                   successor: recommend/PR eager default for this envelope
  5 SDPA-REGRESSION-LARGE gain <= -0.10
Report-only: attn_default sets, out_sha agreement, tok/s.
"""
import json, os, sys

REF = 190.00
TOL = 0.25
G1, G2, GR = 0.10, 0.03, -0.03

def loadW(d, cid, impl):
    p = os.path.join(d, "out", cid + ".json")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return None, None
    res = json.load(open(p))
    rr = res.get("rows") or []
    if len(rr) < 20 or res.get("attn_impl") != impl or not res.get("attn_ok"):
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
    badio = rd("BADIO"); banner = rd("BANNER-FAIL")
    rcs = {}
    for ln in rd("CELL_RC.txt").splitlines():
        parts = ln.split()
        if len(parts) >= 2 and "RC=" in ln:
            rcpart = [q for q in parts if q.startswith("RC=")][0]
            rcs[parts[0]] = int(rcpart[3:])
    L = ["exp780 attention-implementation wall test (manual-loop decode, sdpa vs eager)"]
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict780.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith("b7f6ca4") or "moei-776 /home/mfeth/exp776/src776" not in env or sha != "3571f714c811e1c7" or not engb:
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r} sha={sha!r} engb={engb!r})"); return fin(9)
    if banner:
        L.append(f"IDENTIFY-FAIL banner: {banner[:80]}"); return fin(9)
    if badio:
        L.append(f"DATA-FAIL BADIO non-empty: {badio[:80]}"); return fin(4)
    Ws, rs = loadW(d, "PY_SDPA", "sdpa")
    We, re_ = loadW(d, "PY_EAGER", "eager")
    L.append(f"PY_SDPA RC={rcs.get('PY_SDPA','?')} W={'MISSING' if Ws is None else f'{Ws:.2f}'} default={rs.get('attn_default') if rs else '?'}")
    L.append(f"PY_EAGER RC={rcs.get('PY_EAGER','?')} W={'MISSING' if We is None else f'{We:.2f}'} default={re_.get('attn_default') if re_ else '?'}")
    if rcs.get("PY_SDPA") != 0 or Ws is None:
        L.append("DATA-FAIL: sdpa arm not clean/verified"); return fin(4)
    if rcs.get("PY_EAGER") != 0 or We is None:
        L.append("DATA-FAIL: eager arm not clean/verified"); return fin(4)
    lo, hi = REF * (1 - TOL), REF * (1 + TOL)
    L.append(f"covariate: W(sdpa)={Ws:.2f} vs gate [{lo:.2f}, {hi:.2f}] (exp779 manual-loop ref {REF} +/-25%)")
    if not (lo <= Ws <= hi):
        L.append("DATA-FAIL: sdpa arm outside covariate gate"); return fin(4)
    for nm, r in (("sdpa", rs), ("eager", re_)):
        if not all(x.get("n_new") == 64 for x in r.get("rows", [])):
            L.append(f"DATA-FAIL: {nm} rows n_new!=64"); return fin(4)
    gain = (We - Ws) / We
    L.append(f"gain = (W_eager - W_sdpa)/W_eager = {gain:+.4f}")
    try:
        sa = [r["out_sha"] for r in rs["rows"]]; sb = [r["out_sha"] for r in re_["rows"]]
        agree = sum(1 for x, y in zip(sa, sb) if x == y)
        L.append(f"out_sha agreement sdpa/eager: {agree}/{len(sa)} (report-only)")
    except Exception as e:
        L.append(f"out_sha agreement unavailable: {e!r} (report-only)")
    tpsS = sum(r["n_new"] for r in rs["rows"]) / Ws
    tpsE = sum(r["n_new"] for r in re_["rows"]) / We
    L.append(f"tok/s sdpa={tpsS:.3f} eager={tpsE:.3f}")
    if gain >= G1:
        L.append("KERNEL-MATTERS: fused sdpa saves >=10% wall vs eager — attention kernel is a real lever; successor: FA2/compiled attention"); return fin(1)
    if gain >= G2:
        L.append(f"MILD: sdpa saves {gain:.1%} vs eager; kernel headroom modest at this context length"); return fin(2)
    if gain <= -0.10:
        L.append("SDPA-REGRESSION-LARGE: eager >=10% faster than sdpa — default impl is wrong for this envelope; recommend eager"); return fin(5)
    if gain <= GR:
        L.append("SDPA-REGRESSION: eager faster than sdpa — default impl is wrong for this envelope; recommend eager"); return fin(3)
    L.append("NO-KERNEL-GAIN: <3% between sdpa and eager — attention is irreducible math at this context length; redirect"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

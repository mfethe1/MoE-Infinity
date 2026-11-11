#!/usr/bin/env python3
"""exp776 analyzer: routed-expert persistence vs heuristic coverage.

ONE cell (PY_DBL) on src776: async-dbuf config with per-call logging of
  {"t", "ts", "topk": heuristic list(k), "routed": actually-routed set}.

Questions (frozen):
  Q1  routed-set size distribution (mean |R|)
  Q2  persistence: P = |R_t & R_{t+1}| / |R_{t+1}|   (prev-routed predictor)
  Q3  heuristic vs TRUE need: H = |L_t & R_{t+1}| / |R_{t+1}|
  Q4  lift = P - H; ceiling context k/mean|R|
Pairs spanning >1.0 s call gaps (prompt boundaries) excluded.

rc map:
  9 IDENTIFY-FAIL  src/marker/env mismatch
  4 DATA-FAIL      missing/short logs (<200 valid pairs), BADIO, empty routed
  1 PREDICTIVE-LIFT  lift >= 0.15 AND P >= 0.40
  2 MILD-LIFT         lift >= 0.05 (and not rc=1)
  7 NO-LIFT           else
"""
import json, os, sys

GAP = 1.0
PAIRS_MIN = 200
LIFT1 = 0.15
PERSIST1 = 0.40
LIFT2 = 0.05

def load(d):
    p = os.path.join(d, "out", "PY_DBL.rl.jsonl")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return None
    calls = []
    for ln in open(p, errors="replace"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            j = json.loads(ln)
        except ValueError:
            continue
        r = j.get("routed")
        t = j.get("topk")
        if isinstance(r, list) and r and isinstance(t, list) and t:
            calls.append((float(j.get("ts", 0.0)), set(int(x) for x in r), set(int(x) for x in t)))
    return calls

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    env = open(os.path.join(out, "ENV.txt"), errors="replace").read() if os.path.exists(os.path.join(out, "ENV.txt")) else ""
    badio = open(os.path.join(out, "BADIO"), errors="replace").read().strip() if os.path.exists(os.path.join(out, "BADIO")) else ""
    rows = None
    rp = os.path.join(out, "PY_DBL.json")
    if os.path.exists(rp) and os.path.getsize(rp) > 0:
        res = json.load(open(rp))
        rr = res.get("rows") or res.get("results") or []
        if len(rr) >= 20:
            rows = sum(r["t_1tok_s"] + r["t_full_s"] for r in rr)
    calls = load(d)
    L = ["exp776 routed-expert persistence vs heuristic coverage"]
    L.append(f"W(info-only, logging syncs) = {rows:.2f}s" if rows else "W: rows MISSING")
    L.append(f"rl.jsonl: {'MISSING' if calls is None else str(len(calls)) + ' calls'}")
    if badio:
        L.append(f"BADIO non-empty: {badio[:80]}")
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict776.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith("b7f6ca4") or "moei-776 /home/mfeth/exp776/src776/moe_infinity/__init__.py" not in env:
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r}, moei-776={'yes' if 'moei-776' in env else 'no'})"); return fin(9)
    if calls is None or badio or rows is None:
        L.append("DATA-FAIL"); return fin(4)
    sizes = [len(c[1]) for c in calls]
    meanR = sum(sizes) / len(sizes)
    ks = [len(c[2]) for c in calls]
    meanK = sum(ks) / len(ks)
    P = H = 0.0
    n = 0
    for i in range(len(calls) - 1):
        if calls[i + 1][0] - calls[i][0] > GAP:
            continue
        Rt, Rt1, Lt = calls[i][1], calls[i + 1][1], calls[i][2]
        P += len(Rt & Rt1) / len(Rt1)
        H += len(Lt & Rt1) / len(Rt1)
        n += 1
    L += [
        f"Q1 mean|R| = {meanR:.1f} distinct experts/call (min {min(sizes)}, max {max(sizes)}); heuristic k = {meanK:.1f}; ceiling k/|R| = {meanK/meanR:.3f}",
    ]
    if n < PAIRS_MIN:
        L.append(f"DATA-FAIL: valid pairs {n} < {PAIRS_MIN}"); return fin(4)
    P /= n; H /= n
    lift = P - H
    L += [
        f"Q2 routed persistence P = |R_t & R_t+1|/|R_t+1| = {P:.4f} over {n} pairs",
        f"Q3 heuristic vs true need H = |L_t & R_t+1|/|R_t+1| = {H:.4f}",
        f"Q4 lift = P - H = {lift:+.4f}",
    ]
    if lift >= LIFT1 and P >= PERSIST1:
        L.append(f"PREDICTIVE-LIFT: prev-routed set predicts next need ({P:.0%} persistence, lift {lift:+.2%}) — recency is a strong predictor; explains LGC>SPC; successor exp777: routed-set retention policy / prefetch-from-routed (armed async like PR #358)"); return fin(1)
    if lift >= LIFT2:
        L.append(f"MILD-LIFT: persistence {P:.0%}, lift {lift:+.2%} — prediction helps some; quantify against prefetch cost before intervening"); return fin(2)
    L.append(f"NO-LIFT: routing churns too fast for prev-routed prediction (persistence {P:.0%}, lift {lift:+.2%}) — no predictor of this class helps; prefetch-on-use/recency remains the best available class"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

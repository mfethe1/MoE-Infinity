#!/usr/bin/env python3
"""analyze776b.py — same-layer persistence re-analysis of exp776's sealed logs.

exp776 paired ADJACENT log lines; the prefetcher is a single instance fed by
all MoE layers in order, so adjacent lines are CROSS-LAYER pairs. Structure
probe (pre-freeze, frozen facts): calls are period-K; K=15 (20175 = 15 x 1345
exactly; lag-15 overlap 0.1724 vs ~0.016 at all other lags). Same-layer
next-step pair = (i, i+15).

Frozen metrics (same sealed rl.jsonl, sha16 recorded in FREEZE-776B):
  P_same = |R_i & R_{i+15}| / |R_{i+15}|   (span guard ts_{i+15}-ts_i <= 2.0 s)
  H_same = |L_i & R_{i+15}| / |R_{i+15}|   (heuristic same layer prev step)
  P_lag1 = adjacent-line overlap (exp776's published statistic, re-derived)
Random baselines: 1/64 = 0.015625 (P), 2/64 = 0.03125 (H, k=2).
Report-only: lag scan 1..24; per-position marginal skew.

rc map:
  9 IDENTIFY-FAIL   input sha mismatch / unparseable
  4 DATA-FAIL       < 2000 same-layer pairs
  1 REOPENED        P_same >= 0.40  (routed-set prediction viable; exp776
                    mechanism claim RETRACTED; successor intervention)
  2 WEAK-MEMORY     0.06 <= P_same < 0.40 (memory exists, class stays dead;
                    exp776 'memoryless' claim corrected; NO-LIFT verdict stands)
  7 CONFIRMED       P_same < 0.06 (memoryless holds at same-layer pairing too)
"""
import hashlib, json, os, sys

PERIOD = 15
SPAN = 2.0
PAIRS_MIN = 2000
U = 64
RAND_P = 1.0 / U
P_REOPEN = 0.40
P_WEAK = 0.06

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    expect = sys.argv[3] if len(sys.argv) > 3 else ""
    os.makedirs(vdir, exist_ok=True)
    p = os.path.join(d, "out", "PY_DBL.rl.jsonl")
    raw = open(p, "rb").read()
    sha16 = hashlib.sha256(raw).hexdigest()[:16]
    calls = []
    for ln in raw.decode(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            j = json.loads(ln)
        except ValueError:
            continue
        r, t = j.get("routed"), j.get("topk")
        if isinstance(r, list) and r and isinstance(t, list) and t:
            calls.append((float(j.get("ts", 0.0)), set(int(x) for x in r), set(int(x) for x in t)))
    L = ["exp776b same-layer (period-15) persistence re-analysis"]
    L.append(f"input rl.jsonl sha16 = {sha16}" + (f" (expected {expect})" if expect else ""))
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict776b.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if expect and sha16 != expect:
        L.append("IDENTIFY-FAIL: sealed input sha mismatch"); return fin(9)
    if not calls or len(calls) % PERIOD != 0:
        L.append(f"IDENTIFY-FAIL: {len(calls)} calls not period-{PERIOD}-divisible"); return fin(9)
    n = len(calls)
    P = H = 0.0; m = 0
    for i in range(n - PERIOD):
        if calls[i + PERIOD][0] - calls[i][0] > SPAN:
            continue
        R, Rn, Lp = calls[i][1], calls[i + PERIOD][1], calls[i][2]
        P += len(R & Rn) / len(Rn)
        H += len(Lp & Rn) / len(Rn)
        m += 1
    Pl1 = 0.0; m1 = 0
    for i in range(n - 1):
        if calls[i + 1][0] - calls[i][0] > SPAN:
            continue
        Pl1 += len(calls[i][1] & calls[i + 1][1]) / len(calls[i + 1][1]); m1 += 1
    L.append(f"calls={n} ({n//PERIOD} steps x {PERIOD} positions)")
    if m < PAIRS_MIN or m1 < PAIRS_MIN:
        L.append(f"DATA-FAIL: same-layer pairs {m}, adjacent pairs {m1}"); return fin(4)
    P /= m; H /= m; Pl1 /= m1
    L += [
        f"P_same(lag-15) = {P:.4f} over {m} same-layer pairs  [random {RAND_P:.4f}]",
        f"H_same topk2->same-layer-next = {H:.4f}  [random {2*RAND_P:.4f}]",
        f"P_lag1 (exp776 published, cross-layer) = {Pl1:.4f} over {m1} pairs",
        f"same-layer vs adjacent lift = {P-Pl1:+.4f}; P_same/random = {P/RAND_P:.1f}x",
    ]
    if P >= P_REOPEN:
        L.append("REOPENED: same-layer persistence supports routed-set prediction — exp776 'memoryless' RETRACTED; successor: per-layer routed-set retention intervention (wall-gated)"); return fin(1)
    if P >= P_WEAK:
        L.append(f"WEAK-MEMORY: routing is NOT memoryless (P_same {P:.2%} = {P/RAND_P:.1f}x random) but far below the {P_REOPEN:.0%} viability bar — prediction-based prefetch stays dead (exp776 NO-LIFT verdict stands; its 'memoryless' mechanism claim is CORRECTED)"); return fin(2)
    L.append("CONFIRMED: memoryless holds at same-layer pairing (P_same < 0.06); exp776 conclusion stands airtight"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

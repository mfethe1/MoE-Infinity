#!/usr/bin/env python3
"""exp774 analyzer: 4x-horizon replicate of exp773 (async double-buffered
indices) + residual attribution from the same profiles.

3 cells: PY_LGC (src753, spec off), PY_SPEC (src753, spec on),
PY_DB (src774 = src753 + patch773.py async-dbuf, EXP773_DB=1).
24 prompts x 64 tok (4x the exp769-773 horizon; rows gate = 24).

Inputs per cell: out/<ID>.json (rows) + out/<ID>.pyspy (raw collapsed).
Metrics: W(cell) = sum(t_1tok_s + t_full_s); per-leaf sample dicts;
spec-leaf = leaves starting with 'ExpertPrefetcher.speculative_prefetch'.

Q1 (frozen, mirrors exp773 at the new horizon). tau_w = 5.0 s (~0.15 of
the expected 4x-scaled D; run-to-run noise does not scale 4x).
  rc=9 IDENTIFY-FAIL: SRC_HEAD != b7f6ca4, or ENV.txt lacks moei-774 line
  rc=4 DATA-FAIL: missing/short (rows<24, samples<2000, BADIO non-empty)
  D = W(PY_SPEC) - W(PY_LGC)
  |D| <= tau_w:          rc=5 NO-BASELINE-SIGNAL
  W(DB) - W(SPEC) > tau_w: rc=8 REGRESS
  R = 1 - (W(PY_DB) - W(PY_LGC)) / D
  rc=1 RECOVER:   R >= 0.7 AND specleaf(DB) <= 0.5 * specleaf(SPEC)
  rc=2 PARTIAL:   0.3 <= R < 0.7  (or R >= 0.7 but leaf gate fails)
  rc=7 NO-GAIN:   R < 0.3

Q2 (frozen attribution section, appended in every data-complete verdict):
  residual = per-leaf deltas DB-LGC (samples/50 = seconds).
  RESIDUAL-CARRIER named iff top positive delta >= max(75 samples (1.5 s),
  0.3 * net positive samples); else RESIDUAL-DIFFUSE (noise-consistent).
  REMOVED section: top SPEC-DB positive deltas (what the fix removed).
"""
import json, os, sys

RATE = 50.0
TAU_W = 5.0
SRC_OK = "b7f6ca4"
ARMS = ("PY_LGC", "PY_SPEC", "PY_DB")
ROWS_MIN = 24
CARRIER_FLOOR = 75  # samples = 1.5 s
CARRIER_FRAC = 0.3

def load_arm(d, arm):
    j = os.path.join(d, "out", arm + ".json")
    y = os.path.join(d, "out", arm + ".pyspy")
    for p in (j, y):
        if not (os.path.exists(p) and os.path.getsize(p) > 0):
            return None
    res = json.load(open(j))
    rows = res.get("rows") or res.get("results") or []
    if len(rows) < ROWS_MIN:
        return {"bad": f"rows={len(rows)}<{ROWS_MIN}"}
    leaves = {}
    for ln in open(y, errors="replace"):
        ln = ln.strip()
        if not ln or ";" not in ln:
            continue
        stack, _, cnt = ln.rpartition(" ")
        try:
            n = int(cnt)
        except ValueError:
            continue
        leaf = stack.split(";")[-1].strip()
        if leaf in ("", "GIL", "Active", "Idle"):
            continue
        leaves[leaf] = leaves.get(leaf, 0) + n
    total = sum(leaves.values())
    if total < 2000:
        return {"bad": f"samples={total}<2000"}
    spec = sum(v for k, v in leaves.items() if k.startswith("ExpertPrefetcher.speculative_prefetch"))
    tps = [r.get("decode_tok_s") or r.get("tok_s") for r in rows if r.get("decode_tok_s") or r.get("tok_s")]
    return {"W": sum(r["t_1tok_s"] + r["t_full_s"] for r in rows), "total": total, "spec": spec,
            "leaves": leaves, "rows": len(rows), "tps": sorted(tps)[len(tps)//2] if tps else None}

def top_pos(a, b, k=5):
    dd = [((a.get(x, 0) - b.get(x, 0)), x) for x in set(a) | set(b)]
    pos = sorted([t for t in dd if t[0] > 0], reverse=True)
    return pos[:k], sum(t[0] for t in pos)

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    env = open(os.path.join(out, "ENV.txt"), errors="replace").read() if os.path.exists(os.path.join(out, "ENV.txt")) else ""
    badio = open(os.path.join(out, "BADIO"), errors="replace").read().strip() if os.path.exists(os.path.join(out, "BADIO")) else ""
    A = {a: load_arm(d, a) for a in ARMS}
    L = ["exp774 4x-horizon replicate of exp773 async-dbuf + residual attribution", f"SRC_HEAD={src[:12]}"]
    for a in ARMS:
        x = A[a]
        if x is None:
            L.append(f"{a}: MISSING")
        elif "bad" in x:
            L.append(f"{a}: BAD {x['bad']}")
        else:
            L.append(f"{a}: W={x['W']:.2f}s samples={x['total']} specleaf={x['spec']/RATE:.2f}s tok/s={x['tps']}")
    if badio:
        L.append(f"BADIO non-empty: {badio[:80]}")
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict774.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith(SRC_OK) or "moei-774 /home/mfeth/exp774/src774/moe_infinity/__init__.py" not in env:
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r}, moei-774-line={'yes' if 'moei-774' in env else 'no'})"); return fin(9)
    if badio or any(a is None or "bad" in a for a in A.values()):
        L.append("DATA-FAIL"); return fin(4)
    LG, SP, DB = A["PY_LGC"], A["PY_SPEC"], A["PY_DB"]
    # Q2: frozen attribution section (data-complete verdicts only)
    pos, net = top_pos(DB["leaves"], LG["leaves"])
    L.append(f"RESIDUAL DB-LGC net+={net/RATE:.2f}s top: " + "; ".join(f"{x}:{+n/RATE:.2f}s" for n, x in pos))
    gate = max(CARRIER_FLOOR, int(CARRIER_FRAC * net)) if net > 0 else CARRIER_FLOOR
    if pos and pos[0][0] >= gate:
        L.append(f"RESIDUAL-CARRIER: {pos[0][1]} (+{pos[0][0]/RATE:.2f}s, gate {gate/RATE:.2f}s)")
    else:
        mx = pos[0][0]/RATE if pos else 0.0
        L.append(f"RESIDUAL-DIFFUSE: max {mx:.2f}s < gate {gate/RATE:.2f}s (noise-consistent)")
    pos2, net2 = top_pos(SP["leaves"], DB["leaves"], k=3)
    L.append(f"REMOVED SPEC-DB net+={net2/RATE:.2f}s top: " + "; ".join(f"{x}:{+n/RATE:.2f}s" for n, x in pos2))
    # Q1: frozen gates (identical structure to exp773, tau_w scaled)
    D = SP["W"] - LG["W"]
    R = 1 - (DB["W"] - LG["W"]) / D if D != 0 else 0.0
    L += [
        f"D = W(SPEC)-W(LGC) = {D:+.2f}s (tau_w={TAU_W})",
        f"W(DB)-W(SPEC) = {DB['W']-SP['W']:+.2f}s   specleaf ratio DB/SPEC = {DB['spec']/max(SP['spec'],1):.2f}",
        f"recovery R = {R:.2f} (unrounded {R:.4f})",
    ]
    if abs(D) <= TAU_W:
        L.append("NO-BASELINE-SIGNAL: SPEC cost did not appear in this run"); return fin(5)
    if DB["W"] - SP["W"] > TAU_W:
        L.append(f"REGRESS: async double-buffer slower than blocking by {DB['W']-SP['W']:.2f}s"); return fin(8)
    leaf_ok = DB["spec"] <= 0.5 * SP["spec"]
    if R >= 0.7 and leaf_ok:
        L.append(f"RECOVER: {R:.0%} of wall gap reclaimed at 4x horizon, specleaf cut to {DB['spec']/max(SP['spec'],1):.0%} -> exp773 fix confirmed at scale; upstream-able; successor: PR + hit-rate retention study"); return fin(1)
    if R >= 0.3 or (R >= 0.7 and not leaf_ok):
        L.append(f"PARTIAL: R={R:.2f}, leaf_ok={leaf_ok} -> successor: act on RESIDUAL-CARRIER above (ring depth 2 if dispatch/staleness; GPU-side trim if topk) "); return fin(2)
    L.append(f"NO-GAIN: R={R:.2f} at 4x horizon -> exp773 result did not replicate; re-examine before any upstreaming"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

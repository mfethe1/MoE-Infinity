#!/usr/bin/env python3
"""exp773 analyzer: async double-buffered indices vs blocking .cpu() sync.

3 cells: PY_LGC (src753, spec off), PY_SPEC (src753, spec on),
PY_DB (src773 = src753 + env-gated async-dbuf patch, EXP773_DB=1).

Inputs per cell: out/<ID>.json (rows) + out/<ID>.pyspy (raw collapsed).
Metrics: W(cell) = sum(t_1tok_s + t_full_s); total py-spy samples;
spec-leaf(cell) = sum of leaf samples whose leaf starts with
'ExpertPrefetcher.speculative_prefetch' (seconds = samples/50).

Frozen decision rule (PREREG-773). tau_w = 2.0 s.
  rc=9 IDENTIFY-FAIL: SRC_HEAD != b7f6ca4, or ENV.txt lacks the moei-773 line
  rc=4 DATA-FAIL: missing/short artifacts (rows<6, samples<2000, BADIO non-empty)
  D = W(PY_SPEC) - W(PY_LGC)   [the serialization cost to reclaim]
  |D| <= tau_w:          rc=5 NO-BASELINE-SIGNAL
  W(DB) - W(SPEC) > tau_w: rc=8 REGRESS (async double-buffer slower)
  R = 1 - (W(PY_DB) - W(PY_LGC)) / D   [fraction of wall gap reclaimed]
  rc=1 RECOVER:   R >= 0.7 AND specleaf(DB) <= 0.5 * specleaf(SPEC)
  rc=2 PARTIAL:   0.3 <= R < 0.7  (or R >= 0.7 but leaf gate fails)
  rc=7 NO-GAIN:   R < 0.3
"""
import json, os, sys

RATE = 50.0
TAU_W = 2.0
SRC_OK = "b7f6ca4"
ARMS = ("PY_LGC", "PY_SPEC", "PY_DB")

def load_arm(d, arm):
    j = os.path.join(d, "out", arm + ".json")
    y = os.path.join(d, "out", arm + ".pyspy")
    for p in (j, y):
        if not (os.path.exists(p) and os.path.getsize(p) > 0):
            return None
    res = json.load(open(j))
    rows = res.get("rows") or res.get("results") or []
    if len(rows) < 6:
        return {"bad": f"rows={len(rows)}<6"}
    total, spec = 0, 0
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
        total += n
        if leaf.startswith("ExpertPrefetcher.speculative_prefetch"):
            spec += n
    if total < 2000:
        return {"bad": f"samples={total}<2000"}
    tps = [r.get("decode_tok_s") or r.get("tok_s") for r in rows if r.get("decode_tok_s") or r.get("tok_s")]
    return {"W": sum(r["t_1tok_s"] + r["t_full_s"] for r in rows), "total": total, "spec": spec,
            "rows": len(rows), "tps": sorted(tps)[len(tps)//2] if tps else None}

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    env = open(os.path.join(out, "ENV.txt"), errors="replace").read() if os.path.exists(os.path.join(out, "ENV.txt")) else ""
    badio = open(os.path.join(out, "BADIO"), errors="replace").read().strip() if os.path.exists(os.path.join(out, "BADIO")) else ""
    A = {a: load_arm(d, a) for a in ARMS}
    L = ["exp773 async double-buffered expert indices (EXP773_DB=1)", f"SRC_HEAD={src[:12]}"]
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
        open(os.path.join(vdir, "verdict773.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith(SRC_OK) or "moei-773 /home/mfeth/exp773/src773/moe_infinity/__init__.py" not in env:
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r}, moei-773-line={'yes' if 'moei-773' in env else 'no'})"); return fin(9)
    if badio or any(a is None or "bad" in a for a in A.values()):
        L.append("DATA-FAIL"); return fin(4)
    LG, SP, DB = A["PY_LGC"], A["PY_SPEC"], A["PY_DB"]
    D = SP["W"] - LG["W"]
    R = 1 - (DB["W"] - LG["W"]) / D if D != 0 else 0.0
    L += [
        f"D = W(SPEC)-W(LGC) = {D:+.2f}s (tau_w={TAU_W})",
        f"W(DB)-W(SPEC) = {DB['W']-SP['W']:+.2f}s   specleaf ratio DB/SPEC = {DB['spec']/max(SP['spec'],1):.2f}",
        f"recovery R = {R:.2f}",
    ]
    if abs(D) <= TAU_W:
        L.append("NO-BASELINE-SIGNAL: SPEC cost did not appear in this run"); return fin(5)
    if DB["W"] - SP["W"] > TAU_W:
        L.append(f"REGRESS: async double-buffer slower than blocking by {DB['W']-SP['W']:.2f}s"); return fin(8)
    leaf_ok = DB["spec"] <= 0.5 * SP["spec"]
    if R >= 0.7 and leaf_ok:
        L.append(f"RECOVER: {R:.0%} of wall gap reclaimed, specleaf cut to {DB['spec']/max(SP['spec'],1):.0%} -> successor: upstream-able patch; measure hit-rate retention under one-call-stale predictions"); return fin(1)
    if R >= 0.3 or (R >= 0.7 and not leaf_ok):
        L.append(f"PARTIAL: R={R:.2f}, leaf_ok={leaf_ok} -> successor: ring depth 2 consumption or host-side logits prediction"); return fin(2)
    L.append(f"NO-GAIN: R={R:.2f}, specleaf ratio {DB['spec']/max(SP['spec'],1):.2f} -> if leaf collapsed the wait moved to a new sink: profile-attribute next function; else serialization is not on this path"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

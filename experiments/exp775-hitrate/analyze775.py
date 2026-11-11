#!/usr/bin/env python3
"""exp775 analyzer: prefetch hit-rate retention under one-call-staler lists.

2 cells on the SAME instrumented build (src775 = src753 + patch775.py):
  PY_SPEC: blocking path  -> out/PY_SPEC.hits.jsonl lines {"t","ts","issued"}
  PY_DB:   double-buffer  -> out/PY_DB.hits.jsonl   lines {"t","ts","consumed"}

Coverage of the next call's need (frozen):
  SPEC hit(t) = |L_t & L_{t+1}| / |L_{t+1}|   (predicts 1 call ahead)
  DB   hit(t) = |C_t & C_{t+2}| / |C_{t+2}|   (C_t = L_{t-1}: 2 calls stale)
Pairs are valid only if every consecutive call gap inside the pair is
<= 1.0 s (prompt boundaries create >1 s gaps and are excluded).

Wall covariate gate (instrumentation-perturbation guard): W(arm) within
+/-25% of the exp774 sealed references (SPEC 212.13 s, DB 179.72 s).

rc map:
  9 IDENTIFY-FAIL  src/marker/env mismatch
  4 DATA-FAIL      missing/short logs (<200 valid pairs/arm), BADIO, wall dev
  1 RETAINED       D = hit(DB) - hit(SPEC) >= -0.02
  2 ERODED         -0.10 <= D < -0.02
  7 SEVERE         D < -0.10
"""
import json, os, sys

GAP = 1.0
WALL_TOL = 0.25
REF = {"PY_SPEC": 212.13, "PY_DB": 179.72}
PAIRS_MIN = 200
RETAIN = -0.02
ERODE = -0.10
KEY = {"PY_SPEC": "issued", "PY_DB": "consumed"}
LAG = {"PY_SPEC": 1, "PY_DB": 2}

def load_rows(d, arm):
    p = os.path.join(d, "out", arm + ".json")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return None
    res = json.load(open(p))
    rows = res.get("rows") or res.get("results") or []
    if len(rows) < 20:
        return {"bad": f"rows={len(rows)}<20"}
    return {"W": sum(r["t_1tok_s"] + r["t_full_s"] for r in rows)}

def load_hits(d, arm):
    p = os.path.join(d, "out", arm + ".hits.jsonl")
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
        lst = j.get(KEY[arm])
        if isinstance(lst, list) and lst:
            calls.append((float(j.get("ts", 0.0)), [int(x) for x in lst]))
    return calls

def hit_rate(calls, lag):
    """Mean coverage |A&B|/|B| over valid (t, t+lag) pairs; gaps excluded."""
    hits, n = 0.0, 0
    for i in range(len(calls) - lag):
        ok = True
        for j in range(i, i + lag):
            if calls[j + 1][0] - calls[j][0] > GAP:
                ok = False
                break
        if not ok:
            continue
        a = set(calls[i][1])
        b = set(calls[i + lag][1])
        if not b:
            continue
        hits += len(a & b) / len(b)
        n += 1
    return (hits / n if n else 0.0), n

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    env = open(os.path.join(out, "ENV.txt"), errors="replace").read() if os.path.exists(os.path.join(out, "ENV.txt")) else ""
    badio = open(os.path.join(out, "BADIO"), errors="replace").read().strip() if os.path.exists(os.path.join(out, "BADIO")) else ""
    R = {a: load_rows(d, a) for a in ("PY_SPEC", "PY_DB")}
    H = {a: load_hits(d, a) for a in ("PY_SPEC", "PY_DB")}
    L = ["exp775 hit-rate retention: stale-list coverage vs fresh-list coverage"]
    for a in ("PY_SPEC", "PY_DB"):
        if R[a] is None:
            L.append(f"{a}: rows MISSING")
        elif "bad" in R[a]:
            L.append(f"{a}: rows BAD {R[a]['bad']}")
        else:
            dev = (R[a]["W"] - REF[a]) / REF[a]
            L.append(f"{a}: W={R[a]['W']:.2f}s (ref {REF[a]}, dev {dev:+.1%})")
        L.append(f"{a}: hitlog {'MISSING' if H[a] is None else str(len(H[a])) + ' calls'}")
    if badio:
        L.append(f"BADIO non-empty: {badio[:80]}")
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict775.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith("b7f6ca4") or "moei-775 /home/mfeth/exp775/src775/moe_infinity/__init__.py" not in env:
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r}, moei-775={'yes' if 'moei-775' in env else 'no'})"); return fin(9)
    if badio or any(R[a] is None or "bad" in R[a] or H[a] is None for a in R):
        L.append("DATA-FAIL"); return fin(4)
    for a in ("PY_SPEC", "PY_DB"):
        if abs((R[a]["W"] - REF[a]) / REF[a]) > WALL_TOL:
            L.append(f"DATA-FAIL: {a} wall deviates >{WALL_TOL:.0%} from exp774 ref — instrumentation perturbed the system"); return fin(4)
    rate, n = {}, {}
    for a in ("PY_SPEC", "PY_DB"):
        rate[a], n[a] = hit_rate(H[a], LAG[a])
        if n[a] < PAIRS_MIN:
            L.append(f"DATA-FAIL: {a} valid pairs {n[a]} < {PAIRS_MIN}"); return fin(4)
    D = rate["PY_DB"] - rate["PY_SPEC"]
    L += [
        f"hit(SPEC, lag1) = {rate['PY_SPEC']:.4f} over {n['PY_SPEC']} pairs (mean k={sum(len(c[1]) for c in H['PY_SPEC'])/len(H['PY_SPEC']):.1f})",
        f"hit(DB,   lag2) = {rate['PY_DB']:.4f} over {n['PY_DB']} pairs (mean k={sum(len(c[1]) for c in H['PY_DB'])/len(H['PY_DB']):.1f})",
        f"D = hit(DB) - hit(SPEC) = {D:+.4f}",
    ]
    if D >= RETAIN:
        L.append(f"RETAINED: staleness costs <= {abs(RETAIN):.0%} coverage — upstream story complete; successor: upstream PR (exp773 patch) with exp774+775 evidence"); return fin(1)
    if D >= ERODE:
        L.append(f"ERODED: coverage drops {D:+.2%} — quantify dispatch cost; successor: ring depth 2 (consume freshest armed buffer) before upstreaming"); return fin(2)
    L.append(f"SEVERE: coverage drops {D:+.2%} — upstream caveat required; successor: ring depth 2 + hit-rate-aware fallback"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

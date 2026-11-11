#!/usr/bin/env python3
"""exp771 analyzer: FUNCTION-level CPU attribution on the main thread.

Input: run dir with out/{PY_LGC,PY_SPEC}.{json,pyspy} (+ oscsv/tidcsv
cross-checks), out/SRC_HEAD.txt. pyspy files are py-spy `raw` collapsed
stacks: one line per unique stack, "frame;frame;...;frame count". Leaf frame
= last frame before the trailing count. Aggregation is over LEAF functions,
python frames only (attached non-native). Deltas are SPEC - LGC sample
counts; seconds = samples / rate (rate=50, frozen).

Frozen decision rule (PREREG-771), tau=2.0 s, tau_f=1.0 s, f=0.4, g=0.6:
  rc=9 IDENTIFY-FAIL (SRC_HEAD != b7f6ca4)
  rc=4 DATA-FAIL (missing/short artifacts; json rows<6; <2000 total samples/arm)
  DcpuS = (S_samples - L_samples)/rate
  |DcpuS| < tau:  rc=5 NO-SIGNAL (sampled CPU delta did not replicate)
  DcpuS <= -tau:  rc=8 REVERSED
  rank leaf functions by delta_samples DESC; only deltas > 0 counted for gates
  top1 >= max(tau_f, f*positive_sum)/rate... (in samples: top1_d >= max(tau_f*rate, f*pos_sum))
  -> rc=1 F-TOP: single function carries >= max(1.0 s, 40% of positive delta)
  elif top1+top2 >= max(2.0 s, 60% of positive delta)
  -> rc=2 F-PAIR: a pair carries it
  else rc=7 F-DIFFUSE
Cross-checks printed (not gated): DW/Dcpu from oscsv windows as in exp770.
"""
import json, os, sys

RATE = 50.0
TAU, TAU_F, F, G = 2.0, 1.0, 0.4, 0.6
SRC_OK = "b7f6ca4"
ARMS = ("PY_LGC", "PY_SPEC")

def leaf_agg(path):
    """Return {leaf_func_string: samples} and total."""
    agg = {}
    total = 0
    for ln in open(path, errors="replace"):
        ln = ln.strip()
        if not ln or ";" not in ln:
            continue
        stack, _, cnt = ln.rpartition(" ")
        try:
            n = int(cnt)
        except ValueError:
            continue
        frames = stack.split(";")
        leaf = frames[-1].strip()
        if leaf in ("", "GIL", "Active", "Idle"):
            continue  # thread-state markers, not functions
        agg[leaf] = agg.get(leaf, 0) + n
        total += n
    return agg, total

def load_arm(d, arm):
    j = os.path.join(d, "out", arm + ".json")
    y = os.path.join(d, "out", arm + ".pyspy")
    if not (os.path.exists(j) and os.path.getsize(j) > 0 and os.path.exists(y) and os.path.getsize(y) > 0):
        return None
    res = json.load(open(j))
    rows = res.get("rows") or res.get("results") or []
    if len(rows) < 6:
        return {"rows": len(rows), "bad": "rows<6"}
    agg, total = leaf_agg(y)
    if total < 2000:
        return {"rows": len(rows), "bad": f"samples={total}<2000"}
    return {"agg": agg, "total": total, "W": sum(r["t_1tok_s"] + r["t_full_s"] for r in rows), "rows": len(rows)}

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    A = {a: load_arm(d, a) for a in ARMS}
    lines = ["exp771 function-level CPU attribution (py-spy raw leaf, rate=50)", f"SRC_HEAD={src[:12]}"]
    for a in ARMS:
        x = A[a]
        if x is None:
            lines.append(f"{a}: MISSING artifacts")
        else:
            lines.append(f"{a}: rows={x.get('rows')} samples={x.get('total')}" + ("" if "bad" not in x else f" BAD={x.get('bad')}"))
    def fin(rc_val):
        txt = "\n".join(lines)
        print(txt); print(f"rc={rc_val}")
        open(os.path.join(vdir, "verdict771.txt"), "w").write(txt + f"\nrc={rc_val}\n")
        return rc_val
    if not src.startswith(SRC_OK):
        lines.append(f"IDENTIFY-FAIL: SRC_HEAD {src[:12]!r} != {SRC_OK}"); return fin(9)
    if any(a is None or "bad" in a for a in A.values()):
        lines.append("DATA-FAIL: missing/short artifacts"); return fin(4)
    L, S = A["PY_LGC"], A["PY_SPEC"]
    dcpu_s = (S["total"] - L["total"]) / RATE
    allf = set(L["agg"]) | set(S["agg"])
    df = {f: S["agg"].get(f, 0) - L["agg"].get(f, 0) for f in allf}
    pos = sorted(((f, v) for f, v in df.items() if v > 0), key=lambda kv: -kv[1])
    pos_sum = sum(v for _, v in pos)
    lines += [
        f"W(gen wall): LGC {L['W']:.2f}s SPEC {S['W']:.2f}s  DW={S['W']-L['W']:+.2f}s (cross-check)",
        f"sampled CPU: LGC {L['total']/RATE:.1f}s SPEC {S['total']/RATE:.1f}s  DcpuS={dcpu_s:+.2f}s (tau={TAU})",
        f"positive leaf delta sum: {pos_sum/RATE:.2f}s across {len(pos)} functions",
        "top leaf deltas (SPEC-LGC):",
    ]
    for f, v in pos[:8]:
        lines.append(f"  {f[:70]:<70s} {v/RATE:+7.2f}s  {100*v/pos_sum if pos_sum else 0:5.1f}% of +delta")
    if abs(dcpu_s) < TAU:
        lines.append(f"NO-SIGNAL: |DcpuS|={abs(dcpu_s):.2f}s < tau -> successor: raise rate / N-run"); return fin(5)
    if dcpu_s <= -TAU:
        lines.append(f"REVERSED: DcpuS={dcpu_s:+.2f}s"); return fin(8)
    top1 = pos[0] if pos else ("", 0)
    top2 = pos[1] if len(pos) > 1 else ("", 0)
    thr1 = max(TAU_F * RATE, F * pos_sum)
    thr2 = max(2.0 * RATE, G * pos_sum)
    if top1[1] >= thr1:
        lines.append(f"F-TOP: {top1[0]} carries {top1[1]/RATE:+.2f}s ({100*top1[1]/pos_sum:.0f}% of +delta) -> name it; successor: targeted micro-opt / batching of this function"); return fin(1)
    if top1[1] + top2[1] >= thr2:
        lines.append(f"F-PAIR: {top1[0]} ({top1[1]/RATE:+.2f}s) + {top2[0]} ({top2[1]/RATE:+.2f}s) = {(top1[1]+top2[1])/RATE:.2f}s ({100*(top1[1]+top2[1])/pos_sum:.0f}% of +delta) -> successor: optimize the pair"); return fin(2)
    lines.append(f"F-DIFFUSE: top1 {top1[1]/RATE:+.2f}s < max(1.0s,40%) and pair < max(2.0s,60%) -> successor: line-level attribution or code-region timing"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())

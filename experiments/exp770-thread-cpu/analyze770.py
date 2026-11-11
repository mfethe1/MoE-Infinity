#!/usr/bin/env python3
"""exp770 analyzer: per-thread CPU attribution of the spec-prefetch cost.

Input: run dir with out/{OS_LGC,OS_SPEC}.{json,oscsv,tidcsv}, out/SRC_HEAD.txt.
Process-level loading verbatim from analyze769 (windows = epoch
[min(win_full[0]), max(win_full[1])] over the 6 prompt rows). Per-thread: for
each bucket (MAIN = tid==pid, else comm), delta = last minus first in-window
(utime+stime) occurrence of that bucket in tidcsv. dbucket = SPEC - LGC.

Frozen decision rule (PREREG-770), tau_cpu = 4.0 s, tau_bucket = 2.0 s, f=0.5:
  Dcpu = window CPU-time delta (process level, oscsv)
  rc=9 IDENTIFY-FAIL (SRC_HEAD != b7f6ca4)
  rc=4 DATA-FAIL (missing/short artifacts; inwin<100 oscsv samples/arm;
      <50 in-window tidcsv bucket-rows/arm; coverage = sum(positive dbuckets)
      / Dcpu outside [0.5, 2.0])
  |Dcpu| < tau_cpu:            rc=5 NO-SIGNAL (CPU delta didn't replicate)
  Dcpu <= -tau_cpu:            rc=8 REVERSED
  top = argmax dbucket;  threshold = max(tau_bucket, f*Dcpu)
  top < threshold:             rc=7 DIFFUSE (no bucket carries >=50%)
  top == MAIN:                 rc=1 MAIN-BOUND (GIL/python path burns it)
  top matches ^Thread-[0-9]+$:  rc=2 THREADED-WORKER (prefetch worker class)
  else:                        rc=3 POOL-UNNAMED (torch intraop / comm pool)
Covariates: DW wall delta, RSS peak, threads peak, per-arm bucket tables.
"""
import json, os, re, sys

TAU_CPU, TAU_B, F = 4.0, 2.0, 0.5
SRC_OK = "b7f6ca4"
ARMS = ("OS_LGC", "OS_SPEC")

def load_arm(d, arm):
    j = os.path.join(d, "out", arm + ".json")
    c = os.path.join(d, "out", arm + ".oscsv")
    t = os.path.join(d, "out", arm + ".tidcsv")
    if not all(os.path.exists(x) and os.path.getsize(x) > 0 for x in (j, c, t)):
        return None
    res = json.load(open(j))
    rows = res.get("rows") or res.get("results") or []
    if len(rows) < 6:
        return {"rows": len(rows), "bad": "rows<6"}
    W = sum(r["t_1tok_s"] + r["t_full_s"] for r in rows)
    w0 = min(r["win_full"][0] for r in rows)
    w1 = max(r["win_full"][1] for r in rows)
    toks = [r["decode_tok_s"] for r in rows if r.get("decode_tok_s")]
    clk = 100.0
    samples = []
    for ln in open(c, errors="replace"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            if ln.startswith("# clk_tck="): clk = float(ln.split("=")[1])
            continue
        p = ln.split(",")
        if len(p) != 11: continue
        try: samples.append((float(p[0]), [int(x) for x in p[1:]]))
        except ValueError: continue
    inwin = [s for s in samples if w0 <= s[0] <= w1]
    if len(inwin) < 100:
        return {"rows": len(rows), "bad": f"inwin={len(inwin)}<100"}
    first, last = inwin[0][1], inwin[-1][1]
    buckets = {}
    ntid = 0
    for ln in open(t, errors="replace"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            if "clk_tck=" in ln:
                try: clk = float(ln.split("clk_tck=")[1].split()[0])
                except (IndexError, ValueError): pass
            continue
        p = ln.split(",")
        if len(p) != 5: continue
        try:
            ts, b, _nth, ut, stt = float(p[0]), p[1], int(p[2]), int(p[3]), int(p[4])
        except ValueError: continue
        if not (w0 <= ts <= w1): continue
        ntid += 1
        a = buckets.get(b)
        # track earliest and latest in-window (utime+stime) per bucket
        if a is None:
            buckets[b] = [ts, ut + stt, ts, ut + stt]
        else:
            if ts <= a[0]:
                a[0], a[1] = ts, ut + stt
            if ts >= a[2]:
                a[2], a[3] = ts, ut + stt
    if ntid < 50:
        return {"rows": len(rows), "bad": f"tidrows={ntid}<50"}
    bdelta = {b: (v[3] - v[1]) / clk for b, v in buckets.items()}
    (u0, s0, th0, mi0, ma0, r0, v0, nv0, rr0, ww0) = first
    (u1, s1, th1, mi1, ma1, r1, v1, nv1, rr1, ww1) = last
    return {"W": W, "clk": clk,
            "cpu": (u1 - u0 + s1 - s0) / clk,
            "rss_peak_kb": max(s[1][5] for s in inwin if s[1][5] > 0),
            "threads_peak": max(s[1][2] for s in inwin),
            "bdelta": bdelta, "ntid": ntid, "toks": toks, "rows": len(rows)}

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    A = {a: load_arm(d, a) for a in ARMS}
    lines = ["exp770 per-thread CPU attribution", f"SRC_HEAD={src[:12]}"]
    for a in ARMS:
        x = A[a]
        if x is None:
            lines.append(f"{a}: MISSING artifacts")
        else:
            lines.append(f"{a}: rows={x.get('rows')} tidrows={x.get('ntid')}" + ("" if "bad" not in x else f" BAD={x.get('bad')}"))
    def fin(rc_val):
        txt = "\n".join(lines)
        print(txt); print(f"rc={rc_val}")
        open(os.path.join(vdir, "verdict770.txt"), "w").write(txt + f"\nrc={rc_val}\n")
        return rc_val
    if not src.startswith(SRC_OK):
        lines.append(f"IDENTIFY-FAIL: SRC_HEAD {src[:12]!r} != {SRC_OK}"); return fin(9)
    if any(a is None or "bad" in a for a in A.values()):
        lines.append("DATA-FAIL: missing/short artifacts"); return fin(4)
    L, S = A["OS_LGC"], A["OS_SPEC"]
    DW = S["W"] - L["W"]
    Dcpu = S["cpu"] - L["cpu"]
    allb = sorted(set(L["bdelta"]) | set(S["bdelta"]))
    db = {b: S["bdelta"].get(b, 0.0) - L["bdelta"].get(b, 0.0) for b in allb}
    possum = sum(v for v in db.values() if v > 0)
    cov = possum / Dcpu if Dcpu > 0 else 0.0
    lines += [
        f"DW={DW:+.2f}s  Dcpu={Dcpu:+.2f}s (tau_cpu={TAU_CPU})  coverage={cov:.2f} (sum positive bucket deltas / Dcpu)",
        "dbucket (SPEC-LGC, top 5 by delta):",
    ]
    for b, v in sorted(db.items(), key=lambda kv: -kv[1])[:5]:
        lines.append(f"  {b:<28s} {v:+8.2f}s  {100 * v / Dcpu if Dcpu else 0:5.1f}% of Dcpu")
    lines.append(f"covariates: RSSpeak LGC {L['rss_peak_kb']:,} SPEC {S['rss_peak_kb']:,} kB; threads {L['threads_peak']}/{S['threads_peak']}; tok/s LGC {sum(L['toks'])/len(L['toks']):.2f} SPEC {sum(S['toks'])/len(S['toks']):.2f}")
    if abs(Dcpu) < TAU_CPU:
        lines.append(f"NO-SIGNAL: |Dcpu|={abs(Dcpu):.2f}s < tau_cpu -> successor: N-run CPU replicate"); return fin(5)
    if Dcpu <= -TAU_CPU:
        lines.append(f"REVERSED: Dcpu={Dcpu:+.2f}s"); return fin(8)
    if not (0.5 <= cov <= 2.0):
        lines.append(f"DATA-FAIL: coverage {cov:.2f} outside [0.5,2.0] (per-thread view misses process CPU)"); return fin(4)
    top_b, top_v = max(db.items(), key=lambda kv: kv[1])
    thr = max(TAU_B, F * Dcpu)
    if top_v < thr:
        lines.append(f"DIFFUSE: top bucket {top_b} {top_v:+.2f}s < max(tau_b,f*Dcpu)={thr:.2f}s -> successor: perf thread-off sampling / cgroup-level"); return fin(7)
    if top_b == "MAIN":
        lines.append(f"D1 MAIN-BOUND: MAIN {top_v:+.2f}s ({100*top_v/Dcpu:.0f}% of Dcpu) -> cost burns the GIL/python main path; successor: py-level targeted profile of main thread (spec predictor loop)"); return fin(1)
    if re.fullmatch(r"Thread-[0-9]+", top_b):
        lines.append(f"D2 THREADED-WORKER: {top_b} {top_v:+.2f}s ({100*top_v/Dcpu:.0f}% of Dcpu) -> prefetch worker thread class; successor: pin down the exact thread func, amortize/batch"); return fin(2)
    lines.append(f"D3 POOL-UNNAMED: {top_b} {top_v:+.2f}s ({100*top_v/Dcpu:.0f}% of Dcpu) -> unnamed native pool (torch intraop/comm); successor: perf + thread-name injection"); return fin(3)

if __name__ == "__main__":
    sys.exit(main())

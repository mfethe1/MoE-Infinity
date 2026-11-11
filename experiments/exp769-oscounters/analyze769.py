#!/usr/bin/env python3
"""exp769 analyzer: UNPROFILED OS-counter differential (LGC vs SPEC).

Input: run dir with out/{OS_LGC,OS_SPEC}.{json,oscsv}, out/SRC_HEAD.txt.
Windows: per arm, epoch [min(win_full[0]), max(win_full[1])] over the 6 prompt
rows of the .json (warmup excluded by construction). Counter deltas = last
in-window CSV row minus first in-window row.

Frozen decision rule (PREREG-769), tau_wall = 2.0 s:
  W(arm) = sum_rows(t_1tok_s + t_full_s)          (generation wall, unprofiled)
  DW = W(SPEC) - W(LGC)
  rc=9 IDENTIFY-FAIL (SRC_HEAD != b7f6ca4)
  rc=4 DATA-FAIL (missing files, rows<6, or <100 in-window CSV samples/arm)
  DW >= tau:
    rc=1 D1 CPU-DOMINATED    Dcpu >= 0.8*DW        (cpu = utime+stime secs)
    rc=2 D2 FAULT-DOMINATED  (not D1) and (Dmaj>=100000 or Dmin>=5000000)
    rc=6 D3 SCHED-CONTENTION (not D1/D2) and Dnonvol>=500000
    rc=7 D4 UNATTRIBUTED     none of the above -> successor perf-stat/strace
  DW <= -tau:
    rc=8 D6 REVERSED (SPEC faster unprofiled)
  |DW| < tau:
    rc=5 D5 NO-REPLICATION (single-run envelope; successor N-run wall replicate)
Covariates (no gates): RSS peak, io read/write deltas, threads peak, vol switches.
"""
import glob, json, os, re, sys

TAU = 2.0
SRC_OK = "b7f6ca4"
ARMS = ("OS_LGC", "OS_SPEC")

def load_arm(d, arm):
    j = os.path.join(d, "out", arm + ".json")
    c = os.path.join(d, "out", arm + ".oscsv")
    if not (os.path.exists(j) and os.path.exists(c) and os.path.getsize(j) > 0 and os.path.getsize(c) > 0):
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
    (u0, s0, th0, mi0, ma0, r0, v0, nv0, rr0, ww0) = first
    (u1, s1, th1, mi1, ma1, r1, v1, nv1, rr1, ww1) = last
    return {"W": W, "w0": w0, "w1": w1, "clk": clk,
            "cpu": (u1 - u0 + s1 - s0) / clk,
            "dmin": mi1 - mi0, "dmaj": ma1 - ma0,
            "dvol": v1 - v0, "dnonvol": nv1 - nv0,
            "rss_peak_kb": max(s[1][5] for s in inwin if s[1][5] > 0),
            "threads_peak": max(s[1][2] for s in inwin),
            "read_kb": rr1 - rr0, "write_kb": ww1 - ww0,
            "nwin": len(inwin), "toks": toks, "rows": len(rows)}

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""
    A = {a: load_arm(d, a) for a in ARMS}
    lines = ["exp769 unprofiled OS-counter differential", f"SRC_HEAD={src[:12]}"]
    for a in ARMS:
        x = A[a]
        if x is None:
            lines.append(f"{a}: MISSING artifacts")
        else:
            lines.append(f"{a}: rows={x.get('rows')} inwin={x.get('nwin')}" + ("" if "bad" not in x else f" BAD={x.get('bad')}"))
    def fin(rc_val):  # emit + persist + exit
        txt = "\n".join(lines)
        print(txt); print(f"rc={rc_val}")
        open(os.path.join(vdir, "verdict769.txt"), "w").write(txt + f"\nrc={rc_val}\n")
        return rc_val
    if not src.startswith(SRC_OK):
        lines.append(f"IDENTIFY-FAIL: SRC_HEAD {src[:12]!r} != {SRC_OK}"); return fin(9)
    if any(a is None or "bad" in a for a in A.values()):
        lines.append("DATA-FAIL: missing/short artifacts"); return fin(4)
    L, S = A["OS_LGC"], A["OS_SPEC"]
    DW = S["W"] - L["W"]
    Dcpu, Dmin, Dmaj, Dnonvol = S["cpu"] - L["cpu"], S["dmin"] - L["dmin"], S["dmaj"] - L["dmaj"], S["dnonvol"] - L["dnonvol"]
    lines += [
        f"W(gen wall, unprofiled): LGC {L['W']:.2f}s SPEC {S['W']:.2f}s  DW={DW:+.2f}s (tau={TAU})",
        f"window CPU-time: LGC {L['cpu']:.2f}s SPEC {S['cpu']:.2f}s  Dcpu={Dcpu:+.2f}s ({(Dcpu / DW * 100 if DW else 0):.0f}% of DW)",
        f"faults: minflt D={Dmin:+,}  majflt D={Dmaj:+,}",
        f"ctx switches: vol D={S['dvol'] - L['dvol']:+,}  nonvol D={Dnonvol:+,}",
        f"covariates: RSSpeak LGC {L['rss_peak_kb']:,} SPEC {S['rss_peak_kb']:,} kB; threads {L['threads_peak']}/{S['threads_peak']}; io R/W LGC {L['read_kb']:,}/{L['write_kb']:,} SPEC {S['read_kb']:,}/{S['write_kb']:,} kB",
        f"tok/s mean: LGC {sum(L['toks'])/len(L['toks']):.2f} SPEC {sum(S['toks'])/len(S['toks']):.2f}",
    ]
    if DW >= TAU:
        if Dcpu >= 0.8 * DW:
            lines.append(f"D1 CPU-DOMINATED: Dcpu {Dcpu:+.2f}s >= 0.8*DW -> cost is real CPU work; successor: which thread burns it (per-task /proc, perf)")
            return fin(1)
        elif Dmaj >= 100000 or Dmin >= 5000000:
            lines.append(f"D2 FAULT-DOMINATED: Dmaj {Dmaj:+,} Dmin {Dmin:+,} -> memory-path cost; successor: rss/mmap trace, THP/madvise experiments")
            return fin(2)
        elif Dnonvol >= 500000:
            lines.append(f"D3 SCHED-CONTENTION: Dnonvol {Dnonvol:+,} -> preemption cost; successor: affinity/isolation experiment")
            return fin(6)
        else:
            lines.append(f"D4 UNATTRIBUTED: no OS counter explains DW={DW:+.2f}s -> successor: perf-stat counters (bandwidth/caches), strace-c summary")
            return fin(7)
    elif DW <= -TAU:
        lines.append(f"D6 REVERSED: DW={DW:+.2f}s (SPEC faster unprofiled) -> report; re-examine envelope")
        return fin(8)
    else:
        lines.append(f"D5 NO-REPLICATION: |DW|={abs(DW):.2f}s < tau in single-run envelope -> successor: N-run wall-only replicate")
        return fin(5)
    return fin(0)

if __name__ == "__main__":
    sys.exit(main())

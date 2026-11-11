#!/usr/bin/env python3
"""exp767 analyzer: native-vs-python split of speculative_prefetch subtree time.

Input: run dir containing out/NAT_LGC*.pyspy and out/NAT_SPEC*.pyspy
(py-spy --native -r 100 -f raw collapsed stacks, root->leaf, trailing count),
out/SRC_HEAD.txt, out/ENV.txt.

Frozen decision rule (PREREG-767):
  P = seconds(inside_SPEC) - seconds(inside_LGC), inside = any stack frame
      matching the speculative_prefetch literals (executor wrapper or
      prefetcher body).
  NATIVE delta = sum over {N_TORCH, N_LIBC, N_HEX} of max(0, dSecs_family)
  PYTHON delta = sum over {PY_PREF, PY_EXEC, PY_OTH} of max(0, dSecs_family)
  shares normalized over NATIVE+PYTHON.
  rc=1 D1 NATIVE-DOMINATED (native_share >= 0.70)  -> exp766 transfer-restructure
  rc=2 D2 PYTHON-DOMINATED (python_share >= 0.70)  -> exp766 t3 micro-patch
  rc=4 D3 MIXED (both in (0.30, 0.70))             -> exp766 ranked combination
  rc=5 D5 NULL-TIME (P < tau=2.0 s)                -> redesign
  rc=3 INCONCLUSIVE (combined samples < 30000)
  rc=9 IDENTIFY-FAIL (SRC_HEAD != b7f6ca4)
  rc=4 DATA-FAIL (missing/empty pyspy files)
Observation-only: no wall-clock claims vs unprofiled runs.
"""
import glob, json, os, re, sys

RATE_HZ = 100.0
TAU_S = 2.0
MIN_COMBINED = 30000
SRC_OK = "b7f6ca4"
WRAP_RE = re.compile(r"speculative_prefetch \(moe_infinity/(distributed/expert_executor|memory/expert_prefetcher)\.py:")
N_TORCH = ("libtorch_cpu.so", "libtorch_python.so", "libtorch_cuda.so", "libc10.so", "libgomp")
N_LIBC = ("libc.so", "libpthread", "librt.so", "libcuda.so", "cudaStreamSynchronize", "cudaMemcpy", "__intercept")

def classify_leaf(leaf):
    if ".py:" in leaf:
        if "memory/expert_prefetcher.py:" in leaf: return "PY_PREF"
        if "distributed/expert_executor.py:" in leaf: return "PY_EXEC"
        return "PY_OTH"
    if leaf.startswith("0x"): return "N_HEX"
    if any(t in leaf for t in N_TORCH): return "N_TORCH"
    if any(t in leaf for t in N_LIBC): return "N_LIBC"
    return "N_OTH"

def parse(path, acc):
    n = 0
    with open(path, errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line: continue
            frames_txt, _, cnt = line.rpartition(" ")
            try: c = int(cnt)
            except ValueError: continue
            frames = frames_txt.split(";")
            n += c
            if not any(WRAP_RE.search(fr) for fr in frames): continue
            fam = classify_leaf(frames[-1])
            acc[fam] += c
    return n

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    out = os.path.join(d, "out")
    lgc = sorted(glob.glob(os.path.join(out, "NAT_LGC*.pyspy")))
    spec = sorted(glob.glob(os.path.join(out, "NAT_SPEC*.pyspy")))
    files = {"LGC": lgc, "SPEC": spec}
    if not lgc or not spec or any(os.path.getsize(p) == 0 for p in lgc + spec):
        print("DATA-FAIL: missing/empty pyspy files"); print("rc=4"); return 4
    acc = {a: {k: 0 for k in ("PY_PREF","PY_EXEC","PY_OTH","N_TORCH","N_LIBC","N_HEX","N_OTH")} for a in ("LGC","SPEC")}
    tot = {}
    for arm, paths in files.items():
        tot[arm] = sum(parse(p, acc[arm]) for p in paths)
    combined = tot["LGC"] + tot["SPEC"]
    src = ""
    sp = os.path.join(out, "SRC_HEAD.txt")
    if os.path.exists(sp): src = open(sp).read().strip()
    table = {a: {k: round(v / RATE_HZ, 3) for k, v in acc[a].items()} for a in acc}
    def delta(k): return (acc["SPEC"][k] - acc["LGC"][k]) / RATE_HZ
    P = (sum(acc["SPEC"].values()) - sum(acc["LGC"].values())) / RATE_HZ
    nat = sum(max(0.0, delta(k)) for k in ("N_TORCH","N_LIBC","N_HEX"))
    pyt = sum(max(0.0, delta(k)) for k in ("PY_PREF","PY_EXEC","PY_OTH"))
    den = nat + pyt
    lines = ["exp765 native-vs-python split of speculative_prefetch subtree",
             f"samples: LGC={tot['LGC']} SPEC={tot['SPEC']} combined={combined}",
             f"SRC_HEAD={src[:12]}", "family secs (LGC -> SPEC, delta):"]
    for k in ("PY_PREF","PY_EXEC","PY_OTH","N_TORCH","N_LIBC","N_HEX","N_OTH"):
        lines.append(f"  {k:8s} {table['LGC'][k]:8.3f} -> {table['SPEC'][k]:8.3f}  d={delta(k):+8.3f}")
    lines.append(f"P (inside delta) = {P:+.3f} s  raw_deltas={json.dumps({k: round(delta(k),3) for k in acc['LGC']})}")
    if combined < MIN_COMBINED:
        lines.append(f"INCONCLUSIVE: combined {combined} < {MIN_COMBINED}")
        rc = 3
    elif not src.startswith(SRC_OK):
        lines.append(f"IDENTIFY-FAIL: SRC_HEAD {src[:12]!r} != {SRC_OK}")
        rc = 9
    elif P < TAU_S:
        lines.append(f"D5 NULL-TIME: P {P:.3f} < tau {TAU_S}")
        rc = 5
    else:
        ns = nat / den if den else 0.0
        ps = pyt / den if den else 0.0
        lines.append(f"native_share={ns:.3f} python_share={ps:.3f} (normalized over positive deltas {den:.3f}s)")
        if ns >= 0.70:
            lines.append("VERDICT: D1 NATIVE-DOMINATED -> successor exp768 transfer-restructure (device topk, async D2H indices, single sync; decisions identical)")
            rc = 1
        elif ps >= 0.70:
            lines.append("VERDICT: D2 PYTHON-DOMINATED -> successor exp768 apply staged t3 micro-patch (expert_prefetcher.py sha 55b34db95278935f...)")
            rc = 2
        else:
            lines.append("VERDICT: D3 MIXED -> successor exp768 both repairs ranked by share")
            rc = 4
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(out, "verdict.txt"), "w").write(txt + "\n")
    print(f"rc={rc}")
    return rc

if __name__ == "__main__":
    sys.exit(main())

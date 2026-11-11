#!/usr/bin/env python3
"""exp768 analyzer: named-subtree decomposition of the spec-prefetch wall cost
under NATIVE attribution, from exp767's sealed raw stacks.

Input: run dir of SEALED exp767 (containing out/NAT_LGC*.pyspy, out/NAT_SPEC*.pyspy,
out/SRC_HEAD.txt). exp768 adds NO new cells; it is a preregistered re-analysis
(the analyzer only reads sealed artifacts; observation-only, thread-seconds).

Named subtrees (any-frame membership, literals verified by probe 2026-11-11T04:01Z):
  SPEC : speculative_prefetch (executor wrapper / prefetcher body)
  EAGER : DistributedExpertExecutor._dispatch_eager_local (
  WAIT : DistributedExpertExecutor.wait_dispatch_local (

Frozen decision rule (PREREG-768), tau = 2.0 s, per-subtree floor 500 samples/arm:
  De = secsEAGER(SPEC-arm) - secsEAGER(LGC-arm)   [subtree totals, all families]
  Ds = secsSPEC-sub(...)   Dw = secsWAIT(...)
  rc=9 IDENTIFY-FAIL (SRC_HEAD != b7f6ca4)
  rc=4 DATA-FAIL (missing/empty pyspy)
  rc=3 INCONCLUSIVE (combined < 30000 OR any named subtree < 500 samples in an arm)
  rc=1 D1 EAGER-COST    De >= tau
  rc=2 D2 MIGRATION     (not D1) and Ds >= tau and Dw <= -tau
  rc=5 D3 NET-NULL      |De|,|Ds|,|Dw| all < tau  -> successor exp769 OS-counter differential
  rc=6 D4 MIXED         otherwise
Covariates (no gates): whole-process per-family deltas; total attributed delta.
"""
import glob, json, os, re, sys

RATE_HZ = 100.0
TAU_S = 2.0
MIN_COMBINED = 30000
MIN_SUBTREE = 500
SRC_OK = "b7f6ca4"
SUB_RE = {
    "SPEC":  re.compile(r"speculative_prefetch \(moe_infinity/(distributed/expert_executor|memory/expert_prefetcher)\.py:"),
    "EAGER": re.compile(r"_dispatch_eager_local \(moe_infinity/"),
    "WAIT":  re.compile(r"wait_dispatch_local \(moe_infinity/"),
}
N_TORCH = ("libtorch_cpu.so", "libtorch_python.so", "libtorch_cuda.so", "libc10.so", "libgomp")
N_LIBC = ("libc.so", "libpthread", "librt.so", "libcuda.so", "cudaStreamSynchronize", "cudaMemcpy", "__intercept")
FAMS = ("PY_PREF", "PY_EXEC", "PY_OTH", "N_TORCH", "N_LIBC", "N_HEX", "N_OTH")

def classify_leaf(leaf):
    if ".py:" in leaf:
        if "memory/expert_prefetcher.py:" in leaf: return "PY_PREF"
        if "distributed/expert_executor.py:" in leaf: return "PY_EXEC"
        return "PY_OTH"
    if leaf.startswith("0x"): return "N_HEX"
    if any(t in leaf for t in N_TORCH): return "N_TORCH"
    if any(t in leaf for t in N_LIBC): return "N_LIBC"
    return "N_OTH"

def parse(path, sub_acc, whole_acc):
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
            fam = classify_leaf(frames[-1])
            whole_acc[fam] += c
            for name, rx in SUB_RE.items():
                if any(rx.search(fr) for fr in frames):
                    sub_acc[name]["n"] += c
                    sub_acc[name][fam] += c
    return n

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")
    files = {"LGC": sorted(glob.glob(os.path.join(out, "NAT_LGC*.pyspy"))),
             "SPEC": sorted(glob.glob(os.path.join(out, "NAT_SPEC*.pyspy")))}
    allp = files["LGC"] + files["SPEC"]
    if not files["LGC"] or not files["SPEC"] or any(os.path.getsize(p) == 0 for p in allp):
        print("DATA-FAIL: missing/empty pyspy files"); print("rc=4"); return 4
    acc = {a: {"whole": {k: 0 for k in FAMS},
               "sub": {s: {**{"n": 0}, **{k: 0 for k in FAMS}} for s in SUB_RE}} for a in files}
    tot = {}
    for arm, paths in files.items():
        tot[arm] = sum(parse(p, acc[arm]["sub"], acc[arm]["whole"]) for p in paths)
    combined = tot["LGC"] + tot["SPEC"]
    src = open(os.path.join(out, "SRC_HEAD.txt")).read().strip() if os.path.exists(os.path.join(out, "SRC_HEAD.txt")) else ""

    lines = ["exp768 named-subtree decomposition (native attribution, sealed exp767 stacks)",
             f"samples: LGC={tot['LGC']} SPEC={tot['SPEC']} combined={combined}",
             f"SRC_HEAD={src[:12]}",
             "subtree thread-secs totals (LGC -> SPEC, delta):"]
    def sub_secs(arm, s): return acc[arm]["sub"][s]["n"] / RATE_HZ
    Ds_map = {s: sub_secs("SPEC", s) - sub_secs("LGC", s) for s in SUB_RE}
    for s in ("SPEC", "EAGER", "WAIT"):
        lines.append(f"  {s:5s} {sub_secs('LGC', s):8.3f} -> {sub_secs('SPEC', s):8.3f}  D={Ds_map[s]:+8.3f}")
    lines.append("subtree per-family detail (secs):")
    for s in ("SPEC", "EAGER", "WAIT"):
        row = {k: (acc["SPEC"]["sub"][s][k] - acc["LGC"]["sub"][s][k]) / RATE_HZ for k in FAMS}
        lines.append(f"  {s:5s} deltas {json.dumps({k: round(v, 3) for k, v in row.items() if v})}")
    lines.append("whole-process family deltas (covariate, no gates):")
    wd = {k: (acc["SPEC"]["whole"][k] - acc["LGC"]["whole"][k]) / RATE_HZ for k in FAMS}
    lines.append(f"  {json.dumps({k: round(v, 2) for k, v in wd.items()})}")
    lines.append(f"total attributed delta = {(tot['SPEC'] - tot['LGC']) / RATE_HZ:+.3f} thread-secs")
    floor_ok = all(acc[a]["sub"][s]["n"] >= MIN_SUBTREE for a in acc for s in SUB_RE)
    De, Ds, Dw = Ds_map["EAGER"], Ds_map["SPEC"], Ds_map["WAIT"]

    if not src.startswith(SRC_OK):
        lines.append(f"IDENTIFY-FAIL: SRC_HEAD {src[:12]!r} != {SRC_OK}"); rc = 9
    elif combined < MIN_COMBINED or not floor_ok:
        bad = [f"{a}:{s}:{acc[a]['sub'][s]['n']}" for a in acc for s in SUB_RE if acc[a]["sub"][s]["n"] < MIN_SUBTREE]
        lines.append(f"INCONCLUSIVE: combined={combined} floor-fails={bad}"); rc = 3
    elif De >= TAU_S:
        lines.append(f"D1 EAGER-COST: De {De:+.3f} >= tau -> successor exp769 eager restructure"); rc = 1
    elif Ds >= TAU_S and Dw <= -TAU_S:
        lines.append(f"D2 MIGRATION: Ds {Ds:+.3f} >= tau, Dw {Dw:+.3f} <= -tau -> successor exp769 spec-subtree native repair"); rc = 2
    elif abs(De) < TAU_S and abs(Ds) < TAU_S and abs(Dw) < TAU_S:
        lines.append(f"D3 NET-NULL: |De|{De:+.3f} |Ds|{Ds:+.3f} |Dw|{Dw:+.3f} all < tau -> wall cost invisible to in-process 100Hz native sampling; "
                     f"successor exp769 unprofiled OS-counter differential (page-faults, ctx-switches, per-thread CPU, RSS)")
        rc = 5
    else:
        lines.append(f"D4 MIXED: De {De:+.3f} Ds {Ds:+.3f} Dw {Dw:+.3f} -> successor exp769 ranked by magnitude"); rc = 6
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(vdir, "verdict768.txt"), "w").write(txt + "\n")
    print(f"rc={rc}")
    return rc

if __name__ == "__main__":
    sys.exit(main())

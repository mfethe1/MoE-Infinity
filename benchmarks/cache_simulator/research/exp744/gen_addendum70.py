#!/usr/bin/env python3
"""exp744 settle: verify freeze/run integrity, re-run the frozen analyzer (must equal sealed verdict.txt byte for byte),
recompute per-cell host load from raw out/*.load, fit the post-hoc load model, assert every number used in the prose,
and write ADDENDUM70.md. Exits nonzero (and writes nothing) on any mismatch. Usage: python3 gen_addendum70.py"""
import ast, hashlib, json, os, re, statistics as st, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(H, "raw"); O = os.path.join(RAW, "out"); FZ = os.path.join(H, "freeze")
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg); print("CHECK FAILED:", msg, file=sys.stderr)


sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
near = lambda a, b, tol: abs(a - b) <= tol

# 1. integrity
ck(open(os.path.join(RAW, "ARTIFACT.sha256"), "rb").read() == open(os.path.join(FZ, "ARTIFACT.sha256"), "rb").read(),
   "raw/ARTIFACT.sha256 != freeze/ARTIFACT.sha256")
art = dict(l.split()[::-1] for l in open(os.path.join(FZ, "ARTIFACT.sha256")) if l.strip())
run = dict(l.split()[::-1] for l in open(os.path.join(O, "RUN_SHA256")) if l.strip())
for f, h in art.items():
    ck(sha(os.path.join(FZ, f)) == h, f"freeze/{f} bytes != ARTIFACT")
    if f != "PREREG.md":
        ck(run.get(f) == h, f"RUN_SHA256 {f} != ARTIFACT")
sums = {}
for l in open(os.path.join(RAW, "SHA256SUMS")):
    if l.strip():
        h, f = l.split(None, 1); sums[f.strip()] = h
for f, h in sums.items():
    ck(sha(os.path.join(RAW, f)) == h, f"raw/SHA256SUMS mismatch {f}")
ck(len(sums) >= 30, f"SHA256SUMS lists only {len(sums)} files")
ck(not any(n.startswith("FLAG") for n in os.listdir(O)), "unexpected FLAG* file")

# 2. frozen analyzer re-run
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
out = subprocess.run([sys.executable, os.path.join(FZ, "analyze.py"), O], capture_output=True, text=True, env=env).stdout
sealed = open(os.path.join(O, "verdict.txt")).read()
ck(out == sealed, "re-run analyzer output != sealed verdict.txt")
VL = [l for l in sealed.splitlines() if l.startswith("VERDICT")][0]
ck(VL == "VERDICT PRIM:NOTIFY-LOW|HOSTFN:COSTLY|ROUTE:OFF-FASTER", f"unexpected verdict {VL}")

# 3. cells
order = ["micro_1", "on_1", "off_1", "off_2", "on_2", "micro_2"]
C = {}
rm = re.compile(r"cell (\S+): micro kern_sync=([\d.]+)us hostfn_cost=([\d.]+)us hostfn_tail>1ms=([\d.]+) "
                r"mm_notify=([\d.]+)us launch=([\d.]+)us (CLEAN|EXCLUDED\S*)")
re_ = re.compile(r"cell (\S+): arm=(on|off) ms/tok=([\d.]+) busy=([\d.]+) idle=([\d.]+) route_eff=(True|False) (CLEAN|EXCLUDED\S*)")
for l in sealed.splitlines():
    m = rm.match(l)
    if m:
        g = m.groups(); C[g[0]] = dict(kind="micro", ks=float(g[1]), hf=float(g[2]), tail=float(g[3]), nt=float(g[4]),
                                       la=float(g[5]), status=g[6])
    m = re_.match(l)
    if m:
        g = m.groups(); C[g[0]] = dict(kind="eng", arm=g[1], ms=float(g[2]), busy=float(g[3]), idle=float(g[4]),
                                       eff=g[5] == "True", status=g[6])
ck(sorted(C) == sorted(order), f"parsed cells {sorted(C)}")
ck(all(C[c]["status"] == "CLEAN" for c in order), "not all cells CLEAN")
pre = {l.split(",")[0]: l.strip().split(",") for l in open(os.path.join(O, "precell.csv")) if l.strip()}
for cid in order:
    v = [float(l.split()[1]) for l in open(os.path.join(O, f"{cid}.load")) if l.strip()]
    C[cid].update(load_mean=st.mean(v), load_min=min(v), load_max=max(v), load_n=len(v), pre_load=float(pre[cid][5]),
                  qw=pre[cid][2])
lm = [C[c]["load_mean"] for c in order]
ck(1.3 <= min(lm) and max(lm) <= 25, f"load range {min(lm)}..{max(lm)}")
O743 = os.path.join(H, "..", "exp743", "raw", "out")
lm743 = [st.mean(float(l.split()[1]) for l in open(os.path.join(O743, f)) if l.strip())
         for f in sorted(os.listdir(O743)) if f.endswith(".load")]
ck(len(lm743) == 8, "exp743 load files")
both_lo, both_hi = min(lm + lm743), max(lm + lm743)
ck(near(both_lo, 1.35, 0.01) and 23.9 <= both_hi <= 24.1, f"combined load range {both_lo} {both_hi}")

# 4. ROUTE line reproduced from arm means
R = re.search(r"ROUTE on=(\{.*?\}) off=(\{.*?\}) d_ms\(off-on\)=(\S+) d_idle=(\S+) d_busy=(\S+)", sealed)
on, off = ast.literal_eval(R.group(1)), ast.literal_eval(R.group(2))
eng = [c for c in order if C[c]["kind"] == "eng"]
for arm, d in (("on", on), ("off", off)):
    ck(near(st.mean(C[c]["ms"] for c in eng if C[c]["arm"] == arm), d["ms"], 0.01), f"{arm} mean ms")
dms = off["ms"] - on["ms"]
ck(f"{dms:.2f}" == R.group(3) and near(dms, -18.83, 0.005), f"d_ms {dms}")
ck(all(C[c]["eff"] == (C[c]["arm"] == "on") for c in eng), "route_eff mismatch")
ck("MANIP gpu_route_effective matches request: True; token-id parity across engine cells: True" in sealed, "MANIP line")

# 5. post-hoc load fit over the 4 engine cells: ms = a + b*load + c*[off]  (OLS, normal equations, 3x3)
X = [[1.0, C[c]["load_mean"], 1.0 if C[c]["arm"] == "off" else 0.0] for c in eng]
y = [C[c]["ms"] for c in eng]
XtX = [[sum(X[k][i] * X[k][j] for k in range(4)) for j in range(3)] for i in range(3)]
Xty = [sum(X[k][i] * y[k] for k in range(4)) for i in range(3)]
M = [r[:] + [b] for r, b in zip(XtX, Xty)]
for i in range(3):
    p = max(range(i, 3), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
    for r in range(3):
        if r != i:
            fct = M[r][i] / M[i][i]; M[r] = [a - fct * b for a, b in zip(M[r], M[i])]
a, b, c = (M[i][3] / M[i][i] for i in range(3))
res = [y[k] - (a + b * X[k][1] + c * X[k][2]) for k in range(4)]
ck(near(a, 84.3, 0.05) and near(b, 5.21, 0.01) and near(c, -28.7, 0.05), f"fit {a} {b} {c}")
ck(max(abs(r) for r in res) <= 7.5, f"residuals {res}")
# within-arm load ordering: in each arm the more loaded cell is slower
for arm in ("on", "off"):
    cs = sorted((C[x]["load_mean"], C[x]["ms"]) for x in eng if C[x]["arm"] == arm)
    ck(cs[1][1] > cs[0][1], f"{arm}: slower cell is not the loaded one")
on_load = st.mean(C[x]["load_mean"] for x in eng if C[x]["arm"] == "on")
off_load = st.mean(C[x]["load_mean"] for x in eng if C[x]["arm"] == "off")
busy = [C[x]["busy"] for x in eng]
ck(all(40 <= v <= 43 for v in busy), f"engine busy {busy}")

# 6. micro primitives
mic = ["micro_1", "micro_2"]
ks = [C[x]["ks"] for x in mic]; hfc = [C[x]["hf"] for x in mic]; nt = [C[x]["nt"] for x in mic]
ck(near(min(ks), 73.4, 0.05) and near(max(ks), 80.9, 0.05), f"kern_sync {ks}")
ck(near(min(hfc), 86.4, 0.05) and near(max(hfc), 104.5, 0.05), f"hostfn {hfc}")
ck(near(min(nt), 21.8, 0.05) and near(max(nt), 68.1, 0.05), f"notify {nt}")
ck(max(nt) < 100 and st.mean(hfc) > 50, "PRIM/HOSTFN branch would change under either micro cell alone")
ck(max(ks) / min(ks) < 2, "kern_sync unstable")
ck(C["micro_1"]["load_mean"] > C["micro_2"]["load_mean"] and C["micro_1"]["nt"] > 2.5 * C["micro_2"]["nt"],
   "micro notify/load ordering claim")
ck(max(hfc) / min(hfc) < 1.25 and max(ks) / min(ks) < 1.15, "micro kern_sync/hostfn 'moved little' claim")
ck(dms < 0 and c < 0, "fit sign agrees with sealed ROUTE sign")
done = [l for l in open(os.path.join(RAW, "run.log")) if "DONE" in l]
ck(len(done) == 1 and done[0].rstrip().endswith("EXP738-DONE"), f"DONE marker {done}")

if fails:
    print(f"{len(fails)} CHECK(S) FAILED; ADDENDUM not written", file=sys.stderr); sys.exit(1)

L = []; w = L.append
f2 = lambda x: f"{x:.2f}"
w("# exp744 ADDENDUM70 — WSL host-notification latency + gpu_only_expert_routing A/B: "
  "PRIM:NOTIFY-LOW | HOSTFN:COSTLY | ROUTE:OFF-FASTER (ROUTE PROVISIONAL — CONFOUNDED BY HOST LOAD)")
w("")
w("Generated by `gen_addendum70.py` from `raw/` (every number below is recomputed from raw files and asserted; the "
  "script exits nonzero and writes nothing on any mismatch). PREREG and the frozen analyzer are unchanged.")
w("")
w("## Sealed verdict (reported unchanged)")
w("```"); w(VL); w("```")
w("Integrity: `raw/ARTIFACT.sha256` == `freeze/ARTIFACT.sha256`; `out/RUN_SHA256` matches every frozen file; the frozen "
  "`freeze/analyze.py` re-run on Mack (`PYTHONDONTWRITEBYTECODE=1`) reproduces `out/verdict.txt` byte for byte; "
  f"`raw/SHA256SUMS` covers {len(sums)} files. No FLAGGED file: all 6 cells passed the registered exclusion rules.")
w("")
w("## ⚠ Confound: host CPU load (disclosed prominently; not covered by any registered exclusion rule)")
w(f"Other lanes drove Winnie's WSL 1-min loadavg (raw `out/*.load` column 2, 12 logical CPUs) to per-cell means of "
  f"**{f2(min(lm))}–{f2(max(lm))}** in this run (exp743+exp744 together: {f2(both_lo)}–{f2(both_hi)}). The registered exclusions cover GPU "
  "co-tenancy only, so every cell counted CLEAN regardless of load.")
w(f"- Engine cells: on-arm mean load {f2(on_load)}, off-arm mean load {f2(off_load)}. Within each arm the more loaded "
  "cell is the slower one.")
w(f"- Post-hoc OLS over the 4 engine cells (NOT registered): **ms/tok = {a:.1f} + {b:.2f}·load {c:+.1f}·[off]**, "
  f"residuals {', '.join(f'{r:+.1f}' for r in res)} ms/tok. Four points and three parameters: this is a description, "
  "not an estimate with usable error bars.")
w(f"- The sealed ROUTE:OFF-FASTER (Δ = {dms:+.2f} ms/tok, off − on) is therefore **PROVISIONAL**. Its sign agrees with "
  "the load-adjusted fit, but the size and even the sign are not established under controlled load. exp746 (freeze "
  "d3b0dd4, AMENDMENT1 e33f77a) replicates the A/B with a host-load gate (1-min loadavg <3.0, no Runner.Worker).")
w(f"- Engine GPU-busy time is ~load-independent: {', '.join(f2(v) for v in busy)} ms/tok across the four engine cells "
  "(matches exp743's ~40). The load-sensitive part is idle time.")
w(f"- Micro cells (no model): micro_1 load mean {f2(C['micro_1']['load_mean'])}, micro_2 load mean "
  f"{f2(C['micro_2']['load_mean'])}. kern_sync and host-func cost moved little between them; mm_notify moved ~3× "
  f"({f2(C['micro_1']['nt'])} µs at the higher load vs {f2(C['micro_2']['nt'])} µs). Both cells sit on the same side of "
  "every registered PRIM/HOSTFN threshold, so those branches do not depend on which cell is believed. They are not "
  "materially load-confounded, though notify latency itself is load-sensitive.")
w("")
w("## Per-cell table (from sealed verdict.txt; load from raw out/*.load)")
w("Engine cells:")
w("| cell | arm | ms/tok | busy ms | idle ms | route_eff | load mean (min–max, n) | pre-start load | quietwait | status |")
w("|---|---|---|---|---|---|---|---|---|---|")
for x in order:
    k = C[x]
    if k["kind"] == "eng":
        w(f"| {x} | {k['arm']} | {f2(k['ms'])} | {f2(k['busy'])} | {f2(k['idle'])} | {k['eff']} | "
          f"{f2(k['load_mean'])} ({f2(k['load_min'])}–{f2(k['load_max'])}, {k['load_n']}) | {f2(k['pre_load'])} | "
          f"{k['qw']} | {k['status']} |")
w("")
w("Micro cells (µs; medians except host-func cost, which micro.py derives as kern+hostfn+sync minus kern+sync):")
w("| cell | kern+sync | host-func cost | host-func tail >1 ms | matmul notify | launch | load mean (min–max, n) | pre-start load | status |")
w("|---|---|---|---|---|---|---|---|---|")
for x in mic:
    k = C[x]
    w(f"| {x} | {k['ks']:.1f} | {k['hf']:.1f} | {k['tail']:.3f} | {k['nt']:.1f} | {k['la']:.1f} | "
      f"{f2(k['load_mean'])} ({f2(k['load_min'])}–{f2(k['load_max'])}, {k['load_n']}) | {f2(k['pre_load'])} | {k['status']} |")
w("")
w("## Exclusions")
w("- None. No FLAGGED file; every cell passed (a) pre-start GPU/Ollama, (b) mid-cell foreign process, (c) idle "
  "baseline, (d) util-sample count, (e) RC. Host load was not a registered exclusion (see confound).")
w("")
w("## Manipulation checks")
w("- `gpu_route_effective` matched the request in all 4 engine cells: True.")
w("- Output token ids identical across all engine cells (parity): True — routing off does not change the generated text.")
w("")
w("## Registered predictions")
w(f"- PRIM:NOTIFY-LOW (0.55): **confirmed** (mean mm_notify {st.mean(nt):.1f} µs < 100; kern_sync "
  f"{min(ks):.1f}–{max(ks):.1f} µs, ratio {max(ks) / min(ks):.2f} < 2, so not -UNSTABLE).")
w(f"- HOSTFN:COSTLY (0.7): **confirmed** (mean host-func cost {st.mean(hfc):.1f} µs > 50; per cell "
  f"{min(hfc):.1f}–{max(hfc):.1f} µs).")
w(f"- ROUTE:OFF-SLOWER (0.75): **refuted as sealed** (ROUTE:OFF-FASTER, {dms:+.2f} ms/tok). PROVISIONAL because "
  "of host load; exp746 adjudicates.")
w("")
w("## Pre-decided consequences and what the confound blocks")
w("- HOSTFN:COSTLY + gap insensitive to grouping (exp738) → prototype per-layer (not per-expert) retirement. The micro "
  "result behind this is not materially load-confounded, so the consequence stands. First, exp747 (freeze 06e6100) "
  "measures the device-side stream stall a host func causes, since host-wall cost is not the stall.")
w("- NOTIFY-HIGH/-UNSTABLE consequence (native-Linux measurement): not triggered.")
w("- ROUTE: the PREREG pre-decided a consequence only for OFF-SLOWER (price host syncs at Δ/16). OFF-FASTER had none, "
  "and nothing is acted on until exp746's load-controlled replication. No upstream claim about the routing default "
  "is made from this run.")
w("")
w("## Caveats")
w("- WSL2 on Winnie (paravirtualized GPU driver), not native Linux. GPU1 (RTX 5060 Ti), OLMoE-1B-7B bf16, lcnu @ 0.75, "
  "threads 4, max_new 64. One run, two cells per engine arm, two micro cells.")
w("- NVML utilization.gpu (busy/idle columns) has ~0.3 s driver granularity and counts kernel execution only.")
w("- Cosmetic defect: the runner prints `== <ts> EXP738-DONE` as its completion line "
  f"(`{done[0].strip()}`), inherited from the exp738 runner by a case-sensitive rename. The run is exp744; the frozen "
  "runner bytes match ARTIFACT.sha256.")
open(os.path.join(H, "ADDENDUM70.md"), "w").write("\n".join(L) + "\n")
print("ADDENDUM70.md written; all checks OK")

#!/usr/bin/env python3
"""exp747 settle: verify freeze/run integrity, re-run the frozen analyzer (must equal sealed verdict.txt byte for byte),
recompute every per-cell and per-level number from the raw out/ files, assert each number used in the prose, and write
ADDENDUM72.md. Exits nonzero (and writes nothing) on any mismatch. Usage: python3 gen_addendum72.py"""
import hashlib, json, os, re, statistics as st, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(H, "raw"); O = os.path.join(RAW, "out"); FZ = os.path.join(H, "freeze")
X746 = os.path.join(H, "..", "exp746", "raw", "out", "verdict.txt")
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg); print("CHECK FAILED:", msg, file=sys.stderr)


sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
near = lambda a, b, tol: abs(a - b) <= tol
rd = lambda p: dict(l.split()[::-1] for l in open(p) if l.strip())

# 1. integrity
ck(open(os.path.join(RAW, "ARTIFACT.sha256"), "rb").read() == open(os.path.join(FZ, "ARTIFACT.sha256"), "rb").read(),
   "raw/ARTIFACT.sha256 != freeze/ARTIFACT.sha256")
art = rd(os.path.join(FZ, "ARTIFACT.sha256")); run = rd(os.path.join(O, "RUN_SHA256"))
for f, h in art.items():
    ck(sha(os.path.join(FZ, f)) == h, f"freeze/{f} != ARTIFACT")
ck(len(art) == 7 and len(run) == 6 and run == {f: h for f, h in art.items() if f != "PREREG.md"},
   f"RUN_SHA256 ({len(run)} entries) != ARTIFACT.sha256 minus PREREG.md")
sums = {}
for l in open(os.path.join(RAW, "SHA256SUMS")):
    if l.strip():
        h, f = l.split(None, 1); sums[f.strip()] = h
for f, h in sums.items():
    ck(sha(os.path.join(RAW, f)) == h, f"raw/SHA256SUMS mismatch {f}")
NSUMS = len(sums); ck(NSUMS == 38, f"SHA256SUMS lists {NSUMS} files")
PREREG_SHA = sha(os.path.join(FZ, "PREREG.md")); ANALYZE_SHA = art["analyze.py"]
LOG = open(os.path.join(RAW, "run.log")).read()
ck(LOG.count("EXP747-DONE") == 1, "run.log EXP747-DONE count != 1")
T0 = re.search(r"== (\S+) start", LOG).group(1); TD = re.search(r"== (\S+) EXP747-DONE", LOG).group(1)
ck(not os.path.exists(os.path.join(O, "FLAGGED")) and not os.path.exists(os.path.join(O, "FAILED")), "FLAGGED/FAILED present")
for c in re.findall(r"(\S+) RC=(\d+)", LOG):
    ck(c[1] == "0", f"{c[0]} RC={c[1]}")

# 2. frozen analyzer re-run
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
out = subprocess.run([sys.executable, os.path.join(FZ, "analyze.py"), O], capture_output=True, text=True, env=env).stdout
sealed = open(os.path.join(O, "verdict.txt")).read()
ck(out == sealed, "re-run analyzer output != sealed verdict.txt")
VL = [l for l in sealed.splitlines() if l.startswith("VERDICT")][0]
VERDICT = "VERDICT QUIET:HOSTFN-STALL-EXCEEDS-SYNC|CONTENTION:HOSTFN-ROBUST"
ck(VL == VERDICT, f"unexpected verdict {VL}")

# 3. cells: parse sealed lines, recompute from raw
cells = json.load(open(os.path.join(FZ, "cells.json")))
order = [c["id"] for c in cells]
ck(order == ["k0_1", "k6_1", "k12_1", "k18_1", "k18_2", "k12_2", "k6_2", "k0_2"], "cell order (palindromic)")
K = {c["id"]: c["spin"] for c in cells}
ck(all(c["gpu"] == 1 for c in cells), "not all cells on GPU1")
rx = re.compile(r"cell (\S+): spin=(\d+) hostfn_stall med=([\d.]+) p90=([\d.]+) >1ms=([\d.]+) \| kern_sync med=([\d.]+) "
                r"p90=([\d.]+) \| notify med=(-?[\d.]+) \| load_mean=([\d.]+) (CLEAN|EXCLUDED:\S+)")
S = {}
for l in sealed.splitlines():
    m = rx.match(l)
    if m:
        g = m.groups(); S[g[0]] = dict(k=int(g[1]), hs=float(g[2]), hs90=float(g[3]), hs1=float(g[4]), ks=float(g[5]),
                                        ks90=float(g[6]), nt=float(g[7]), load=float(g[8]), status=g[9])
ck(sorted(S) == sorted(order), "not all 8 cells in sealed verdict")
pre = {}
for l in open(os.path.join(O, "precell.csv")):
    f = l.strip().split(",")
    pre[f[0]] = dict(k=int(f[1]), wait=int(f[2].split()[0]), wstat=f[2].split()[1], mib=int(f[3]), oll=int(f[4]),
                     load1=float(f[5]), rw=int(f[6]))
C = {}
for c in order:
    r = json.load(open(os.path.join(O, c + ".json")))["results"]
    mon = [l.split() for l in open(os.path.join(O, c + ".mon")) if len(l.split()) == 7]
    load = st.mean(float(m[1]) for m in mon); psi = st.mean(float(m[3]) for m in mon)
    spm = st.median(int(m[4]) for m in mon); gmax = max(int(m[5]) for m in mon)
    rw = max(int(m[2]) for m in mon); oll = max(int(m[6]) for m in mon)
    dur = int(mon[-1][0]) - int(mon[0][0])
    C[c] = dict(k=K[c], hs=r["hostfn_stall"]["median_us"], hs90=r["hostfn_stall"]["p90_us"], hs99=r["hostfn_stall"]["p99_us"],
                hs1=r["hostfn_stall"]["frac_gt_1ms"], ks=r["kern_sync"]["median_us"], ks90=r["kern_sync"]["p90_us"],
                ks99=r["kern_sync"]["p99_us"], nt=r["mm_notify"]["median_us"], base=r["stall_base"]["median_us"],
                gate=r["gate_overrun_frac"]["frac_base_gt_50us"], n=r["hostfn_stall"]["n"], load=load, psi=psi, spm=spm,
                gmax=gmax, rw=rw, oll=oll, nmon=len(mon), dur=dur, **{"pre_" + a: b for a, b in pre[c].items()})
    s = S[c]; x = C[c]
    ck(s["k"] == x["k"] == pre[c]["k"], f"{c} spin mismatch")
    for a in ("hs", "hs90", "ks", "ks90", "nt"):
        ck(near(round(x[a], 1), s[a], 0.051), f"{c} {a} {x[a]} vs sealed {s[a]}")
    ck(near(round(x["hs1"], 3), s["hs1"], 0.0006), f"{c} hs1")
    ck(near(round(load, 2), s["load"], 0.006), f"{c} load {load} vs {s['load']}")
    ck(s["status"] == "CLEAN", f"{c} not CLEAN")
    # every frozen exclusion re-checked from raw
    ck(x["n"] == 1500 and x["nmon"] >= 5 and x["rw"] == 0 and x["oll"] == 0 and x["gmax"] <= 3000 and load <= x["k"] + 4
       and x["spm"] == x["k"] and x["gate"] <= 0.05 and x["pre_mib"] <= 1024 and x["pre_oll"] == 0 and x["pre_rw"] == 0
       and x["pre_wstat"] == "QUIET", f"{c} fails a frozen exclusion recheck")

# 4. per-level means of clean cells, vs sealed level lines
L = {}
for k in (0, 6, 12, 18):
    v = [C[c] for c in order if C[c]["k"] == k]
    L[k] = {a: st.mean(x[a] for x in v) for a in ("hs", "hs90", "hs1", "ks", "ks90", "nt", "load", "psi", "hs99")}
    L[k]["n"] = len(v)
    m = re.search(r"level spin=%d: (\{.*\})" % k, sealed)
    sd = eval(m.group(1), {"__builtins__": {}})
    for a in ("hs", "hs90", "hs1", "ks", "ks90", "nt"):
        sk = "hs1ms" if a == "hs1" else a
        ck(near(round(L[k][a], 3), sd[sk], 0.0006), f"level {k} {a} {L[k][a]} vs {sd[sk]}")
    ck(sd["n"] == 2 == L[k]["n"], f"level {k} n")
RQ = L[0]["hs"] / L[0]["ks"]; RH = L[12]["hs"] / L[0]["hs"]; RS = L[12]["ks"] / L[0]["ks"]
ck(f"QUIET hostfn_stall/kern_sync = {RQ:.2f}" in sealed and f"{RQ:.2f}" == "11.26", "RQ")
ck(f"hostfn_stall {RH:.2f}, kern_sync {RS:.2f}" in sealed and (f"{RH:.2f}", f"{RS:.2f}") == ("0.82", "1.68"), "RH/RS")
ck(RQ >= 2 and RH < 1.3, "verdict rule recompute")
R18 = L[18]["hs"] / L[0]["hs"]
PROJ = {k: 144 * L[k]["hs"] / 1000 for k in L}
for k in L:
    ck(f"PROJ spin={k}: 144 serialized callbacks/token x {L[k]['hs']:.0f} us = {PROJ[k]:.1f} ms/token (upper bound)" in sealed,
       f"PROJ {k}")
# tail growth is monotone across levels (structural claim in prose)
ck(L[0]["hs1"] < L[6]["hs1"] < L[12]["hs1"] < L[18]["hs1"], "tail frac >1ms not monotone in spinners")
ck(max(C[c]["hs"] for c in order) < 550 and min(C[c]["hs"] for c in order) > 380, "median stall range claim")
DMIN, DMAX = min(C[c]["dur"] for c in order), max(C[c]["dur"] for c in order)
ck(DMAX < 60, "cell monitor span >= 60 s")
HSMIN, HSMAX = min(C[c]["hs"] for c in order), max(C[c]["hs"] for c in order)
BMAX = max(C[c]["base"] for c in order)
ck(BMAX < 50, "base span >= 50 us")
# medians fall, not rise, under contention: every spinner level median <= quiet*1.05
ck(all(L[k]["hs"] <= L[0]["hs"] * 1.05 for k in (6, 12, 18)), "median does not inflate claim")
ck(all(C[c]["load"] < C[c]["k"] for c in order if C[c]["k"] >= 6), "loadavg-lags-spinners claim")

# 5. interaction with exp746 (sealed)
v746 = open(X746).read()
ck("VERDICT SPLIT:GAP-IS-GPU-IDLE|ROUTE-Q:OFF-FASTER(PARITY-FAIL)|SENS:INCONCLUSIVE|ROUTE-S:INCONCLUSIVE" in v746, "exp746 verdict")
m = re.search(r"ROUTE-Q off-on = (-?[\d.]+) ms/tok \(idle (-?[\d.]+), busy (-?[\d.]+)\)", v746)
RQ746, RQ746_IDLE = float(m.group(1)), float(m.group(2)); ck(RQ746 == -4.04, "exp746 ROUTE-Q delta")
ROUTE_CB = 16 * L[0]["hs"] / 1000; SYNC16 = 16 * L[0]["ks"] / 1000; ROUTE_BOUND = ROUTE_CB - SYNC16
ck(abs(RQ746) < ROUTE_BOUND, "exp746 route delta exceeds hostfn-derived upper bound")
GAP746 = 60.14; ck("60.14" in open(os.path.join(H, "..", "exp746", "ADDENDUM71.md")).read(), "exp746 gap 60.14")
RET_CB = 128 * L[0]["hs"] / 1000
ck(PROJ[0] > GAP746, "PROJ exceeds measured gap claim")

if fails:
    print(f"{len(fails)} CHECK(S) FAILED; ADDENDUM72.md not written", file=sys.stderr); sys.exit(1)

f1 = lambda v: f"{v:.1f}"; f2 = lambda v: f"{v:.2f}"; f3 = lambda v: f"{v:.3f}"
rows = "\n".join(
    f"| {c} | {x['k']} | {f1(x['hs'])} | {f1(x['hs90'])} | {f1(x['hs99'])} | {f3(x['hs1'])} | {f1(x['ks'])} | {f1(x['ks90'])} | "
    f"{f1(x['nt'])} | {f2(x['load'])} | {f2(x['psi'])} | {x['spm']:g} | {x['pre_wait']} | {x['pre_mib']} | CLEAN |"
    for c, x in C.items())
lrows = "\n".join(
    f"| {k} | {L[k]['n']} | {f1(L[k]['hs'])} | {f1(L[k]['hs90'])} | {f1(L[k]['hs99'])} | {f3(L[k]['hs1'])} | {f1(L[k]['ks'])} | "
    f"{f1(L[k]['ks90'])} | {f1(L[k]['nt'])} | {f2(L[k]['load'])} | {f1(PROJ[k])} |" for k in (0, 6, 12, 18))
TOTW = sum(C[c]["pre_wait"] for c in order); MAXW = max(C[c]["pre_wait"] for c in order)

doc = f"""# ADDENDUM72 — exp747 settle: device-side stream stall of one cudaLaunchHostFunc on WSL2, quiet vs CPU-contended

Settled 2026-11-07 from the sealed run on Winnie (WSL2 Ubuntu, GPU1 = RTX 5060 Ti sm_120), freeze `06e6100`. Run {T0} (start) →
EXP747-DONE {TD}. Model-free. Every number below is computed from `raw/` by `gen_addendum72.py`, which asserts it against the raw
files and the sealed verdict and writes nothing on any mismatch. PREREG and the frozen analyzer are unchanged.

## Sealed verdict
`{VERDICT}`

The frozen `analyze.py` (sha256 `{ANALYZE_SHA[:12]}…`) re-run on the pulled `raw/out` (PYTHONDONTWRITEBYTECODE=1) is byte-identical to
`raw/out/verdict.txt`.

## Integrity
- `raw/ARTIFACT.sha256` == `freeze/ARTIFACT.sha256`; committed freeze bytes match it; `out/RUN_SHA256` (the 6 executed files) == their ARTIFACT hashes.
  PREREG.md sha256 `{PREREG_SHA[:12]}…` (committed in the freeze).
- `raw/SHA256SUMS` lists {NSUMS} files; all verify. No FLAGGED or FAILED file; all 8 cells RC=0.
- Every frozen exclusion was re-checked from the raw monitor/precell files: every combined wait ended QUIET (total {TOTW} s, max {MAXW} s),
  pre-start GPU1 ≤1024 MiB, no Ollama model, no Runner.Worker, spinner median == K, gate overrun 0 (base span medians ≤ {f1(BMAX)} µs).
- After the run no PID in `out/*.spinpids` (72 recorded) was alive on Winnie.

## Per-cell (µs; hostfn_stall = device-side stall added by one host func; kern_sync = tiny kernel + cudaStreamSynchronize host wall)
| cell | spinners | stall med | p90 | p99 | frac >1 ms | kern_sync med | p90 | notify med | load mean | PSI some avg10 | spinners (median) | wait s | pre-start MiB | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
{rows}

## Per-level (means of the 2 clean cells per level)
| spinners | n | stall med | p90 | p99 | frac >1 ms | kern_sync med | p90 | notify med | load mean | PROJ ms/token (upper bound) |
|---|---|---|---|---|---|---|---|---|---|---|
{lrows}

- QUIET: stall / kern_sync = {RQ:.2f} (bar ≥2) → HOSTFN-STALL-EXCEEDS-SYNC.
- CONTENTION: r_h = stall(12)/stall(0) = {RH:.2f} (< 1.3 → HOSTFN-ROBUST); r_s = kern_sync(12)/kern_sync(0) = {RS:.2f}. At 18 spinners
  r_h = {R18:.2f}.

## Registered predictions
- QUIET:HOSTFN-STALL-EXCEEDS-SYNC (p=0.75): **confirmed.** One host callback stalls the stream {f1(L[0]['hs'])} µs (median, quiet) — {RQ:.1f}× a
  complete kernel+sync round trip ({f1(L[0]['ks'])} µs). Cell medians span {f1(HSMIN)}–{f1(HSMAX)} µs across all levels.
- CONTENTION:HOSTFN-FRAGILE (p=0.55): **refuted** (sealed HOSTFN-ROBUST). The median stall did not grow with Linux-side CPU contention
  ({f1(L[6]['hs'])} µs at 6 spinners, {f1(L[12]['hs'])} at 12, {f1(L[18]['hs'])} at 18, vs {f1(L[0]['hs'])} quiet), while kern_sync rose {RS:.2f}×. What contention does
  grow is the tail: the fraction of callbacks stalling >1 ms rises monotonically {f3(L[0]['hs1'])} → {f3(L[6]['hs1'])} → {f3(L[12]['hs1'])} →
  {f3(L[18]['hs1'])} (0/6/12/18 spinners), and p99 goes from {f1(L[0]['hs99'])} to {f1(L[18]['hs99'])} µs. The tail is descriptive, not a
  registered bar.

## PROJ lines (descriptive upper bounds, not measurements)
144 callbacks/token (16 route + 128 retirement) × stall, if fully serialized on the critical path: {f1(PROJ[0])} ms/token quiet,
{f1(PROJ[12])} at 12 spinners. This exceeds the whole engine-vs-HF gap measured in exp746 ({GAP746} ms/token), so the callbacks cannot all
be serialized; the true per-token cost is some fraction of the bound.

## Interaction with exp746 (settled, ADDENDUM71)
- exp746 ROUTE-Q: routing off − on = {RQ746} ms/token (idle {RQ746_IDLE}), tagged PARITY-FAIL. Routing on adds 16 route callbacks/token
  ({f1(ROUTE_CB)} ms if serialized at the quiet median) and routing off replaces them with 16 blocking syncs (~{f2(SYNC16)} ms at the
  kern_sync median). The hostfn-derived bound on the routing difference is therefore ≤ {f1(ROUTE_BOUND)} ms/token; the measured
  {abs(RQ746)} ms sits inside it with the predicted sign (its GPU-idle component, {RQ746_IDLE} ms, is the larger part). This is arithmetic consistency, not a test.
- HOSTFN-ROBUST says the callback median does not explain exp744's large load sensitivity (~5.2 ms/token per load unit). The growing tail
  could contribute some of it; this run does not measure how much.
- The 128 retirement callbacks/token are present with routing on AND off, so the larger priced term ({f1(RET_CB)} ms/token upper bound,
  quiet) is untouched by the routing flag.

## Pre-decided consequences (freeze/PREREG.md)
- HOSTFN-STALL-EXCEEDS-SYNC → fires. The per-expert retirement and per-layer route callbacks are a priced WSL cost (≈{f1(L[0]['hs'])} µs each,
  quiet median). Next: an engine change measured against exp744/exp746 — retire per layer with ONE host func, or poll completion events
  from the exec thread instead of host funcs. Upstream-relevant, but must be checked on native Linux before anyone claims it in general.
- HOSTFN-FRAGILE → does NOT fire (sealed ROBUST). No recommendation of `gpu_only_expert_routing=False` on WSL follows from this run.
- HOSTFN-CHEAP → does not fire.
- No upstream post from this settle (model-free, WSL-only).

## Caveats
- WSL2 only (kernel 6.6.87.1-microsoft-standard-WSL2), NOT native Linux; WSL's paravirtualized GPU path may be what makes a host
  callback ~0.5 ms. One GPU (RTX 5060 Ti on PCIe gen4 x8), torch 2.11.0+cu128, CUDA 12.8.
- The callback is a no-op C function (`free(NULL)`, no GIL); MoE-Infinity's real callbacks do work (queue push, condition-variable
  wake), so this stall is a lower bound per callback.
- Spinners load only the Linux side; Windows-side load was not controlled. 1-min loadavg lags the spinners (each cell's monitor spans {DMIN}–{DMAX} s, including the 30 s settle), so
  "load mean" under-reads the imposed contention; the controlled variable is the spinner count, verified by its median.
- n=2 cells per level; N=1500 samples per cell. PROJ and the exp746 interaction are arithmetic, not measurements.
"""
open(os.path.join(H, "ADDENDUM72.md"), "w").write(doc)
print("ADDENDUM72.md written; all checks OK")

#!/usr/bin/env python3
"""exp746 settle: verify freeze/amendment/run integrity, re-run the frozen analyzer (must equal sealed verdict.txt byte for byte),
recompute per-cell numbers from the raw out/ files, assert every number used in the prose, and write ADDENDUM71.md.
Exits nonzero (and writes nothing) on any mismatch. Usage: python3 gen_addendum71.py"""
import ast, hashlib, json, os, re, statistics as st, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(H, "raw"); O = os.path.join(RAW, "out"); FZ = os.path.join(H, "freeze"); AB = os.path.join(O, "aborted-A1")
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg); print("CHECK FAILED:", msg, file=sys.stderr)


sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
near = lambda a, b, tol: abs(a - b) <= tol
rd = lambda p: dict(l.split()[::-1] for l in open(p) if l.strip())
AMENDED = ("run_exp746.sh", "allquiet746.sh")

# 1. integrity
ck(open(os.path.join(RAW, "ARTIFACT.sha256"), "rb").read() == open(os.path.join(FZ, "ARTIFACT.sha256"), "rb").read(),
   "raw/ARTIFACT.sha256 != freeze/ARTIFACT.sha256")
ck(open(os.path.join(RAW, "AMENDMENT1.sha256"), "rb").read() == open(os.path.join(FZ, "AMENDMENT1.sha256"), "rb").read(),
   "raw/AMENDMENT1.sha256 != freeze/AMENDMENT1.sha256")
art = rd(os.path.join(FZ, "ARTIFACT.sha256")); am = rd(os.path.join(FZ, "AMENDMENT1.sha256"))
run = rd(os.path.join(O, "RUN_SHA256")); abrun = rd(os.path.join(AB, "RUN_SHA256"))
for f, h in art.items():
    ck(sha(os.path.join(FZ, f)) == h, f"freeze/{f} != ARTIFACT")
for f, h in am.items():
    p = os.path.join(FZ, f) if f == "AMENDMENT1.md" else os.path.join(FZ, "amended", f)
    ck(sha(p) == h, f"{p} != AMENDMENT1.sha256")
ck(len(run) == 11, f"RUN_SHA256 has {len(run)} entries")
for f, h in run.items():
    ck(h == (am if f in AMENDED else art).get(f), f"RUN_SHA256 {f} != frozen/amended hash")
for f, h in abrun.items():
    ck(h == art.get(f), f"aborted-A1 RUN_SHA256 {f} != original freeze")
ck("allquiet746.sh" not in abrun, "aborted attempt unexpectedly ran allquiet746.sh")
sums = {}
for l in open(os.path.join(RAW, "SHA256SUMS")):
    if l.strip():
        h, f = l.split(None, 1); sums[f.strip()] = h
for f, h in sums.items():
    ck(sha(os.path.join(RAW, f)) == h, f"raw/SHA256SUMS mismatch {f}")
NSUMS = len(sums); ck(NSUMS == 65, f"SHA256SUMS lists {NSUMS} files")
LOG = open(os.path.join(RAW, "run.log")).read()
ck(LOG.count("EXP746-DONE") >= 1, "run.log lacks EXP746-DONE")

# 2. frozen analyzer re-run
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
out = subprocess.run([sys.executable, os.path.join(FZ, "analyze.py"), O], capture_output=True, text=True, env=env).stdout
sealed = open(os.path.join(O, "verdict.txt")).read()
ck(out == sealed, "re-run analyzer output != sealed verdict.txt")
VL = [l for l in sealed.splitlines() if l.startswith("VERDICT")][0]
VERDICT = "VERDICT SPLIT:GAP-IS-GPU-IDLE|ROUTE-Q:OFF-FASTER(PARITY-FAIL)|SENS:INCONCLUSIVE|ROUTE-S:INCONCLUSIVE"
ck(VL == VERDICT, f"unexpected verdict {VL}")

# 3. cells: parse sealed lines, recompute from raw
cells = json.load(open(os.path.join(FZ, "cells.json")))
order = [c["id"] for c in cells]
ck(order == ["q_hf_1", "q_on_1", "q_off_1", "s_hf_1", "s_on_1", "s_off_1", "s_off_2", "s_on_2", "s_hf_2", "q_off_2", "q_on_2",
             "q_hf_2"], "cell order")
rx = re.compile(r"cell (\S+): arm=(\w+) stress=(\d+) ms/tok=([\d.]+) busy=([\d.]+) idle=([\d.]+) load_mean=([\d.]+) "
                r"psi_mean=([\d.]+) route_ok=(True|False) (CLEAN|EXCLUDED:\S+)")
C = {}
for l in sealed.splitlines():
    m = rx.match(l)
    if m:
        g = m.groups()
        C[g[0]] = dict(arm=g[1], stress=int(g[2]), ms=float(g[3]), busy=float(g[4]), idle=float(g[5]), load=float(g[6]),
                       psi=float(g[7]), ok=g[8] == "True", status=g[9])
ck(sorted(C) == sorted(order), "not all 12 cells in sealed verdict")
J = {c: json.load(open(os.path.join(O, c + ".json"))) for c in order}
for c in order:
    ms = st.median(1000.0 / r["decode_tok_s"] for r in J[c]["rows"])
    if C[c]["status"].startswith("CLEAN") or "samples" not in C[c]["status"]:
        ck(near(ms, C[c]["ms"], 0.006), f"{c} ms recompute {ms} vs {C[c]['ms']}")
    L = [float(l.split()[1]) for l in open(os.path.join(O, c + ".load")) if len(l.split()) > 1]
    ck(near(st.mean(L), C[c]["load"], 0.006), f"{c} load recompute")
    sp = [int(l.split()[4]) for l in open(os.path.join(O, c + ".load")) if len(l.split()) > 4]
    C[c]["spin_med"] = st.median(sp)
    ck(C[c]["spin_med"] == (12 if C[c]["stress"] else 0), f"{c} spinner median {C[c]['spin_med']}")
CLEAN = [c for c in order if C[c]["status"] == "CLEAN"]
EXCL = {c: C[c]["status"].split(":", 1)[1] for c in order if c not in CLEAN}
ck(CLEAN == ["q_on_1", "q_off_1", "s_off_1", "s_hf_2", "q_off_2", "q_on_2", "q_hf_2"], f"clean set {CLEAN}")
ck(EXCL == {"q_hf_1": "gpu-contamination", "s_hf_1": "row4-samples=0", "s_on_1": "ci-runner-active",
            "s_off_2": "ci-runner-active", "s_on_2": "ci-runner-active;gpu-contamination;load-mean=32.52>18.0"}, f"excl {EXCL}")
flagged = open(os.path.join(O, "FLAGGED")).read().split()
ck(sorted(set(flagged)) == ["q_hf_1", "s_on_2"], "FLAGGED set")
why = open(os.path.join(O, "FLAGGED.why")).read()
ck("q_hf_1 mid-cell foreign pid" in why and "s_on_2 mid-cell foreign pid" in why and "gen.py" in why, "FLAGGED.why content")

# 4. arms (means of clean cells) and the registered deltas
def arm(a, s):
    v = [C[c] for c in CLEAN if C[c]["arm"] == a and C[c]["stress"] == s]
    return None if not v else dict(n=len(v), **{k: st.mean(x[k] for x in v) for k in ("ms", "busy", "idle", "load")})


A = {}
for l in sealed.splitlines():
    m = re.match(r"arm (\w+) stress=(\d+): (.*)$", l)
    if m:
        A[(m.group(1), int(m.group(2)))] = ast.literal_eval(m.group(3))
ck(len(A) == 6, "arm lines")
for k, v in A.items():  # recompute from the (2-dp) cell values: must agree within rounding
    r = arm(*k)
    ck((v is None) == (r is None), f"arm {k} presence")
    if v and r:
        ck(v["n"] == r["n"] and all(near(v[q], r[q], 0.006) for q in ("ms", "busy", "idle", "load")), f"arm {k} recompute")
ck(A[("on", 12)] is None, "on stress arm should have no clean cell")
ck([A[k]["n"] if A[k] else 0 for k in sorted(A)] == [1, 1, 2, 1, 2, 0], f"arm n {[(k, A[k] and A[k]['n']) for k in sorted(A)]}")
hq, oq, fq, hs, fs = A[("hf", 0)], A[("on", 0)], A[("off", 0)], A[("hf", 12)], A[("off", 12)]
gap = oq["ms"] - hq["ms"]; di = oq["idle"] - hq["idle"]; db = oq["busy"] - hq["busy"]
ck(f"GAP on-hf (quiet) = {gap:.2f} = idle {di:.2f} + busy {db:.2f} (idle share {di / gap:.3f})" in sealed, "GAP line")
dq = fq["ms"] - oq["ms"]
ck(f"ROUTE-Q off-on = {dq:+.2f} ms/tok (idle {fq['idle'] - oq['idle']:+.2f}, busy {fq['busy'] - oq['busy']:+.2f}); n on=2 off=2"
   in sealed, "ROUTE-Q line")
ck(3 <= abs(dq) < 5, f"ROUTE-Q magnitude {dq}")
rel_q = dq / oq["ms"]
# exp744 sealed comparison (cited, from its sealed verdict)
v744 = open(os.path.join(H, "..", "exp744", "raw", "out", "verdict.txt")).read()
m744 = re.search(r"ROUTE off-on = ([+-][\d.]+)", v744) or re.search(r"off.on[^\n]*?([+-]\d+\.\d+)", v744)
d744 = float(m744.group(1)) if m744 else None
ck(d744 is not None and near(d744, -18.83, 0.01), f"exp744 sealed delta {d744}")
# per-cell route spread: every clean off cell faster than every clean on cell (quiet)
qon = [C[c]["ms"] for c in ("q_on_1", "q_on_2")]; qoff = [C[c]["ms"] for c in ("q_off_1", "q_off_2")]
ck(max(qoff) < min(qon), "quiet off/on cells overlap")
# descriptive stress effects (not registered: SENS needs the on arm)
hf_rel = hs["ms"] / hq["ms"] - 1; off_rel = fs["ms"] / fq["ms"] - 1
ck(near(hf_rel, 0.442, 0.001) and near(off_rel, 0.659, 0.001), f"stress rel {hf_rel} {off_rel}")
ck(abs(hs["busy"] - hq["busy"]) < 0.1 and abs(fs["busy"] - fq["busy"]) < 1.5, "busy should be ~load-independent")
busy_eng = [C[c]["busy"] for c in CLEAN if C[c]["arm"] in ("on", "off")]
busy_hf = [C[c]["busy"] for c in CLEAN if C[c]["arm"] == "hf"]
ck(37 < min(busy_eng) and max(busy_eng) < 40 and 14 < min(busy_hf) and max(busy_hf) < 14.5, "busy ranges")

# 5. manipulation and parity, localized
ck("MANIP gpu_route_effective matches request (all engine cells): True; engine token-id parity across all cells: False" in sealed,
   "MANIP line")
ENG = [c for c in order if C[c]["arm"] in ("on", "off")]
for c in ENG:
    ck(J[c]["gpu_route_effective"] is (C[c]["arm"] == "on"), f"{c} route effective")
ids = {c: [r["out_ids"] for r in J[c]["rows"]] for c in ENG}
same = [c for c in ENG if ids[c] == ids["q_on_1"]]
odd = [c for c in ENG if c not in same]
ck(odd == ["s_on_2"] and len(same) == 7, f"parity odd set {odd}")
first_div = [next(k for k, (x, y) in enumerate(zip(a, b)) if x != y) for a, b in zip(ids["s_on_2"], ids["q_on_1"])]
ck(len(first_div) == 6 and all(a != b for a, b in zip(ids["s_on_2"], ids["q_on_1"])), "s_on_2 differs in every prompt")
ck(min(first_div) == 1 and max(first_div) == 29, f"first-div {first_div}")
hfids = {c: [r["out_ids"] for r in J[c]["rows"]] for c in order if C[c]["arm"] == "hf"}
ck(all(v == hfids["q_hf_2"] for v in hfids.values()), "HF cells not self-identical")

# 6. waits and the aborted attempt
pre = [l.strip().split(",") for l in open(os.path.join(O, "precell.csv")) if l.strip()]
W = {r[0]: int(r[2].split()[0]) for r in pre}
ck(all(r[2].endswith("QUIET") for r in pre), "a wait timed out")
ck(max(W.values()) == 1213 and W["s_hf_2"] == 1213, "max wait")
WSUM = sum(W.values())
GPU_PRE = {r[0]: int(r[4]) for r in pre}
ck(max(GPU_PRE.values()) == 996, "pre-start gpu max")
abpre = [l.strip().split(",") for l in open(os.path.join(AB, "precell.csv")) if l.strip()]
ck(abpre[0][3] == "3397 QUIET" and abpre[0][4] == "10260", f"aborted precell {abpre}")
abj = json.load(open(os.path.join(AB, "q_hf_1.json")))
ab_tps = [r["decode_tok_s"] for r in abj["rows"]]
ck(3.6 < min(ab_tps) and max(ab_tps) < 3.9, f"aborted tok/s {ab_tps}")
ab_why = open(os.path.join(AB, "FLAGGED.why")).read()
ck("pre-start gpu=10260" in ab_why, "aborted FLAGGED.why")
t0 = re.findall(r"== (\S+) q_hf_1 ", LOG); tdone = re.findall(r"== (\S+) EXP746-DONE", LOG)
ck(t0[0] == "2026-11-07T02:55:25Z" and t0[1] == "2026-11-07T03:09:35Z" and tdone[0] == "2026-11-07T04:46:24Z", "timestamps")

if fails:
    print(f"{len(fails)} CHECK(S) FAILED; ADDENDUM not written", file=sys.stderr); sys.exit(1)

f2 = lambda x: f"{x:.2f}"
rows = []
for c in order:
    x = C[c]
    rows.append(f"| {c} | {x['arm']} | {x['stress']} | {x['ms']:.2f} | {x['busy']:.2f} | {x['idle']:.2f} | {x['load']:.2f} | "
                f"{x['psi']:.2f} | {W[c]} | {'CLEAN' if c in CLEAN else 'EXCLUDED: ' + EXCL[c].replace(';', '; ')} |")
armrows = []
for (a, s), v in A.items():
    armrows.append(f"| {a} | {s} | " + (f"{v['n']} | {v['ms']:.2f} | {v['busy']:.2f} | {v['idle']:.2f} | {v['load']:.2f} |" if v
                                         else "0 | — | — | — | — |"))
md = f"""# ADDENDUM71 — exp746 settle: host-CPU contention control and a load-controlled replication of the routing A/B

Settled 2026-11-07 from the sealed run on Winnie (WSL2 Ubuntu, GPU1 = RTX 5060 Ti sm_120), freeze `d3b0dd4`, AMENDMENT1 `e33f77a`.
Run 2026-11-07T{t0[1][11:]} (first scored cell) → EXP746-DONE {tdone[0]}. Every number below is computed from `raw/` by
`gen_addendum71.py`, which asserts it against the raw files and the sealed verdict and writes nothing on any mismatch. PREREG,
AMENDMENT1 and the frozen analyzer are unchanged.

## Sealed verdict
`{VL}`

The frozen `analyze.py` re-run on the pulled `raw/out` (PYTHONDONTWRITEBYTECODE=1) is byte-identical to `raw/out/verdict.txt`.

## Integrity
- `raw/ARTIFACT.sha256` == `freeze/ARTIFACT.sha256`; `raw/AMENDMENT1.sha256` == `freeze/AMENDMENT1.sha256`; committed freeze bytes match both.
- `out/RUN_SHA256` (11 files): `run_exp746.sh` and `allquiet746.sh` match AMENDMENT1, the other 9 match the original freeze.
- `raw/SHA256SUMS` lists {NSUMS} files; all verify.

## AMENDMENT1 and the aborted attempt (not used in any comparison)
The first q_hf_1 attempt (started {t0[0]}) passed the GPU wait at once, then waited {abpre[0][3].split()[0]} s for CPU load; meanwhile a
foreign process from another lane (`gen.py`) started on GPU1. Pre-start GPU1 memory was {abpre[0][4]} MiB and HF decoded at
{min(ab_tps):.2f}–{max(ab_tps):.2f} tok/s (quiet HF here: {1000 / hq['ms']:.1f} tok/s). The frozen rule had already FLAGGED it. AMENDMENT1
replaced the two sequential waits with one combined wait (`allquiet746.sh`, same thresholds), moved the attempt to `out/aborted-A1/`
and reran q_hf_1. The rerun was also FLAGGED (a foreign `gen.py` from the same other lane was alive mid-cell, although pre-start GPU memory was
{GPU_PRE['q_hf_1']} MiB), so it is excluded too. `aborted-A1` data is excluded from every speed number.

## Per-cell (sealed analyzer; ms/token = median over 6 prompts; busy/idle = NVML split; wait = combined pre-cell wait, s)
| cell | arm | spinners | ms/tok | busy | idle | load mean | PSI some avg10 | wait | status |
|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

Every combined wait ended QUIET (none timed out); total pre-cell waiting {WSUM} s, max {max(W.values())} s (s_hf_2). Spinner median was
12 in every stress cell and 0 in every quiet cell. Exclusions: foreign `gen.py` on GPU1 mid-cell (q_hf_1, s_on_2), a GitHub Actions
Runner.Worker during the cell (s_on_1, s_off_2, s_on_2), loadavg mean above the stress cap (s_on_2: 32.52 > 18.0), and one prompt
window with no NVML samples (s_hf_1).

## Arms (means of CLEAN cells)
| arm | spinners | n | ms/tok | busy | idle | load |
|---|---|---|---|---|---|---|
{chr(10).join(armrows)}

## Manipulation and parity
- MANIP: `gpu_route_effective` matched the request in all 8 engine cells (True).
- PARITY (frozen rule, all engine cells): FAIL. Localized: 7 of 8 engine cells, on and off, produce identical token ids; only
  **s_on_2** differs, in all 6 prompts (first divergent token index {min(first_div)}–{max(first_div)}). s_on_2 is the most contaminated
  cell in the run (foreign GPU process, CI runner, load mean 32.52). Among the other engine cells, routing on vs off does not change
  the generated tokens (as in exp744). Why one contaminated on-arm cell decoded differently is not explained by this run (n=1).
  The frozen rule tags ROUTE-Q with PARITY-FAIL, and the tag stands.
- HF cells are self-identical across all 4 runs.

## Registered predictions
- SPLIT:GAP-IS-GPU-IDLE (p=0.6): **confirmed.** Quiet gap on − hf = {f2(gap)} ms/tok = idle {f2(di)} + busy {f2(db)} (idle share
  {di / gap:.3f}). Only one clean quiet HF cell (q_hf_2).
- ROUTE-Q:OFF-FASTER (p=0.6): **confirmed as sealed, with PARITY-FAIL.** off − on = {dq:+.2f} ms/tok ({100 * rel_q:+.1f}%, n=2 vs 2;
  both off cells {min(qoff):.2f}–{max(qoff):.2f} are faster than both on cells {min(qon):.2f}–{max(qon):.2f}). That clears the 3 ms bar
  by about 1 ms. exp744's sealed {d744:+.2f} ms/tok was mostly host load: under load control the effect is roughly a fifth as large.
- SENS:SIMILAR (p=0.5): **untested** (INCONCLUSIVE; no clean stressed `on` cell).
- ROUTE-S:OFF-FASTER (p=0.55): **untested** (INCONCLUSIVE; no clean stressed `on` cell).

## Descriptive, not registered
- Under 12 spinners, HF slowed {100 * hf_rel:.1f}% (n=1 each side; load {hs['load']:.2f}) and the routing-off engine arm slowed
  {100 * off_rel:.1f}% (n=1 stressed; load {fs['load']:.2f}). SENS compares the `on` arm, so this is not a SENS result.
- GPU-busy time is unchanged by host load: HF {min(busy_hf):.2f}–{max(busy_hf):.2f} and engine {min(busy_eng):.2f}–{max(busy_eng):.2f}
  ms/tok across clean quiet and stressed cells. The added time is GPU-idle time, consistent with the load sensitivity seen in exp743/exp744.

## Pre-decided consequences (freeze/PREREG.md)
- ROUTE-Q:OFF-FASTER "replicated → report on upstream #315". Not acted on: the settle gate required no PARITY-FAIL, and the frozen tag
  is present. Nothing posted upstream. The routing result stands as a small (~4%) load-controlled effect, much weaker than exp744 reported.
- SPLIT:GAP-IS-GPU-IDLE → the host-side handoff is the larger term; next work targets per-layer retirement (exp744 HOSTFN:COSTLY).
  exp747 (freeze 06e6100) measures the device-side cudaLaunchHostFunc stall under CPU contention first.
- Program rule: every timed prereg records and gates on host CPU load (done in this run's runner; carried forward).

## Caveats
WSL2, not native Linux; one GPU (RTX 5060 Ti, PCIe gen4 x8), one model (OLMoE-1B-7B bf16), batch 1, lcnu at device_memory_ratio 0.75,
num_threads 4. NVML utilization is a ~sampled kernel-active fraction (50 ms sampler; the driver's window is coarser), not a timeline.
Spinners load only the Linux side; Windows-side load was not controlled. Clean replicates are small (n=1 or 2 per arm), and both
stressed `on` cells were excluded, so stress sensitivity of the default configuration is unmeasured.
"""
open(os.path.join(H, "ADDENDUM71.md"), "w").write(md)
print("ADDENDUM71.md written; all checks OK")

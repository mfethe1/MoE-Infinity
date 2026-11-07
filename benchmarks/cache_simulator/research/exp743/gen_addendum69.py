#!/usr/bin/env python3
"""exp743 settle: verify freeze/run integrity, re-run the frozen analyzer (must equal sealed verdict.txt byte for byte),
recompute per-cell host load from raw out/*.load, assert every number used in the prose, and write ADDENDUM69.md.
Exits nonzero (and writes nothing) on any mismatch. Usage: python3 gen_addendum69.py"""
import hashlib, json, os, re, statistics as st, subprocess, sys
from collections import Counter

H = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(H, "raw"); O = os.path.join(RAW, "out"); FZ = os.path.join(H, "freeze")
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg); print("CHECK FAILED:", msg, file=sys.stderr)


sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
near = lambda a, b, tol: abs(a - b) <= tol

# 1. integrity: raw ARTIFACT == freeze ARTIFACT; RUN_SHA256 == freeze bytes; raw/SHA256SUMS
ck(open(os.path.join(RAW, "ARTIFACT.sha256"), "rb").read() == open(os.path.join(FZ, "ARTIFACT.sha256"), "rb").read(),
   "raw/ARTIFACT.sha256 != freeze/ARTIFACT.sha256")
art = dict(l.split()[::-1] for l in open(os.path.join(FZ, "ARTIFACT.sha256")) if l.strip())
run = dict(l.split()[::-1] for l in open(os.path.join(O, "RUN_SHA256")) if l.strip())
for f, h in art.items():
    ck(sha(os.path.join(FZ, f)) == h, f"freeze/{f} bytes != ARTIFACT")
    if f != "PREREG.md":
        ck(run.get(f) == h, f"RUN_SHA256 {f} != ARTIFACT")
sums = dict(l.split(None, 1)[::-1] for l in open(os.path.join(RAW, "SHA256SUMS")) if l.strip())
sums = {k.strip(): v for k, v in sums.items()}
for f, h in sums.items():
    ck(sha(os.path.join(RAW, f)) == h, f"raw/SHA256SUMS mismatch {f}")
ck(len(sums) >= 40, f"SHA256SUMS lists only {len(sums)} files")

# 2. frozen analyzer re-run == sealed verdict
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
out = subprocess.run([sys.executable, os.path.join(FZ, "analyze.py"), O], capture_output=True, text=True, env=env).stdout
sealed = open(os.path.join(O, "verdict.txt")).read()
ck(out == sealed, "re-run analyzer output != sealed verdict.txt")
VL = [l for l in sealed.splitlines() if l.startswith("VERDICT")][0]
ck(VL == "VERDICT GAP-IS-GPU-BUSY|GRP:INCONCLUSIVE|T1:IDLE-UP", f"unexpected verdict line {VL}")

# 3. per-cell values from the sealed analyzer lines
cells = json.load(open(os.path.join(FZ, "cells.json")))
order = [c["id"] for c in cells]
ck(order == ["hf_1", "t4_1", "grp_1", "t1_1", "t1_2", "grp_2", "t4_2", "hf_2"], f"cell order {order}")
C = {}
rx = re.compile(r"cell (\S+): arm=(\S+) t=(\d+) ms/tok=([\d.]+) busy_ms=([\d.]+) idle_ms=([\d.]+) busy_frac=([\d.]+) "
                r"base_util=(\S+) grouped_experts=(\d+) threads_eff=(\S+) (CLEAN|EXCLUDED:\S+)")
for l in sealed.splitlines():
    m = rx.match(l)
    if m:
        g = m.groups()
        C[g[0]] = dict(arm=g[1], t=int(g[2]), ms=float(g[3]), busy=float(g[4]), idle=float(g[5]), bf=float(g[6]),
                       base=g[7], grp=int(g[8]), thr=g[9], status=g[10])
ck(sorted(C) == sorted(order), "not every cell parsed from verdict.txt")

# 4. host load per cell: raw out/<cell>.load column 2 = WSL 1-min loadavg (12 logical CPUs), col 3 = Runner.Worker count
for cid in order:
    rows = [l.split() for l in open(os.path.join(O, f"{cid}.load")) if l.strip()]
    v = [float(r[1]) for r in rows]
    C[cid].update(load_mean=st.mean(v), load_min=min(v), load_max=max(v), load_n=len(v))
pre = {l.split(",")[0]: l.strip().split(",") for l in open(os.path.join(O, "precell.csv")) if l.strip()}
for cid in order:
    C[cid]["pre_load"] = float(pre[cid][5]); C[cid]["qw"] = pre[cid][2]; C[cid]["pre_mib"] = int(pre[cid][3])

# 5. exclusions from FLAGGED / FLAGGED.why
flagged = set(open(os.path.join(O, "FLAGGED")).read().split())
why = Counter((l.split()[0] + " mid-cell foreign GPU process (another lane's gen.py)") if "foreign pid" in l else l.strip()
              for l in open(os.path.join(O, "FLAGGED.why")) if l.strip())
reasons = {}
for k, n in why.items():
    cid = k.split()[0]; reasons.setdefault(cid, []).append(f"{k[len(cid) + 1:]} ×{n}")
ck(flagged == {"t4_1", "grp_1", "t1_2", "grp_2", "hf_2"}, f"flagged set {flagged}")
for cid in order:
    ck((C[cid]["status"] == "CLEAN") == (cid not in flagged), f"{cid} status vs FLAGGED disagree")
ck(any("ollama model loaded" in r for r in reasons["hf_2"]), "hf_2 exclusion reason is not the Ollama load")
ck(not any("foreign" in r for r in reasons["hf_2"]), "hf_2 also has a foreign pid")

# 6. assert the numbers the settle brief and the prose rely on (recomputed, not trusted)
ck(near(C["hf_1"]["ms"], 62.41, 0.005) and near(C["hf_2"]["ms"], 32.49, 0.005), "hf ms/tok")
ck(near(C["hf_1"]["load_mean"], 23.4, 0.05), f"hf_1 load mean {C['hf_1']['load_mean']}")
ck(near(C["hf_2"]["load_mean"], 1.35, 0.01), f"hf_2 load mean {C['hf_2']['load_mean']}")
lm = [C[c]["load_mean"] for c in order]
ck(near(min(lm), 1.35, 0.01) and 23.9 <= max(lm) <= 24.1, f"load mean range {min(lm)}..{max(lm)}")
ck(min(C[c]["load_min"] for c in order) >= 1.2 and max(C[c]["load_max"] for c in order) <= 36,
   "raw load sample range")
clean = [c for c in order if C[c]["status"] == "CLEAN"]
ck(clean == ["hf_1", "t1_1", "t4_2"], f"clean cells {clean}")
hf, t4, t1 = C["hf_1"], C["t4_2"], C["t1_1"]
import ast
A = {l.split()[1].rstrip(":"): ast.literal_eval(l.split(":", 1)[1].strip()) for l in sealed.splitlines() if l.startswith("arm ")}
for a, cid in (("hf", "hf_1"), ("t4", "t4_2"), ("t1", "t1_1")):
    ck(near(A[a]["ms"], C[cid]["ms"], 0.005) and A[a]["n"] == 1, f"arm {a} != cell {cid}")
ck(A["grp"] is None, "grp arm not None")
gap = A["t4"]["ms"] - A["hf"]["ms"]; d_idle = A["t4"]["idle"] - A["hf"]["idle"]; d_busy = A["t4"]["busy"] - A["hf"]["busy"]
ck(f"GAP t4-hf={gap:.2f} ms/tok = idle {d_idle:.2f} + busy {d_busy:.2f} (idle share {d_idle / gap:.3f})" in sealed,
   "sealed GAP line not reproduced from parsed cells")
# counterfactual pairing with the quiet (excluded) hf_2 -- post hoc, NOT the registered analysis
h2 = C["hf_2"]
gap2 = t4["ms"] - h2["ms"]; di2 = t4["idle"] - h2["idle"]; db2 = t4["busy"] - h2["busy"]; share2 = di2 / gap2
ck(near(share2, 0.59, 0.005), f"hf_2-paired idle share {share2}")
ck(di2 >= 0.5 * gap2, "hf_2 pairing would not cross the IDLE bar")
# HF load sensitivity (two HF cells, post hoc)
hf_slope = (C["hf_1"]["ms"] - h2["ms"]) / (C["hf_1"]["load_mean"] - h2["load_mean"])
ck(1.2 <= hf_slope <= 1.6, f"hf slope {hf_slope}")
# busy ms is ~load-independent among cells with no foreign GPU process (t4_1 had one)
nofg = [c for c in order if not any("foreign" in r for r in reasons.get(c, []))]
eng_busy = [C[c]["busy"] for c in nofg if C[c]["arm"] in ("eng", "grp")]
hf_busy = [C[c]["busy"] for c in nofg if C[c]["arm"] == "hf"]
ck(nofg == ["hf_1", "t1_1", "t4_2", "hf_2"], f"no-foreign-GPU cells {nofg}")
ck(all(38 <= b <= 42 for b in eng_busy) and all(14 <= b <= 16 for b in hf_busy), f"busy {eng_busy} {hf_busy}")
# T1 vs t4 load gap (the T1 branch is load-confounded too)
t1_dl = t1["load_mean"] - t4["load_mean"]
ck(t1_dl > 9, f"t1-t4 load gap {t1_dl}")
ck("T1 vs t4: d_ms=+53.66 d_idle=+57.96 d_busy=-1.62" in sealed, "T1 line")
ck("MANIP threads_effective==requested: True; grouped engaged only in grp: True" in sealed, "manip line")
done = [l for l in open(os.path.join(RAW, "run.log")) if "DONE" in l]
ck(len(done) == 1 and done[0].rstrip().endswith("EXP738-DONE"), f"DONE marker {done}")
ck("EXP743-DONE" not in open(os.path.join(RAW, "run.log")).read(), "unexpected EXP743-DONE")

if fails:
    print(f"{len(fails)} CHECK(S) FAILED; ADDENDUM not written", file=sys.stderr); sys.exit(1)

# ---- write ----
L = []; w = L.append
f2 = lambda x: f"{x:.2f}"
w("# exp743 ADDENDUM69 — GPU-busy vs GPU-idle split of the engine's per-token overhead: "
  "GAP-IS-GPU-BUSY (CONFOUNDED BY HOST LOAD — NOT RELIED UPON)")
w("")
w("Generated by `gen_addendum69.py` from `raw/` (every number below is recomputed from raw files and asserted; the "
  "script exits nonzero and writes nothing on any mismatch). PREREG and the frozen analyzer are unchanged.")
w("")
w("## Sealed verdict (reported unchanged)")
w("```"); w(VL); w("```")
w("Integrity: `raw/ARTIFACT.sha256` == `freeze/ARTIFACT.sha256`; `out/RUN_SHA256` matches every frozen file; the frozen "
  "`freeze/analyze.py` re-run on Mack (`PYTHONDONTWRITEBYTECODE=1`) reproduces `out/verdict.txt` byte for byte; "
  f"`raw/SHA256SUMS` covers {len(sums)} files.")
w("")
w("## ⚠ Confound: host CPU load (disclosed prominently; not covered by any registered exclusion rule)")
w(f"Other lanes drove Winnie's WSL 1-min loadavg (raw `out/*.load` column 2, 12 logical CPUs) from a per-cell mean of "
  f"**{f2(min(lm))}** to **{f2(max(lm))}** across cells (individual samples {f2(min(C[c]['load_min'] for c in order))}–"
  f"{f2(max(C[c]['load_max'] for c in order))}). The PREREG's exclusions cover GPU co-tenancy only, so load was never gated.")
w(f"- The CLEAN HF cell **hf_1** ran at load mean **{f2(hf['load_mean'])}** and measured **{f2(hf['ms'])} ms/tok**. "
  f"The quiet HF cell **hf_2** (load mean **{f2(h2['load_mean'])}**) measured **{f2(h2['ms'])} ms/tok** but was excluded "
  f"(mid-cell Ollama model loaded, ×{why['hf_2 mid-cell ollama model loaded']} monitor ticks; idle-baseline util {C['hf_2']['base']}).")
w(f"- The only CLEAN t4 cell, t4_2, was quiet (load mean {f2(t4['load_mean'])}). So the sealed SPLIT compares a quiet engine "
  f"cell against a loaded HF cell.")
w(f"- Post-hoc counterfactual (NOT the registered analysis): pairing t4_2 with hf_2 gives gap {f2(gap2)} ms/tok = idle "
  f"{f2(di2)} + busy {f2(db2)}, **idle share {share2:.3f}**, which would cross the registered IDLE bar (≥0.5). The "
  f"sealed GAP-IS-GPU-BUSY therefore hinges on which HF cell happened to be clean.")
w(f"- The two HF cells imply ~{hf_slope:.2f} ms/tok per load unit for HF (2 points, post hoc).")
w(f"- The T1 branch is confounded the same way: clean t1_1 ran at load {f2(t1['load_mean'])} vs t4_2 at "
  f"{f2(t4['load_mean'])} (Δ {f2(t1_dl)}).")
w("- What survives the confound: GPU-busy ms/token is roughly load-independent. Among cells with no foreign GPU process, "
  f"engine busy = {', '.join(f2(b) for b in eng_busy)} ms/tok and HF busy = {', '.join(f2(b) for b in hf_busy)} ms/tok, "
  "across loads from ~1.3 to ~23. The load-sensitive part is idle time.")
w("")
w("**Label: the sealed verdict stands as the preregistered outcome but is CONFOUNDED BY HOST LOAD and is NOT RELIED UPON "
  "for any decision.** exp746 (freeze d3b0dd4, AMENDMENT1 at e33f77a) gates its quiet cells on host "
  "load (1-min loadavg <3.0, no Runner.Worker) in one combined GPU+CPU quiet wait.")
w("")
w("## Per-cell table (from sealed verdict.txt; load from raw out/*.load)")
w("| cell | arm | thr | ms/tok | busy ms | idle ms | busy frac | load mean (min–max, n) | pre-start load | quietwait | status |")
w("|---|---|---|---|---|---|---|---|---|---|---|")
for cid in order:
    c = C[cid]
    w(f"| {cid} | {c['arm']} | {c['t']} | {f2(c['ms'])} | {f2(c['busy'])} | {f2(c['idle'])} | {c['bf']:.3f} | "
      f"{f2(c['load_mean'])} ({f2(c['load_min'])}–{f2(c['load_max'])}, {c['load_n']}) | {f2(c['pre_load'])} | {c['qw']} | "
      f"{c['status']} |")
w("")
w("## Exclusions (from out/FLAGGED.why, monitor ticks per reason)")
for cid in order:
    if cid in reasons:
        w(f"- **{cid}**: " + "; ".join(sorted(reasons[cid])))
w("- Clean arms: hf n=1 (hf_1), t4 n=1 (t4_2), t1 n=1 (t1_1), grp n=0.")
w("")
w("## Manipulation checks")
w("- `threads_effective == requested` in every engine cell: True.")
w("- Grouped decode engaged only in grp cells: True (grp_1 " f"{C['grp_1']['grp']}, grp_2 {C['grp_2']['grp']} grouped "
  "experts; eng cells 0). Both grp cells were excluded, so GRP is INCONCLUSIVE.")
w("")
w("## Registered predictions")
w(f"- Q1 SPLIT, predicted GAP-IS-GPU-IDLE (0.7): **refuted as sealed** (GAP-IS-GPU-BUSY; idle share {d_idle / gap:.3f}). "
  f"Confounded: the hf_2 pairing gives {share2:.3f}. Not relied upon either way.")
w("- Q2 GRP, predicted GRP:NO-CHANGE (0.8): **untested** (GRP:INCONCLUSIVE; no clean grp cell).")
w(f"- Q3 T1, predicted T1:IDLE-UP (0.65): **confirmed as sealed** (d_ms +53.66, d_idle +57.96, d_busy −1.62). "
  f"Load-confounded: t1_1 ran {f2(t1_dl)} load units above t4_2.")
w("")
w("## Pre-decided consequence and what the confound blocks")
w("- PREREG consequence for GAP-IS-GPU-BUSY: count kernels and memcpy per token and target the copy path. "
  "**Not acted on**: the branch selection depends on the load confound. The load-controlled successors are exp746 "
  "(routing replication with a CPU-quiet gate) and exp747 (freeze 06e6100, WSL host-func stream stall vs CPU contention).")
w("- Usable as a descriptive input: the engine keeps the GPU busy ~40 ms/tok vs HF ~14–16 ms/tok, whatever the load.")
w("")
w("## Caveats")
w("- NVML `utilization.gpu` has ~0.3 s driver granularity on Winnie (refreshes ~every 6 polls at 50 ms) and counts kernel "
  "execution only; copy-engine activity without a concurrent kernel reads as idle. Windows include prefill.")
w("- One clean cell per arm. WSL2 on Winnie, not native Linux. GPU1 (RTX 5060 Ti), OLMoE-1B-7B bf16, lcnu @ 0.75.")
w("- Cosmetic defect: the runner prints `== <ts> EXP738-DONE` as its completion line "
  f"(`{done[0].strip()}`), inherited from the exp738 runner by a case-sensitive rename. The run is exp743; the frozen "
  "runner bytes match ARTIFACT.sha256.")
open(os.path.join(H, "ADDENDUM69.md"), "w").write("\n".join(L) + "\n")
print("ADDENDUM69.md written; all checks OK")

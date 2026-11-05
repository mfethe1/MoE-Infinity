#!/usr/bin/env python3
"""gen_addendum60.py — independent follow-up-controller adjudication of exp714 (lane 79990, STACK-1001).

Written independently from the frozen PREREG.md; never imports or executes run_barbo.py and never
trusts a stored boolean/summary when raw data or a sealed reference allows recomputation. Every
constant, hash and parameter is parsed at runtime from PREREG.md / ARTIFACT.sha256 / the sealed
exp668/exp669/exp670/exp713 artifacts — no hand-transcribed values.

Sections
  A  freeze & identity   : ARTIFACT vs local files vs freeze-commit blobs; sealed dep shas; JSON shas;
                           freeze-before-result ordering; run.log/JSON verdict agreement
  B  rules vs PREREG     : T/H split partition, caps, bars, budget, RNG; seed params re-derived from
                           sealed exp713 arms + exp669 trial-1 + exp712 certified edge (via exp713 rules)
  C  points & ladder     : per-point score recomputation (J/c/s/acct/feasible), feasible-argmax x*,
                           frozen verdict ladder re-implementation, pearson recompute, run.log parse
  D  heldout             : H stats re-derived from the stored raw grids (own synth-stats implementation)
  E  H0 static re-deriv. : stored raw H grids vs sealed exp713 cells (exact); real summaries vs sealed
                           exp668/exp669 raw caps; seed-arm T-synth summaries vs sealed exp713 raw cells;
                           432-cell decomposition; exp670 stream-sha/cfg consistency
  F  live re-evaluation  : sealed exp713/exp669 code in THIS process — 11 regenerated streams sha-asserted
                           vs exp670; H-side standalones/center/x* cell-exact vs stored AND vs exp713;
                           T-side x* summary; real-trace center vs exp668 anchor (45 fields) and real-trace
                           x* summary + live J recompute; seed-arm spot at caps {128,4096} vs exp713

Writes ADDENDUM60.md into the run dir only if EVERY check passes; exit 1 otherwise.
Interpreter: exp650 venv python (torch needed for the live real-trace re-evaluation).
"""
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

T0 = time.time()
HOME = Path.home()
RUNDIR = HOME / "warp-work/exp714-moei-barbo"
REPO = HOME / "warp-work/moei-granite3b"              # pinned import/data path (NOT a git repo)
REBUILT = HOME / "warp-work/moei-granite3b-rebuilt"    # canonical git clone (remote mfethe1)
RESULT = RUNDIR / "exp714-barbo.json"
ARTIFACT = RUNDIR / "ARTIFACT.sha256"

# ------------------------------------------------------------------ check ledger
CHECKS = []          # (name, ok, detail)
FAILFAST = os.environ.get("ADJ_FAILFAST") == "1"


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    if not ok:
        print(f"CHECK FAIL: {name} :: {detail}", flush=True)
        if FAILFAST:
            report_and_exit()
    return bool(ok)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def jdumps(o):
    return json.dumps(o, sort_keys=True, default=str)


def eq(name, got, want):
    return check(name, got == want, f"got={jdumps(got)[:300]} want={jdumps(want)[:300]}")


# ------------------------------------------------------------------ artifacts / refs (runtime-parsed)
art = {}
for line in ARTIFACT.read_text().splitlines():
    if line.strip():
        sha, path = line.split()
        art[path] = sha

D = json.loads(RESULT.read_text())
E668 = json.loads((HOME / "warp-work/exp668-moei-costfit-grid/exp668-grid.json").read_text())
E669 = json.loads((HOME / "warp-work/exp669-moei-costfit-bo/exp669-bo.json").read_text())
E670 = json.loads((REPO / "benchmarks/cache_simulator/research/exp670-synth.json").read_text())
E713 = json.loads((HOME / "warp-work/exp713-moei-gclamp/exp713-gclamp.json").read_text())

ART_PATHS = {
    "run_barbo.py": RUNDIR / "run_barbo.py",
    "PREREG.md": RUNDIR / "PREREG.md",
    "smoke.log": RUNDIR / "smoke.log",
    "smoke-attempt1.log": RUNDIR / "smoke-attempt1.log",
    "smoke-attempt2.log": RUNDIR / "smoke-attempt2.log",
    "exp669/run_bo.py": HOME / "warp-work/exp669-moei-costfit-bo/run_bo.py",
    "exp713/run_gclamp.py": HOME / "warp-work/exp713-moei-gclamp/run_gclamp.py",
    "policies.py": REPO / "benchmarks/cache_simulator/policies.py",
    "policies_costfit.py": REPO / "benchmarks/cache_simulator/research/policies_costfit.py",
    "run_policies_real.py": REPO / "benchmarks/cache_simulator/research/run_policies_real.py",
    "exp668-grid.json": HOME / "warp-work/exp668-moei-costfit-grid/exp668-grid.json",
    "exp669-bo.json": HOME / "warp-work/exp669-moei-costfit-bo/exp669-bo.json",
    "exp670-synth.json": REPO / "benchmarks/cache_simulator/research/exp670-synth.json",
    "exp713-gclamp.json": HOME / "warp-work/exp713-moei-gclamp/exp713-gclamp.json",
}

print("=== SECTION A: freeze & identity", flush=True)
for name, sha in art.items():
    p = ART_PATHS.get(name)
    check(f"A.artifact-entry[{name}]", p is not None, "no path mapping")
    if p is not None:
        eq(f"A.sha256[{name}]", sha256_file(p), sha)

# freeze commit discovery (no hand-transcribed sha): the commit that ADDED research/exp714/PREREG.md
rel = "benchmarks/cache_simulator/research/exp714"
out = subprocess.run(["git", "-C", str(REBUILT), "log", "--format=%H", "--diff-filter=A", "--",
                      f"{rel}/PREREG.md"], capture_output=True, text=True, check=True).stdout.split()
check("A.freeze-commit-unique", len(out) == 1, f"adding commits: {out}")
FREEZE = out[-1]
freeze_short = FREEZE[:7]
for f in ("PREREG.md", "run_barbo.py", "ARTIFACT.sha256"):
    blob = subprocess.run(["git", "-C", str(REBUILT), "cat-file", "blob", f"{FREEZE}:{rel}/{f}"],
                          capture_output=True, check=True).stdout
    eq(f"A.freeze-blob[{f}]", sha256_bytes(blob), art.get(f if f != "ARTIFACT.sha256" else "PREREG.md")
       if False else sha256_file(RUNDIR / f))
ct = int(subprocess.run(["git", "-C", str(REBUILT), "show", "-s", "--format=%ct", FREEZE],
                        capture_output=True, text=True, check=True).stdout.strip())
check("A.freeze-before-result", ct < RESULT.stat().st_mtime,
      f"freeze {time.ctime(ct)} result mtime {time.ctime(RESULT.stat().st_mtime)}")

# JSON-embedded sealed input shas must equal ARTIFACT entries and actual bytes
for jname, jsha in D["sealed_inputs_sha256"].items():
    eq(f"A.json-sealed-sha[{jname}]", jsha, art[jname])

# run.log agreement
log_lines = [ln for ln in (RUNDIR / "run.log").read_text().splitlines() if ln.strip()]
eq("A.runlog-verdict", log_lines[-1].strip(), "settled verdict=" + D["verdict"])
last_mark = int(re.findall(r"\[(\d+)s\]", log_lines[-2])[-1])
check("A.elapsed-consistent", D["elapsed_s"] >= last_mark, f"elapsed {D['elapsed_s']} < last log {last_mark}")

print("=== SECTION B: rules vs PREREG / sealed refs", flush=True)
R = D["rules"]
TR, HE = R["train_idx"], R["held_idx"]
check("B.split-partition", sorted(TR + HE) == list(range(11)), f"{TR}+{HE}")
check("B.split-disjoint", not (set(TR) & set(HE)), "")
eq("B.train-idx", TR, [0, 2, 4, 6, 8, 10])
eq("B.held-idx", HE, [1, 3, 5, 7, 9])
eq("B.caps", R["caps"], E713["rules"]["caps"])
eq("B.safety-pp", R["safety_pp"], 0.5)
eq("B.switch-max", R["switch_max"], 6)
eq("B.informative-pp", R["informative_pp"], 0.1)
eq("B.train-gain-pp", R["train_gain_pp"], 0.05)
eq("B.gain-pp", R["gain_pp"], 0.05)
eq("B.noninf-pp", R["noninf_pp"], -0.05)
eq("B.n-trials", R["n_trials"], 20)
eq("B.rng-seed", R["rng_seed"], 20261105)
eq("B.n-cand", R["n_cand"], 2048)
eq("B.center", R["center"], list(E713["rules"]["center"]))

# seed params re-derived from sealed refs (never from exp714's own claims alone)
t1 = [t for t in E669["trials"] if t.get("trial") == 1][0]
bo669 = [float(t1["params"][k]) for k in ("margin", "gamma", "half_life")]
g_edge = float(E713["rules"]["g_edge"])
want_seeds = {
    "center": list(E713["rules"]["center"]),
    "bo": bo669,
    "clamp": [bo669[0], g_edge, bo669[2]],
    "clampM": [bo669[0], g_edge, list(E713["rules"]["center"])[2]],
    "clampH": [list(E713["rules"]["center"])[0], g_edge, bo669[2]],
}
eq("B.seed-arms", R["seed_arms"], list(want_seeds.keys()))
for a, wp in want_seeds.items():
    eq(f"B.seed-params[{a}]", R["seed_params"][a], wp)
    eq(f"B.seed-params-vs-exp713[{a}]", R["seed_params"][a], E713["arms"][a]["params"])

# exp713 grid seeds vs exp670 (sealed-vs-sealed)
for i, st in enumerate(E713["grid"]):
    eq(f"B.exp713-seed[{i}]", st["seed"], E670["grid"][i]["seed"])
    eq(f"B.exp713-cfg[{i}]", st["cfg"], E670["grid"][i]["cfg"])

print("=== SECTION C: points, x*, ladder, pearson, run.log", flush=True)
pts = D["points"]
eq("C.n-points", len(pts), 5 + R["n_trials"])
SAFE, SWMAX = R["safety_pp"], R["switch_max"]
for k, pt in enumerate(pts):
    rs, ss, sc = pt["real"], pt["syn"], pt["score"]
    J = 0.5 * rs["mean_delta_pp"] + 0.5 * ss["mean_delta_pp"]
    c = max(rs["worst_pp"], ss["worst_pp"])
    s = max(rs["max_switches"], ss["max_switches"])
    acct = rs["acct_ok"] and not ss["acct_violations"]
    feas = c <= SAFE and s <= SWMAX and acct
    eq(f"C.J[{k}:{pt['src']}]", sc["J"], J)
    eq(f"C.c[{k}]", sc["c"], c)
    eq(f"C.s[{k}]", sc["s"], s)
    eq(f"C.acct[{k}]", sc["acct_ok"], acct)
    eq(f"C.feas[{k}]", sc["feasible"], feas)
    eq(f"C.real-n[{k}]", rs["n"], 15)
    eq(f"C.syn-n[{k}]", ss["n"], 33)

feas = [k for k, pt in enumerate(pts) if pt["score"]["feasible"]]
eq("C.n-feasible", D["n_feasible"], len(feas))
kstar = max(feas, key=lambda k: (pts[k]["score"]["J"], -k))
star = pts[kstar]
eq("C.xstar-src", D["x_star"]["src"], star["src"])
eq("C.xstar-params", D["x_star"]["params"], star["params"])
eq("C.xstar-train-deep", jdumps(D["x_star"]["train"]), jdumps(star))
Jstar = star["score"]["J"]
others = sorted(((pts[k]["score"]["J"], pts[k]["src"]) for k in feas if k != kstar), reverse=True)
check("C.xstar-argmax-strict", Jstar > others[0][0], f"runner-up {others[0]}")

# frozen ladder, re-implemented from PREREG text (top-down)
def ladder(h0_ok, h4_ok, Jst, held_safe, held_mean):
    if not (h0_ok and h4_ok):
        return "ACCOUNTING-FAIL"
    if Jst < 0.05:
        return "NO-TRAIN-HEADROOM"
    if not held_safe:
        return "HELDOUT-UNSAFE"
    if held_mean >= 0.05:
        return "TRANSFERS-GAIN"
    if held_mean >= -0.05:
        return "TRANSFERS-NONINFERIOR"
    return "NO-TRANSFER"

# smoke S6 ladder edge cases (guards my re-implementation against PREREG boundaries)
lad = [ladder(False, True, 1, True, 1) == "ACCOUNTING-FAIL",
       ladder(True, False, 1, True, 1) == "ACCOUNTING-FAIL",
       ladder(True, True, 0.0499, True, 1) == "NO-TRAIN-HEADROOM",
       ladder(True, True, 0.05, False, 1) == "HELDOUT-UNSAFE",
       ladder(True, True, 0.05, True, 0.05) == "TRANSFERS-GAIN",
       ladder(True, True, 0.05, True, -0.05) == "TRANSFERS-NONINFERIOR",
       ladder(True, True, 0.05, True, -0.0501) == "NO-TRANSFER"]
check("C.ladder-selftest-7/7", all(lad), str(lad))

# pearson recompute from stored trial pred_J vs observed J
pr = np.array([[p["pred_J"], p["score"]["J"]] for p in pts[5:]])
pear = float(np.corrcoef(pr[:, 0], pr[:, 1])[0, 1])
check("C.pearson", abs(pear - D["pearson_predJ_vs_obsJ"]) < 1e-12, f"{pear} vs {D['pearson_predJ_vs_obsJ']}")

# run.log line-by-line vs points
seed_re = re.compile(r"^seed (\S+) J=([+-][\d.]+) c=([\d.]+) s=(\d+) feas=(\S+)")
trial_re = re.compile(r"^trial\s+(\d+) M([\d.]+) G([\d.]+) HL(\d+) J=([+-][\d.]+) c=([\d.]+) s=(\d+) feas=(\S+)")
seeds_seen, trials_seen = [], []
for ln in log_lines:
    m = seed_re.match(ln)
    if m:
        seeds_seen.append(m.groups())
        continue
    m = trial_re.match(ln)
    if m:
        trials_seen.append(m.groups())
check("C.log-seed-count", len(seeds_seen) == 5, str(len(seeds_seen)))
check("C.log-trial-count", len(trials_seen) == 20, str(len(trials_seen)))
for j, (arm, J, c, s, f) in enumerate(seeds_seen):
    pt = pts[j]
    eq(f"C.log-seed-src[{arm}]", pt["src"], "seed:" + arm)
    check(f"C.log-seed-J[{arm}]", abs(float(J) - pt["score"]["J"]) < 5e-5, f"{J} vs {pt['score']['J']}")
    check(f"C.log-seed-c[{arm}]", abs(float(c) - pt["score"]["c"]) < 5e-4, f"{c} vs {pt['score']['c']}")
    eq(f"C.log-seed-s[{arm}]", int(s), pt["score"]["s"])
    eq(f"C.log-seed-feas[{arm}]", f == "True", pt["score"]["feasible"])
for j, (tn, M, G, HL, J, c, s, f) in enumerate(trials_seen):
    pt = pts[5 + j]
    eq(f"C.log-trial-src[{tn}]", pt["src"], f"trial:{int(tn)}")
    check(f"C.log-trial-M[{tn}]", abs(float(M) - pt["params"][0]) < 5e-6, f"{M} vs {pt['params'][0]}")
    check(f"C.log-trial-G[{tn}]", abs(float(G) - pt["params"][1]) < 5e-6, f"{G} vs {pt['params'][1]}")
    check(f"C.log-trial-HL[{tn}]", abs(float(HL) - pt["params"][2]) < 0.5, f"{HL} vs {pt['params'][2]}")
    check(f"C.log-trial-J[{tn}]", abs(float(J) - pt["score"]["J"]) < 5e-5, f"{J} vs {pt['score']['J']}")
    eq(f"C.log-trial-s[{tn}]", int(s), pt["score"]["s"])
    eq(f"C.log-trial-feas[{tn}]", f == "True", pt["score"]["feasible"])

print("=== SECTION D: heldout stats re-derivation (own implementation)", flush=True)
HO = D["heldout"]
gs, gc, st_ho = HO["grid_star"], HO["grid_center"], HO["standalones"]
INFORM = R["informative_pp"]


def informative(cell):
    return abs(cell["lcnu"]["rate"] - cell["s3fifo"]["rate"]) * 100 >= INFORM


def my_synth_stats(arm_res, center_res, stand, stream_order=None):
    """Independent re-implementation of the PREREG's synthetic paired stats (informative cells only)."""
    deltas, worst, maxsw, acct, over = [], None, 0, [], []
    idxs = stream_order if stream_order is not None else sorted(int(i) for i in arm_res)
    for i in idxs:
        si = str(i) if not isinstance(i, int) or str(i) in arm_res else i
        per = arm_res[si] if isinstance(arm_res, dict) and si in arm_res else arm_res[i]
        cper = center_res[str(i)] if str(i) in center_res else center_res[i]
        sper = stand[str(i)] if str(i) in stand else stand[i]
        for cap in sorted(per, key=int):
            x = per[cap]
            if x["rate"] != x["prop"]:
                acct.append([i, cap])
            stc = sper[cap]
            if not informative(stc):
                continue
            best = max(stc["lcnu"]["rate"], stc["s3fifo"]["rate"])
            d = (best - x["rate"]) * 100
            deltas.append((x["rate"] - cper[cap]["rate"]) * 100)
            maxsw = max(maxsw, x["switches"])
            if worst is None or d > worst[0]:
                worst = (d, i, cap)
            if d > SAFE or x["switches"] > SWMAX:
                over.append({"stream": i, "cap": cap, "deficit_pp": round(d, 3), "switches": x["switches"]})
    return {"n": len(deltas), "mean_delta_pp": sum(deltas) / len(deltas), "worst_pp": worst[0],
            "worst_cell": [worst[1], worst[2]], "max_switches": maxsw, "acct_violations": acct, "over": over}


ho_stats = my_synth_stats(gs, gc, st_ho, stream_order=[int(i) for i in sorted(gs, key=int)])
st_stored = HO["stats"]
for f in ("n", "mean_delta_pp", "worst_pp", "worst_cell", "max_switches", "acct_violations", "over"):
    eq(f"D.heldout-{f}", ho_stats[f], st_stored[f])
held_safe = (not ho_stats["over"]) and ho_stats["max_switches"] <= SWMAX and ho_stats["worst_pp"] <= SAFE
eq("D.H1-safe", HO["H1_safe"], held_safe)
eq("D.mean-round", HO["mean_delta_vs_center_pp"], round(ho_stats["mean_delta_pp"], 4))

print("=== SECTION E: H0 static re-derivation vs sealed refs", flush=True)
ref_cells = {(i, cap): cell for i, st in enumerate(E713["grid"]) for cap, cell in st["caps"].items()}
CAPS = [str(c) for c in R["caps"]]

# H-side stored grids vs sealed exp713 (exact cell dicts)
n_cmp = 0
for i in HE:
    for cap in CAPS:
        eq(f"E.h0-hcenter[{i},{cap}]", gc[str(i)][cap], ref_cells[(i, cap)]["cf_center"])
        eq(f"E.h0-hstand-lcnu[{i},{cap}]", st_ho[str(i)][cap]["lcnu"], ref_cells[(i, cap)]["lcnu"])
        eq(f"E.h0-hstand-s3fifo[{i},{cap}]", st_ho[str(i)][cap]["s3fifo"], ref_cells[(i, cap)]["s3fifo"])
        n_cmp += 3
check("E.h-side-cell-comparisons", n_cmp == 90, str(n_cmp))

# real-trace center summary vs sealed exp668 m0.005_g0.0025
ref668 = E668["grid"]["m0.005_g0.0025"]
deltas, worst, maxsw, acct = [], None, 0, True
for name in ref668:  # qwen30b, granite (dict order as sealed)
    for cap, cc in ref668[name]["caps"].items():
        deltas.append((cc["rate"] - cc["rate"]) * 100)
        maxsw = max(maxsw, cc["switches"])
        acct = acct and cc["loop_eq_prop"]
        if worst is None or cc["deficit_pp"] > worst:
            worst = cc["deficit_pp"]
rs0 = pts[0]["real"]
eq("E.real-center-n", rs0["n"], len(deltas))
eq("E.real-center-mean", rs0["mean_delta_pp"], sum(deltas) / len(deltas))
eq("E.real-center-worst", rs0["worst_pp"], worst)
eq("E.real-center-maxsw", rs0["max_switches"], maxsw)
eq("E.real-center-acct", rs0["acct_ok"], acct)
eq("E.real-center-n15", len(deltas), 15)

# real-trace bo summary vs sealed exp669 trial 1 (deltas vs exp668 center rates)
deltas, worst, maxsw, acct = [], None, 0, True
for name in ref668:
    for cap, cc in t1["per_model"][name]["caps"].items():
        deltas.append((cc["rate"] - ref668[name]["caps"][cap]["rate"]) * 100)
        maxsw = max(maxsw, cc["switches"])
        acct = acct and cc["loop_eq_prop"]
        if worst is None or cc["deficit_pp"] > worst:
            worst = cc["deficit_pp"]
rs1 = pts[1]["real"]
eq("E.real-bo-mean", rs1["mean_delta_pp"], sum(deltas) / len(deltas))
eq("E.real-bo-worst", rs1["worst_pp"], worst)
eq("E.real-bo-maxsw", rs1["max_switches"], maxsw)
eq("E.real-bo-acct", rs1["acct_ok"], acct)

# seed-arm T-synth summaries vs sealed exp713 raw cells
for j, a in enumerate(R["seed_arms"]):
    arm_res = {i: {cap: ref_cells[(i, cap)]["cf_" + a] for cap in CAPS} for i in TR}
    center_res = {i: {cap: ref_cells[(i, cap)]["cf_center"] for cap in CAPS} for i in TR}
    stand = {i: {cap: ref_cells[(i, cap)] for cap in CAPS} for i in TR}
    rec = my_synth_stats(arm_res, center_res, stand, stream_order=TR)
    got = pts[j]["syn"]
    for f in ("n", "mean_delta_pp", "worst_pp", "worst_cell", "max_switches", "acct_violations", "over"):
        eq(f"E.seed-syn[{a}].{f}", got[f], rec[f])

# H0 432-cell decomposition per PREREG design
decomp = (5 * 36) + 72 + 45 + 45 + 30 + 60
eq("E.h0-cells", D["H0"]["cells"], decomp)
eq("E.h0-mismatches-empty", D["H0"]["mismatches"], [])
eq("E.h0-ok", D["H0"]["ok"], True)
eq("E.h4-acct-all", D["H4"]["accounting_all"], all(p["score"]["acct_ok"] for p in pts) and not ho_stats["acct_violations"])
eq("E.h4-ok-consistent", D["H4"]["ok"], D["H4"]["determinism_xstar"] and D["H4"]["accounting_all"])

print("=== SECTION F: live re-evaluation via sealed code (separate process from the runner)", flush=True)
sys.path.insert(0, str(REPO))
from benchmarks.cache_simulator.research.run_policies_real import load_accesses  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R669 = _load("sealed_exp669", HOME / "warp-work/exp669-moei-costfit-bo/run_bo.py")
R713 = _load("sealed_exp713", HOME / "warp-work/exp713-moei-gclamp/run_gclamp.py")

# x* within the sealed search space
LO = np.array([b[0] for b in R669.BOUNDS])
HI = np.array([b[1] for b in R669.BOUNDS])
xstar_vec = np.array(R669.from_params(*D["x_star"]["params"]))
check("F.xstar-in-bounds", bool(np.all(xstar_vec >= LO) and np.all(xstar_vec <= HI)),
      f"{xstar_vec} in [{LO},{HI}]")

# regenerate all 11 streams; sha8 must equal sealed exp670
cfgs = R713.stream_cfgs()
seeds = np.random.default_rng(67020261104).spawn(11)
streams = {}
for i, cfg in enumerate(cfgs):
    keys = R713.gen_stream(int(seeds[i].integers(0, 2**63)), cfg["E"], cfg["L"], cfg["s"], cfg["lam"], R713.N_ACC)
    sha = R713.stream_sha(keys)
    eq(f"F.stream-sha[{i}]", sha, E670["grid"][i]["seed"])
    streams[i] = (cfg, keys)


def live_standalones(i):
    cfg, keys = streams[i]
    return R713.evaluate(keys, cfg["E"], cfg["L"], R713.CAPS, [])


def live_arm(i, params):
    cfg, keys = streams[i]
    gk = {"num_layers": cfg["L"], "prior": 8 / cfg["E"]}
    n = len(keys)
    per = {}
    for cap in R713.CAPS:
        pol = R713.make_costfit(cap, gk, tuple(params))
        assert (pol.MARGIN, pol.GAMMA, pol.HALF_LIFE) == tuple(params) and pol._decay == 0.5 ** (1.0 / params[2])
        hits = sum(1 for k in keys if pol.on_access(k))
        per[str(cap)] = {"rate": round(hits / n, 6), "prop": round(pol.effective_hit_rate, 6),
                         "switches": getattr(pol, "switches", 0)}
    return per


# H-side: standalones + center + x*, cell-exact vs stored grids AND vs sealed exp713
for i in HE:
    stl = live_standalones(i)
    cen = live_arm(i, R["center"])
    xst = live_arm(i, D["x_star"]["params"])
    for cap in CAPS:
        eq(f"F.ho-stand[{i},{cap}]", stl[cap], st_ho[str(i)][cap])
        eq(f"F.ho-stand-vs713[{i},{cap}]", {k: stl[cap][k] for k in ("lcnu", "s3fifo")},
           {k: ref_cells[(i, cap)][k] for k in ("lcnu", "s3fifo")})
        eq(f"F.ho-center[{i},{cap}]", cen[cap], gc[str(i)][cap])
        eq(f"F.ho-center-vs713[{i},{cap}]", cen[cap], ref_cells[(i, cap)]["cf_center"])
        eq(f"F.ho-xstar[{i},{cap}]", xst[cap], gs[str(i)][cap])
    print(f"F: H stream {i} done [{time.time()-T0:.0f}s]", flush=True)

# T-side: x* only (center/standalones come from the sealed exp713 refs verified above)
t_arm = {i: live_arm(i, D["x_star"]["params"]) for i in TR}
t_center = {i: {cap: ref_cells[(i, cap)]["cf_center"] for cap in CAPS} for i in TR}
t_stand = {i: {cap: ref_cells[(i, cap)] for cap in CAPS} for i in TR}
rec_syn = my_synth_stats(t_arm, t_center, t_stand, stream_order=TR)
for f in ("n", "mean_delta_pp", "worst_pp", "worst_cell", "max_switches", "acct_violations", "over"):
    eq(f"F.train-syn[{f}]", rec_syn[f], D["x_star"]["train"]["syn"][f])
print(f"F: T-side x* done [{time.time()-T0:.0f}s]", flush=True)

# seed-arm spot: all 5 arms x T streams x caps {128, 4096} vs sealed exp713 cells
for a in R["seed_arms"]:
    p = tuple(R["seed_params"][a])
    for i in TR:
        cfg, keys = streams[i]
        gk = {"num_layers": cfg["L"], "prior": 8 / cfg["E"]}
        n = len(keys)
        for cap in (128, 4096):
            pol = R713.make_costfit(cap, gk, p)
            hits = sum(1 for k in keys if pol.on_access(k))
            live = {"rate": round(hits / n, 6), "prop": round(pol.effective_hit_rate, 6),
                    "switches": getattr(pol, "switches", 0)}
            eq(f"F.seed-spot[{a},{i},{cap}]", live, ref_cells[(i, str(cap))]["cf_" + a])
print(f"F: seed-arm spot done [{time.time()-T0:.0f}s]", flush=True)

# real traces: center anchored vs exp668 (45 fields), then x* summary + live J recompute
traces, bases = {}, {}
for name, cfgm in R669.MODELS.items():
    traces[name] = load_accesses([str(REPO / p) for p in cfgm["trace"]], ignore_layers=0, prefill="skip")
    bases[name] = R669.base_rows(REPO / "benchmarks/cache_simulator/research" / cfgm["base"])
print(f"F: traces loaded [{time.time()-T0:.0f}s]", flush=True)


def real_eval(params):
    return R669.evaluate(R669.from_params(*params), traces, bases)


def my_real_stats(rec, center_rec):
    deltas, worst, maxsw, acct = [], None, 0, True
    for name in R669.MODELS:
        for cap, cc in rec["per_model"][name]["caps"].items():
            deltas.append((cc["rate"] - center_rec["per_model"][name]["caps"][cap]["rate"]) * 100)
            maxsw = max(maxsw, cc["switches"])
            acct = acct and cc["loop_eq_prop"]
            if worst is None or cc["deficit_pp"] > worst:
                worst = cc["deficit_pp"]
    return {"n": len(deltas), "mean_delta_pp": sum(deltas) / len(deltas), "worst_pp": worst,
            "max_switches": maxsw, "acct_ok": acct}


rc_live = real_eval(R["center"])
n_f = 0
for name in R669.MODELS:
    for cap, cc in rc_live["per_model"][name]["caps"].items():
        r668 = ref668[name]["caps"][cap]
        for f in ("rate", "switches", "deficit_pp"):
            eq(f"F.real-center-h0[{name},{cap},{f}]", cc[f], r668[f])
            n_f += 1
check("F.real-center-45-fields", n_f == 45, str(n_f))
print(f"F: real center done [{time.time()-T0:.0f}s]", flush=True)

rx_live = real_eval(D["x_star"]["params"])
rec_real = my_real_stats(rx_live, rc_live)
for f in ("n", "mean_delta_pp", "worst_pp", "max_switches", "acct_ok"):
    eq(f"F.train-real[{f}]", rec_real[f], D["x_star"]["train"]["real"][f])
J_live = 0.5 * rec_real["mean_delta_pp"] + 0.5 * rec_syn["mean_delta_pp"]
eq("F.live-J", J_live, D["x_star"]["train"]["score"]["J"])
check("F.live-J-under-bar", J_live < R["train_gain_pp"], f"{J_live} < {R['train_gain_pp']}")
print(f"F: real x* done [{time.time()-T0:.0f}s]", flush=True)

# ------------------------------------------------------------------ verdict & addendum
h0_ok = (D["H0"]["cells"] == decomp and D["H0"]["mismatches"] == []
         and all(ok for nm, ok, _ in CHECKS if nm.startswith("E.")))
h4_ok = (D["H4"]["accounting_all"] and D["H4"]["determinism_xstar"]
         and all(ok for nm, ok, _ in CHECKS if nm.startswith("F.ho-xstar") or nm.startswith("F.train-")))
verdict = ladder(h0_ok, h4_ok, Jstar, held_safe, ho_stats["mean_delta_pp"])
eq("Z.verdict-vs-runner", verdict, D["verdict"])

n_pass = sum(1 for _, ok, _ in CHECKS if ok)
n_all = len(CHECKS)
elapsed = time.time() - T0
print(f"CHECKS {n_pass}/{n_all} PASS in {elapsed:.0f}s; adjudicated verdict={verdict}", flush=True)


def report_and_exit():
    n_pass = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"ADJUDICATION FAILED: {n_pass}/{len(CHECKS)} passed", flush=True)
    for nm, ok, det in CHECKS:
        if not ok:
            print(f"  FAIL {nm} :: {det}", flush=True)
    sys.exit(1)


if n_pass != n_all:
    report_and_exit()

# top feasible points for the addendum table
top = sorted(((pts[k]["score"]["J"], pts[k]["src"], pts[k]["params"], pts[k]["score"]["c"], pts[k]["score"]["s"])
              for k in feas), reverse=True)[:6]
xs = D["x_star"]
xp = xs["params"]
seed_rows = "\n".join(
    f"| {pts[j]['src'].split(':')[1]} | {R['seed_params'][a][0]:.6f} | {R['seed_params'][a][1]:.6f} | "
    f"{R['seed_params'][a][2]:.0f} | {pts[j]['score']['J']:+.4f} | {pts[j]['score']['c']:.3f} | "
    f"{pts[j]['score']['s']} | {'yes' if pts[j]['score']['feasible'] else 'no'} |"
    for j, a in enumerate(R["seed_arms"]))
top_rows = "\n".join(f"| {src} | {p[0]:.6f} | {p[1]:.6f} | {p[2]:.0f} | {J:+.4f} | {c:.3f} | {s} |"
                     for J, src, p, c, s in top)
worst_i, worst_cap = ho_stats["worst_cell"]
wcfg = E670["grid"][worst_i]["cfg"]

ADD = f"""# ADDENDUM 60 — exp714: bar-constrained joint BO of CostFit (M × G × HL) with a held-out synthetic split

Verdict: **NO-TRAIN-HEADROOM** — with the objective corrected to the paired MEAN gain vs center
(J = 0.5·real + 0.5·T-synth informative), the 0.5pp/6-switch safety bars as hard constraints, and
synthetic training streams included, 5 seeds + 20 constrained-BO trials inside the sealed exp669 BOUNDS
produce a best feasible point x* with J(x*) = {Jstar:+.4f}pp — below the frozen +0.05pp training-headroom
bar. Center (0.005, 0.0025, 32768) is at the bar-constrained mean optimum of this space; the CostFit
tuning line is CLOSED. Held-out numbers below are DESCRIPTIVE ONLY (ladder rung 2 fired before the
held-out gates): x* was safe on H (worst {ho_stats['worst_pp']:.3f}pp ≤ 0.5, 0 over, max switches
{ho_stats['max_switches']}) with mean {ho_stats['mean_delta_pp']:+.4f}pp vs center on {ho_stats['n']}
informative cells. H0 replication {D['H0']['cells']}/{D['H0']['cells']} exact (0 mismatches); H4
accounting + in-process determinism held. Exit 0, {D['elapsed_s']:.0f}s.

## Design (frozen PREREG b64f46ea…)
- Training set T: both real traces exactly as exp669 (qwen30b 10 caps + granite 5 caps, base-CSV
  standalones) + synthetic streams {{0,2,4,6,8,10}} × 6 caps [128…4096], informative cells only
  (|lcnu−s3fifo| ≥ 0.1pp; 33/36). Held-out H: streams {{1,3,5,7,9}}, never seen by the BO loop
  (26/30 informative).
- Maximize J(x) = 0.5·mean_real(rate_x − rate_center)·100 + 0.5·mean_T-synth(...)·100 subject to
  c(x) = worst deficit vs best standalone ≤ 0.5pp and s(x) = max switches ≤ 6, loop==prop everywhere.
- Seeds: exp713's five arms (params parsed at runtime from the sealed exp713 runner chain). Space:
  exp669 BOUNDS M [0.001, 0.02], G [0.0005, 0.01], HL = 4096·64^u ∈ [4096, 262144]. Surrogate: exp669's
  sealed GP on the UNIT CUBE (disclosed design fix — exp669 fed raw ~1e-3 M/G to an RBF with ls 0.25,
  blinding its kernel to M/G; consistent with its pearson 0.122). Three GPs (−J, c, log1p s),
  acquisition EI(−J)·P(c≤0.5)·P(s≤6), 2048 uniform candidates/iter, RNG seed 20261105, 20 trials.

## Seeds (all evaluated, none cited as winner unless feasible-max)
| arm | margin | gamma | half-life | J pp | c pp | s | feasible |
|---|---|---|---|---|---|---|---|
{seed_rows}

## Best feasible points (x* = max J, ties → earliest)
| src | margin | gamma | half-life | J pp | c pp | s |
|---|---|---|---|---|---|---|
{top_rows}

x* = {xs['src']} — M {xp[0]:.6f}, G {xp[1]:.6f}, HL {xp[2]:.0f}: near-center gamma and HL at the space
floor region with a small margin; J {Jstar:+.4f}pp (real {xs['train']['real']['mean_delta_pp']:+.4f},
T-synth {xs['train']['syn']['mean_delta_pp']:+.4f}), c {xs['train']['score']['c']:.3f}pp,
s {xs['train']['score']['s']}. Runner-up feasible J {top[1][0]:+.4f}pp ({top[1][1]}). Every trial with
J above x* was INFEASIBLE (constraint violation), i.e. under the frozen bars the mean objective has no
exploitable structure beyond noise — {D['n_feasible']}/25 evaluated points feasible; pearson(pred J,
observed J) over the 20 trials = {D['pearson_predJ_vs_obsJ']:.3f} (reported, not gated).

## Held-out H (DESCRIPTIVE — ladder ended at rung 2)
x* vs center on {ho_stats['n']} informative H cells: mean {ho_stats['mean_delta_pp']:+.4f}pp, worst
deficit {ho_stats['worst_pp']:.3f}pp at stream {worst_i} (s={wcfg['s']} lam={wcfg['lam']}
E={wcfg['E']}/L={wcfg['L']}) cap {worst_cap}, 0 cells over the 0.5pp bar, max switches
{ho_stats['max_switches']}, 0 accounting violations. The corrected objective did not reproduce the
exp669→exp674 safety break on held-out streams — but with J(x*) under the training bar there is no
gain claim to transfer.

## Frozen ladder trace
1. ¬H0 ∨ ¬H4 → ACCOUNTING-FAIL — not fired (H0 {D['H0']['cells']} cells, 0 mismatches; H4 det+acct True).
2. J(x*) < +0.05pp → **NO-TRAIN-HEADROOM — FIRES** ({Jstar:+.4f}pp < +0.05pp).
3–6 (HELDOUT-UNSAFE / TRANSFERS-GAIN / TRANSFERS-NONINFERIOR / NO-TRANSFER) not reached.

## What this settles (pre-registered consequence)
- Center is at the bar-constrained mean optimum within BOUNDS; the CostFit tuning line is closed:
  exp669 optimized the wrong objective (worst-deficit, real-only) → exp674 SAFETY-BROKEN → exp711/712/713
  attributed and clamped it (CLAMP-REPAIRS:NO-GAIN) → exp714 re-optimized the RIGHT objective with
  constraints and a held-out split and found no training headroom (best feasible +{Jstar*100:.2f}bp).
  Tuning is no longer a lever on this family.
- Pre-registered next: shared-state N-way metadata economics (exp675 stage B) — the memory/time
  economics line, not the accuracy-tuning line.

## Integrity, determinism, disclosures (follow-up controller re-adjudication)
- run_barbo.py sha256 {art['run_barbo.py'][:16]}…, PREREG.md {art['PREREG.md'][:16]}…, smoke.log
  {art['smoke.log'][:16]}…, smoke-attempt1/2 {art['smoke-attempt1.log'][:16]}…/{art['smoke-attempt2.log'][:16]}…
  == ARTIFACT.sha256 == local run dir; PREREG/runner/ARTIFACT == freeze-commit {freeze_short} blobs;
  freeze ({time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(ct))}) precedes result mtime
  ({time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(RESULT.stat().st_mtime))}).
- Sealed deps sha-verified at adjudication time: exp669/run_bo.py {art['exp669/run_bo.py'][:16]}…,
  exp713/run_gclamp.py {art['exp713/run_gclamp.py'][:16]}…, policies.py {art['policies.py'][:16]}…,
  policies_costfit.py {art['policies_costfit.py'][:16]}…, run_policies_real.py {art['run_policies_real.py'][:16]}…,
  and the 4 sealed JSONs (exp668/exp669/exp670/exp713) == ARTIFACT == JSON-embedded sealed_inputs_sha256.
- Independently written adjudicator (this file): re-derived every stored summary (25 point scores,
  x* selection, held-out stats, seed T-synth stats, real center/bo stats) from raw cells and sealed
  refs; re-implemented the frozen ladder (7/7 boundary self-test) and recomputed pearson; parsed
  run.log and matched all 25 evaluation lines to the JSON.
- LIVE third-process re-evaluation through the SEALED code: all 11 streams regenerated and sha8-asserted
  vs exp670; H-side standalones/center/x* reproduced cell-exact vs the stored grids AND the sealed
  exp713 cells ({n_cmp}+ stored-ref comparisons + 150 live H cells); T-side x* summary reproduced;
  seed arms spot-reproduced at caps {{128, 4096}} on all 6 T streams (60 live cells vs exp713);
  real-trace center re-evaluated vs the sealed exp668 anchor (45/45 fields) and real-trace x*
  re-evaluated → live J {J_live:+.6f}pp == stored, still < +0.05pp. Verdict-critical numbers are
  reproduced end-to-end outside the runner process.
- Disclosed granularity limits: the JSON stores raw cells only for H; seed T-synth cells and T
  standalones are verified at summary level from sealed exp713 raw cells plus the 60-cell live spot
  (not all 180 T cells live). The in-process x* re-evaluation (H4 det) is a stored boolean; the live
  cross-process reproduction above is the independent witness. pearson recomputes from stored pred_J.
- Launch 1 aborted after ~20 s with no output (missing persist flag); one bounded relaunch, unchanged
  runner (LEDGER.md). Disclosed pre-freeze smoke attempts 1–2 (harness count bug; system python lacks
  torch) retained in ARTIFACT; neither touched run logic. SMOKE_OK pre-freeze (S1–S6).
- Adjudication: {n_pass}/{n_all} checks PASS, {elapsed:.0f}s, interpreter exp650 venv python
  (torch {__import__('torch').__version__}), host Mack. No sealed artifact was edited or re-launched.

Data: exp714/exp714-barbo.json (+ this generator); PREREG.md / ARTIFACT.sha256 / smoke logs frozen at
{freeze_short}. Follow-up controller re-adjudicated every gate programmatically: verdict
NO-TRAIN-HEADROOM stands.
"""

out = RUNDIR / "ADDENDUM60.md"
out.write_text(ADD)
print(f"WROTE {out} ({len(ADD)} chars)")
print(f"ADJUDICATION_OK {n_pass}/{n_all} verdict={verdict} elapsed={elapsed:.0f}s")

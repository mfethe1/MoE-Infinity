#!/usr/bin/env python3
"""exp714: bar-constrained joint BO of CostFit (MARGIN, GAMMA, HALF_LIFE) with a HELD-OUT synthetic test.

Pre-registered consequence of exp713 (CLAMP-REPAIRS:NO-GAIN): the exp669 BO pointer (objective = worst
deficit on the 2 real traces only) does not transfer even when made safe. exp714 re-asks the tuning
question with (a) an objective that is the paired MEAN gain vs center (what H2 bars actually test),
(b) the frozen 0.5pp / 6-switch safety bars as BO CONSTRAINTS, and (c) a training set that includes
half of the exp670 synthetic family, with the other half HELD OUT for the verdict.

Training set T:  2 real traces (exp669 MODELS: qwen30b 10 caps + granite 5 caps, base CSV standalones)
                 + synthetic train streams {0,2,4,6,8,10} x 6 caps (informative cells only).
Held-out set H:  synthetic streams {1,3,5,7,9} x 6 caps (informative cells only).
J(x) = 0.5*mean_real(rate_x - rate_center)*100 + 0.5*mean_synth_train_informative(...)*100   (maximize)
c(x) = max(real worst deficit over 15 caps, synth-train worst informative deficit)   constraint <= 0.5pp
s(x) = max switches over 15 real caps and synth-train informative cells            constraint <= 6

Reused SEALED code, imported by path (sha256 of each recorded in ARTIFACT.sha256), never copied:
  exp669 run_bo.py   -> MODELS, BOUNDS, evaluate (real traces), base_rows, to_params, from_params, GP, phi
  exp713 run_gclamp.py -> gen_stream, stream_sha, make_costfit, evaluate (standalones), stream_cfgs, PARAMS
Modes: default = full frozen run. SMOKE=1 = disclosed machinery smoke.
"""
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

D = Path(__file__).parent
HOME = Path.home()
REPO = HOME / "warp-work/moei-granite3b"
sys.path.insert(0, str(REPO))
from benchmarks.cache_simulator.research.run_policies_real import load_accesses  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R669 = _load("sealed_exp669", HOME / "warp-work/exp669-moei-costfit-bo/run_bo.py")
R713 = _load("sealed_exp713", HOME / "warp-work/exp713-moei-gclamp/run_gclamp.py")
EXP668 = HOME / "warp-work/exp668-moei-costfit-grid/exp668-grid.json"
EXP669 = HOME / "warp-work/exp669-moei-costfit-bo/exp669-bo.json"
EXP670 = REPO / "benchmarks/cache_simulator/research/exp670-synth.json"
EXP713 = HOME / "warp-work/exp713-moei-gclamp/exp713-gclamp.json"

TRAIN_IDX = [0, 2, 4, 6, 8, 10]
HELD_IDX = [1, 3, 5, 7, 9]
CAPS = list(R713.CAPS)
SEED_ARMS = list(R713.ARMS)               # center, bo, clamp, clampM, clampH (exp713 params)
SEED_PARAMS = {a: tuple(R713.PARAMS[a]) for a in SEED_ARMS}
CENTER = tuple(R713.CENTER)
SAFETY_PP, SWITCH_MAX, INFORMATIVE_PP = 0.5, 6, 0.1
TRAIN_GAIN_PP, GAIN_PP, NONINF_PP = 0.05, 0.05, -0.05
N_TRIALS = 20
RNG_SEED = 20261105
N_CAND = 2048


def key_of(cfg):
    return json.dumps(cfg, sort_keys=True)


# ---------------------------------------------------------------- data
def build_streams(idxs, n_acc=R713.N_ACC, check_sha=True, seed_perturb=0):
    exp670 = json.loads(EXP670.read_text())
    shas = [st["seed"] for st in exp670["grid"]]
    cfgs = R713.stream_cfgs()
    seeds = np.random.default_rng(67020261104).spawn(11)
    out = {}
    for i, cfg in enumerate(cfgs):
        if i not in idxs:
            continue
        keys = R713.gen_stream(int(seeds[i].integers(0, 2**63)) + seed_perturb, cfg["E"], cfg["L"], cfg["s"],
                               cfg["lam"], n_acc)
        sha = R713.stream_sha(keys)
        if check_sha:
            assert sha == shas[i], f"stream {i} sha {sha} != exp670 {shas[i]}"
        out[i] = {"cfg": cfg, "seed": sha, "keys": keys}
    return out


def standalones(streams, caps=CAPS):
    """lcnu/s3fifo per (stream, cap) via the SEALED exp713 evaluate (arms=[] -> standalones only)."""
    return {i: R713.evaluate(s["keys"], s["cfg"]["E"], s["cfg"]["L"], caps, []) for i, s in streams.items()}


def synth_arm(streams, params, caps=CAPS, top_k=8):
    """One costfit arm on each stream x cap; record format identical to exp713 evaluate's arm entry."""
    out = {}
    for i, s in streams.items():
        E, L, keys = s["cfg"]["E"], s["cfg"]["L"], s["keys"]
        gk = {"num_layers": L, "prior": top_k / E}
        n = len(keys)
        per = {}
        for cap in caps:
            pol = R713.make_costfit(cap, gk, params)
            assert (pol.MARGIN, pol.GAMMA, pol.HALF_LIFE) == tuple(params) and pol._decay == 0.5 ** (1.0 / params[2])
            hits = sum(1 for k in keys if pol.on_access(k))
            per[str(cap)] = {"rate": round(hits / n, 6), "prop": round(pol.effective_hit_rate, 6),
                             "switches": getattr(pol, "switches", 0)}
        out[i] = per
    return out


def real_eval(params, traces, bases):
    x = R669.from_params(*params)
    rec = R669.evaluate(x, traces, bases)
    return rec


# ---------------------------------------------------------------- scoring
def informative(stand_cell):
    return abs(stand_cell["lcnu"]["rate"] - stand_cell["s3fifo"]["rate"]) * 100 >= INFORMATIVE_PP


def synth_stats(arm_res, center_res, stand):
    deltas, worst, maxsw, acct, over = [], None, 0, [], []
    for i in sorted(arm_res):
        for cap, x in arm_res[i].items():
            if x["rate"] != x["prop"]:
                acct.append((i, cap))
            st = stand[i][cap]
            if not informative(st):
                continue
            best = max(st["lcnu"]["rate"], st["s3fifo"]["rate"])
            d = (best - x["rate"]) * 100
            deltas.append((x["rate"] - center_res[i][cap]["rate"]) * 100)
            maxsw = max(maxsw, x["switches"])
            if worst is None or d > worst[0]:
                worst = (d, i, cap)
            if d > SAFETY_PP or x["switches"] > SWITCH_MAX:
                over.append({"stream": i, "cap": cap, "deficit_pp": round(d, 3), "switches": x["switches"]})
    return {"n": len(deltas), "mean_delta_pp": sum(deltas) / len(deltas), "worst_pp": worst[0],
            "worst_cell": [worst[1], worst[2]], "max_switches": maxsw, "acct_violations": acct, "over": over}


def real_stats(rec, center_rec):
    deltas, worst, maxsw, acct = [], None, 0, True
    for name in R669.MODELS:
        for cap, c in rec["per_model"][name]["caps"].items():
            deltas.append((c["rate"] - center_rec["per_model"][name]["caps"][cap]["rate"]) * 100)
            maxsw = max(maxsw, c["switches"])
            acct = acct and c["loop_eq_prop"]
            if worst is None or c["deficit_pp"] > worst:
                worst = c["deficit_pp"]
    return {"n": len(deltas), "mean_delta_pp": sum(deltas) / len(deltas), "worst_pp": worst,
            "max_switches": maxsw, "acct_ok": acct}


def score(real, syn):
    J = 0.5 * real["mean_delta_pp"] + 0.5 * syn["mean_delta_pp"]
    c = max(real["worst_pp"], syn["worst_pp"])
    s = max(real["max_switches"], syn["max_switches"])
    acct = real["acct_ok"] and not syn["acct_violations"]
    return {"J": J, "c": c, "s": s, "acct_ok": acct,
            "feasible": c <= SAFETY_PP and s <= SWITCH_MAX and acct}


# ---------------------------------------------------------------- BO
LO = np.array([b[0] for b in R669.BOUNDS])
HI = np.array([b[1] for b in R669.BOUNDS])


def unit(X):
    """Map exp669 coordinates to the unit cube BEFORE the GP (exp669 fed raw M/G in ~1e-3 units to an
    RBF with lengthscale 0.25, so its kernel was effectively blind to M and G; disclosed design fix)."""
    return (np.atleast_2d(X) - LO) / (HI - LO)


def next_x(X, negJ, C, S, rng):
    U = unit(X)
    jgp, cgp, sgp = R669.GP(U, negJ), R669.GP(U, C), R669.GP(U, np.log1p(S))
    Us = rng.uniform(0.0, 1.0, (N_CAND, 3))
    Xs = LO + Us * (HI - LO)
    mu, sig = jgp.post(Us)
    mc, sc = cgp.post(Us)
    ms, ss = sgp.post(Us)
    feas_obs = (C <= SAFETY_PP) & (S <= SWITCH_MAX)
    best = float(np.min(negJ[feas_obs])) if feas_obs.any() else float(np.min(negJ))
    z = (best - mu) / np.maximum(sig, 1e-9)
    ei = sig * (z * R669.phi(z) + np.exp(-0.5 * z ** 2) / math.sqrt(2 * math.pi))
    pf = R669.phi((SAFETY_PP - mc) / np.maximum(sc, 1e-9)) * R669.phi((math.log1p(SWITCH_MAX + 0.5) - ms) / np.maximum(ss, 1e-9))
    acq = ei * pf
    k = int(np.argmax(acq))
    return Xs[k], float(acq[k]), float(mu[k])


def classify(h0_ok, h4_ok, train_J_star, held_safe, held_mean):
    """Frozen ladder (PREREG)."""
    if not (h0_ok and h4_ok):
        return "ACCOUNTING-FAIL"
    if train_J_star < TRAIN_GAIN_PP:
        return "NO-TRAIN-HEADROOM"
    if not held_safe:
        return "HELDOUT-UNSAFE"
    if held_mean >= GAIN_PP:
        return "TRANSFERS-GAIN"
    if held_mean >= NONINF_PP:
        return "TRANSFERS-NONINFERIOR"
    return "NO-TRANSFER"


# ---------------------------------------------------------------- H0 references
def h0_synth(arm_name, arm_res, stand_res, ref713):
    """Seed-arm synth cells and standalones must equal sealed exp713 grid dicts exactly."""
    ref = {(i, cap): cell for i, st in enumerate(ref713["grid"]) for cap, cell in st["caps"].items()}
    n, mism = 0, []
    for i, per in arm_res.items():
        for cap, x in per.items():
            n += 1
            if x != ref[(i, cap)]["cf_" + arm_name]:
                mism.append([arm_name, i, cap])
    for i, per in stand_res.items():
        for cap, cell in per.items():
            for a in ("lcnu", "s3fifo"):
                n += 1
                if cell[a] != ref[(i, cap)][a]:
                    mism.append([a, i, cap])
    return n, mism


def h0_real(arm_name, rec):
    """center == sealed exp668 cell m0.005_g0.0025 (HL 32768); bo == sealed exp669 trial 1."""
    if arm_name == "center":
        ref = json.loads(EXP668.read_text())["grid"]["m0.005_g0.0025"]
    elif arm_name == "bo":
        t1 = [t for t in json.loads(EXP669.read_text())["trials"] if t.get("trial") == 1][0]
        assert tuple(float(t1["params"][k]) for k in ("margin", "gamma", "half_life")) == SEED_PARAMS["bo"]
        ref = t1["per_model"]
    else:
        return 0, []
    n, mism = 0, []
    for name in R669.MODELS:
        for cap, c in rec["per_model"][name]["caps"].items():
            r = ref[name]["caps"][cap]
            for f in ("rate", "switches", "deficit_pp"):
                n += 1
                if c[f] != r[f]:
                    mism.append([arm_name, name, cap, f])
    return n, mism


# ---------------------------------------------------------------- main run
def load_real():
    traces, bases = {}, {}
    for name, cfg in R669.MODELS.items():
        traces[name] = load_accesses([str(REPO / p) for p in cfg["trace"]], ignore_layers=0, prefill="skip")
        bases[name] = R669.base_rows(REPO / "benchmarks/cache_simulator/research" / cfg["base"])
    return traces, bases


def run(n_trials=N_TRIALS, real=None, train=None, held=None, log=print, caps=None):
    caps = caps or CAPS
    t0 = time.time()
    ref713 = json.loads(EXP713.read_text())
    traces, bases = real if real is not None else load_real()
    train = train if train is not None else build_streams(set(TRAIN_IDX))
    held = held if held is not None else build_streams(set(HELD_IDX))
    st_tr, st_ho = standalones(train, caps), standalones(held, caps)
    h0n, h0m = 0, []
    pts = []  # dicts: params, real, syn, score, src
    center_real = center_syn = None
    for a in SEED_ARMS:
        p = SEED_PARAMS[a]
        rr = real_eval(p, traces, bases)
        sy = synth_arm(train, p, caps)
        n1, m1 = h0_synth(a, sy, st_tr if a == "center" else {}, ref713)
        n2, m2 = h0_real(a, rr)
        h0n += n1 + n2
        h0m += m1 + m2
        if a == "center":
            center_real, center_syn = rr, sy
        rs, ss = real_stats(rr, center_real), synth_stats(sy, center_syn, st_tr)
        pts.append({"src": "seed:" + a, "params": list(p), "real": rs, "syn": ss, "score": score(rs, ss)})
        log(f"seed {a} J={pts[-1]['score']['J']:+.4f} c={pts[-1]['score']['c']:.3f} s={pts[-1]['score']['s']} "
            f"feas={pts[-1]['score']['feasible']} [{time.time()-t0:.0f}s]")
    X = np.array([R669.from_params(*pt["params"]) for pt in pts])
    negJ = np.array([-pt["score"]["J"] for pt in pts])
    C = np.array([pt["score"]["c"] for pt in pts])
    S = np.array([float(pt["score"]["s"]) for pt in pts])
    rng = np.random.default_rng(RNG_SEED)
    preds = []
    for t in range(n_trials):
        xt, acq, mu = next_x(X, negJ, C, S, rng)
        p = R669.to_params(xt)
        rr = real_eval(p, traces, bases)
        sy = synth_arm(train, p, caps)
        rs, ss = real_stats(rr, center_real), synth_stats(sy, center_syn, st_tr)
        sc = score(rs, ss)
        pts.append({"src": f"trial:{t+1}", "params": list(p), "real": rs, "syn": ss, "score": sc,
                    "acq": round(acq, 6), "pred_J": -mu})
        preds.append((-mu, sc["J"]))
        X = np.vstack([X, xt]); negJ = np.append(negJ, -sc["J"]); C = np.append(C, sc["c"]); S = np.append(S, sc["s"])
        log(f"trial {t+1:2d} M{p[0]:.5f} G{p[1]:.5f} HL{p[2]:.0f} J={sc['J']:+.4f} c={sc['c']:.3f} s={sc['s']} "
            f"feas={sc['feasible']} [{time.time()-t0:.0f}s]")
    feas = [k for k, pt in enumerate(pts) if pt["score"]["feasible"]]
    kstar = max(feas or [0], key=lambda k: (pts[k]["score"]["J"], -k))  # ties -> earliest point
    star = pts[kstar]
    pstar = tuple(star["params"])
    # held-out evaluation: center + x*, H0 for center/standalones vs exp713
    ho_center = synth_arm(held, CENTER, caps)
    n3, m3 = h0_synth("center", ho_center, st_ho, ref713)
    h0n += n3
    h0m += m3
    ho_star = synth_arm(held, pstar, caps)
    ho = synth_stats(ho_star, ho_center, st_ho)
    held_safe = not ho["over"] and ho["max_switches"] <= SWITCH_MAX and ho["worst_pp"] <= SAFETY_PP
    # H4: determinism re-evaluation of x* (real + train + held-out) in the same process, must match exactly
    rr2 = real_eval(pstar, traces, bases)
    sy2 = synth_arm(train, pstar, caps)
    ho2 = synth_arm(held, pstar, caps)
    det = (real_stats(rr2, center_real) == star["real"]
           and json.dumps(ho2, sort_keys=True) == json.dumps(ho_star, sort_keys=True)
           and synth_stats(sy2, center_syn, st_tr) == star["syn"])
    acct_all = all(pt["score"]["acct_ok"] for pt in pts) and not ho["acct_violations"]
    h0_ok = h0n > 0 and not h0m
    h4_ok = det and acct_all
    verdict = classify(h0_ok, h4_ok, star["score"]["J"], held_safe, ho["mean_delta_pp"])
    pr = np.array(preds)
    pear = float(np.corrcoef(pr[:, 0], pr[:, 1])[0, 1]) if len(pr) > 2 and np.std(pr[:, 1]) > 0 else None
    return {"verdict": verdict, "H0": {"cells": h0n, "mismatches": h0m, "ok": h0_ok},
            "H4": {"determinism_xstar": det, "accounting_all": acct_all, "ok": h4_ok},
            "x_star": {"src": star["src"], "params": list(pstar), "train": star},
            "heldout": {"stats": ho, "H1_safe": held_safe, "mean_delta_vs_center_pp": round(ho["mean_delta_pp"], 4),
                        "grid_star": ho_star, "grid_center": ho_center, "standalones": st_ho},
            "points": pts, "n_feasible": len(feas), "pearson_predJ_vs_obsJ": pear,
            "elapsed_s": round(time.time() - t0, 1)}


RULES = {"train_idx": TRAIN_IDX, "held_idx": HELD_IDX, "caps": CAPS, "seed_arms": SEED_ARMS,
         "seed_params": {a: list(p) for a, p in SEED_PARAMS.items()}, "center": list(CENTER),
         "safety_pp": SAFETY_PP, "switch_max": SWITCH_MAX, "informative_pp": INFORMATIVE_PP,
         "train_gain_pp": TRAIN_GAIN_PP, "gain_pp": GAIN_PP, "noninf_pp": NONINF_PP, "n_trials": N_TRIALS,
         "rng_seed": RNG_SEED, "n_cand": N_CAND, "kernel": "exp669 GP (RBF ls 0.25, signal 1, noise 1e-4)",
         "space": "exp669 BOUNDS: M[0.001,0.02] G[0.0005,0.01] HL 4096*64^u"}


def smoke():
    print("PARAMS seeds", json.dumps(SEED_PARAMS))
    ok = True
    # S1 sha assertion bites
    try:
        build_streams({0}, seed_perturb=1)
        print("SMOKE S1 FAIL: perturbed seed not caught"); ok = False
    except AssertionError:
        print("SMOKE S1 ok: sha assertion bites on perturbed seed")
    # S2 full-N H0 on one train stream (idx 4) x 2 caps for center/bo + standalones; and timing
    ref713 = json.loads(EXP713.read_text())
    tr = build_streams({4})
    t = time.time()
    st = standalones(tr, caps=[512, 2048])
    c = synth_arm(tr, CENTER, caps=[512, 2048])
    b = synth_arm(tr, SEED_PARAMS["bo"], caps=[512, 2048])
    dt = time.time() - t
    n1, m1 = h0_synth("center", c, st, ref713)
    n2, m2 = h0_synth("bo", b, {}, ref713)
    s2 = (n1 + n2) == 8 and not (m1 or m2)
    print(f"SMOKE S2 full-N synth H0 vs exp713 cells {n1+n2} (expect 8) mismatches {m1 + m2} ok {s2} "
          f"(time {dt:.1f}s for 2 caps x 4 policies)")
    import copy
    bad = copy.deepcopy(b); bad[4]["512"]["rate"] += 1e-6
    s3 = bool(h0_synth("bo", bad, {}, ref713)[1])
    print("SMOKE S3 H0 negative control detects perturbation:", s3)
    # S4 real-trace H0 for center and bo (full traces) + timing
    t = time.time()
    real = load_real()
    rc = real_eval(CENTER, *real)
    rb = real_eval(SEED_PARAMS["bo"], *real)
    n4, m4 = h0_real("center", rc)
    n5, m5 = h0_real("bo", rb)
    s4 = n4 == 45 and n5 == 45 and not (m4 or m5)
    print(f"SMOKE S4 real-trace H0 center vs exp668 + bo vs exp669 trial1: cells {n4+n5} ok {s4} "
          f"({time.time()-t:.0f}s for 2 real evals incl load)")
    # S5 reduced end-to-end run (2 trials, short streams, no sha) twice -> deterministic, well-formed
    trs = build_streams({0, 10}, n_acc=60_000, check_sha=False)
    hos = build_streams({1, 9}, n_acc=60_000, check_sha=False)
    short = ({n: (a[:50_000], st_) for n, (a, st_) in real[0].items()}, real[1])
    r1 = run(n_trials=2, real=short, train=trs, held=hos, log=lambda *_: None, caps=[128, 256])
    r2 = run(n_trials=2, real=short, train=trs, held=hos, log=lambda *_: None, caps=[128, 256])
    strip = lambda r: {k: v for k, v in r.items() if k != "elapsed_s"}  # noqa: E731
    s5 = json.dumps(strip(r1), sort_keys=True, default=str) == json.dumps(strip(r2), sort_keys=True, default=str)
    wf = (len(r1["points"]) == 7 and r1["verdict"] in {"ACCOUNTING-FAIL", "NO-TRAIN-HEADROOM", "HELDOUT-UNSAFE",
                                                       "TRANSFERS-GAIN", "TRANSFERS-NONINFERIOR", "NO-TRANSFER"}
          and r1["H4"]["determinism_xstar"] and r1["H4"]["accounting_all"])
    print(f"SMOKE S5 reduced e2e det {s5} | well-formed {wf} | verdict(reduced, NOT a result) {r1['verdict']} "
          f"| H0 reduced (expected FAIL: short streams) ok={r1['H0']['ok']}")
    # S6 hand-built stats arithmetic + ladder
    stand = {0: {"1": {"lcnu": {"rate": 0.30, "prop": 0.30}, "s3fifo": {"rate": 0.31, "prop": 0.31}},
                 "2": {"lcnu": {"rate": 0.50, "prop": 0.50}, "s3fifo": {"rate": 0.5005, "prop": 0.5005}}}}
    cen = {0: {"1": {"rate": 0.309, "prop": 0.309, "switches": 1}, "2": {"rate": 0.4, "prop": 0.4, "switches": 0}}}
    arm = {0: {"1": {"rate": 0.304, "prop": 0.304, "switches": 7}, "2": {"rate": 0.1, "prop": 0.2, "switches": 0}}}
    ss = synth_stats(arm, cen, stand)
    arith = (ss["n"] == 1 and round(ss["worst_pp"], 6) == 0.6 and round(ss["mean_delta_pp"], 6) == -0.5
             and ss["max_switches"] == 7 and ss["acct_violations"] == [(0, "2")] and len(ss["over"]) == 1)
    T, F = True, False
    lad = [classify(F, T, 1, T, 1) == "ACCOUNTING-FAIL", classify(T, F, 1, T, 1) == "ACCOUNTING-FAIL",
           classify(T, T, 0.0499, T, 1) == "NO-TRAIN-HEADROOM", classify(T, T, 0.05, F, 1) == "HELDOUT-UNSAFE",
           classify(T, T, 0.05, T, 0.05) == "TRANSFERS-GAIN", classify(T, T, 0.05, T, -0.05) == "TRANSFERS-NONINFERIOR",
           classify(T, T, 0.05, T, -0.0501) == "NO-TRANSFER"]
    split = sorted(TRAIN_IDX + HELD_IDX) == list(range(11)) and not set(TRAIN_IDX) & set(HELD_IDX)
    print(f"SMOKE S6 stats arithmetic {arith} | ladder 7/7 {all(lad)} | split partition {split}")
    ok = ok and s2 and s3 and s4 and s5 and wf and arith and all(lad) and split
    print("SMOKE_OK" if ok else "SMOKE_FAIL")
    return 0 if ok else 1


def main():
    if os.environ.get("SMOKE") == "1":
        sys.exit(smoke())
    out = run()
    out["rules"] = RULES
    out["sealed_inputs_sha256"] = {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (EXP668, EXP669, EXP670, EXP713)}
    (D / "exp714-barbo.json").write_text(json.dumps(out, indent=1, default=str))
    print("settled verdict=" + out["verdict"], flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""exp713: exp674 joint BO point with GAMMA CLAMPED to exp712's certified edge.

exp712 (G-BOUNDARY@g4) certified gamma at center M/HL on [0.0025, g3]; its pre-registered
G-BOUNDARY@g_j (j>=2) consequence is to re-run exp674's joint transfer with gamma clamped to the
certified edge while keeping exp674's BO margin and BO half-life. Params are parsed at runtime:
BO margin/HL from sealed exp674 bo_params, the clamp gamma from sealed exp712
certified_gamma_upper_edge. No hand-transcribed values.

Arms (costfit; margin, gamma, half_life):
  center = (0.005, 0.0025, 32768)            bookend == exp674 cf_center
  bo     = (M_BO, G_BO, HL_BO)               bookend == exp674 cf_bo
  clamp  = (M_BO, G_EDGE, HL_BO)             PRIMARY (verdict arm)
  clampM = (M_BO, G_EDGE, 32768)             attribution: HL back at center
  clampH = (0.005, G_EDGE, HL_BO)            attribution: margin back at center
Streams: exactly exp670/674/710/711/712's 11 (sha8-asserted vs research/exp670-synth.json).
Stream/costfit/evaluate/run_all/h0 machinery is AST-asserted identical to the sealed exp712 runner.

Modes: default = full frozen run.  SMOKE=1 = disclosed machinery smoke.
"""
import ast
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path.home() / "warp-work/moei-granite3b"))
from benchmarks.cache_simulator.policies import build_policy  # noqa: E402

D = Path(__file__).parent
REPO = Path.home() / "warp-work/moei-granite3b"
N_ACC = 638_208
H_RECENCY, R_WINDOW = 2048, 4096
SKEWS = [0.8, 1.1, 1.4]
LOCALITIES = [0.0, 0.3, 0.6]
CAPS = [128, 256, 512, 1024, 2048, 4096]
CENTER = (0.005, 0.0025, 32768.0)
EXP670 = REPO / "benchmarks/cache_simulator/research/exp670-synth.json"
EXP674 = Path.home() / "warp-work/exp674-moei-hl-transfer/exp674-hl-transfer.json"
EXP712 = Path.home() / "warp-work/exp712-moei-gdose/exp712-gdose.json"
EXP712_RUNNER = Path.home() / "warp-work/exp712-moei-gdose/run_gdose.py"
_BO = json.loads(EXP674.read_text())["bo_params"]
BO = (float(_BO["margin"]), float(_BO["gamma"]), float(_BO["half_life"]))
_X712 = json.loads(EXP712.read_text())
assert _X712["verdict"].startswith("G-BOUNDARY@g"), _X712["verdict"]
G_EDGE = float(_X712["certified_gamma_upper_edge"])
PARAMS = {
    "center": CENTER,
    "bo": BO,
    "clamp": (BO[0], G_EDGE, BO[2]),
    "clampM": (BO[0], G_EDGE, CENTER[2]),
    "clampH": (CENTER[0], G_EDGE, BO[2]),
}
ARMS = list(PARAMS)
BOOKENDS = {"center": "cf_center", "bo": "cf_bo"}
SAFETY_PP, SWITCH_MAX, INFORMATIVE_PP, TRANSFER_PP = 0.5, 6, 0.1, -0.05


def arm_params(a):
    return PARAMS[a]


def arm(a):
    return f"cf_{a}"


def gen_stream(seed, E, L, s, lam, n_acc=N_ACC):
    rng = np.random.default_rng(seed)
    ranks = np.arange(1, E + 1, dtype=np.float64)
    zipf_p = ranks ** (-s)
    zipf_p /= zipf_p.sum()
    experts = rng.choice(E, size=n_acc, p=zipf_p)
    layers = rng.integers(0, L, size=n_acc)
    keys = list(zip(layers.tolist(), experts.tolist()))
    n_replay = int(lam * n_acc)
    idx = rng.choice(np.arange(R_WINDOW, n_acc), size=n_replay, replace=False)
    w = 0.5 ** (np.arange(1, R_WINDOW + 1) / H_RECENCY)
    w /= w.sum()
    ages = rng.choice(R_WINDOW, size=n_replay, p=w) + 1
    for i, a in zip(idx.tolist(), ages.tolist()):
        keys[i] = keys[i - a]
    return keys


def stream_sha(keys):
    raw = "\x00".join(f"{l}:{e}" for l, e in keys[:50000])
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def make_costfit(cap, gk, params):
    m, g, hl = params
    pol = build_policy("costfit", cap, **gk)
    pol.MARGIN, pol.GAMMA, pol.HALF_LIFE = m, g, hl
    pol._decay = 0.5 ** (1.0 / hl)
    return pol


def evaluate(keys, E, L, caps, arms, top_k=8):
    out = {}
    gk = {"num_layers": L, "prior": top_k / E}
    n = len(keys)
    for cap in caps:
        cell = {}
        for name in ("lcnu", "s3fifo"):
            pol = build_policy(name, cap)
            hits = sum(1 for k in keys if pol.on_access(k))
            cell[name] = {"rate": round(hits / n, 6), "prop": round(pol.effective_hit_rate, 6)}
        for a in arms:
            p = arm_params(a)
            pol = make_costfit(cap, gk, p)
            assert (pol.MARGIN, pol.GAMMA, pol.HALF_LIFE) == p and pol._decay == 0.5 ** (1.0 / p[2])
            hits = sum(1 for k in keys if pol.on_access(k))
            cell[arm(a)] = {"rate": round(hits / n, 6), "prop": round(pol.effective_hit_rate, 6),
                            "switches": getattr(pol, "switches", 0)}
        out[str(cap)] = cell
    return out


def stream_cfgs():
    streams = [{"s": s, "lam": lam, "E": 128, "L": 48} for s in SKEWS for lam in LOCALITIES]
    streams.append({"s": 1.1, "lam": 0.3, "E": 32, "L": 32})
    streams.append({"s": 1.4, "lam": 0.6, "E": 32, "L": 32})
    return streams


def run_all(expected_shas, idxs=None, caps=CAPS, arms=ARMS, n_acc=N_ACC, check_sha=True, seed_perturb=0):
    streams = stream_cfgs()
    seeds = np.random.default_rng(67020261104).spawn(11)
    t0 = time.time()
    grid = []
    for i, cfg in enumerate(streams):
        if idxs is not None and i not in idxs:
            continue
        keys = gen_stream(int(seeds[i].integers(0, 2**63)) + seed_perturb, cfg["E"], cfg["L"], cfg["s"], cfg["lam"], n_acc)
        sha = stream_sha(keys)
        if check_sha:
            assert sha == expected_shas[i], f"stream {i} sha {sha} != exp670 {expected_shas[i]}"
        res = evaluate(keys, cfg["E"], cfg["L"], caps, arms)
        grid.append({"cfg": cfg, "seed": sha, "caps": res})
        print(f"stream {i} done [{time.time()-t0:.0f}s]", flush=True)  # timings only until settlement
    return grid


def h0_replication(grid, ref_grid):
    ref = {(json.dumps(st["cfg"], sort_keys=True), cap): cell for st in ref_grid for cap, cell in st["caps"].items()}
    mism, n = [], 0
    for st in grid:
        for cap, cell in st["caps"].items():
            r = ref[(json.dumps(st["cfg"], sort_keys=True), cap)]
            for a, refarm in BOOKENDS.items():
                if arm(a) not in cell:
                    continue
                n += 1
                if cell[arm(a)] != r[refarm]:
                    mism.append({"cfg": st["cfg"], "cap": cap, "arm": arm(a), "ref": refarm})
            for a in ("lcnu", "s3fifo"):
                n += 1
                if cell[a] != r[a]:
                    mism.append({"cfg": st["cfg"], "cap": cap, "arm": a, "ref": a})
    return {"cells": n, "mismatches": mism, "ok": n > 0 and not mism}




def classify(h0_ok, h4_ok, safe, h2):
    """Frozen ladder (PREREG). safe: dict arm -> H1 bool; h2: clamp mean delta vs center >= TRANSFER_PP."""
    if not (h0_ok and h4_ok):
        return "ACCOUNTING-FAIL"
    if safe["clamp"]:
        return "CLAMP-REPAIRS:" + ("TRANSFERS" if h2 else "NO-GAIN")
    tag = {(True, False): "HL-CONDITIONAL", (True, True): "JOINT-ONLY",
           (False, True): "M-CONDITIONAL", (False, False): "BOTH-CONTEXTS"}[(safe["clampM"], safe["clampH"])]
    return "CLAMP-INSUFFICIENT:" + tag


def adjudicate(grid, h0, arms=ARMS):
    informative, acct = 0, []
    per = {a: {"worst": None, "safety_cells": 0, "sw_cells": 0, "max_sw": 0, "deltas": [], "over": []} for a in arms}
    for st in grid:
        for cap, cell in st["caps"].items():
            for a in arms:
                x = cell[arm(a)]
                if x["rate"] != x["prop"]:
                    acct.append({"cfg": st["cfg"], "cap": cap, "arm": arm(a)})
            lc, s3 = cell["lcnu"]["rate"], cell["s3fifo"]["rate"]
            if abs(lc - s3) * 100 < INFORMATIVE_PP:
                continue
            informative += 1
            best = max(lc, s3)
            for a in arms:
                x = cell[arm(a)]
                p = per[a]
                d = (best - x["rate"]) * 100
                p["deltas"].append((x["rate"] - cell[arm("center")]["rate"]) * 100)
                p["max_sw"] = max(p["max_sw"], x["switches"])
                if p["worst"] is None or d > p["worst"]["deficit_pp"]:
                    p["worst"] = {"cfg": st["cfg"], "cap": cap, "deficit_pp": round(d, 3), "switches": x["switches"]}
                if d > SAFETY_PP:
                    p["safety_cells"] += 1
                    p["over"].append({"cfg": st["cfg"], "cap": cap, "deficit_pp": round(d, 3)})
                if x["switches"] > SWITCH_MAX:
                    p["sw_cells"] += 1
    out_arms = {}
    for a in arms:
        p = per[a]
        out_arms[a] = {"params": list(arm_params(a)), "H1_safe": p["safety_cells"] == 0 and p["sw_cells"] == 0,
                       "worst": p["worst"], "cells_over_bar": p["safety_cells"], "over_cells": p["over"],
                       "cells_over_switch": p["sw_cells"], "max_switches": p["max_sw"],
                       "mean_delta_vs_center_pp": round(sum(p["deltas"]) / len(p["deltas"]), 4) if p["deltas"] else None}
    h4 = not acct
    if list(arms) == ARMS:
        md = out_arms["clamp"]["mean_delta_vs_center_pp"]
        h2 = md is not None and md >= TRANSFER_PP
        verdict = classify(h0["ok"], h4, {a: out_arms[a]["H1_safe"] for a in ARMS}, h2)
    else:
        h2, verdict = None, "PARTIAL-GRID"
    return {"verdict": verdict, "H2_transfer_clamp": h2, "H0_replication": h0, "H4_accounting": h4,
            "accounting_violations": acct, "informative_cells": informative, "arms": out_arms}


def machinery_identity():
    """Stream/costfit/evaluate/run_all/h0 code must be AST-identical to the sealed exp712 runner."""
    def fns(p):
        t = ast.parse(Path(p).read_text())
        return {n.name: ast.dump(n) for n in t.body if isinstance(n, ast.FunctionDef)}
    mine, sealed = fns(__file__), fns(EXP712_RUNNER)
    return all(mine[k] == sealed[k] for k in ("gen_stream", "stream_sha", "make_costfit", "evaluate",
                                               "stream_cfgs", "run_all", "h0_replication"))


def smoke():
    exp670 = json.loads(EXP670.read_text()); shas = [st["seed"] for st in exp670["grid"]]
    ref = json.loads(EXP674.read_text())["grid"]
    print("PARAMS", json.dumps(PARAMS), "| exp712 verdict", _X712["verdict"])
    ident = machinery_identity()
    print("SMOKE S0 machinery AST-identical to sealed exp712 runner:", ident)
    try:
        run_all(shas, idxs={0}, caps=[], arms=[], seed_perturb=1)
        print("SMOKE S1 FAIL: perturbed seed not caught"); return 1
    except AssertionError:
        print("SMOKE S1 ok: sha assertion bites on perturbed seed")
    g = run_all(shas, idxs={4}, caps=[512, 2048], arms=list(BOOKENDS))
    h0 = h0_replication(g, ref)
    assert h0["cells"] == 8, h0
    print("SMOKE S2 H0 full-N bookend replication vs exp674 cells", h0["cells"], "ok", h0["ok"])
    bad = json.loads(json.dumps(g)); bad[0]["caps"]["512"][arm("bo")]["rate"] += 1e-6
    neg = not h0_replication(bad, ref)["ok"]
    print("SMOKE S3 H0 negative control detects perturbation:", neg)
    r1 = run_all(shas, idxs={0, 9}, caps=[128, 256], n_acc=60_000, check_sha=False)
    r2 = run_all(shas, idxs={0, 9}, caps=[128, 256], n_acc=60_000, check_sha=False)
    det = json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    adj = adjudicate(r1, {"ok": True, "cells": 0, "mismatches": []})
    wf = set(adj["arms"]) == set(ARMS) and adj["verdict"] != "PARTIAL-GRID"
    ser = isinstance(json.dumps(adj), str)
    rates = [0.31, 0.304, 0.3049, 0.3051, 0.31]
    cell = {"lcnu": {"rate": 0.30, "prop": 0.30}, "s3fifo": {"rate": 0.31, "prop": 0.31}}
    for i, a in enumerate(ARMS):
        cell[arm(a)] = {"rate": rates[i], "prop": rates[i], "switches": [0, 7, 1, 1, 0][i]}
    syn = adjudicate([{"cfg": {"s": 0, "lam": 0, "E": 1, "L": 1}, "caps": {"1": cell}}],
                     {"ok": True, "cells": 0, "mismatches": []})
    A = syn["arms"]
    arith = (A["bo"]["worst"]["deficit_pp"] == 0.6 and not A["bo"]["H1_safe"] and A["bo"]["cells_over_switch"] == 1
             and A["clamp"]["worst"]["deficit_pp"] == 0.51 and not A["clamp"]["H1_safe"] and A["clampM"]["H1_safe"]
             and A["clampH"]["H1_safe"] and A["clamp"]["mean_delta_vs_center_pp"] == -0.51
             and syn["verdict"] == "CLAMP-INSUFFICIENT:JOINT-ONLY")
    T, F = True, False
    lad = [classify(T, T, {"clamp": T, "clampM": F, "clampH": F}, T) == "CLAMP-REPAIRS:TRANSFERS",
           classify(T, T, {"clamp": T, "clampM": T, "clampH": T}, F) == "CLAMP-REPAIRS:NO-GAIN",
           classify(T, T, {"clamp": F, "clampM": T, "clampH": F}, T) == "CLAMP-INSUFFICIENT:HL-CONDITIONAL",
           classify(T, T, {"clamp": F, "clampM": T, "clampH": T}, T) == "CLAMP-INSUFFICIENT:JOINT-ONLY",
           classify(T, T, {"clamp": F, "clampM": F, "clampH": T}, T) == "CLAMP-INSUFFICIENT:M-CONDITIONAL",
           classify(T, T, {"clamp": F, "clampM": F, "clampH": F}, T) == "CLAMP-INSUFFICIENT:BOTH-CONTEXTS",
           classify(F, T, {"clamp": T, "clampM": T, "clampH": T}, T) == "ACCOUNTING-FAIL",
           classify(T, F, {"clamp": T, "clampM": T, "clampH": T}, T) == "ACCOUNTING-FAIL"]
    gam = _X712["rules"]["gammas"]
    par = (G_EDGE in gam and gam.index(G_EDGE) == int(_X712["verdict"].split("@g")[1]) - 1
           and CENTER[1] < G_EDGE < BO[1] and PARAMS["clamp"][0] == BO[0] and PARAMS["clamp"][2] == BO[2]
           and len(set(PARAMS.values())) == 5)
    print("SMOKE S4 det", det, "| adjudicate well-formed", wf, "| serializable", ser, "| accounting",
          adj["H4_accounting"], "| adjudicator arithmetic", arith, "| ladder 8/8", all(lad), "| params", par)
    ok = ident and h0["ok"] and neg and det and wf and ser and adj["H4_accounting"] and arith and all(lad) and par
    print("SMOKE_OK" if ok else "SMOKE_FAIL")
    return 0 if ok else 1


def main():
    if os.environ.get("SMOKE") == "1":
        sys.exit(smoke())
    assert machinery_identity(), "machinery drifted from sealed exp712 runner"
    exp670 = json.loads(EXP670.read_text()); shas = [st["seed"] for st in exp670["grid"]]
    ref = json.loads(EXP674.read_text())["grid"]
    t0 = time.time()
    g1 = run_all(shas)
    g2 = run_all(shas)
    assert json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True), "nondeterministic"
    v = adjudicate(g1, h0_replication(g1, ref))
    out = {**v, "determinism_two_runs": True, "elapsed_s": round(time.time() - t0, 1), "grid": g1,
           "rules": {"caps": CAPS, "skews": SKEWS, "localities": LOCALITIES, "n_acc": N_ACC,
                     "center": list(CENTER), "bo": list(BO), "bo_source": "exp674 bo_params",
                     "g_edge": G_EDGE, "g_edge_source": "exp712 certified_gamma_upper_edge",
                     "params": {a: list(p) for a, p in PARAMS.items()}, "arms": ARMS, "bookends": BOOKENDS,
                     "bookend_source": "exp674", "safety_pp": SAFETY_PP, "switch_max": SWITCH_MAX,
                     "informative_pp": INFORMATIVE_PP, "transfer_pp": TRANSFER_PP}}
    (D / "exp713-gclamp.json").write_text(json.dumps(out, indent=1))
    print("settled verdict=" + v["verdict"], flush=True)


if __name__ == "__main__":
    main()

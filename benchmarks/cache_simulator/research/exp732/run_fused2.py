#!/usr/bin/env python3
"""exp732: FusedCostFit (exp729's fused per-key record ported to the N=2 CostFit head) — A/A-gated paired
CPU-time payoff + metadata economics + descriptive C-level array-of-struct byte model.

Pre-registered CONFIRMED branch of exp729 (ADDENDUM64). Runner = sealed exp729 runner with the unit list, arm module,
oracle policy, seed and file names changed (asserted substitutions); timing, ladder and self-test are unchanged.
Units, timed in fresh spawned processes, interleaved ABBA (even rounds) / BAAB (odd rounds), per-thread CPU time:
  null   : costfit (A) vs costfit (A')       <- A/A null control (validity gate)
  fused2 : costfit (A) vs FusedCostFit (B)   <- ONE Key->list record for all 5 per-key fields (PRIMARY)
Every timed replay's hit_rate must equal exp718 PASS-1 costfit exactly; in round 0 the terminal full state of the
B arm must equal the paired costfit A arm's exactly, and the per-key struct census (+ C-level model) is recorded.
"""
import ctypes
import gc
import hashlib
import json
import multiprocessing
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
HOME = Path.home()
REPO = HOME / "warp-work/moei-granite3b"          # sealed tree (data + package), NOT a git repo
sys.path.insert(0, str(REPO))
EXP718_JSON = HOME / "warp-work/exp718-moei-shared-econ/exp718-econ.json"
sys.path.insert(0, str(D))

CAPS = [256, 1024, 4096, 262144]
STREAMS = {
    "qwen30b": REPO / "data/belady/stream_qwen30b.pt",
    "granite": REPO / "benchmarks/cache_simulator/data/handcrafted8-greedy512/belady/stream_granite3b.pt",
}
UNITS = [("null", "costfit", "costfit"), ("fused2", "costfit", "fused2")]
SAVING_MAX_STRUCT = 0.80       # economics qualifier: fused2/costfit struct_bytes at EVERY cell
ROUNDS = 8
MIN_ROUNDS = 5
WALL_BUDGET_S = int(5.5 * 3600)
SEED = 732
NULL_POOLED = (0.97, 1.03)     # median over 8 cells of per-cell median A/A ratio
NULL_CELL = (0.93, 1.07)       # every cell's median A/A ratio
PAYOFF_CONFIRMED = 1.10
PAYOFF_MARGINAL = 1.35
QOS_USER_INTERACTIVE = 0x21
SMOKE_LIMIT = 40_000


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_sealed_deps():
    deps = {}
    for line in (D / "sealed_deps.sha256").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sha, path = line.split()
        p = Path(path)
        if not p.is_absolute():
            p = REPO / path
        deps[str(p)] = sha
    return deps


def assert_sealed():
    deps = load_sealed_deps()
    for p, sha in deps.items():
        got = sha256_file(p)
        if got != sha:
            raise RuntimeError(f"SEALED DRIFT {p}: {got} != {sha}")
    return deps


import benchmarks.cache_simulator.research.census_shared_costfit as CEN  # noqa: E402
from benchmarks.cache_simulator.policies import build_policy  # noqa: E402
from benchmarks.cache_simulator.research.run_policies_real import (  # noqa: E402
    geometry_kwargs,
    load_accesses,
)
import policies_fused2 as PF  # noqa: E402


def hb(t0, msg):
    print(f"[{time.time() - t0:7.0f}s] {msg}", flush=True)


def set_qos():
    try:
        lib = ctypes.CDLL("/usr/lib/libSystem.dylib")
        return int(lib.pthread_set_qos_class_self_np(QOS_USER_INTERACTIVE, 0))
    except Exception as e:  # disclosed, never fatal
        return f"unavailable: {e!r}"


def make(name, cap, kw):
    return PF.ARMS[name](cap, **kw) if name in PF.ARMS else build_policy(name, cap, **kw)


def timed_replay(name, cap, acc, kw, keep=False):
    p = make(name, cap, kw)
    gc.collect()
    t_th, t_pr, t_wall = time.thread_time_ns(), time.process_time_ns(), time.perf_counter_ns()
    CEN._replay(p, acc)
    t_wall = time.perf_counter_ns() - t_wall
    t_pr = time.process_time_ns() - t_pr
    t_th = time.thread_time_ns() - t_th
    hr = p.hit_rate
    out = {"thread_ns": t_th, "proc_ns": t_pr, "wall_ns": t_wall, "hit_rate": hr}
    if keep:
        out["_policy"] = p
    del p
    return out


def worker(job):
    """One fresh spawned process: one stream, all caps, all units, one round."""
    stream, path, rnd, cap_order, limit = job
    qos = set_qos()
    acc, stats = load_accesses([str(path)], ignore_layers=0, prefill="skip")
    if limit:
        acc = acc[:limit]
    out = {"stream": stream, "round": rnd, "qos_rc": qos, "accesses": len(acc), "units": [],
           "loadavg_start": os.getloadavg()[0]}
    abba = (rnd % 2 == 0)
    for cap in cap_order:
        for unit, a_name, b_name in UNITS:
            kw_a = geometry_kwargs(a_name, stats)
            kw_b = geometry_kwargs("costfit", stats)  # every arm takes costfit geometry
            seq = ["A", "B", "B", "A"] if abba else ["B", "A", "A", "B"]
            reps = []
            census = None
            for j, arm in enumerate(seq):
                nm, kw = (a_name, kw_a) if arm == "A" else (b_name, kw_b)
                # round 0: keep the LAST A and LAST B policies for untimed parity/census after timing
                keep = rnd == 0 and j >= 2
                r = timed_replay(nm, cap, acc, kw, keep=keep)
                r["arm"] = arm
                reps.append(r)
            if rnd == 0:
                pa = [r.pop("_policy") for r in reps if r["arm"] == "A" and "_policy" in r][0]
                pb = [r.pop("_policy") for r in reps if r["arm"] == "B" and "_policy" in r][0]
                census = {"state_eq": PF.full_state(pb) == PF.full_state(pa), "a": PF.census(pa),
                          "b": PF.census(pb), "a_eq_CEN": {k: v for k, v in PF.census(pa).items() if not k.startswith("occ_")} == CEN.structure_census(pa),
                          "c_model": PF.c_model(PF.census(pb))}
                del pa, pb
                gc.collect()
            out["units"].append({"cap": cap, "unit": unit, "a": a_name, "b": b_name, "order": "".join(seq),
                                 "reps": reps, "loadavg": os.getloadavg()[0], "census": census})
    out["loadavg_end"] = os.getloadavg()[0]
    return out


def run_worker(job):
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(1) as pool:
        return pool.apply(worker, (job,))


def pair_ratio(reps, key="thread_ns"):
    a = sum(r[key] for r in reps if r["arm"] == "A")
    b = sum(r[key] for r in reps if r["arm"] == "B")
    return b / a


def q(xs, f):
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0]
    pos = f * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def summarize(records, oracle):
    """records: list of worker outputs. Returns per-cell stats + gate inputs."""
    cells = {}
    hr_bad = []
    rounds_streams = {}
    for w in records:
        rounds_streams.setdefault(w["round"], set()).add(w["stream"])
        for u in w["units"]:
            for r in u["reps"]:
                nm = u["a"] if r["arm"] == "A" else u["b"]
                want = oracle.get((w["stream"], u["cap"], "costfit")) if oracle else None
                if oracle is not None and r["hit_rate"] != want:
                    hr_bad.append((w["stream"], u["cap"], nm, r["hit_rate"], want))
            k = (w["stream"], u["cap"], u["unit"])
            c = cells.setdefault(k, {"thread": [], "proc": [], "wall": []})
            c["thread"].append(pair_ratio(u["reps"], "thread_ns"))
            c["proc"].append(pair_ratio(u["reps"], "proc_ns"))
            c["wall"].append(pair_ratio(u["reps"], "wall_ns"))
    complete = sorted(r for r, s in rounds_streams.items() if s == set(STREAMS))
    stat = {}
    for k, c in cells.items():
        stat[k] = {m: {"median": statistics.median(v), "q25": q(v, 0.25), "q75": q(v, 0.75), "n": len(v)}
                   for m, v in c.items()}
    return stat, complete, hr_bad


def ladder(st):
    """First match wins. st keys: sealed_ok, hr_ok, rounds, null_pooled, null_cells_ok, R3, R3_q25, R3_q75.
    (R3* = the PRIMARY fused arm's argmax cell; name kept from exp723 so the self-test is unchanged.
    hr_ok includes round-0 full-state parity of every B arm.)"""
    if not st["sealed_ok"] or not st["hr_ok"]:
        return "SEALED-FAIL"
    if st["rounds"] < MIN_ROUNDS:
        return "INCOMPLETE-BUDGET"
    if not (NULL_POOLED[0] <= st["null_pooled"] <= NULL_POOLED[1]) or not st["null_cells_ok"]:
        return "TIME-INVALID"
    for t in (PAYOFF_CONFIRMED, PAYOFF_MARGINAL):
        if st["R3_q25"] <= t < st["R3_q75"]:
            return "PAYOFF-UNRESOLVED"
    if st["R3"] <= PAYOFF_CONFIRMED:
        return "PAYOFF-CONFIRMED"
    if st["R3"] <= PAYOFF_MARGINAL:
        return "PAYOFF-MARGINAL"
    return "PAYOFF-REJECTED"


def gate_inputs(stat, complete, hr_bad, sealed_ok):
    cells8 = [(s, c) for s in STREAMS for c in CAPS]
    null_meds = [stat[(s, c, "null")]["thread"]["median"] for s, c in cells8 if (s, c, "null") in stat]
    r3 = {(s, c): stat[(s, c, "fused2")]["thread"] for s, c in cells8 if (s, c, "fused2") in stat}
    r2 = {}
    arg = max(r3, key=lambda k: r3[k]["median"]) if r3 else None
    return {
        "sealed_ok": sealed_ok, "hr_ok": not hr_bad, "rounds": len(complete),
        "null_pooled": statistics.median(null_meds) if null_meds else float("nan"),
        "null_cells_ok": len(null_meds) == 8 and all(NULL_CELL[0] <= x <= NULL_CELL[1] for x in null_meds),
        "R3": r3[arg]["median"] if arg else float("nan"),
        "R3_q25": r3[arg]["q25"] if arg else float("nan"),
        "R3_q75": r3[arg]["q75"] if arg else float("nan"),
        "R3_argmax": list(arg) if arg else None,
        "R2": max(v["median"] for v in r2.values()) if r2 else float("nan"),
    }


def ladder_selftest():
    ok = dict(sealed_ok=True, hr_ok=True, rounds=8, null_pooled=1.0, null_cells_ok=True,
              R3=1.0, R3_q25=0.98, R3_q75=1.02)
    T = [({}, "PAYOFF-CONFIRMED"),
         ({"R3": 1.10, "R3_q25": 1.05, "R3_q75": 1.10}, "PAYOFF-CONFIRMED"),
         ({"R3": 1.2, "R3_q25": 1.15, "R3_q75": 1.25}, "PAYOFF-MARGINAL"),
         ({"R3": 1.35, "R3_q25": 1.30, "R3_q75": 1.35}, "PAYOFF-MARGINAL"),
         ({"R3": 1.5, "R3_q25": 1.40, "R3_q75": 1.6}, "PAYOFF-REJECTED"),
         ({"R3": 1.12, "R3_q25": 1.08, "R3_q75": 1.15}, "PAYOFF-UNRESOLVED"),
         ({"R3": 1.34, "R3_q25": 1.30, "R3_q75": 1.40}, "PAYOFF-UNRESOLVED"),
         ({"null_pooled": 1.031}, "TIME-INVALID"), ({"null_pooled": 0.969}, "TIME-INVALID"),
         ({"null_pooled": 1.03}, "PAYOFF-CONFIRMED"), ({"null_cells_ok": False}, "TIME-INVALID"),
         ({"rounds": 4, "null_pooled": 2.0}, "INCOMPLETE-BUDGET"), ({"rounds": 5}, "PAYOFF-CONFIRMED"),
         ({"hr_ok": False, "rounds": 0}, "SEALED-FAIL"), ({"sealed_ok": False}, "SEALED-FAIL")]
    res = [(o, w, ladder({**ok, **o})) for o, w in T]
    return sum(g == w for _, w, g in res), len(T), [r for r in res if r[1] != r[2]]


def census_summary(records):
    """Round-0 parity + struct economics. Returns (parity_bad, struct ratios per arm per cell, qualifier)."""
    bad, ratios = [], {}
    for w in records:
        for u in w["units"]:
            c = u.get("census")
            if c is None:
                continue
            if not (c["state_eq"] and c["a_eq_CEN"]):
                bad.append((w["stream"], u["cap"], u["unit"], c["state_eq"], c["a_eq_CEN"]))
            ratios.setdefault(u["unit"], {})[f"{w['stream']}|{u['cap']}"] = \
                c["b"]["struct_bytes"] / c["a"]["struct_bytes"]
    fz = ratios.get("fused2", {})
    qual = ("SAVING" if fz and len(fz) == len(STREAMS) * len(CAPS) and max(fz.values()) <= SAVING_MAX_STRUCT
            else "NO-SAVING")
    return bad, ratios, qual


def load_oracle():
    R = json.loads(EXP718_JSON.read_text())
    return {(k.split("|")[0], int(k.split("|")[1]), k.split("|")[2]): v["hit_rate"] for k, v in R["pass1"].items()}


def run(smoke=False):
    t0 = time.time()
    deps = assert_sealed()
    hb(t0, f"sealed deps ok ({len(deps)} files)")
    st_ok, st_n, st_bad = ladder_selftest()
    hb(t0, f"ladder self-test {st_ok}/{st_n}")
    if st_ok != st_n:
        raise RuntimeError(f"ladder self-test failed {st_bad}")
    rng = random.Random(SEED)
    rounds = 2 if smoke else ROUNDS
    caps = [256, 4096] if smoke else CAPS
    limit = SMOKE_LIMIT if smoke else 0
    oracle = None if smoke else load_oracle()
    records = []
    budget_hit = False
    for rnd in range(rounds):
        order = list(caps)
        rng.shuffle(order)
        sorder = list(STREAMS)
        rng.shuffle(sorder)
        for s in sorder:
            if time.time() - t0 > WALL_BUDGET_S:
                budget_hit = True
                break
            hb(t0, f"round {rnd} {s} caps {order} loadavg {os.getloadavg()[0]:.2f}")
            w = run_worker((s, str(STREAMS[s]), rnd, order, limit))
            records.append(w)
            done = {u['unit']: round(pair_ratio(u['reps']), 4) for u in w['units'] if u['cap'] == order[0]}
            hb(t0, f"  done {s} r{rnd} qos={w['qos_rc']} first-cap thread ratios {done}")
            (D / ("smoke-partial.json" if smoke else "exp732-partial.json")).write_text(
                json.dumps({"records": records}, default=str))
        if budget_hit:
            break
    stat, complete, hr_bad = summarize(records, oracle)
    parity_bad, struct_ratios, econ = census_summary(records)
    if smoke:
        # smoke: self-consistency only (truncated stream -> exp718 oracle not applicable)
        hr_pairs_ok = all(len({r["hit_rate"] for r in u["reps"] if r["arm"] == arm}) == 1
                          for w in records for u in w["units"] for arm in "AB")
        fam_eq = all({r["hit_rate"] for r in u["reps"]} .__len__() == 1 for w in records for u in w["units"])
        n_census = sum(u.get("census") is not None for w in records for u in w["units"])
        res = {"mode": "SMOKE", "records": len(records), "complete_rounds": complete, "hit_rate_deterministic": hr_pairs_ok,
               "base_eq_shared_hit_rate": fam_eq, "ladder_selftest": [st_ok, st_n],
               "parity_bad": parity_bad, "n_census": n_census, "struct_ratios": struct_ratios, "economics": econ,
               "cells": {"|".join(map(str, k)): v for k, v in stat.items()}, "elapsed_s": round(time.time() - t0, 1)}
        (D / "smoke-result.json").write_text(json.dumps(res, indent=1, default=str))
        ok = (hr_pairs_ok and fam_eq and len(complete) == 2 and st_ok == st_n and len(stat) == 2 * 2 * len(UNITS)
              and not parity_bad and n_census == 2 * 2 * len(UNITS))
        print(f"SMOKE_OK={ok} records={len(records)} cells={len(stat)} det={hr_pairs_ok} fam_eq={fam_eq} "
              f"parity_bad={len(parity_bad)}/{n_census} econ={econ} {time.time() - t0:.0f}s", flush=True)
        (D / "smoke-partial.json").unlink(missing_ok=True)
        return 0 if ok else 3
    hr_bad = hr_bad + [("STATE",) + tuple(b) for b in parity_bad]
    if 0 in complete and sum(u.get("census") is not None for w in records for u in w["units"]) != 2 * len(CAPS) * len(UNITS):
        hr_bad.append(("STATE", "round-0 census incomplete"))
    gi = gate_inputs(stat, complete, hr_bad, True)
    verdict = ladder(gi)
    res = {"exp": "exp732", "verdict": verdict, "economics": econ, "struct_ratios": struct_ratios,
           "gate_inputs": gi, "budget_hit": budget_hit,
           "hit_rate_mismatches": hr_bad[:50], "ladder_selftest": [st_ok, st_n],
           "cells": {"|".join(map(str, k)): v for k, v in stat.items()}, "records": records,
           "host": {"node": platform.node(), "python": sys.version.split()[0], "machine": platform.machine()},
           "design": {"rounds": ROUNDS, "min_rounds": MIN_ROUNDS, "caps": CAPS, "streams": list(STREAMS),
                      "units": UNITS, "seed": SEED, "wall_budget_s": WALL_BUDGET_S, "null_pooled": NULL_POOLED,
                      "null_cell": NULL_CELL, "payoff": [PAYOFF_CONFIRMED, PAYOFF_MARGINAL],
                      "saving_max_struct": SAVING_MAX_STRUCT, "c_model": {"load": PF.C_LOAD, "soa_slot": PF.C_SOA_SLOT, "aos_rec": PF.C_AOS_REC}},
           "sealed_deps": {Path(p).name: s for p, s in deps.items()}, "elapsed_s": round(time.time() - t0, 1)}
    (D / "exp732-fused2.json").write_text(json.dumps(res, indent=1, default=str))
    (D / "exp732-partial.json").unlink(missing_ok=True)
    hb(t0, f"settled verdict={verdict} economics={econ} fused2-F={gi['R3']:.4f} [{gi['R3_q25']:.4f},{gi['R3_q75']:.4f}] "
           f"argmax={gi['R3_argmax']} R2={gi['R2']:.4f} null={gi['null_pooled']:.4f} rounds={gi['rounds']}")
    print("RUN_EXIT=0", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run(smoke=os.environ.get("SMOKE") == "1"))

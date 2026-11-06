"""gen_addendum63.py — independent follow-up adjudication of exp723 (contention-robust paired CPU-time payoff).

Re-derives every gate of the FROZEN exp723 PREREG from primary sources: the raw per-replay ns timings in the
result JSON (not the runner's summary), the exp718 PASS-1 hit-rate oracle (parsed here), run.log, the sealed
dependency shas and the freeze commit. Re-implements the frozen ladder (first match wins) with its own boundary
self-test, reproduces the Random(723) stream/cap schedule, and runs a small LIVE third-process re-check of the
argmax cell through the sealed runner's worker(). Writes ADDENDUM63.md + exp723-adjudication.json.
Sealed artifacts are read-only here; nothing is re-launched.
"""
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
HOME = Path.home()
REPO = HOME / "warp-work/moei-granite3b"
GITREPO = HOME / "warp-work/moei-granite3b-rebuilt"
FREEZE = "fcba7bb"
REL = "benchmarks/cache_simulator/research/exp723"
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    return bool(ok)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parse_sums(p):
    out = {}
    for line in Path(p).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            h, f = line.split()
            out[f] = h
    return out


def quant(xs, f):  # independent linear-interpolation quantile (numpy 'linear' definition)
    xs = sorted(xs)
    n = len(xs)
    if n == 1:
        return xs[0]
    h = (n - 1) * f
    i = int(h // 1)
    j = min(i + 1, n - 1)
    return xs[i] + (h - i) * (xs[j] - xs[i])


def main():
    t0 = time.time()
    R = json.loads((D / "exp723-cpupair.json").read_text())
    log = (D / "run.log").read_text()
    # ---------------- 1. freeze integrity
    art = parse_sums(D / "ARTIFACT.sha256")
    for f, h in art.items():
        check(f"artifact sha {f}", sha(D / f) == h, h[:12])
        gs = subprocess.run(["git", "-C", str(GITREPO), "show", f"{FREEZE}:{REL}/{f}"], capture_output=True)
        check(f"freeze commit {FREEZE} carries {f} byte-exact",
              gs.returncode == 0 and hashlib.sha256(gs.stdout).hexdigest() == h)
    ga = subprocess.run(["git", "-C", str(GITREPO), "show", f"{FREEZE}:{REL}/ARTIFACT.sha256"], capture_output=True)
    check("committed ARTIFACT.sha256 == local ARTIFACT.sha256", ga.stdout == (D / "ARTIFACT.sha256").read_bytes())
    ct = int(subprocess.run(["git", "-C", str(GITREPO), "show", "-s", "--format=%ct", FREEZE],
                            capture_output=True, text=True).stdout.strip())
    res_mtime = (D / "exp723-cpupair.json").stat().st_mtime
    check("freeze commit time precedes result mtime", ct < res_mtime, f"freeze {ct} < result {int(res_mtime)}")
    deps = parse_sums(D / "sealed_deps.sha256")
    for f, h in deps.items():
        p = Path(f) if Path(f).is_absolute() else REPO / f
        check(f"sealed dep {p.name} unchanged", sha(p) == h, h[:12])
        check(f"result JSON records sealed dep {p.name}", R["sealed_deps"].get(p.name) == h)
    check("15 sealed deps (13 exp718 + run_econ.py + exp718-econ.json)", len(deps) == 15 == len(R["sealed_deps"]))
    check("run.log RUN_EXIT=0", "RUN_EXIT=0" in log)
    check("run.log sealed deps ok (15 files)", "sealed deps ok (15 files)" in log)
    check("run.log ladder self-test 15/15 before measurement", "ladder self-test 15/15" in log
          and log.index("ladder self-test 15/15") < log.index("round 0"))
    check("run.log settled verdict == JSON verdict", f"settled verdict={R['verdict']}" in log, R["verdict"])
    check("stored ladder_selftest 15/15", R["ladder_selftest"] == [15, 15])

    # ---------------- 2. design + schedule reproduction
    des = R["design"]
    CAPS, STREAMS = des["caps"], des["streams"]
    check("design == PREREG (8 rounds, min 5, caps, streams, seed 723, 5.5h, null [0.97,1.03]/[0.93,1.07], 1.10/1.35)",
          des["rounds"] == 8 and des["min_rounds"] == 5 and CAPS == [256, 1024, 4096, 262144]
          and STREAMS == ["qwen30b", "granite"] and des["seed"] == 723 and des["wall_budget_s"] == 19800
          and des["null_pooled"] == [0.97, 1.03] and des["null_cell"] == [0.93, 1.07] and des["payoff"] == [1.10, 1.35]
          and des["units"] == [["fam2", "costfit", "shared_costfit"], ["fam3", "costfit3", "shared_costfit3"],
                               ["null", "costfit3", "costfit3"]])
    rng = random.Random(723)
    sched = []
    for rnd in range(8):
        order = list(CAPS)
        rng.shuffle(order)
        so = list(STREAMS)
        rng.shuffle(so)
        for s in so:
            sched.append((rnd, s, order))
    recs = R["records"]
    got = [(w["round"], w["stream"], [u["cap"] for u in w["units"][::3]]) for w in recs]
    check("16 worker records = 8 rounds x 2 streams", len(recs) == 16)
    check("Random(723) stream/cap schedule reproduced exactly (16/16 records)", got == sched)
    n_acc = {"qwen30b": 1424640, "granite": 638208}
    check("every worker replayed the FULL stream (qwen30b 1,424,640 / granite 638,208)",
          all(w["accesses"] == n_acc[w["stream"]] for w in recs))
    check("every worker QOS rc == 0", all(w["qos_rc"] == 0 for w in recs))
    struct_ok = True
    for w in recs:
        want_order = "ABBA" if w["round"] % 2 == 0 else "BAAB"
        if len(w["units"]) != 12:
            struct_ok = False
        for i, u in enumerate(w["units"]):
            un, a, b = des["units"][i % 3]
            if (u["unit"], u["a"], u["b"]) != (un, a, b) or u["order"] != want_order or \
                    "".join(r["arm"] for r in u["reps"]) != want_order or len(u["reps"]) != 4:
                struct_ok = False
    check("every unit: fixed fam2/fam3/null order, 4 reps, ABBA even / BAAB odd rounds (192/192 units)", struct_ok)
    check("budget not hit; elapsed < 5.5h", R["budget_hit"] is False and R["elapsed_s"] < 19800, R["elapsed_s"])

    # ---------------- 3. hit-rate oracle (rung 1) parsed HERE from exp718 PASS-1
    E = json.loads((HOME / "warp-work/exp718-moei-shared-econ/exp718-econ.json").read_text())
    orc = {(k.split("|")[0], int(k.split("|")[1]), k.split("|")[2]): v["hit_rate"] for k, v in E["pass1"].items()}
    n_rep, bad = 0, []
    for w in recs:
        for u in w["units"]:
            for r in u["reps"]:
                nm = u["a"] if r["arm"] == "A" else u["b"]
                n_rep += 1
                if r["hit_rate"] != orc[(w["stream"], u["cap"], nm)]:
                    bad.append((w["stream"], u["cap"], nm))
    check(f"rung 1: every timed replay hit_rate == exp718 PASS-1 exactly ({n_rep - len(bad)}/{n_rep})",
          not bad and n_rep == 768)
    check("stored hit_rate_mismatches empty", R["hit_rate_mismatches"] == [])
    base_eq = all(orc[(s, c, "costfit")] == orc[(s, c, "shared_costfit")]
                  and orc[(s, c, "costfit3")] == orc[(s, c, "shared_costfit3")] for s in STREAMS for c in CAPS)
    check("oracle: shared == base hit_rate in all 16 (stream,cap,family) pairs", base_eq)

    # ---------------- 4. re-derive pair ratios + cell stats from raw ns
    raw = {}
    for w in recs:
        for u in w["units"]:
            for clk, key in (("thread", "thread_ns"), ("proc", "proc_ns"), ("wall", "wall_ns")):
                A = sum(r[key] for r in u["reps"] if r["arm"] == "A")
                B = sum(r[key] for r in u["reps"] if r["arm"] == "B")
                raw.setdefault((w["stream"], u["cap"], u["unit"]), {}).setdefault(clk, []).append(B / A)
    cell = {k: {clk: {"median": statistics.median(v), "q25": quant(v, .25), "q75": quant(v, .75), "n": len(v)}
                for clk, v in d.items()} for k, d in raw.items()}
    check("24 cells (2 streams x 4 caps x 3 units), n=8 rounds each", len(cell) == 24
          and all(c[m]["n"] == 8 for c in cell.values() for m in c))
    maxdiff = max(abs(cell[k][m][s] - R["cells"]["|".join(map(str, k))][m][s])
                  for k in cell for m in cell[k] for s in ("median", "q25", "q75"))
    check("stored cell stats == re-derived from raw ns (24 cells x 3 clocks x 3 stats, |d| <= 1e-12)",
          maxdiff <= 1e-12, f"max |d| {maxdiff:.2e}")
    cells8 = [(s, c) for s in STREAMS for c in CAPS]
    null_meds = {sc: cell[(*sc, "null")]["thread"]["median"] for sc in cells8}
    null_pooled = statistics.median(null_meds.values())
    null_cells_ok = all(0.93 <= x <= 1.07 for x in null_meds.values())
    r3c = {sc: cell[(*sc, "fam3")]["thread"] for sc in cells8}
    r2c = {sc: cell[(*sc, "fam2")]["thread"] for sc in cells8}
    arg = max(r3c, key=lambda k: r3c[k]["median"])
    gi = {"sealed_ok": True, "hr_ok": not bad, "rounds": len({w["round"] for w in recs if
                                                              sum(x["round"] == w["round"] for x in recs) == 2}),
          "null_pooled": null_pooled, "null_cells_ok": null_cells_ok, "R3": r3c[arg]["median"],
          "R3_q25": r3c[arg]["q25"], "R3_q75": r3c[arg]["q75"], "R3_argmax": list(arg),
          "R2": max(v["median"] for v in r2c.values())}
    sg = R["gate_inputs"]
    check("rung 2: complete rounds 8 >= MIN 5", gi["rounds"] == 8 == sg["rounds"])
    check("rung 3 null pooled in [0.97,1.03]", 0.97 <= null_pooled <= 1.03, f"{null_pooled:.4f}")
    check("rung 3 every cell null median in [0.93,1.07] (8/8)", null_cells_ok,
          f"range {min(null_meds.values()):.4f}-{max(null_meds.values()):.4f}")
    for k in ("null_pooled", "R3", "R3_q25", "R3_q75", "R2"):
        check(f"gate input {k} re-derived == stored", abs(gi[k] - sg[k]) <= 1e-12, f"{gi[k]:.6f}")
    check("argmax cell re-derived == stored", gi["R3_argmax"] == sg["R3_argmax"], arg)
    check("rung 4: argmax IQR does not straddle 1.10 or 1.35",
          not any(gi["R3_q25"] <= t < gi["R3_q75"] for t in (1.10, 1.35)),
          f"[{gi['R3_q25']:.4f},{gi['R3_q75']:.4f}]")

    # ---------------- 5. independent ladder + boundary self-test
    def ladder(st):
        if not (st["sealed_ok"] and st["hr_ok"]):
            return "SEALED-FAIL"
        if st["rounds"] < 5:
            return "INCOMPLETE-BUDGET"
        if not (0.97 <= st["null_pooled"] <= 1.03 and st["null_cells_ok"]):
            return "TIME-INVALID"
        if any(st["R3_q25"] <= t < st["R3_q75"] for t in (1.10, 1.35)):
            return "PAYOFF-UNRESOLVED"
        if st["R3"] <= 1.10:
            return "PAYOFF-CONFIRMED"
        if st["R3"] <= 1.35:
            return "PAYOFF-MARGINAL"
        return "PAYOFF-REJECTED"
    base = dict(sealed_ok=True, hr_ok=True, rounds=8, null_pooled=1.0, null_cells_ok=True, R3=1.0, R3_q25=.99, R3_q75=1.01)
    T = [({}, "PAYOFF-CONFIRMED"), ({"R3": 1.10, "R3_q25": 1.10, "R3_q75": 1.10}, "PAYOFF-CONFIRMED"),
         ({"R3": 1.1001, "R3_q25": 1.1001, "R3_q75": 1.2}, "PAYOFF-MARGINAL"),
         ({"R3": 1.35, "R3_q25": 1.36, "R3_q75": 1.36}, "PAYOFF-MARGINAL"),
         ({"R3": 1.3501, "R3_q25": 1.3501, "R3_q75": 1.4}, "PAYOFF-REJECTED"),
         ({"R3": 1.4, "R3_q25": 1.35, "R3_q75": 1.45}, "PAYOFF-UNRESOLVED"),
         # q75 == t is NOT a straddle under the frozen half-open rule (q25 <= t < q75) -> falls through to rung 7.
         # (First draft of this generator expected UNRESOLVED here; corrected against the PREREG text, disclosed.)
         ({"R3": 1.4, "R3_q25": 1.3, "R3_q75": 1.35}, "PAYOFF-REJECTED"),
         ({"R3": 1.1, "R3_q25": 1.10, "R3_q75": 1.11}, "PAYOFF-UNRESOLVED"),
         ({"null_pooled": 1.0301}, "TIME-INVALID"), ({"null_pooled": 0.97}, "PAYOFF-CONFIRMED"),
         ({"null_cells_ok": False}, "TIME-INVALID"), ({"rounds": 4}, "INCOMPLETE-BUDGET"),
         ({"rounds": 5, "null_pooled": 5.0}, "TIME-INVALID"), ({"hr_ok": False, "rounds": 0}, "SEALED-FAIL"),
         ({"sealed_ok": False}, "SEALED-FAIL")]
    st_ok = sum(ladder({**base, **o}) == w for o, w in T)
    check(f"independent ladder boundary self-test {st_ok}/{len(T)}", st_ok == len(T))
    verdict = ladder(gi)
    check("re-adjudicated verdict == stored verdict", verdict == R["verdict"], verdict)

    # ---------------- 6. descriptive robustness (non-gating)
    rob = {}
    for clk in ("proc", "wall"):
        meds = {sc: cell[(*sc, "fam3")][clk]["median"] for sc in cells8}
        a2 = max(meds, key=meds.get)
        rob[clk] = {"R3": meds[a2], "argmax": list(a2),
                    "null_pooled": statistics.median(cell[(*sc, "null")][clk]["median"] for sc in cells8)}
    loro = []
    for drop in range(8):
        sub = {}
        for w in recs:
            if w["round"] == drop:
                continue
            for u in w["units"]:
                A = sum(r["thread_ns"] for r in u["reps"] if r["arm"] == "A")
                B = sum(r["thread_ns"] for r in u["reps"] if r["arm"] == "B")
                sub.setdefault((w["stream"], u["cap"], u["unit"]), []).append(B / A)
        st = {k: (statistics.median(v), quant(v, .25), quant(v, .75)) for k, v in sub.items()}
        a3 = max(cells8, key=lambda sc: st[(*sc, "fam3")][0])
        nm = [st[(*sc, "null")][0] for sc in cells8]
        loro.append(ladder(dict(sealed_ok=True, hr_ok=True, rounds=7, null_pooled=statistics.median(nm),
                                null_cells_ok=all(0.93 <= x <= 1.07 for x in nm), R3=st[(*a3, "fam3")][0],
                                R3_q25=st[(*a3, "fam3")][1], R3_q75=st[(*a3, "fam3")][2])))
    min_fam3 = min(r3c, key=lambda k: r3c[k]["median"])
    min_fam2 = min(r2c, key=lambda k: r2c[k]["median"])
    null_units = [x for k, d in raw.items() if k[2] == "null" for x in d["thread"]]
    null_out = sum(abs(x - 1) > 0.10 for x in null_units)
    fam3_units = [x for k, d in raw.items() if k[2] == "fam3" for x in d["thread"]]
    fam3_le135 = sum(x <= 1.35 for x in fam3_units)
    check("descriptive: leave-one-round-out verdict stable (8/8 == stored)", all(v == verdict for v in loro), loro)
    # exp718 loaded wall R3 (informational) for the prediction check
    ld = []
    for g in E["pass2_groups"]:
        rw = g["rows"]
        if "shared_costfit3" in rw and "costfit3" in rw:
            ld.append({"stream": g["stream"], "cap": g["cap"],
                       "R3": rw["shared_costfit3"]["ns_per_access"] / rw["costfit3"]["ns_per_access"]})
    loads = [w["loadavg_start"] for w in recs] + [w["loadavg_end"] for w in recs]

    # ---------------- 7. LIVE third-process re-check of the argmax cell through the sealed runner's worker()
    live = {}
    py = HOME / "warp-work/exp650-moei-granite3b-trace-pr/.venv/bin/python"
    code = r'''
import sys, json, importlib.util
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("run_cpupair", sys.argv[1]); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
if __name__ == "__main__":
    M.assert_sealed()
    st = sys.argv[2]; cap = int(sys.argv[3])
    w = M.worker((st, str(M.STREAMS[st]), 0, [cap], 0))
    print("LIVEJSON" + json.dumps(w, default=str))
'''
    scr = HOME / ".hermes/cache/scratch/exp723_live_recheck.py"
    scr.write_text(code)
    try:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        out = subprocess.run([str(py), str(scr), str(D / "run_cpupair.py"), arg[0], str(arg[1])],
                             capture_output=True, text=True, timeout=1800, env=env)
        line = [x for x in out.stdout.splitlines() if x.startswith("LIVEJSON")]
        live = json.loads(line[0][8:]) if line else {"error": out.stderr[-800:]}
    finally:
        scr.unlink(missing_ok=True)
    if "error" in live:
        check("LIVE re-check ran", False, live["error"])
    else:
        lhr = all(r["hit_rate"] == orc[(arg[0], arg[1], u["a"] if r["arm"] == "A" else u["b"])]
                  for u in live["units"] for r in u["reps"])
        check(f"LIVE {arg[0]}@{arg[1]}: 12/12 fresh replays hit_rate == exp718 oracle", lhr and
              sum(len(u["reps"]) for u in live["units"]) == 12)
        lr = {}
        for u in live["units"]:
            A = sum(r["thread_ns"] for r in u["reps"] if r["arm"] == "A")
            B = sum(r["thread_ns"] for r in u["reps"] if r["arm"] == "B")
            lr[u["unit"]] = B / A
        live["ratios"] = lr
        live["loadavg"] = [live["loadavg_start"], live["loadavg_end"]]
        live.pop("units", None)
        check(f"LIVE {arg[0]}@{arg[1]} fam3 thread ratio > 1.35 (single ABBA unit, descriptive)", lr["fam3"] > 1.35,
              f"fam3 {lr['fam3']:.4f} fam2 {lr['fam2']:.4f} null {lr['null']:.4f}")

    n_ok = sum(c["ok"] for c in CHECKS)
    # ---------------- ADDENDUM
    f4 = lambda x: f"{x:.4f}"  # noqa: E731
    L = ["# ADDENDUM 63 — exp723: contention-robust paired CPU-time payoff of shared-state N-way metadata\n"]
    L.append(f"Verdict: **{verdict}** (frozen ladder rung 7). The A/A null control certified the measurement under "
             f"contention (pooled null x{f4(null_pooled)}, every cell in [{f4(min(null_meds.values()))}, "
             f"{f4(max(null_meds.values()))}] vs the frozen [0.93, 1.07]), and the shared-key-table views cost "
             f"**x{f4(gi['R3'])}** per-thread CPU time vs the per-key-dict originals at the argmax cell "
             f"{arg[0]} @{arg[1]} (IQR [{f4(gi['R3_q25'])}, {f4(gi['R3_q75'])}], clear of both thresholds), above the "
             f"1.35 REJECTED bar. 8/8 rounds complete, {R['elapsed_s']:.0f}s, exit 0, freeze {FREEZE}; host loadavg "
             f"{min(loads):.2f}–{max(loads):.2f} throughout (not gated, disclosed).\n")
    L.append(f"Independent follow-up adjudication: **{n_ok}/{len(CHECKS)} checks pass** (gen_addendum63.py), re-derived "
             f"from the 768 raw per-replay ns timings, the exp718 PASS-1 hit-rate oracle parsed here, run.log, "
             f"sealed-dep shas and the freeze commit, plus a LIVE third-process re-run of the argmax cell. "
             f"Re-derived verdict == stored.\n")
    L.append("## Decision-grade result\n")
    L.append(f"- **rung 1**: every timed replay ({n_rep}/{n_rep}) reproduced the exp718 PASS-1 hit rate exactly — "
             f"each timing ran the sealed decision path; shared == base hit rate in all 16 (stream,cap,family) pairs.")
    L.append(f"- **A/A null (validity gate)**: pooled x{f4(null_pooled)} (bar [0.97, 1.03]); per-cell medians "
             + ", ".join(f"{s}@{c} {f4(v)}" for (s, c), v in null_meds.items())
             + f". {null_out}/{len(null_units)} individual null units deviated > 10% (e.g. contention spikes); "
               f"the per-cell median absorbs them, which is what the gate certifies.")
    L.append("- **Per-thread CPU-time ratio shared/base (median over 8 rounds, [q25, q75])**:")
    for s in STREAMS:
        for c in CAPS:
            a, b = cell[(s, c, "fam3")]["thread"], cell[(s, c, "fam2")]["thread"]
            L.append(f"  - {s} @{c}: N=3 x{f4(a['median'])} [{f4(a['q25'])}, {f4(a['q75'])}]; "
                     f"N=2 x{f4(b['median'])} [{f4(b['q25'])}, {f4(b['q75'])}]")
    L.append(f"- R3 (N=3, flagship) x{f4(gi['R3'])} @ {arg[0]}/{arg[1]}; R2 (N=2) max x{f4(gi['R2'])}. Cheapest cells: "
             f"N=3 x{f4(r3c[min_fam3]['median'])} @ {min_fam3[0]}/{min_fam3[1]}, N=2 x{f4(r2c[min_fam2]['median'])} @ "
             f"{min_fam2[0]}/{min_fam2[1]}; {fam3_le135}/{len(fam3_units)} individual N=3 "
             f"units were <= 1.35.")
    L.append("\n## Descriptive (non-gating)\n")
    L.append(f"- Clock robustness: process_time R3 x{f4(rob['proc']['R3'])} @ {rob['proc']['argmax']}, null "
             f"x{f4(rob['proc']['null_pooled'])}; wall R3 x{f4(rob['wall']['R3'])} @ {rob['wall']['argmax']}, null "
             f"x{f4(rob['wall']['null_pooled'])} — single-threaded replay, so thread/process/wall agree.")
    L.append(f"- Leave-one-round-out ladder: {sorted(set(loro))} in 8/8 drops.")
    if "error" not in live:
        L.append(f"- LIVE third-process re-run of {arg[0]} @{arg[1]} (one ABBA unit per family, sealed worker(), "
                 f"loadavg {live['loadavg'][0]:.2f}→{live['loadavg'][1]:.2f}): N=3 x{f4(live['ratios']['fam3'])}, "
                 f"N=2 x{f4(live['ratios']['fam2'])}, null x{f4(live['ratios']['null'])}; hit rates == oracle 12/12.")
    ldm = statistics.median(x["R3"] for x in ld)
    p1 = verdict in ("PAYOFF-MARGINAL", "PAYOFF-REJECTED")
    p2 = arg[1] in (256, 1024)
    p3 = gi["R3"] < ldm
    L.append(f"- Prediction check (PREREG, stated pre-run): (a) MARGINAL or REJECTED — {'HELD' if p1 else 'MISSED'}; "
             f"(b) max cell at eviction-heavy caps 256/1024 — {'HELD' if p2 else 'MISSED'} (argmax {arg[1]}); "
             f"(c) CPU ratios modestly below loaded wall ratios — {'HELD' if p3 else 'MISSED'}: flagship CPU R3 "
             f"x{f4(gi['R3'])} vs exp718 loaded wall R3 x{min(x['R3'] for x in ld):.3f}–x{max(x['R3'] for x in ld):.3f}"
             f" (median x{ldm:.3f}).")
    L.append("\n## Consequence (pre-registered branch)\n")
    s3 = [v["struct"] for k, v in E["ratios"].items() if k.split("|")[1] == "costfit3"]
    L.append(f"- {verdict}: the shared-key-table views cost x{min(v['median'] for v in r3c.values()):.2f}–"
             f"x{max(v['median'] for v in r3c.values()):.2f} per-thread CPU time (N=3 cell medians) as implemented. "
             f"The metadata cut (exp718 N=3 struct-bytes ratio x{min(s3):.2f}–x{max(s3):.2f}) is real but not free; "
             "it is NOT proposed for adoption in the N-way CostFit heads as is.")
    L.append("- Next (pre-registered): profile the shared-table hot path (record lookup + live counter) and test an "
             "array-of-struct redesign against the same oracle and the same A/A-gated paired CPU-time design.")
    L.append("\n## Integrity\n")
    L.append(f"- PREREG/runner/smoke.log/sealed_deps byte-exact in freeze commit {FREEZE} == ARTIFACT.sha256 == disk; "
             f"freeze precedes the result; 15/15 sealed deps unchanged and recorded in the result JSON; ladder "
             f"self-test 15/15 ran before measurement; sealed artifacts untouched; nothing re-launched.")
    L.append("\n## Check list\n")
    for c in CHECKS:
        L.append(f"- [{'x' if c['ok'] else ' '}] {c['check']}" + (f" — {c['detail']}" if c["detail"] else ""))
    (D / "ADDENDUM63.md").write_text("\n".join(L) + "\n")
    (D / "exp723-adjudication.json").write_text(json.dumps(
        {"verdict": verdict, "checks_ok": n_ok, "checks_total": len(CHECKS), "checks": CHECKS,
         "gate_inputs": gi, "null_cell_medians": {f"{s}|{c}": v for (s, c), v in null_meds.items()},
         "robustness": rob, "leave_one_round_out": loro, "exp718_loaded_R3": ld, "live": live,
         "null_units_over_10pct": [null_out, len(null_units)], "elapsed_s": round(time.time() - t0, 1)},
        indent=1, default=str))
    print(f"verdict={verdict} checks {n_ok}/{len(CHECKS)} R3={gi['R3']:.4f} null={null_pooled:.4f} "
          f"{time.time() - t0:.0f}s")
    for c in CHECKS:
        if not c["ok"]:
            print("FAIL", c)


if __name__ == "__main__":
    main()

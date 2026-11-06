"""gen_addendum64.py — independent follow-up adjudication of exp729 (fused shared-state CostFit3 redesign).

Re-derives every gate of the FROZEN exp729 PREREG from primary sources: the raw per-replay ns timings in the result
JSON (not the runner's summary), the exp718 PASS-1 hit-rate oracle (parsed here), the round-0 full-state parity and
struct census records, run.log, the sealed dependency shas and the freeze commit. Re-implements the frozen ladder
(first match wins) + economics qualifier with its own boundary self-test, reproduces the Random(729) stream/cap
schedule, and runs a LIVE third-process re-check of the fused argmax cell through the sealed runner's worker()
(round-0 mode, so parity + census are re-checked live too). Writes ADDENDUM64.md + exp729-adjudication.json.
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
FREEZE = "534c2f5"
REL = "benchmarks/cache_simulator/research/exp729"
UNITS = [["null", "costfit3", "costfit3"], ["floor", "costfit3", "floor"], ["lean", "costfit3", "lean"],
         ["fused", "costfit3", "fused"]]
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


def ratio(reps, key):
    A = sum(r[key] for r in reps if r["arm"] == "A")
    B = sum(r[key] for r in reps if r["arm"] == "B")
    return B / A


def ladder(st):
    if not (st["sealed_ok"] and st["hr_ok"]):
        return "SEALED-FAIL"
    if st["rounds"] < 5:
        return "INCOMPLETE-BUDGET"
    if not (0.97 <= st["null_pooled"] <= 1.03 and st["null_cells_ok"]):
        return "TIME-INVALID"
    if any(st["F_q25"] <= t < st["F_q75"] for t in (1.10, 1.35)):
        return "PAYOFF-UNRESOLVED"
    if st["F"] <= 1.10:
        return "PAYOFF-CONFIRMED"
    if st["F"] <= 1.35:
        return "PAYOFF-MARGINAL"
    return "PAYOFF-REJECTED"


def econ(fz, n_cells=8):
    return "SAVING" if len(fz) == n_cells and max(fz.values()) <= 0.80 else "NO-SAVING"


def main():
    t0 = time.time()
    R = json.loads((D / "exp729-fused.json").read_text())
    log = (D / "run.log").read_text()
    # ---------------- 1. freeze integrity
    art = parse_sums(D / "ARTIFACT.sha256")
    check("ARTIFACT.sha256 lists PREREG, runner, policies, sealed_deps, smoke.log",
          set(art) == {"PREREG.md", "run_fused.py", "policies_fused.py", "sealed_deps.sha256", "smoke.log"})
    for f, h in art.items():
        check(f"artifact sha {f}", sha(D / f) == h, h[:12])
        gs = subprocess.run(["git", "-C", str(GITREPO), "show", f"{FREEZE}:{REL}/{f}"], capture_output=True)
        check(f"freeze commit {FREEZE} carries {f} byte-exact",
              gs.returncode == 0 and hashlib.sha256(gs.stdout).hexdigest() == h)
    src = HOME / "warp-work/exp729-moei-fused-sharedstate"
    for f in list(art) + ["exp729-fused.json", "run.log"]:
        check(f"published copy {f} == run dir copy", sha(src / f) == sha(D / f))
    ga = subprocess.run(["git", "-C", str(GITREPO), "show", f"{FREEZE}:{REL}/ARTIFACT.sha256"], capture_output=True)
    check("committed ARTIFACT.sha256 == local ARTIFACT.sha256", ga.stdout == (D / "ARTIFACT.sha256").read_bytes())
    ct = int(subprocess.run(["git", "-C", str(GITREPO), "show", "-s", "--format=%ct", FREEZE],
                            capture_output=True, text=True).stdout.strip())
    res_mtime = (src / "exp729-fused.json").stat().st_mtime
    check("freeze commit time precedes result mtime", ct < res_mtime, f"freeze {ct} < result {int(res_mtime)}")
    run_rec = json.loads((HOME / ".hermes/state/warp-research/running.json").read_text())
    rr = [x for x in run_rec if x.get("exp") == "exp729"]
    check("running.json registration shas == ARTIFACT (PREREG + runner)",
          len(rr) == 1 and rr[0]["prereg_sha256"] == art["PREREG.md"] and rr[0]["runner_sha256"] == art["run_fused.py"])
    deps = parse_sums(D / "sealed_deps.sha256")
    for f, h in deps.items():
        p = Path(f) if Path(f).is_absolute() else REPO / f
        check(f"sealed dep {p.name} unchanged", sha(p) == h, h[:12])
        check(f"result JSON records sealed dep {p.name}", R["sealed_deps"].get(p.name) == h)
    check("15 sealed deps", len(deps) == 15 == len(R["sealed_deps"]))
    check("run.log RUN_EXIT=0", "RUN_EXIT=0" in log)
    check("run.log sealed deps ok (15 files)", "sealed deps ok (15 files)" in log)
    check("run.log ladder self-test 15/15 before measurement", "ladder self-test 15/15" in log
          and log.index("ladder self-test 15/15") < log.index("round 0"))
    check("run.log settled verdict + economics == JSON",
          f"settled verdict={R['verdict']} economics={R['economics']}" in log, f"{R['verdict']} {R['economics']}")
    check("stored ladder_selftest 15/15", R["ladder_selftest"] == [15, 15])

    # ---------------- 2. design + schedule reproduction
    des = R["design"]
    CAPS, STREAMS = des["caps"], des["streams"]
    check("design == PREREG (8 rounds, min 5, caps incl. ceiling, streams, seed 729, 5.5h, null bars, 1.10/1.35, 0.80)",
          des["rounds"] == 8 and des["min_rounds"] == 5 and CAPS == [256, 1024, 4096, 262144]
          and STREAMS == ["qwen30b", "granite"] and des["seed"] == 729 and des["wall_budget_s"] == 19800
          and des["null_pooled"] == [0.97, 1.03] and des["null_cell"] == [0.93, 1.07] and des["payoff"] == [1.10, 1.35]
          and des["saving_max_struct"] == 0.8 and des["units"] == UNITS)
    rng = random.Random(729)
    sched = []
    for rnd in range(8):
        order = list(CAPS)
        rng.shuffle(order)
        so = list(STREAMS)
        rng.shuffle(so)
        for s in so:
            sched.append((rnd, s, order))
    recs = R["records"]
    got = [(w["round"], w["stream"], [u["cap"] for u in w["units"][::4]]) for w in recs]
    check("16 worker records = 8 rounds x 2 streams", len(recs) == 16)
    check("Random(729) stream/cap schedule reproduced exactly (16/16 records)", got == sched)
    n_acc = {"qwen30b": 1424640, "granite": 638208}
    check("every worker replayed the FULL stream (qwen30b 1,424,640 / granite 638,208)",
          all(w["accesses"] == n_acc[w["stream"]] for w in recs))
    check("every worker QOS rc == 0", all(w["qos_rc"] == 0 for w in recs))
    struct_ok, n_units = True, 0
    for w in recs:
        want_order = "ABBA" if w["round"] % 2 == 0 else "BAAB"
        if len(w["units"]) != 16:
            struct_ok = False
        for i, u in enumerate(w["units"]):
            n_units += 1
            un, a, b = UNITS[i % 4]
            if (u["unit"], u["a"], u["b"]) != (un, a, b) or u["order"] != want_order or \
                    "".join(r["arm"] for r in u["reps"]) != want_order or len(u["reps"]) != 4:
                struct_ok = False
    check(f"every unit: fixed null/floor/lean/fused order, 4 reps, ABBA even / BAAB odd ({n_units}/256 units)",
          struct_ok and n_units == 256)
    check("budget not hit; elapsed < 5.5h", R["budget_hit"] is False and R["elapsed_s"] < 19800, R["elapsed_s"])

    # ---------------- 3. rung 1: hit-rate oracle parsed HERE from exp718 PASS-1 + round-0 parity/census
    E = json.loads((HOME / "warp-work/exp718-moei-shared-econ/exp718-econ.json").read_text())
    orc = {(k.split("|")[0], int(k.split("|")[1]), k.split("|")[2]): v["hit_rate"] for k, v in E["pass1"].items()}
    n_rep, bad = 0, []
    for w in recs:
        for u in w["units"]:
            for r in u["reps"]:
                n_rep += 1
                if r["hit_rate"] != orc[(w["stream"], u["cap"], "costfit3")]:
                    bad.append((w["stream"], u["cap"], u["unit"], r["arm"]))
    check(f"rung 1: every timed replay hit_rate == exp718 PASS-1 costfit3 exactly ({n_rep - len(bad)}/{n_rep})",
          not bad and n_rep == 1024)
    check("stored hit_rate_mismatches empty", R["hit_rate_mismatches"] == [])
    cen = [(w["stream"], u["cap"], u["unit"], u["census"]) for w in recs for u in w["units"] if u.get("census")]
    check("round-0 census complete: 32/32 (2 streams x 4 caps x 4 units), only in round 0",
          len(cen) == 32 and all(w["round"] == 0 for w in recs for u in w["units"] if u.get("census")))
    check("rung 1: round-0 terminal FULL STATE of every B arm == sealed costfit3 A (32/32)",
          all(c["state_eq"] for *_, c in cen), sum(c["state_eq"] for *_, c in cen))
    check("rung 1: A-arm census == sealed structure_census (32/32)", all(c["a_eq_CEN"] for *_, c in cen))
    a_by_cell = {}
    for s, cap, un, c in cen:
        a_by_cell.setdefault((s, cap), []).append(json.dumps(c["a"], sort_keys=True))
    check("A-arm (costfit3) census identical across the 4 units of each cell (8/8)",
          all(len(set(v)) == 1 for v in a_by_cell.values()) and len(a_by_cell) == 8)
    sr = {}
    for s, cap, un, c in cen:
        sr.setdefault(un, {})[f"{s}|{cap}"] = c["b"]["struct_bytes"] / c["a"]["struct_bytes"]
    md = max(abs(sr[u][k] - R["struct_ratios"][u][k]) for u in sr for k in sr[u])
    check("struct ratios re-derived from census == stored (32/32, |d| <= 1e-15)", md <= 1e-15, f"{md:.1e}")
    check("null and floor struct ratio == 1.0 at all cells (no sharing)",
          all(v == 1.0 for u in ("null", "floor") for v in sr[u].values()))
    econ_v = econ(sr["fused"])
    check("economics qualifier re-derived (fused/costfit3 struct_bytes <= 0.80 at all 8 cells) == stored",
          econ_v == R["economics"], f"{econ_v}; fused max {max(sr['fused'].values()):.4f}")
    fused_tables = {k: c["b"]["tables"] for s, cap, un, c in cen if un == "fused" for k in [f"{s}|{cap}"]}
    base_tables = {f"{s}|{cap}": c["a"]["tables"] for s, cap, un, c in cen if un == "fused"}

    # ---------------- 4. re-derive pair ratios + cell stats from raw ns
    raw = {}
    for w in recs:
        for u in w["units"]:
            for clk, key in (("thread", "thread_ns"), ("proc", "proc_ns"), ("wall", "wall_ns")):
                raw.setdefault((w["stream"], u["cap"], u["unit"]), {}).setdefault(clk, []).append(ratio(u["reps"], key))
    cell = {k: {clk: {"median": statistics.median(v), "q25": quant(v, .25), "q75": quant(v, .75), "n": len(v)}
                for clk, v in d.items()} for k, d in raw.items()}
    check("32 cells (2 streams x 4 caps x 4 units), n=8 rounds each", len(cell) == 32
          and all(c[m]["n"] == 8 for c in cell.values() for m in c))
    maxdiff = max(abs(cell[k][m][s] - R["cells"]["|".join(map(str, k))][m][s])
                  for k in cell for m in cell[k] for s in ("median", "q25", "q75"))
    check("stored cell stats == re-derived from raw ns (32 cells x 3 clocks x 3 stats, |d| <= 1e-12)",
          maxdiff <= 1e-12, f"max |d| {maxdiff:.2e}")
    cells8 = [(s, c) for s in STREAMS for c in CAPS]
    null_meds = {sc: cell[(*sc, "null")]["thread"]["median"] for sc in cells8}
    null_pooled = statistics.median(null_meds.values())
    null_cells_ok = all(0.93 <= x <= 1.07 for x in null_meds.values())
    fc = {sc: cell[(*sc, "fused")]["thread"] for sc in cells8}
    lc = {sc: cell[(*sc, "lean")]["thread"] for sc in cells8}
    flc = {sc: cell[(*sc, "floor")]["thread"] for sc in cells8}
    arg = max(fc, key=lambda k: fc[k]["median"])
    comp = sorted({w["round"] for w in recs if sum(x["round"] == w["round"] for x in recs) == 2})
    gi = {"sealed_ok": True, "hr_ok": not bad and all(c["state_eq"] and c["a_eq_CEN"] for *_, c in cen)
          and len(cen) == 32, "rounds": len(comp), "null_pooled": null_pooled, "null_cells_ok": null_cells_ok,
          "F": fc[arg]["median"], "F_q25": fc[arg]["q25"], "F_q75": fc[arg]["q75"], "F_argmax": list(arg),
          "lean_max": max(v["median"] for v in lc.values())}
    sg = R["gate_inputs"]
    check("rung 2: complete rounds 8 >= MIN 5", gi["rounds"] == 8 == sg["rounds"])
    check("rung 3 null pooled in [0.97,1.03]", 0.97 <= null_pooled <= 1.03, f"{null_pooled:.4f}")
    check("rung 3 every cell null median in [0.93,1.07] (8/8)", null_cells_ok,
          f"range {min(null_meds.values()):.4f}-{max(null_meds.values()):.4f}")
    for mine, theirs in (("null_pooled", "null_pooled"), ("F", "R3"), ("F_q25", "R3_q25"), ("F_q75", "R3_q75"),
                         ("lean_max", "R2")):
        check(f"gate input {mine} re-derived == stored {theirs}", abs(gi[mine] - sg[theirs]) <= 1e-12,
              f"{gi[mine]:.6f}")
    check("fused argmax cell re-derived == stored", gi["F_argmax"] == sg["R3_argmax"], arg)
    check("rung 4: fused argmax IQR does not straddle 1.10 or 1.35",
          not any(gi["F_q25"] <= t < gi["F_q75"] for t in (1.10, 1.35)), f"[{gi['F_q25']:.4f},{gi['F_q75']:.4f}]")
    check("rung 5: F <= 1.10", gi["F"] <= 1.10, f"{gi['F']:.4f}")

    # ---------------- 5. independent ladder + boundary self-test
    base = dict(sealed_ok=True, hr_ok=True, rounds=8, null_pooled=1.0, null_cells_ok=True, F=1.0, F_q25=.99, F_q75=1.01)
    T = [({}, "PAYOFF-CONFIRMED"), ({"F": 1.10, "F_q25": 1.10, "F_q75": 1.10}, "PAYOFF-CONFIRMED"),
         ({"F": 1.10, "F_q25": 1.05, "F_q75": 1.10}, "PAYOFF-CONFIRMED"),  # q75 == t is not a straddle
         ({"F": 1.1001, "F_q25": 1.1001, "F_q75": 1.2}, "PAYOFF-MARGINAL"),
         ({"F": 1.35, "F_q25": 1.36, "F_q75": 1.36}, "PAYOFF-MARGINAL"),
         ({"F": 1.3501, "F_q25": 1.3501, "F_q75": 1.4}, "PAYOFF-REJECTED"),
         ({"F": 1.4, "F_q25": 1.35, "F_q75": 1.45}, "PAYOFF-UNRESOLVED"),
         ({"F": 1.4, "F_q25": 1.3, "F_q75": 1.35}, "PAYOFF-REJECTED"),
         ({"F": 1.1, "F_q25": 1.10, "F_q75": 1.11}, "PAYOFF-UNRESOLVED"),
         ({"null_pooled": 1.0301}, "TIME-INVALID"), ({"null_pooled": 0.97}, "PAYOFF-CONFIRMED"),
         ({"null_cells_ok": False}, "TIME-INVALID"), ({"rounds": 4}, "INCOMPLETE-BUDGET"),
         ({"rounds": 5, "null_pooled": 5.0}, "TIME-INVALID"), ({"hr_ok": False, "rounds": 0}, "SEALED-FAIL"),
         ({"sealed_ok": False}, "SEALED-FAIL")]
    st_ok = sum(ladder({**base, **o}) == w for o, w in T)
    E8 = {f"c{i}": 0.5 for i in range(8)}
    TE = [(E8, "SAVING"), ({**E8, "c0": 0.80}, "SAVING"), ({**E8, "c0": 0.8001}, "NO-SAVING"),
          ({f"c{i}": 0.5 for i in range(7)}, "NO-SAVING")]
    se_ok = sum(econ(f) == w for f, w in TE)
    check(f"independent ladder boundary self-test {st_ok}/{len(T)}", st_ok == len(T))
    check(f"independent economics qualifier self-test {se_ok}/{len(TE)}", se_ok == len(TE))
    verdict = ladder(gi)
    check("re-adjudicated verdict == stored verdict", verdict == R["verdict"], verdict)

    # ---------------- 6. descriptive robustness (non-gating)
    rob = {}
    for clk in ("proc", "wall"):
        meds = {sc: cell[(*sc, "fused")][clk]["median"] for sc in cells8}
        a2 = max(meds, key=meds.get)
        rob[clk] = {"F": meds[a2], "argmax": list(a2),
                    "null_pooled": statistics.median(cell[(*sc, "null")][clk]["median"] for sc in cells8)}
    loro = []
    for drop in range(8):
        sub = {}
        for w in recs:
            if w["round"] == drop:
                continue
            for u in w["units"]:
                sub.setdefault((w["stream"], u["cap"], u["unit"]), []).append(ratio(u["reps"], "thread_ns"))
        st = {k: (statistics.median(v), quant(v, .25), quant(v, .75)) for k, v in sub.items()}
        a3 = max(cells8, key=lambda sc: st[(*sc, "fused")][0])
        nm = [st[(*sc, "null")][0] for sc in cells8]
        loro.append(ladder(dict(sealed_ok=True, hr_ok=True, rounds=7, null_pooled=statistics.median(nm),
                                null_cells_ok=all(0.93 <= x <= 1.07 for x in nm), F=st[(*a3, "fused")][0],
                                F_q25=st[(*a3, "fused")][1], F_q75=st[(*a3, "fused")][2])))
    check("descriptive: leave-one-round-out verdict stable (8/8 == stored)", all(v == verdict for v in loro), loro)
    fused_units = [x for k, d in raw.items() if k[2] == "fused" for x in d["thread"]]
    fused_lt1 = sum(x < 1.0 for x in fused_units)
    fused_max_unit = max(fused_units)
    null_units = [x for k, d in raw.items() if k[2] == "null" for x in d["thread"]]
    null_out = sum(abs(x - 1) > 0.10 for x in null_units)
    loads = [w["loadavg_start"] for w in recs] + [w["loadavg_end"] for w in recs]
    # exp723 comparison (sealed, parsed at runtime): sealed shared views at the same cells
    S723 = json.loads((GITREPO / "benchmarks/cache_simulator/research/exp723/exp723-cpupair.json").read_text())
    s723 = {(k.split("|")[0], int(k.split("|")[1])): v["thread"]["median"] for k, v in S723["cells"].items()
            if k.split("|")[2] == "fam3"}
    check("exp723 sealed result parsed: 8 N=3 cells", len(s723) == 8)
    ex718 = {k: v["struct"] for k, v in E["ratios"].items() if k.split("|")[1] == "costfit3"}

    # ---------------- 7. LIVE third-process re-check of the fused argmax cell (round-0 mode: parity + census too)
    live = {}
    py = HOME / "warp-work/exp650-moei-granite3b-trace-pr/.venv/bin/python"
    code = r'''
import sys, json, importlib.util
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[4])
spec = importlib.util.spec_from_file_location("run_fused", sys.argv[1]); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
if __name__ == "__main__":
    M.assert_sealed()
    st = sys.argv[2]; cap = int(sys.argv[3])
    w = M.worker((st, str(M.STREAMS[st]), 0, [cap], 0))
    print("LIVEJSON" + json.dumps(w, default=str))
'''
    scr = HOME / ".hermes/cache/scratch/exp729_live_recheck.py"
    scr.write_text(code)
    try:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        out = subprocess.run([str(py), str(scr), str(D / "run_fused.py"), arg[0], str(arg[1]), str(D)],
                             capture_output=True, text=True, timeout=2400, env=env)
        line = [x for x in out.stdout.splitlines() if x.startswith("LIVEJSON")]
        live = json.loads(line[0][8:]) if line else {"error": out.stderr[-800:]}
    finally:
        scr.unlink(missing_ok=True)
    if "error" in live:
        check("LIVE re-check ran", False, live["error"])
    else:
        lhr = all(r["hit_rate"] == orc[(arg[0], arg[1], "costfit3")] for u in live["units"] for r in u["reps"])
        check(f"LIVE {arg[0]}@{arg[1]}: 16/16 fresh replays hit_rate == exp718 oracle", lhr and
              sum(len(u["reps"]) for u in live["units"]) == 16)
        check(f"LIVE {arg[0]}@{arg[1]}: full-state parity 4/4 units + A census == sealed structure_census",
              all(u["census"]["state_eq"] and u["census"]["a_eq_CEN"] for u in live["units"]))
        lf = [u for u in live["units"] if u["unit"] == "fused"][0]["census"]
        lsr = lf["b"]["struct_bytes"] / lf["a"]["struct_bytes"]
        check(f"LIVE fused struct ratio == stored {arg[0]}|{arg[1]}",
              lsr == R["struct_ratios"]["fused"][f"{arg[0]}|{arg[1]}"], f"{lsr:.4f}")
        lr = {u["unit"]: ratio(u["reps"], "thread_ns") for u in live["units"]}
        live["ratios"] = lr
        live["loadavg"] = [live["loadavg_start"], live["loadavg_end"]]
        live.pop("units", None)
        check(f"LIVE {arg[0]}@{arg[1]} fused thread ratio <= 1.10 (single ABBA unit, descriptive)", lr["fused"] <= 1.10,
              ", ".join(f"{k} {v:.4f}" for k, v in lr.items()))

    n_ok = sum(c["ok"] for c in CHECKS)
    # ---------------- ADDENDUM
    f4 = lambda x: f"{x:.4f}"  # noqa: E731
    fmin = min(fc, key=lambda k: fc[k]["median"])
    L = ["# ADDENDUM 64 — exp729: fused shared-state CostFit3 — A/A-gated paired CPU-time payoff + metadata economics\n"]
    L.append(f"Verdict: **{verdict} + {econ_v}** (frozen ladder rung 5 + economics qualifier). Holding all 10 per-key "
             f"fields of the N=3 CostFit arbiter in ONE shared list record per key (FusedCostFit3) costs "
             f"**x{f4(gi['F'])}** per-thread CPU time vs the sealed per-key-dict costfit3 at its WORST cell "
             f"{arg[0]} @{arg[1]} (IQR [{f4(gi['F_q25'])}, {f4(gi['F_q75'])}]) — i.e. it is faster everywhere, "
             f"under a valid A/A null (pooled x{f4(null_pooled)}, cells [{f4(min(null_meds.values()))}, "
             f"{f4(max(null_meds.values()))}]) — while cutting per-key struct bytes to "
             f"x{min(sr['fused'].values()):.3f}–x{max(sr['fused'].values()):.3f} of costfit3 at all 8 cells (bar <= 0.80). "
             f"8/8 rounds, {R['elapsed_s']:.0f}s, exit 0, freeze {FREEZE}; host loadavg "
             f"{min(loads):.2f}–{max(loads):.2f} throughout (not gated, disclosed).\n")
    L.append(f"Independent follow-up adjudication: **{n_ok}/{len(CHECKS)} checks pass** (gen_addendum64.py), "
             f"re-derived from the {n_rep} raw per-replay ns timings, the exp718 PASS-1 hit-rate oracle parsed here, "
             f"the 32 round-0 parity/census records, run.log, sealed-dep shas and the freeze commit, plus a LIVE "
             f"third-process re-run of the fused argmax cell. Re-derived verdict == stored.\n")
    L.append("## Decision-grade result\n")
    L.append(f"- **rung 1**: every timed replay ({n_rep}/{n_rep}) reproduced the exp718 PASS-1 costfit3 hit rate "
             f"exactly; round-0 terminal FULL STATE (arbiter, every leaf's order/hits/misses, every LCNU and S3-FIFO "
             f"per-key field) of all 32 B arms == sealed costfit3; A-arm census == sealed structure_census 32/32. "
             f"Fused parity is verified, not by construction.")
    L.append(f"- **A/A null (validity gate)**: pooled x{f4(null_pooled)} (bar [0.97, 1.03]); per-cell medians "
             + ", ".join(f"{s}@{c} {f4(v)}" for (s, c), v in null_meds.items())
             + f". {null_out}/{len(null_units)} individual null units deviated > 10%.")
    L.append("- **Per-thread CPU-time ratio arm/costfit3 (median over 8 rounds, [q25, q75]); struct-bytes ratio**:")
    for s in STREAMS:
        for c in CAPS:
            k = f"{s}|{c}"
            a, b, d = fc[(s, c)], lc[(s, c)], flc[(s, c)]
            L.append(f"  - {s} @{c}: fused x{f4(a['median'])} [{f4(a['q25'])}, {f4(a['q75'])}] struct "
                     f"x{sr['fused'][k]:.3f}; lean x{f4(b['median'])} struct x{sr['lean'][k]:.3f}; floor "
                     f"x{f4(d['median'])}; (exp723 sealed shared views x{s723[(s, c)]:.4f})")
    L.append(f"- Fused: {fused_lt1}/{len(fused_units)} individual ABBA units < 1.0 (max unit x{fused_max_unit:.4f}); "
             f"cheapest cell x{f4(fc[fmin]['median'])} @ {fmin[0]}/{fmin[1]}. Per-key tables "
             f"{sorted(set(base_tables.values()))} -> {sorted(set(fused_tables.values()))}.")
    L.append("\n## Attribution of exp723's cost (descriptive)\n")
    L.append(f"- floor (private dict-like Python views, no sharing): x{min(v['median'] for v in flc.values()):.3f}–"
             f"x{max(v['median'] for v in flc.values()):.3f}; lean (shared __slots__ records minus live counter): "
             f"x{min(v['median'] for v in lc.values()):.3f}–x{max(v['median'] for v in lc.values()):.3f}; exp723 "
             f"sealed views x{min(s723.values()):.3f}–x{max(s723.values()):.3f}. Most of exp723's ~1.2–1.6x is "
             f"per-access Python view dispatch (floor alone pays ~1.2–1.3x with zero sharing); removing the dispatch "
             f"layer and re-expressing the leaf methods over one record (fused) turns the cost into a saving.")
    L.append("\n## Descriptive (non-gating)\n")
    L.append(f"- Clock robustness: process_time fused worst x{f4(rob['proc']['F'])} @ {rob['proc']['argmax']}, null "
             f"x{f4(rob['proc']['null_pooled'])}; wall fused worst x{f4(rob['wall']['F'])} @ {rob['wall']['argmax']}, "
             f"null x{f4(rob['wall']['null_pooled'])}.")
    L.append(f"- Leave-one-round-out ladder: {sorted(set(loro))} in 8/8 drops.")
    if "error" not in live:
        L.append(f"- LIVE third-process re-run of {arg[0]} @{arg[1]} (one ABBA unit per arm, sealed worker() in "
                 f"round-0 mode, loadavg {live['loadavg'][0]:.2f}→{live['loadavg'][1]:.2f}): "
                 + ", ".join(f"{k} x{v:.4f}" for k, v in live["ratios"].items())
                 + "; hit rates == oracle 16/16; full-state parity 4/4; fused struct ratio == stored.")
    p1 = verdict == "PAYOFF-CONFIRMED" and econ_v == "SAVING" and 0.85 <= gi["F"] <= 1.05
    fl = [v["median"] for v in flc.values()]
    ln = [v["median"] for v in lc.values()]
    p2f = all(1.10 <= x <= 1.45 for x in fl)
    p2l = all(1.25 <= x <= 1.55 for x in ln)
    p3 = all(0.45 <= x <= 0.65 for x in sr["fused"].values())
    L.append(f"- Prediction check (PREREG, stated pre-run): (a) CONFIRMED + SAVING with F in [0.85, 1.05] — "
             f"{'HELD' if p1 else 'MISSED'} (F x{f4(gi['F'])}); (b) floor cells x1.10–1.45 — "
             f"{'HELD' if p2f else 'MISSED'} (x{min(fl):.4f}–x{max(fl):.4f}), lean cells x1.25–1.55 — "
             f"{'HELD' if p2l else 'MISSED'} (x{min(ln):.4f}–x{max(ln):.4f}); (c) fused struct 0.45–0.65 at all cells — "
             f"{'HELD' if p3 else 'MISSED'} (x{min(sr['fused'].values()):.4f}–x{max(sr['fused'].values()):.4f}; "
             f"qwen30b cells save more than predicted). exp718 N=3 struct ratios for reference "
             f"x{min(ex718.values()):.3f}–x{max(ex718.values()):.3f} (exp675 shared design).")
    L.append("\n## Consequence (pre-registered branch)\n")
    L.append("- PAYOFF-CONFIRMED + SAVING: FusedCostFit3 is proposed as the N-way metadata layout for the CostFit "
             f"heads — identical decisions (verified full state), lower per-access CPU, and a "
             f"{(1 - max(sr['fused'].values())) * 100:.0f}–{(1 - min(sr['fused'].values())) * 100:.0f}% per-key "
             "metadata cut. This closes the exp675 -> exp718 -> exp723 -> exp729 shared-state line in the simulator.")
    L.append("- Next (pre-registered): port the fused record to the 2-trace joint-BO head and produce a C-level "
             "array-of-struct estimate for the engine.")
    L.append("\n## Integrity\n")
    L.append(f"- PREREG/runner/policies/smoke.log/sealed_deps byte-exact in freeze commit {FREEZE} == ARTIFACT.sha256 "
             f"== disk == running.json registration; freeze precedes the result; 15/15 sealed deps unchanged and "
             f"recorded in the result JSON; ladder self-test 15/15 ran before measurement; sealed artifacts "
             f"untouched; nothing re-launched. run.log is force-added (repo .gitignore has *.log) as primary evidence.")
    L.append("\n## Check list\n")
    for c in CHECKS:
        L.append(f"- [{'x' if c['ok'] else ' '}] {c['check']}" + (f" — {c['detail']}" if c["detail"] else ""))
    (D / "ADDENDUM64.md").write_text("\n".join(L) + "\n")
    (D / "exp729-adjudication.json").write_text(json.dumps(
        {"verdict": verdict, "economics": econ_v, "checks_ok": n_ok, "checks_total": len(CHECKS), "checks": CHECKS,
         "gate_inputs": gi, "null_cell_medians": {f"{s}|{c}": v for (s, c), v in null_meds.items()},
         "struct_ratios": sr, "robustness": rob, "leave_one_round_out": loro, "exp723_fam3_cells":
         {f"{s}|{c}": v for (s, c), v in s723.items()}, "live": live,
         "predictions": {"a": p1, "b_floor": p2f, "b_lean": p2l, "c": p3},
         "null_units_over_10pct": [null_out, len(null_units)], "elapsed_s": round(time.time() - t0, 1)},
        indent=1, default=str))
    print(f"verdict={verdict} econ={econ_v} checks {n_ok}/{len(CHECKS)} F={gi['F']:.4f} null={null_pooled:.4f} "
          f"{time.time() - t0:.0f}s")
    for c in CHECKS:
        if not c["ok"]:
            print("FAIL", c)


if __name__ == "__main__":
    main()

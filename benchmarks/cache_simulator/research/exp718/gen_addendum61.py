"""gen_addendum61.py — independent follow-up adjudication of exp718 (exp675 stage B).

Re-derives every gate of the FROZEN exp718 PREREG from primary sources (result JSON raw rows,
run.log, stage-A anchor CSVs parsed here, sha-checked sealed inputs), re-implements the frozen
verdict ladder (first match wins) with a boundary self-test, runs a small LIVE third-process
re-check through the sealed code (granite @262144: both full-state parity pairs + the 4 census
cells whose PASS-2 rows the budget cut), and writes ADDENDUM61.md + exp718-adjudication.json.
Sealed artifacts are read-only here; nothing is re-launched.
"""
import csv
import hashlib
import json
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
FREEZE = "0a042de"
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
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


def main():
    t0 = time.time()
    # ---------------- 1. freeze integrity
    art = parse_sums(D / "ARTIFACT.sha256")
    for f, h in art.items():
        check(f"artifact sha {f}", sha(D / f) == h, h[:12])
        rel = f"benchmarks/cache_simulator/research/exp718/{f}"
        gs = subprocess.run(["git", "-C", str(GITREPO), "show", f"{FREEZE}:{rel}"], capture_output=True)
        if gs.returncode == 0:
            check(f"freeze commit {FREEZE} carries {f} byte-exact", hashlib.sha256(gs.stdout).hexdigest() == h)
        else:
            ign = subprocess.run(["git", "-C", str(GITREPO), "check-ignore", rel], capture_output=True).returncode == 0
            art_c = subprocess.run(["git", "-C", str(GITREPO), "show", f"{FREEZE}:benchmarks/cache_simulator/research/exp718/ARTIFACT.sha256"],
                                   capture_output=True, text=True).stdout
            check(f"{f} absent from freeze commit only via .gitignore *.log; its sha is in the committed ARTIFACT.sha256 "
                  f"and the repo copy matches (disclosed; force-added at publish)",
                  ign and f"{h}  {f}" in art_c and sha(GITREPO / rel) == h)
    deps = parse_sums(D / "sealed_deps.sha256")
    R = json.loads((D / "exp718-econ.json").read_text())
    for f, h in deps.items():
        p = Path(f) if Path(f).is_absolute() else REPO / f
        check(f"sealed dep {p.name} unchanged", sha(p) == h, h[:12])
        check(f"result JSON records sealed dep {p.name}", R["sealed_deps"].get(p.name) == h)
    log = (D / "run.log").read_text()
    check("run.log RUN_EXIT=0", "RUN_EXIT=0" in log)
    check("run.log settled verdict matches JSON", f"settled verdict={R['verdict']}" in log)
    check("runner sealed-deps assertion passed at start", "sealed deps ok (13 files)" in log)

    # ---------------- 2. completeness / budget (rung 2 inputs)
    CAPS, STREAMS = R["design"]["caps"], list(R["design"]["streams"])
    POL = R["design"]["policies"]
    FAM = [("costfit", "shared_costfit"), ("costfit3", "shared_costfit3")]
    budget = R["design"]["wall_budget_s"]
    check("design matches PREREG (caps/policies/budget/repeats/quiet)",
          CAPS == [256, 1024, 4096, 262144] and sorted(POL) == sorted(
              ["costfit", "shared_costfit", "costfit3", "shared_costfit3"]) and budget == 21600
          and R["design"]["repeats_timed"] == 5 and R["design"]["quiet_start"] == 1.5
          and R["design"]["quiet_end"] == 2.5)
    p1 = {tuple([k.split("|")[0], int(k.split("|")[1]), k.split("|")[2]]): v for k, v in R["pass1"].items()}
    exp_cells = {(s, c, p) for s in STREAMS for c in CAPS for p in POL}
    miss1 = sorted(exp_cells - set(p1))
    check("PASS-1 census 32/32 cells present", not miss1, f"{len(p1)}/32")
    groups = R["pass2_groups"]
    have_g = {(g["stream"], int(g["cap"])) for g in groups if g["error"] is None and len(g["rows"]) == 4}
    exp_g = {(s, c) for c in CAPS for s in STREAMS}
    missing_groups = sorted(exp_g - have_g)
    p2 = {(g["stream"], int(g["cap"]), pol): row for g in groups for pol, row in g["rows"].items()}
    missing_p2 = sorted(exp_cells - set(p2))
    elapsed = R["elapsed_s"]
    budget_exceeded = elapsed > budget and bool(missing_groups)
    check("budget exhausted (elapsed > 6h) with groups missing", budget_exceeded,
          f"elapsed {elapsed}s > {budget}s; missing groups {missing_groups}")
    last_start = None
    for line in log.splitlines():
        if "passB qwen30b @262144" in line:
            last_start = float(line.split("]")[0].strip("[ s"))
    check("missing group cut by budget, not spawn error",
          all(g["error"] is None for g in groups) and "ERROR" not in log, f"last group logged at {last_start}s")
    check("runner state flags agree with re-derivation",
          R["state"]["budget_exceeded"] == budget_exceeded and R["state"]["cells_missing"] is False)

    # ---------------- 3. H1' parity (rung 1)
    par = R["parity"]
    keys = {(p["stream"], int(p["cap"]), p["base"], p["shared"]) for p in par}
    want = {(s, c, b, sh) for s in STREAMS for c in CAPS for b, sh in FAM}
    check("H1' 16/16 parity pairs present", keys == want and len(par) == 16, f"{len(par)}")
    check("H1' all full-state tuples equal (no diff_fields)", all(p["equal"] and not p["diff_fields"] for p in par))
    smoke_ok = "sealed parity_smoke: True" in log and R["state"]["parity_smoke_ok"] is True
    check("H1' sealed synthetic parity_smoke True (log + JSON)", smoke_ok)
    hit_base = all(p1[(p["stream"], int(p["cap"]), p["base"])]["hit_rate"] == p["hit_rate"] for p in par)
    hit_shared = all(p1[(p["stream"], int(p["cap"]), p["shared"])]["hit_rate"] == p["hit_rate"] for p in par)
    check("H1' parity hit_rate == PASS-1 census hit_rate (base cells, frozen gate)", hit_base)
    check("H1' parity hit_rate == PASS-1 census hit_rate (shared cells, stronger)", hit_shared)
    res0 = [(p["stream"], p["cap"], p["base"]) for p in par if p["resident_len"] == 0]
    parity_ok = keys == want and all(p["equal"] for p in par) and smoke_ok and hit_base

    # ---------------- 4. H4' accounting on available cells (descriptive: rung 2 fires first)
    want_t = {"costfit": 5, "costfit3": 10, "shared_costfit": 1, "shared_costfit3": 1}
    tables_ok = all(p1[k]["tables"] == want_t[k[2]] for k in p1)
    check("H4' tables 1/5/10 on all 32 PASS-1 cells", tables_ok)
    xp_exact, xp_jit, worst_jit = 0, 0, 0.0
    for k, r2 in p2.items():
        r1 = p1[k]
        if all(r1[f] == r2[f] for f in ("hit_rate", "tables", "records", "slots", "struct_bytes")):
            xp_exact += 1
        j = max(abs(r2[f] - r1[f]) / r1[f] for f in ("peak_bytes", "terminal_bytes"))
        worst_jit = max(worst_jit, j)
        xp_jit += j <= 0.01
    check(f"H4' cross-pass exact struct fields on {len(p2)}/{len(p2)} available cells", xp_exact == len(p2),
          f"{xp_exact}/{len(p2)}")
    check(f"H4' cross-pass peak/terminal <=1% on available cells", xp_jit == len(p2), f"worst {worst_jit:.6f}")
    accounting_ok_frozen = tables_ok and not missing_p2 and xp_exact == len(p2) and xp_jit == len(p2)
    check("H4' frozen accounting_ok False ONLY because PASS-2 rows missing (agrees with runner)",
          (not accounting_ok_frozen) == (R["state"]["accounting_ok"] is False) and tables_ok
          and xp_exact == len(p2) and xp_jit == len(p2), f"missing PASS-2 {missing_p2}")

    # ---------------- 5. ratios re-derived from raw rows
    ratios = {}
    for s in STREAMS:
        for b, sh in FAM:
            for c in CAPS:
                rb, rs = p1[(s, c, b)], p1[(s, c, sh)]
                ratios[(s, b, c)] = {"struct": rs["struct_bytes"] / rb["struct_bytes"],
                                     "terminal": rs["terminal_bytes"] / rb["terminal_bytes"],
                                     "peak": rs["peak_bytes"] / rb["peak_bytes"],
                                     "records": (rb["records"], rs["records"])}
    stored_eq = all(abs(R["ratios"][f"{s}|{b}|{c}"][m] - v[m]) == 0 for (s, b, c), v in ratios.items()
                    for m in ("struct", "terminal", "peak"))
    check("stored ratios == re-derived from raw PASS-1 rows (16 keys x 3 metrics, exact)", stored_eq)

    # ---------------- 6. H2' drift vs stage-A anchors parsed HERE from the sealed CSVs
    drift = []
    for s in STREAMS:
        rows = {(r["policy"], int(r["capacity"])): r for r in
                csv.DictReader((REPO / f"benchmarks/cache_simulator/research/census_exp675-{s}.csv").open())}
        for b, sh in FAM:
            for c in [256, 1024, 4096]:
                a_s = int(rows[(sh, c)]["struct_bytes"]) / int(rows[(b, c)]["struct_bytes"])
                a_t = int(rows[(sh, c)]["terminal_bytes"]) / int(rows[(b, c)]["terminal_bytes"])
                r = ratios[(s, b, c)]
                drift.append({"stream": s, "family": b, "cap": c, "struct_A": a_s, "struct_B": r["struct"],
                              "ds": abs(r["struct"] / a_s - 1), "term_A": a_t, "term_B": r["terminal"],
                              "dt": abs(r["terminal"] / a_t - 1)})
    drift_ok = all(x["ds"] <= 0.05 and x["dt"] <= 0.10 for x in drift)
    check("H2' drift 12/12 within struct 5% / terminal 10% (descriptive)", drift_ok,
          f"max ds {max(x['ds'] for x in drift):.4f} max dt {max(x['dt'] for x in drift):.4f}")
    # ---------------- 7. H5' ceiling
    ceil = []
    for s in STREAMS:
        for b, _ in FAM:
            r4, rc = ratios[(s, b, 4096)]["struct"], ratios[(s, b, 262144)]["struct"]
            ceil.append({"stream": s, "family": b, "r4096": r4, "rceil": rc, "ok": rc <= 1.05 * r4})
    ceiling_ok = all(x["ok"] for x in ceil)
    check("H5' ceiling 4/4 struct(262144) <= 1.05 x struct(4096) (descriptive)", ceiling_ok)

    # ---------------- 8. H3' quiet groups / informational loaded time ratios
    quiet = [g for g in groups if g["quiet"]]
    requiet = [g for g in groups if g["loadavg_start"] < 1.5 and g["loadavg_end"] < 2.5 and g["error"] is None]
    check("H3' quiet groups 0/8 (re-derived from per-group loadavg)", len(quiet) == 0 and len(requiet) == 0,
          f"{len(quiet)} quiet; loadavg starts {[g['loadavg_start'] for g in groups]}")
    loaded = []
    for g in groups:
        rw = g["rows"]
        loaded.append({"stream": g["stream"], "cap": g["cap"], "la": (g["loadavg_start"], g["loadavg_end"]),
                       "R3": rw["shared_costfit3"]["ns_per_access"] / rw["costfit3"]["ns_per_access"],
                       "R2": rw["shared_costfit"]["ns_per_access"] / rw["costfit"]["ns_per_access"]})

    # ---------------- 9. frozen ladder re-implementation + boundary self-test
    def ladder(st):
        if not st["parity"]:
            return "PARITY-FAIL"
        if st["budget"] or st["missing"]:
            return "INCOMPLETE-BUDGET"
        if not st["acct"]:
            return "ACCOUNTING-FAIL"
        if not st["drift"]:
            return "ECONOMICS-DRIFT"
        if not st["ceil"]:
            return "CEILING-DRIFT"
        if st["quiet"] < 6:
            return "ECONOMICS-TIME-UNMEASURED"
        if st["R3"] <= 1.10:
            return "PAYOFF-CONFIRMED"
        if st["R3"] <= 1.35:
            return "PAYOFF-MARGINAL"
        return "PAYOFF-REJECTED"
    ok = dict(parity=True, budget=False, missing=False, acct=True, drift=True, ceil=True, quiet=8, R3=1.0)
    st_tests = [({}, "PAYOFF-CONFIRMED"), ({"R3": 1.10}, "PAYOFF-CONFIRMED"), ({"R3": 1.1001}, "PAYOFF-MARGINAL"),
                ({"R3": 1.35}, "PAYOFF-MARGINAL"), ({"R3": 1.3501}, "PAYOFF-REJECTED"),
                ({"quiet": 5}, "ECONOMICS-TIME-UNMEASURED"), ({"quiet": 6}, "PAYOFF-CONFIRMED"),
                ({"ceil": False}, "CEILING-DRIFT"), ({"drift": False, "ceil": False}, "ECONOMICS-DRIFT"),
                ({"acct": False, "drift": False}, "ACCOUNTING-FAIL"), ({"budget": True, "acct": False}, "INCOMPLETE-BUDGET"),
                ({"parity": False, "budget": True}, "PARITY-FAIL")]
    st_ok = sum(ladder({**ok, **o}) == w for o, w in st_tests)
    check(f"ladder boundary self-test {st_ok}/{len(st_tests)}", st_ok == len(st_tests))
    st = dict(parity=parity_ok, budget=budget_exceeded, missing=bool(missing_groups), acct=accounting_ok_frozen,
              drift=drift_ok, ceil=ceiling_ok, quiet=len(quiet), R3=None)
    verdict = ladder(st)
    check("re-adjudicated verdict == stored verdict", verdict == R["verdict"], verdict)
    counterfactual = ladder({**st, "budget": False, "missing": False, "acct": True})

    # ---------------- 10. LIVE third-process re-check through sealed code (granite @262144)
    live = {}
    py = HOME / "warp-work/exp650-moei-granite3b-trace-pr/.venv/bin/python"
    code = r'''
import sys, json, importlib.util
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("run_econ", sys.argv[1]); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
if __name__ == "__main__":
    M.assert_sealed()
    acc, stats = M.load_accesses([str(M.STREAMS["granite"])], ignore_layers=0, prefill="skip")
    par = [M.parity_pair(acc, stats, b, s, 262144) for b, s in M.FAMILIES]
    cells = {p: M.measure_cell(p, 262144, M.STREAMS["granite"], 1) for p in M.POLICIES}
    print("LIVEJSON" + json.dumps({"parity": par, "cells": cells}, default=str))
'''
    scr = HOME / ".hermes/cache/scratch/exp718_live_recheck.py"
    scr.write_text(code)
    try:
        out = subprocess.run([str(py), str(scr), str(D / "run_econ.py")], capture_output=True, text=True, timeout=1200)
        line = [x for x in out.stdout.splitlines() if x.startswith("LIVEJSON")]
        live = json.loads(line[0][8:]) if line else {"error": out.stderr[-800:]}
    finally:
        scr.unlink(missing_ok=True)
    if "error" in live:
        check("LIVE re-check ran", False, live["error"])
    else:
        lp = live["parity"]
        stored = {(p["base"]): p for p in par if p["stream"] == "granite" and int(p["cap"]) == 262144}
        check("LIVE granite@262144 parity 2/2 equal and hit_rate == stored",
              all(p["equal"] and p["hit_rate"] == stored[p["base"]]["hit_rate"] for p in lp))
        ex, jt = 0, 0.0
        for pol, row in live["cells"].items():
            r1 = p1[("granite", 262144, pol)]
            ex += all(r1[f] == row[f] for f in ("hit_rate", "tables", "records", "slots", "struct_bytes"))
            jt = max(jt, max(abs(row[f] - r1[f]) / r1[f] for f in ("peak_bytes", "terminal_bytes")))
        live["xrun_exact"], live["xrun_worst_jitter"] = ex, jt
        check("LIVE granite@262144 cross-run (vs PASS-1) exact struct fields 4/4 (fills the cut PASS-2 gap, descriptive)",
              ex == 4, f"{ex}/4")
        check("LIVE granite@262144 cross-run peak/terminal <=1%", jt <= 0.01, f"worst {jt:.6f}")

    n_ok = sum(c["ok"] for c in CHECKS)
    # ---------------- ADDENDUM
    def f4(x):
        return f"{x:.4f}"
    L = []
    L.append("# ADDENDUM 61 — exp718: shared-state N-way metadata economics at the cap ceiling (exp675 stage B)\n")
    L.append(f"Verdict: **{verdict}** (frozen ladder rung 2). The 6 h wall budget ran out after 7 of 8 quiet-gated "
             f"timing groups: Mack never reached loadavg(1) < 1.5 (group-start loads "
             f"{min(g['loadavg_start'] for g in groups):.2f}–{max(g['loadavg_start'] for g in groups):.2f}); every "
             f"group waited the full 45 min, so 0/8 groups were quiet and the granite @262144 group "
             f"({', '.join(sorted({p for _, _, p in missing_p2}))}) never ran. Parity (rung 1) held. "
             f"Elapsed {elapsed:.0f}s, exit 0, freeze {FREEZE}.\n")
    L.append(f"Independent follow-up adjudication: **{n_ok}/{len(CHECKS)} checks pass**, computed by gen_addendum61.py "
             f"from the result JSON raw rows, run.log, the sealed stage-A CSVs (parsed here) and sha-checked sealed "
             f"inputs, plus a LIVE third-process re-check through the sealed code. Re-derived verdict == stored.\n")
    L.append("## What is decision-grade (load-independent)\n")
    L.append(f"- **H1' parity HOLDS, including the never-tested cap ceiling 262144**: 16/16 full-state tuples "
             f"(hits, misses, hit_rate, switches, choice_switches, choice, _mass, _sw_mass, resident order) exactly equal "
             f"on both real decode streams × 4 caps × N=2/N=3; sealed synthetic event-sequence smoke True; every "
             f"parity hit_rate equals the census hit_rate for base AND shared cells.")
    if res0:
        L.append(f"  - Disclosed: {res0} report resident_len 0 (base AND shared both expose an empty resident list at "
                 f"that cell; cause not investigated here), so resident order is vacuous there; all other state fields were equal.")
    L.append(f"- **N-way metadata reduction** (PASS-1 census, struct bytes shared/base):")
    for s in STREAMS:
        for b, _ in FAM:
            seq = ", ".join(f"{c}: x{f4(ratios[(s, b, c)]['struct'])} (records {ratios[(s, b, c)]['records'][0]}→"
                            f"{ratios[(s, b, c)]['records'][1]})" for c in CAPS)
            L.append(f"  - {s} {b}: {seq}")
    L.append("\n## Descriptive only (rung 2 fired before these gates)\n")
    L.append(f"- H4' accounting: tables 1/5/10 on 32/32 cells; cross-pass exact struct fields "
             f"{xp_exact}/{len(p2)} available cells, peak/terminal jitter worst {worst_jit:.6f} (≤1%). The frozen "
             f"accounting flag is False ONLY because the 4 granite @262144 PASS-2 rows were cut by the budget.")
    if "error" not in live:
        L.append(f"  - LIVE re-measure of those 4 cells (fresh spawned processes, sealed _measure, repeats=1): "
                 f"{live['xrun_exact']}/4 exact struct fields vs PASS-1, worst peak/terminal jitter "
                 f"{live['xrun_worst_jitter']:.6f}; granite @262144 parity re-run 2/2 equal. Fills the gap descriptively; "
                 f"the frozen verdict is not changed.")
    L.append(f"- H2' drift vs stage A (Winnie, py3.12) — 12/12 within tolerance: "
             f"max |struct ratio drift| {max(x['ds'] for x in drift):.4f} (≤0.05), max |terminal drift| "
             f"{max(x['dt'] for x in drift):.4f} (≤0.10). Struct ratios replicate cross-host:")
    for x in drift:
        L.append(f"  - {x['stream']} {x['family']} @{x['cap']}: struct A {f4(x['struct_A'])} / B {f4(x['struct_B'])}; "
                 f"terminal A {f4(x['term_A'])} / B {f4(x['term_B'])}")
    L.append(f"- H5' ceiling 4/4: " + "; ".join(f"{x['stream']} {x['family']} x{f4(x['rceil'])} vs 4096 x{f4(x['r4096'])}"
                                              for x in ceil))
    L.append(f"- Ladder counterfactual (if the cut group had been present and matched): {counterfactual} — "
             f"i.e. memory gates would pass and the payoff would STILL be unmeasured (0/8 quiet groups).")
    L.append("\n## Timing — INFORMATIONAL ONLY (every group loaded; NOT a payoff claim)\n")
    for x in loaded:
        L.append(f"- {x['stream']} @{x['cap']} (load {x['la'][0]}→{x['la'][1]}): R3 x{f4(x['R3'])}, R2 x{f4(x['R2'])}")
    L.append(f"- loaded R3 range x{min(x['R3'] for x in loaded):.3f}–x{max(x['R3'] for x in loaded):.3f}, "
             f"median x{statistics.median(x['R3'] for x in loaded):.3f}; R2 median x{statistics.median(x['R2'] for x in loaded):.3f}. "
             f"Wall-clock perf_counter medians under loadavg 4–6 with many co-tenant agent sessions.")
    L.append("\n## Consequence (pre-registered branch + attribution)\n")
    L.append("- INCOMPLETE-BUDGET is not a payoff verdict. The memory side of the 3x-to-1x claim is now replicated "
             "cross-host and extended to the ceiling (descriptive, all gates would pass); the payoff (R3) is unmeasured "
             "for the second time (stage A: Winnie loadavg ~23; stage B: Mack loadavg 4–6).")
    L.append("- Root cause is the measurement design, not the host window: a loadavg quiet gate on a shared agent "
             "fleet host never opens. Next = exp723: timing-only completion with a contention-robust paired design "
             "(interleaved ABBA, process CPU time, A/A null control as a validity gate) — the PREREG's "
             "'quiet-window re-run of timing only' branch, with the gate redesigned so it can actually fire.")
    L.append("\n## Integrity\n")
    L.append(f"- ARTIFACT.sha256 (PREREG/runner/smoke/sealed_deps) matches on disk; PREREG/runner/sealed_deps byte-exact in freeze commit {FREEZE} (smoke.log was .gitignored there, its sha is in the committed ARTIFACT.sha256); "
             f"13/13 sealed deps unchanged and recorded in the result JSON; sealed artifacts untouched; nothing re-launched.")
    L.append("\n## Check list\n")
    for c in CHECKS:
        L.append(f"- [{'x' if c['ok'] else ' '}] {c['check']}" + (f" — {c['detail']}" if c["detail"] else ""))
    (D / "ADDENDUM61.md").write_text("\n".join(L) + "\n")
    (D / "exp718-adjudication.json").write_text(json.dumps(
        {"verdict": verdict, "checks_ok": n_ok, "checks_total": len(CHECKS), "checks": CHECKS,
         "drift": drift, "ceiling": ceil, "loaded_time_ratios": loaded, "live": {k: v for k, v in live.items() if k != "parity"},
         "counterfactual": counterfactual, "elapsed_s": round(time.time() - t0, 1)}, indent=1, default=str))
    print(f"verdict={verdict} checks {n_ok}/{len(CHECKS)} counterfactual={counterfactual} {time.time() - t0:.0f}s")
    for c in CHECKS:
        if not c["ok"]:
            print("FAIL", c)


if __name__ == "__main__":
    main()

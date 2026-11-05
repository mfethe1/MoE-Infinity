#!/usr/bin/env python3
"""exp718: shared-state N-way metadata economics at cap ceiling, quiet-host timing (exp675 stage B).

Frozen PREREG.md in this dir is the authority; this runner only executes it. Sealed stage-A machinery
(census_shared_costfit) is imported, never edited. Sealed dependency integrity is asserted at start
from sealed_deps.sha256 (mechanically generated with shasum -a 256; frozen into ARTIFACT.sha256).

Design (see PREREG): streams {qwen30b, granite} x caps {256,1024,4096,262144} x policies
{costfit, shared_costfit, costfit3, shared_costfit3}.
  PASS A (any load): sealed parity_smoke + 16 full-state parity pairs + census repeats=1 rows.
  PASS B (quiet-gated per (stream,cap) group): census repeats=5 rows (median ns/access) + byte
         cross-pass determinism.
Verdict ladder (first match): PARITY-FAIL, INCOMPLETE-BUDGET, ACCOUNTING-FAIL, ECONOMICS-DRIFT,
CEILING-DRIFT, ECONOMICS-TIME-UNMEASURED, PAYOFF-CONFIRMED (R3<=1.10), PAYOFF-MARGINAL (<=1.35),
PAYOFF-REJECTED.

Modes: default = full frozen run. SMOKE=1 = disclosed machinery smoke (never a result).
"""
import csv
import hashlib
import json
import multiprocessing
import os
import platform
import sys
import time
from pathlib import Path

D = Path(__file__).parent
HOME = Path.home()
REPO = HOME / "warp-work/moei-granite3b"          # sealed tree (data + package), NOT a git repo
RESEARCH = REPO / "benchmarks/cache_simulator/research"
sys.path.insert(0, str(REPO))

# ------------------------------------------------------------------ frozen design constants (PREREG)
CAPS = [256, 1024, 4096, 262144]
OVERLAP_CAPS = [256, 1024, 4096]
FAMILIES = [("costfit", "shared_costfit"), ("costfit3", "shared_costfit3")]
POLICIES = ["costfit", "costfit3", "shared_costfit", "shared_costfit3"]
STREAMS = {
    "qwen30b": REPO / "data/belady/stream_qwen30b.pt",
    "granite": REPO / "benchmarks/cache_simulator/data/handcrafted8-greedy512/belady/stream_granite3b.pt",
}
WALL_BUDGET_S = 6 * 3600
QUIET_START = 1.5          # loadavg(1) below this at group start
QUIET_END = 2.5            # and below this at group end -> group counts QUIET
QUIET_WAIT_S = 45 * 60
QUIET_POLL_S = 60
MIN_QUIET_GROUPS = 6       # of 8
REPEATS_MEM = 1
REPEATS_TIMED = 5
STRUCT_DRIFT = 0.05        # relative, vs stage-A anchor ratio
TERMINAL_DRIFT = 0.10      # relative (allocator-sensitive, disclosed)
PASS_JITTER = 0.01         # peak/terminal cross-pass relative tolerance
CEILING_MARGIN = 1.05      # struct_ratio(262144) <= margin * struct_ratio(4096), same run
PAYOFF_CONFIRMED = 1.10
PAYOFF_MARGINAL = 1.35
SMOKE_LIMIT = 150_000


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_sealed_deps():
    """label -> (abs path, expected sha256), parsed from the frozen sealed_deps.sha256."""
    deps = {}
    for line in (D / "sealed_deps.sha256").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sha, path = line.split()
        p = Path(path)
        if not p.is_absolute():
            p = REPO / path
        deps[p.name] = (p, sha)
    return deps


def assert_sealed(deps=None):
    deps = deps if deps is not None else load_sealed_deps()
    for label, (p, sha) in deps.items():
        got = sha256_file(p)
        if got != sha:
            raise RuntimeError(f"SEALED DRIFT {label}: {got} != {sha}")
    return deps


import benchmarks.cache_simulator.research.census_shared_costfit as CEN  # noqa: E402
from benchmarks.cache_simulator.policies import build_policy  # noqa: E402
from benchmarks.cache_simulator.research.run_policies_real import (  # noqa: E402
    geometry_kwargs,
    load_accesses,
)


# ------------------------------------------------------------------ helpers
def hb(t0, msg):
    print(f"[{time.time() - t0:7.0f}s] {msg}", flush=True)


def measure_cell(name, cap, stream_path, repeats, limit=0):
    """One sealed census cell in a fresh spawned process (stage-A code path, unmodified)."""
    ctx = multiprocessing.get_context("spawn")
    job = (name, cap, [str(stream_path)], 0, "skip", repeats, limit)
    with ctx.Pool(1) as pool:
        return pool.apply(CEN._measure, (job,))


def full_state(p):
    return (p.hits, p.misses, p.hit_rate, p.switches, getattr(p, "choice_switches", None),
            p.choice, p._mass, p._sw_mass, list(p.resident))


def parity_pair(acc, stats, base_name, shared_name, cap):
    kw_b = geometry_kwargs(base_name, stats)
    kw_s = geometry_kwargs(shared_name, stats)
    a = build_policy(base_name, cap, **kw_b)
    b = build_policy(shared_name, cap, **kw_s)
    CEN._replay(a, acc)
    CEN._replay(b, acc)
    ta, tb = full_state(a), full_state(b)
    fields = ("hits", "misses", "hit_rate", "switches", "choice_switches", "choice",
              "_mass", "_sw_mass", "resident_order")
    diff = [f for f, x, y in zip(fields, ta, tb) if x != y]
    return {"base": base_name, "shared": shared_name, "cap": cap, "equal": not diff,
            "diff_fields": diff, "hit_rate": ta[2], "resident_len": len(ta[8]),
            "detail": None if not diff else {f: [ta[i], tb[i]] for i, f in enumerate(fields)
                                             if f in diff and f != "resident_order"}}


def load_anchor(stream):
    """Stage-A per-cell rows -> ratios keyed (family_base, cap)."""
    path = RESEARCH / f"census_exp675-{stream}.csv"
    rows = {(r["policy"], int(r["capacity"])): r for r in csv.DictReader(path.open())}
    out = {}
    for base, shared in FAMILIES:
        for cap in OVERLAP_CAPS:
            b, s = rows[(base, cap)], rows[(shared, cap)]
            out[(base, cap)] = {
                "struct_ratio": int(s["struct_bytes"]) / int(b["struct_bytes"]),
                "terminal_ratio": int(s["terminal_bytes"]) / int(b["terminal_bytes"]),
                "tables_base": int(b["tables"]), "tables_shared": int(s["tables"]),
                "hit_equal": s["hit_rate"] == b["hit_rate"],
            }
    return out


def wait_quiet(t0):
    t0w = time.time()
    while os.getloadavg()[0] >= QUIET_START:
        if time.time() - t0w > QUIET_WAIT_S:
            return False, time.time() - t0w
        hb(t0, f"waiting for quiet (loadavg {os.getloadavg()[0]:.2f} >= {QUIET_START})")
        time.sleep(QUIET_POLL_S)
    return True, time.time() - t0w


def ladder(st):
    trace = []
    if not (st["parity_ok"] and st["parity_smoke_ok"] and st["hitrate_consistent"]):
        trace.append("rung1 PARITY-FAIL fired")
        return "PARITY-FAIL", trace
    trace.append("rung1 parity ok (16 full-state pairs + sealed smoke + census hit_rate consistency)")
    if st["budget_exceeded"] or st["cells_missing"]:
        trace.append("rung2 INCOMPLETE-BUDGET fired")
        return "INCOMPLETE-BUDGET", trace
    trace.append("rung2 all cells completed within budget")
    if not st["accounting_ok"]:
        trace.append("rung3 ACCOUNTING-FAIL fired")
        return "ACCOUNTING-FAIL", trace
    trace.append("rung3 accounting ok (tables 1/5/10; cross-pass exact struct fields)")
    if not st["drift_ok"]:
        trace.append("rung4 ECONOMICS-DRIFT fired")
        return "ECONOMICS-DRIFT", trace
    trace.append("rung4 stage-A ratios replicated within tolerance")
    if not st["ceiling_ok"]:
        trace.append("rung5 CEILING-DRIFT fired")
        return "CEILING-DRIFT", trace
    trace.append("rung5 ceiling ratios within 1.05x of this run's 4096 ratios")
    if st["quiet_groups"] < MIN_QUIET_GROUPS or st["R3"] is None:
        trace.append("rung6 ECONOMICS-TIME-UNMEASURED fired")
        return "ECONOMICS-TIME-UNMEASURED", trace
    trace.append(f"rung6 {st['quiet_groups']}/8 quiet groups (>= {MIN_QUIET_GROUPS})")
    if st["R3"] <= PAYOFF_CONFIRMED:
        trace.append(f"rung7 PAYOFF-CONFIRMED (R3 {st['R3']:.3f} <= {PAYOFF_CONFIRMED})")
        return "PAYOFF-CONFIRMED", trace
    if st["R3"] <= PAYOFF_MARGINAL:
        trace.append(f"rung8 PAYOFF-MARGINAL (R3 {st['R3']:.3f} <= {PAYOFF_MARGINAL})")
        return "PAYOFF-MARGINAL", trace
    trace.append(f"rung9 PAYOFF-REJECTED (R3 {st['R3']:.3f} > {PAYOFF_MARGINAL})")
    return "PAYOFF-REJECTED", trace


# ------------------------------------------------------------------ smoke (disclosed; never a result)
def smoke():
    t0 = time.time()
    ok = True
    deps = assert_sealed()
    print(f"SMOKE S0 sealed deps ok ({len(deps)} files)")
    # S7 drift bite first (pure function, no replay)
    mut = {k: (p, "0" * 64) for k, (p, _) in deps.items()}
    try:
        assert_sealed(mut)
        print("SMOKE S7 FAIL: mutated sha not caught"); ok = False
    except RuntimeError:
        print("SMOKE S7 ok: sealed-drift assertion bites")
    # S5 anchors
    anchors = {s: load_anchor(s) for s in STREAMS}
    s5 = all(len(a) == 6 for a in anchors.values()) and all(
        v["tables_base"] in (5, 10) and v["tables_shared"] == 1 and v["hit_equal"]
        and 0 < v["struct_ratio"] < 1 for a in anchors.values() for v in a.values())
    print(f"SMOKE S5 anchors parsed {sum(len(a) for a in anchors.values())} ratios ok {s5}")
    ok &= s5
    # S6 ladder self-test (hand-built states, boundary cases)
    base = dict(parity_ok=True, parity_smoke_ok=True, hitrate_consistent=True, budget_exceeded=False,
                cells_missing=False, accounting_ok=True, drift_ok=True, ceiling_ok=True,
                quiet_groups=8, R3=1.05, R2=1.0)
    v = lambda **kw: ladder({**base, **kw})[0]  # noqa: E731
    lad = [v(parity_ok=False, budget_exceeded=True) == "PARITY-FAIL",
           v(budget_exceeded=True) == "INCOMPLETE-BUDGET",
           v(cells_missing=True) == "INCOMPLETE-BUDGET",
           v(accounting_ok=False) == "ACCOUNTING-FAIL",
           v(drift_ok=False) == "ECONOMICS-DRIFT",
           v(ceiling_ok=False) == "CEILING-DRIFT",
           v(quiet_groups=5) == "ECONOMICS-TIME-UNMEASURED",
           v(R3=None) == "ECONOMICS-TIME-UNMEASURED",
           v(R3=1.10) == "PAYOFF-CONFIRMED",
           v(R3=1.1001) == "PAYOFF-MARGINAL",
           v(R3=1.35) == "PAYOFF-MARGINAL",
           v(R3=1.3501) == "PAYOFF-REJECTED"]
    print(f"SMOKE S6 ladder self-test {sum(lad)}/12 ok {all(lad)}")
    ok &= all(lad)
    # S1 sealed synthetic parity smoke (event sequences)
    s1 = CEN.parity_smoke()
    print(f"SMOKE S1 sealed parity_smoke {s1} [{time.time()-t0:.0f}s]")
    ok &= s1
    # S2/S3 census spawn cells at reduced limit (granite)
    g = STREAMS["granite"]
    r2 = measure_cell("costfit", 1024, g, 1, limit=SMOKE_LIMIT)
    s2 = (r2["tables"] == 5 and 0 < r2["hit_rate"] < 1 and r2["records"] == r2["slots"] > 0
          and r2["struct_bytes"] > 0 and r2["ns_per_access"] > 0 and r2["accesses"] == SMOKE_LIMIT)
    print(f"SMOKE S2 costfit cell well-formed {s2} {json.dumps({k: r2[k] for k in ('tables','records','hit_rate','ns_per_access')}, default=str)} [{time.time()-t0:.0f}s]")
    ok &= s2
    r3 = measure_cell("shared_costfit3", 1024, g, 1, limit=SMOKE_LIMIT)
    r3b = measure_cell("costfit3", 1024, g, 1, limit=SMOKE_LIMIT)
    s3 = (r3["tables"] == 1 and r3["records"] > 0 and r3["slots"] >= r3["records"]
          and r3b["tables"] == 10 and r3["struct_bytes"] < r3b["struct_bytes"]
          and r3["hit_rate"] == r3b["hit_rate"])
    print(f"SMOKE S3 shared_costfit3 tables=1 slots {r3['slots']} records {r3['records']} "
          f"struct {r3['struct_bytes']} < base {r3b['struct_bytes']} hit-equal {r3['hit_rate'] == r3b['hit_rate']} ok {s3} [{time.time()-t0:.0f}s]")
    ok &= s3
    # S4 real-stream parity pair at reduced limit
    acc, stats = load_accesses([str(g)], ignore_layers=0, prefill="skip")
    pr = parity_pair(acc[:SMOKE_LIMIT], stats, "costfit", "shared_costfit", 1024)
    s4 = pr["equal"]
    print(f"SMOKE S4 granite[:150k] costfit vs shared_costfit full-state parity {s4} "
          f"(hit {pr['hit_rate']:.6f}, diff {pr['diff_fields']}) [{time.time()-t0:.0f}s]")
    ok &= s4
    print("SMOKE_OK" if ok else "SMOKE_FAIL")
    return 0 if ok else 1


# ------------------------------------------------------------------ full run
def run():
    t0 = time.time()
    deps = assert_sealed()
    hb(t0, f"sealed deps ok ({len(deps)} files); host {platform.platform()} py {sys.version.split()[0]} "
           f"loadavg {os.getloadavg()}")
    import torch
    hb(t0, f"torch {torch.__version__}")

    budget_exceeded = False
    cells_missing = False
    out = {"experiment": "exp718", "date": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
           "host": {"platform": platform.platform(), "python": sys.version.split()[0],
                    "torch": torch.__version__, "loadavg_start": list(os.getloadavg())},
           "design": {"caps": CAPS, "policies": POLICIES, "streams": {k: str(v) for k, v in STREAMS.items()},
                      "quiet_start": QUIET_START, "quiet_end": QUIET_END, "repeats_timed": REPEATS_TIMED,
                      "wall_budget_s": WALL_BUDGET_S},
           "sealed_deps": {k: v[1] for k, v in deps.items()}}

    # streams loaded once in the parent for parity (children reload per sealed _measure)
    accs, statss = {}, {}
    for name, path in STREAMS.items():
        accs[name], statss[name] = load_accesses([str(path)], ignore_layers=0, prefill="skip")
        hb(t0, f"stream {name}: {len(accs[name])} accesses, stats {statss[name]}")

    # ---- PASS A.0: sealed synthetic parity smoke (event sequences)
    parity_smoke_ok = CEN.parity_smoke()
    hb(t0, f"sealed parity_smoke: {parity_smoke_ok}")

    # ---- PASS A.1: real-stream full-state parity pairs (16)
    parity = []
    for cap in CAPS:
        for sname in STREAMS:
            for base, shared in FAMILIES:
                if time.time() - t0 > WALL_BUDGET_S:
                    budget_exceeded = True
                    break
                pr = parity_pair(accs[sname], statss[sname], base, shared, cap)
                pr["stream"] = sname
                parity.append(pr)
                hb(t0, f"parity {sname} {base} vs {shared} @{cap}: equal={pr['equal']} "
                       f"hit={pr['hit_rate']:.6f} residents={pr['resident_len']}")
            if budget_exceeded:
                break
        if budget_exceeded:
            break
    parity_ok = len(parity) == 16 and all(p["equal"] for p in parity)
    if len(parity) != 16:
        cells_missing = True
    out["parity"] = parity

    # ---- PASS A.2: census PASS-1 (byte fields, repeats=1, any load)
    pass1, pass2 = {}, {}
    for cap in CAPS:
        for sname, spath in STREAMS.items():
            for pol in POLICIES:
                if time.time() - t0 > WALL_BUDGET_S:
                    budget_exceeded = True
                    break
                try:
                    row = measure_cell(pol, cap, spath, REPEATS_MEM)
                    row["loadavg"] = list(os.getloadavg())
                    pass1[(sname, cap, pol)] = row
                    hb(t0, f"pass1 {sname} {pol} @{cap}: hit={row['hit_rate']:.6f} tables={row['tables']} "
                           f"records={row['records']} struct={row['struct_bytes']} term={row['terminal_bytes']}")
                except Exception as e:  # spawn/measurement error -> honest missing cell
                    cells_missing = True
                    hb(t0, f"pass1 {sname} {pol} @{cap}: ERROR {type(e).__name__}: {e}")
            if budget_exceeded:
                break
        if budget_exceeded:
            break
    out["pass1"] = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in pass1.items()}

    # ---- PASS B: quiet-gated timed groups (repeats=5)
    groups = []
    for cap in CAPS:
        for sname, spath in STREAMS.items():
            if budget_exceeded or time.time() - t0 > WALL_BUDGET_S:
                budget_exceeded = True
                break
            quiet, waited = wait_quiet(t0)
            la_start = os.getloadavg()[0]
            rows, err = {}, None
            try:
                for pol in POLICIES:
                    rows[pol] = measure_cell(pol, cap, spath, REPEATS_TIMED)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                cells_missing = True
            la_end = os.getloadavg()[0]
            g = {"stream": sname, "cap": cap, "quiet_waited_s": round(waited),
                 "loadavg_start": round(la_start, 2), "loadavg_end": round(la_end, 2),
                 "quiet": bool(quiet and la_end < QUIET_END and err is None), "error": err,
                 "rows": rows}
            groups.append(g)
            hb(t0, f"passB {sname} @{cap}: quiet={g['quiet']} load {la_start:.2f}->{la_end:.2f} "
                   f"waited {waited:.0f}s" + (f" ERROR {err}" if err else ""))
    out["pass2_groups"] = groups
    for g in groups:
        for pol, row in g["rows"].items():
            pass2[(g["stream"], g["cap"], pol)] = row

    # ---- gate computations (raw rows only)
    # H1' hit-rate consistency: parity hit_rate == pass1 census hit_rate (base cells)
    hitrate_consistent = True
    for pr in parity:
        row = pass1.get((pr["stream"], pr["cap"], pr["base"]))
        if row is None or row["hit_rate"] != pr["hit_rate"]:
            hitrate_consistent = False
            hb(t0, f"hitrate mismatch {pr['stream']} {pr['base']} @{pr['cap']}")

    # H4' accounting
    accounting_ok = True
    for (sname, cap, pol), row in pass1.items():
        want_tables = {"costfit": 5, "costfit3": 10, "shared_costfit": 1, "shared_costfit3": 1}[pol]
        if row["tables"] != want_tables:
            accounting_ok = False
            hb(t0, f"tables wrong {sname} {pol} @{cap}: {row['tables']} != {want_tables}")
        r2row = pass2.get((sname, cap, pol))
        if r2row is None:
            accounting_ok = False
            hb(t0, f"pass2 missing {sname} {pol} @{cap}")
            continue
        for f in ("hit_rate", "tables", "records", "slots", "struct_bytes"):
            if row[f] != r2row[f]:
                accounting_ok = False
                hb(t0, f"cross-pass {f} differ {sname} {pol} @{cap}: {row[f]} != {r2row[f]}")
        for f in ("peak_bytes", "terminal_bytes"):
            if row[f] and abs(r2row[f] - row[f]) / row[f] > PASS_JITTER:
                accounting_ok = False
                hb(t0, f"cross-pass {f} jitter>1% {sname} {pol} @{cap}: {row[f]} -> {r2row[f]}")

    # ratios from pass1 (load-independent byte fields)
    ratios = {}
    for sname in STREAMS:
        for base, shared in FAMILIES:
            for cap in CAPS:
                b, s = pass1.get((sname, cap, base)), pass1.get((sname, cap, shared))
                if b and s:
                    ratios[f"{sname}|{base}|{cap}"] = {
                        "struct": s["struct_bytes"] / b["struct_bytes"],
                        "terminal": s["terminal_bytes"] / b["terminal_bytes"],
                        "peak": s["peak_bytes"] / b["peak_bytes"],
                        "records_base": b["records"], "records_shared": s["records"],
                        "slots_base": b["slots"], "slots_shared": s["slots"]}
    out["ratios"] = ratios

    # H2' drift vs stage-A anchors (overlap caps)
    anchors = {s: load_anchor(s) for s in STREAMS}
    out["anchors_stageA"] = {s: {f"{b}|{c}": v for (b, c), v in a.items()} for s, a in anchors.items()}
    drift_ok, drift_detail = True, []
    for sname in STREAMS:
        for base, _ in FAMILIES:
            for cap in OVERLAP_CAPS:
                key = f"{sname}|{base}|{cap}"
                r, a = ratios.get(key), anchors[sname][(base, cap)]
                if r is None:
                    drift_ok = False
                    drift_detail.append([key, "missing"])
                    continue
                ds = abs(r["struct"] / a["struct_ratio"] - 1)
                dt = abs(r["terminal"] / a["terminal_ratio"] - 1)
                if ds > STRUCT_DRIFT or dt > TERMINAL_DRIFT:
                    drift_ok = False
                    drift_detail.append([key, round(ds, 4), round(dt, 4)])
    out["drift_detail"] = drift_detail

    # H5' ceiling vs this run's 4096
    ceiling_ok, ceiling_detail = True, []
    for sname in STREAMS:
        for base, _ in FAMILIES:
            r4, rc = ratios.get(f"{sname}|{base}|4096"), ratios.get(f"{sname}|{base}|262144")
            if r4 is None or rc is None:
                ceiling_ok = False
                ceiling_detail.append([sname, base, "missing"])
            elif rc["struct"] > CEILING_MARGIN * r4["struct"]:
                ceiling_ok = False
                ceiling_detail.append([sname, base, round(r4["struct"], 4), round(rc["struct"], 4)])
    out["ceiling_detail"] = ceiling_detail

    # H3' payoff: worst quiet-group time ratio per family
    quiet_groups = sum(1 for g in groups if g["quiet"])
    R2 = R3 = None
    time_ratios = []
    for g in groups:
        if not g["quiet"] or "costfit3" not in g["rows"]:
            continue
        r3 = g["rows"]["shared_costfit3"]["ns_per_access"] / g["rows"]["costfit3"]["ns_per_access"]
        r2 = g["rows"]["shared_costfit"]["ns_per_access"] / g["rows"]["costfit"]["ns_per_access"]
        time_ratios.append({"stream": g["stream"], "cap": g["cap"], "R3": round(r3, 4), "R2": round(r2, 4)})
        R3 = r3 if R3 is None else max(R3, r3)
        R2 = r2 if R2 is None else max(R2, r2)
    out["time_ratios_quiet"] = time_ratios
    out["quiet_groups"] = quiet_groups
    out["R2"] = None if R2 is None else round(R2, 4)
    out["R3"] = None if R3 is None else round(R3, 4)

    state = {"parity_ok": parity_ok, "parity_smoke_ok": parity_smoke_ok,
             "hitrate_consistent": hitrate_consistent, "budget_exceeded": budget_exceeded,
             "cells_missing": cells_missing, "accounting_ok": accounting_ok, "drift_ok": drift_ok,
             "ceiling_ok": ceiling_ok, "quiet_groups": quiet_groups, "R3": R3, "R2": R2}
    verdict, trace = ladder(state)
    out["state"] = state
    out["ladder_trace"] = trace
    out["verdict"] = verdict
    out["elapsed_s"] = round(time.time() - t0, 1)
    (D / "exp718-econ.json").write_text(json.dumps(out, indent=1, default=str))
    hb(t0, f"wrote exp718-econ.json")
    print("settled verdict=" + verdict, flush=True)


if __name__ == "__main__":
    if os.environ.get("SMOKE") == "1":
        sys.exit(smoke())
    run()

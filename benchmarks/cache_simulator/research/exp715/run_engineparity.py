"""exp715: shipped engine eviction-policy port vs simulator on 3 independent real traces.

Upstream EfficientMoE/MoE-Infinity merged C++ ports of the cache-simulator policies
(#339, core/prefetch/eviction_policy.cpp) and made LCNU the default (#341). Upstream
checked parity on fuzzed traces and 200k accesses of ONE Qwen3-30B decode trace.
This run checks the pinned upstream port on our three full real decode streams
(granite-3b: a model family upstream never traced; qwen30b hi/lo) at the sealed
exp704 capacity grids, for all 13 shipped policies. PREREG.md is binding.
Run modes: SMOKE=1 (reduced) | default (full).
"""
import json, os, statistics, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
from common import ALPHA, BETA, POLICIES, TRACES, cpp_hits, load_keys, py_hits, trace_text  # noqa: E402

SMOKE = os.environ.get("SMOKE") == "1"
SEALED = Path.home() / "warp-work/exp704-moei-capacitymap/exp704-capacitymap.json"
P2_TOL = 1e-12
P3_WITHIN_PP = 0.5
P3_MIN_FRAC = 0.90
P4_MAX_NS = 1000.0
REPS = 3


def build():
    for out, drv in (("driver", "src/eviction_policy_driver.cpp"), ("timing", "src/timing_driver.cpp")):
        subprocess.run(["clang++", "-std=c++17", "-O2", "-Isrc", "src/prefetch/eviction_policy.cpp",
                        drv, "-o", out], cwd=D, check=True)


def trace_job(tag):
    cfg = TRACES[tag]
    t0 = time.time()
    keys = load_keys(tag)
    caps = cfg["caps"]
    if SMOKE:
        keys, caps = keys[:60000], [cfg["det"]]
    n = len(keys)
    txt = trace_text(keys)
    qs = [(p, c, cfg["nl"], ALPHA, BETA, cfg["prior"]) for c in caps for p in POLICIES]
    run1, dt1 = cpp_hits(txt, qs)
    run2, _ = cpp_hits(txt, qs)
    cells = {}
    for (p, c, *_), h1, h2 in zip(qs, run1, run2):
        hp = py_hits(p, c, keys, cfg["nl"], cfg["prior"])
        cells.setdefault(str(c), {})[p] = {"cpp": h1, "cpp_rep": h2, "py": hp, "rate": h1 / n}
    # timing: own driver, det cap and max cap, REPS reps
    tq = [(p, c, cfg["nl"], ALPHA, BETA, cfg["prior"]) for c in sorted({cfg["det"], caps[-1]}) for p in POLICIES]
    lines = "\n".join([txt, str(len(tq))] + [f"{a} {b} {c} {d!r} {e!r} {f!r}" for a, b, c, d, e, f in tq]) + "\n"
    ns = {}
    for _ in range(REPS):
        out = subprocess.run([str(D / "timing")], input=lines, capture_output=True, text=True, check=True).stdout.split("\n")
        for (p, c, *_), row in zip(tq, out):
            h, v = row.split()
            assert int(h) == cells[str(c)][p]["cpp"], ("timing driver hit mismatch", p, c)
            ns.setdefault(f"{c}", {}).setdefault(p, []).append(float(v))
    timing = {c: {p: statistics.median(v) for p, v in d.items()} for c, d in ns.items()}
    return tag, {"N": n, "caps": caps, "cells": cells, "ns_per_access_median": timing,
                 "ns_raw": ns, "cpp_grid_s": dt1, "elapsed_s": time.time() - t0}


def adjudicate(res):
    sealed = json.loads(SEALED.read_text())["traces"]
    p1_fail, p2_fail, p2_n, p3 = [], [], 0, []
    det_ok = True
    for tag, r in res.items():
        for c, row in r["cells"].items():
            for p, v in row.items():
                det_ok &= v["cpp"] == v["cpp_rep"]
                if v["cpp"] != v["py"]:
                    p1_fail.append((tag, c, p, v["cpp"], v["py"]))
            if not SMOKE:
                ref = sealed[tag]["policy_grid"][c]["lcnu"]["whole"]
                p2_n += 1
                if abs(row["lcnu"]["rate"] - ref) > P2_TOL:
                    p2_fail.append((tag, c, row["lcnu"]["rate"], ref))
            rates = {p: v["rate"] for p, v in row.items()}
            best = max(rates, key=rates.get)
            gap = 100 * (rates[best] - rates["lcnu"])
            ranked = sorted(rates, key=rates.get, reverse=True)
            p3.append({"trace": tag, "cap": int(c), "best": best, "best_rate": rates[best],
                       "lcnu_rate": rates["lcnu"], "lcnu_gap_pp": gap,
                       "lcnu_rank": ranked.index("lcnu") + 1,
                       "spread_pp": 100 * (rates[best] - min(rates.values())),
                       "runner_up": ranked[1] if ranked[0] == "lcnu" else ranked[0],
                       "lcnu_lead_pp": 100 * (rates["lcnu"] - rates[ranked[1]]) if ranked[0] == "lcnu" else -gap})
    within = sum(1 for x in p3 if x["lcnu_gap_pp"] <= P3_WITHIN_PP)
    frac = within / len(p3)
    lcnu_ns = {tag: max(r["ns_per_access_median"][c]["lcnu"] for c in r["ns_per_access_median"]) for tag, r in res.items()}
    P1 = not p1_fail
    P2 = (not p2_fail) if not SMOKE else None
    P3 = frac >= P3_MIN_FRAC
    P4 = all(v <= P4_MAX_NS for v in lcnu_ns.values())
    if not (P1 and det_ok) or P2 is False:
        verdict = "PARITY-BREAK"
    else:
        verdict = "PARITY-HOLDS:" + ("DEFAULT-CONFIRMED" if P3 else "DEFAULT-CHALLENGED")
    verdict += "|" + ("OVERHEAD-OK" if P4 else "OVERHEAD-HIGH")
    return {"verdict": verdict, "P1_exact": P1, "P1_fail": p1_fail, "det_cpp": det_ok,
            "P2_sealed": P2, "P2_cells": p2_n, "P2_fail": p2_fail,
            "P3_within_frac": frac, "P3_within_n": within, "P3_cells": len(p3), "P3_pass": P3,
            "P3_table": p3, "P4_lcnu_worst_ns": lcnu_ns, "P4_pass": P4,
            "n_cells_total": sum(len(r["cells"]) * len(POLICIES) for r in res.values())}


def main():
    t0 = time.time()
    build()
    with ProcessPoolExecutor(max_workers=3) as ex:
        res = dict(ex.map(trace_job, list(TRACES)))
    adj = adjudicate(res)
    out = {"exp": "exp715-engineparity", "smoke": SMOKE,
           "upstream_sha": (D / "UPSTREAM_SHA").read_text().strip(),
           "loadavg": os.getloadavg(), "traces": res, "adjudication": adj,
           "total_elapsed_s": time.time() - t0}
    name = "smoke.json" if SMOKE else "exp715-engineparity.json"
    (D / name).write_text(json.dumps(out, indent=1, default=str))
    print("VERDICT", adj["verdict"], "| P1", adj["P1_exact"], "det", adj["det_cpp"], "| P2", adj["P2_sealed"],
          adj["P2_cells"], "| P3", f'{adj["P3_within_n"]}/{adj["P3_cells"]}', "| P4", adj["P4_lcnu_worst_ns"],
          f"| {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

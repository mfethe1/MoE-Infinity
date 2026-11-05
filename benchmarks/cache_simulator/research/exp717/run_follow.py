"""exp717: realizable LCNU/S3-FIFO arbiter (FOLLOW) vs optimistic CostFit vs static rules.

SMOKE=1: first 65536 accesses of each trace, 2 caps, no adjudication bars.
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
from common import TRACES, load_keys  # noqa: E402  (also inserts ref/ on sys.path)
from follow import FollowPolicy  # noqa: E402

SMOKE = os.environ.get("SMOKE") == "1"
E715 = json.loads((Path.home() / "warp-work/exp715-moei-engineparity/exp715-engineparity.json").read_text())
WS20_SEALED = {"granite": 1228, "hi": 3396, "lo": 4662}  # exp707 ledger
CHECK_EVERY = 65536


def run_cell(args):
    tag, cap, n = args
    keys = load_keys(tag)[:n]
    cfg = TRACES[tag]
    p = FollowPolicy(cap, num_layers=cfg["nl"], prior=cfg["prior"])
    t0 = time.perf_counter()
    for i, k in enumerate(keys):
        p.on_access(k)
        if (i + 1) % CHECK_EVERY == 0:
            p.check()
    p.check()
    inn = p.cf._inners
    return {"tag": tag, "cap": cap, "N": len(keys), "follow": p.hits, "costfit": p.cf.hits,
            "ghost_lcnu": inn["lcnu"].hits, "ghost_s3fifo": inn["s3fifo"].hits,
            "switches": p.cf.switches, "final_choice": p.cf.choice, "fallbacks": p.fallbacks,
            "mean_D": p.d_mass / len(keys), "elapsed_s": time.perf_counter() - t0}


def ws_stats(tag):
    keys = load_keys(tag)
    tail = keys[int(0.8 * len(keys)):]
    return {"distinct": len(set(keys)), "ws20": len(set(tail))}


def main():
    jobs = []
    for tag, cfg in TRACES.items():
        caps = cfg["caps"][:1] + cfg["caps"][-1:] if SMOKE else cfg["caps"]
        n = 65536 if SMOKE else cfg["N"]
        jobs += [(tag, c, n) for c in caps]
    jobs.sort(key=lambda j: -j[2] * (2 if j[0] != "granite" else 1))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(os.environ.get("WORKERS", "6"))) as ex:
        cells = list(ex.map(run_cell, jobs))
    out = {"exp": "exp717", "smoke": SMOKE, "cells": cells, "loadavg": os.getloadavg(),
           "total_elapsed_s": time.time() - t0}
    if not SMOKE:
        out["ws"] = {t: ws_stats(t) for t in TRACES}
        out["rerun"] = [run_cell((t, TRACES[t]["caps"][4], TRACES[t]["N"])) for t in TRACES]
    name = "smoke.json" if SMOKE else "exp717-follow.json"
    (D / name).write_text(json.dumps(out, indent=1))
    for c in cells:
        print(c["tag"], c["cap"], "follow", c["follow"], "cf", c["costfit"], "gL", c["ghost_lcnu"],
              "gS", c["ghost_s3fifo"], "sw", c["switches"], "fb", c["fallbacks"],
              f"D={c['mean_D']:.1f}", f"{c['elapsed_s']:.0f}s")
    print("total", round(out["total_elapsed_s"]), "s")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""exp750 PREREG Amendment A1 sensitivity analysis (owner, result time). NOT a gate; never edits the sealed verdict.

OWN-GPU-ANOMALY: a cell of record (eff) whose peak memory on any ASSIGNED GPU exceeds the median, over the arm's
effective cells, of that GPU's peak by > 2048 MiB. D1-D3 are recomputed with such cells dropped (-> INCOMPLETE if a
block is lost). If a decision changes, print SENSITIVE(<D>).

usage: sens750_a1.py OUT REFJSON [--cells CELLS.json] [--anomaly-only]
--anomaly-only skips the D recomputation (for replaying the rule on exp749 raw, whose cells lack exp750 timing).
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classify750 as C  # noqa: E402

SLACK = 2048


def peaks(samples, cid, gpus):
    ss = samples.get(cid) or []
    out = {}
    for g in gpus:
        vals = [mem[g] for mem, _ in ss if g in mem]
        out[g] = max(vals) if vals else None
    return out


def anomalies(got, samples):
    """{cid_of_record: [(gpu, peak, median)]} for OWN-GPU-ANOMALY eff cells; plus per-arm table."""
    by_arm = {}
    for cid, g in got.items():
        e = g["eff"]
        if not e["present"]:
            continue
        gpus = [int(x) for x in str(g["def"]["gpus"]).split(",")]
        by_arm.setdefault(g["def"]["arm"], []).append((e["id"], g["def"]["block"], gpus, peaks(samples, e["id"], gpus)))
    flagged, table = {}, {}
    for arm, rows in by_arm.items():
        gpus = rows[0][2]
        med = {}
        for gpu in gpus:
            vals = [p[gpu] for _, _, _, p in rows if p.get(gpu) is not None]
            med[gpu] = statistics.median(vals) if vals else None
        table[arm] = (rows, med)
        for rid, _, _, p in rows:
            for gpu in gpus:
                if p.get(gpu) is not None and med[gpu] is not None and p[gpu] > med[gpu] + SLACK:
                    flagged.setdefault(rid, []).append((gpu, p[gpu], med[gpu]))
    return flagged, table


def main(argv):
    out = Path(argv[1])
    ref = C.rows_key(json.load(open(argv[2]))) if len(argv) > 2 and not argv[2].startswith("--") else None
    cells_p = argv[argv.index("--cells") + 1] if "--cells" in argv else None
    cells = json.load(open(cells_p)) if cells_p else C.find_cells(out)
    anomaly_only = "--anomaly-only" in argv
    got, mon_bad, _ = C.gather(out, cells, ref)
    samples, _ = C.read_monitor(out)
    flagged, table = anomalies(got, samples)
    for arm in sorted(table):
        rows, med = table[arm]
        print(f"arm {arm}: median assigned-GPU peak {med}")
        for rid, b, _, p in sorted(rows, key=lambda r: r[1]):
            print(f"  {rid} block={b} peaks={p}" + (f" OWN-GPU-ANOMALY {flagged[rid]}" if rid in flagged else ""))
    print(f"OWN-GPU-ANOMALY cells: {sorted(flagged)}")
    if anomaly_only:
        return 0
    gm, _ = C.manip(out, cells)
    qfail = C.quality_fail_arms(got, ref)
    full, drop = {}, {}
    for g in got.values():
        e = g["eff"]
        if e["clean"]:
            full[(e["arm"], e["block"])] = e["D"]
            if e["id"] not in flagged:
                drop[(e["arm"], e["block"])] = e["D"]
    res = []
    for name, fn, n, d in (("D1", C.decide_d1, "K2", "P2"), ("D2", C.decide_d2, "S1", "R1"),
                           ("D3", C.decide_d3, "S1", "P2")):
        a, ra = C.decision(fn, n, d, full, qfail, gm)
        b, rb = C.decision(fn, n, d, drop, qfail, gm)
        if ref is None:
            a = b = "INCOMPLETE"
        print(f"{name}: sealed-recompute={a} {ra} | A1-dropped={b} {rb}")
        if a != b:
            res.append(f"SENSITIVE({name})")
    print("A1 RESULT: " + (" ".join(res) if res else "NOT-SENSITIVE"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

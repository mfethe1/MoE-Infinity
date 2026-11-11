#!/usr/bin/env python3
"""exp783 analyzer: FP8 (uniform_fp8 + fp8 store) vs BF16 (legacy + bf16 store) decode A/B.
Usage: python3 analyze783.py <root>   (root contains out/B1.json ... out/F2.json, *.util.csv)
Verdict rc: 1 MAJOR-POS (delta>=+0.50) | 2 MILD-POS (>=+0.10) | 3 NO-MOVE | 5 FP8-NONDET |
9 DATA-FAIL. Numbers only from frozen artifacts under <root>.
"""
import json, math, os, sys

def load_cell(root, cid):
    p = os.path.join(root, "out", cid + ".json")
    if not os.path.exists(p):
        return None, f"missing {cid}.json"
    with open(p) as f:
        return json.load(f), None

def cell_stats(d):
    rows = d["rows"]
    tps = [r["decode_tok_s"] for r in rows]
    mean = sum(tps) / len(tps)
    shas = [r["out_sha"] for r in rows]
    return len(rows), mean, shas

def util_mean(root, cid, cap=10**9):
    p = os.path.join(root, "out", cid + ".util.csv")
    if not os.path.exists(p):
        return None
    vals = []
    with open(p) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 2:
                try:
                    vals.append(float(parts[1]))
                except ValueError:
                    pass
    vals = vals[:cap]
    return (sum(vals) / len(vals)) if vals else None

def main(root):
    cells = {"B1": ("B", "legacy"), "B2": ("B", "legacy"), "F1": ("F", "uniform_fp8"), "F2": ("F", "uniform_fp8")}
    per, problems = {}, []
    N_EXPECT = None
    for cid, (arm, want_mode) in cells.items():
        d, err = load_cell(root, cid)
        if err:
            problems.append(err)
            continue
        res = d.get("res", d)
        mode = res.get("resident_mode")
        offload = str(res.get("offload", ""))
        n, mean, shas = cell_stats(d)
        if mode != want_mode:
            problems.append(f"{cid}: resident_mode={mode!r} expected {want_mode!r}")
        is_fp8_store = "fp8" in os.path.basename(offload.rstrip("/"))
        if arm == "F" and not is_fp8_store:
            problems.append(f"{cid}: offload={offload!r} expected fp8 store")
        if arm == "B" and is_fp8_store:
            problems.append(f"{cid}: offload={offload!r} expected bf16 store")
        if n < 2:
            problems.append(f"{cid}: only {n} rows")
        per[cid] = {"arm": arm, "n": n, "mean_tok_s": mean, "shas": shas,
                    "mode": mode, "offload": offload, "load_s": res.get("load_s"),
                    "util_mean": util_mean(root, cid)}
        N_EXPECT = n if N_EXPECT is None else N_EXPECT
    det_b = det_f = None
    if "B1" in per and "B2" in per:
        det_b = per["B1"]["shas"] == per["B2"]["shas"]
        if not det_b:
            problems.append("B arm nondeterministic (B1 != B2 out_sha sequence)")
    if "F1" in per and "F2" in per:
        det_f = per["F1"]["shas"] == per["F2"]["shas"]
    if problems:
        rc = 9
        summary = {"rc": rc, "problems": problems, "cells": per}
    else:
        b_mean = (per["B1"]["mean_tok_s"] + per["B2"]["mean_tok_s"]) / 2
        f_mean = (per["F1"]["mean_tok_s"] + per["F2"]["mean_tok_s"]) / 2
        delta = f_mean / b_mean - 1
        if not det_f:
            rc = 5
        elif delta >= 0.50:
            rc = 1
        elif delta >= 0.10:
            rc = 2
        else:
            rc = 3
        summary = {"rc": rc, "b_mean_tok_s": b_mean, "f_mean_tok_s": f_mean,
                   "delta": delta, "det_b": det_b, "det_f": det_f, "cells": per}
    out = os.path.join(root, "out", "verdict.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))
    print("VERDICT rc=%d" % summary["rc"])
    return summary

if __name__ == "__main__":
    main(sys.argv[1])

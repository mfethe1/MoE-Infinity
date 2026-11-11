#!/usr/bin/env python3
"""exp784 analyzer: FP8 vs BF16 decode A/B across device_memory_ratio {0.25, 0.50}, 2 reps/config.
Usage: python3 analyze784.py <root>   (root contains out/<ID>.json for 8 cells, *.util.csv)
Verdict rc: 1 MAJOR-POS (max delta>=+0.50) | 2 MILD-POS (>=+0.10) | 3 NO-MOVE | 5 FP8-NONDET |
9 DATA-FAIL. Numbers only from frozen artifacts under <root>.
"""
import json, os, sys

CELLS = {"B25a": ("B", 0.25), "B25b": ("B", 0.25), "F25a": ("F", 0.25), "F25b": ("F", 0.25),
         "B50a": ("B", 0.50), "B50b": ("B", 0.50), "F50a": ("F", 0.50), "F50b": ("F", 0.50)}

def util_mean(root, cid):
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
    return (sum(vals) / len(vals)) if vals else None

def main(root):
    per, problems = {}, []
    for cid, (arm, ratio) in CELLS.items():
        p = os.path.join(root, "out", cid + ".json")
        if not os.path.exists(p):
            problems.append(f"missing {cid}.json")
            continue
        with open(p) as f:
            d = json.load(f)
        res = d.get("res", d)
        rows = d["rows"]
        mode, offload = res.get("resident_mode"), str(res.get("offload", ""))
        want_mode = "uniform_fp8" if arm == "F" else "legacy"
        if mode != want_mode:
            problems.append(f"{cid}: resident_mode={mode!r} expected {want_mode!r}")
        is_fp8 = "fp8" in os.path.basename(offload.rstrip("/"))
        if (arm == "F") != is_fp8:
            problems.append(f"{cid}: offload={offload!r} inconsistent with arm {arm}")
        if abs(float(res.get("ratio", -1)) - ratio) > 1e-9:
            problems.append(f"{cid}: res.ratio={res.get('ratio')} expected {ratio}")
        if len(rows) < 2:
            problems.append(f"{cid}: only {len(rows)} rows")
        sd = {}
        for r in rows:
            for k, v in r.get("stats_delta", {}).items():
                sd[k] = sd.get(k, 0) + v
        h, m = sd.get("policy_routed_hits", 0), sd.get("policy_routed_misses", 0)
        per[cid] = {"arm": arm, "ratio": ratio, "n": len(rows), "mode": mode, "offload": offload,
                    "mean_tok_s": sum(r["decode_tok_s"] for r in rows) / len(rows),
                    "shas": [r["out_sha"] for r in rows], "hits": h, "misses": m,
                    "missrate": m / max(h + m, 1), "util_mean": util_mean(root, cid)}
    # determinism within each (arm, ratio) config across reps
    det = {}
    for arm in "BF":
        for ratio in (0.25, 0.50):
            a = f"{arm}{int(ratio*100)}a"; b = f"{arm}{int(ratio*100)}b"
            if a in per and b in per:
                det[f"{arm}{int(ratio*100)}"] = per[a]["shas"] == per[b]["shas"]
    for k, v in det.items():
        if not v and k.startswith("B"):
            problems.append(f"{k} config nondeterministic (a != b out_sha sequence)")
    if problems:
        rc = 9
        summary = {"rc": rc, "problems": problems, "cells": per}
    else:
        configs = {}
        for arm in "BF":
            for ratio in (0.25, 0.50):
                a, b = f"{arm}{int(ratio*100)}a", f"{arm}{int(ratio*100)}b"
                cells = [per[a], per[b]]
                configs[f"{arm}{int(ratio*100)}"] = {
                    "mean_tok_s": sum(c["mean_tok_s"] for c in cells) / 2,
                    "misses": sum(c["misses"] for c in cells),
                    "hits": sum(c["hits"] for c in cells),
                    "missrate": sum(c["misses"] for c in cells) /
                                max(sum(c["misses"] for c in cells) + sum(c["hits"] for c in cells), 1)}
        deltas = {}
        for ratio in (0.25, 0.50):
            k = int(ratio * 100)
            deltas[f"d{k}"] = configs[f"F{k}"]["mean_tok_s"] / configs[f"B{k}"]["mean_tok_s"] - 1
        maxd = max(deltas.values())
        fp8_det = all(det.get(f"F{k}", False) for k in (25, 50))
        if not fp8_det:
            rc = 5
        elif maxd >= 0.50:
            rc = 1
        elif maxd >= 0.10:
            rc = 2
        else:
            rc = 3
        summary = {"rc": rc, "deltas": deltas, "max_delta": maxd, "det": det,
                   "configs": configs, "cells": per}
    with open(os.path.join(root, "out", "verdict.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))
    print("VERDICT rc=%d" % summary["rc"])
    return summary

if __name__ == "__main__":
    main(sys.argv[1])

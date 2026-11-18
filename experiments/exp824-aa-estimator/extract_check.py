#!/usr/bin/env python3
"""Recompute exp824 agreement metrics from the sealed artifact. 2026-11-18."""
import tarfile, json, sys
t = tarfile.open(sys.argv[1])
def tok_agree(a, b):
    per_p = []
    for pa, pb in zip(a, b):
        assert len(pa) == len(pb)
        per_p.append(sum(x == y for x, y in zip(pa, pb)) / len(pa))
    return sum(per_p) / len(per_p)
for i in range(1, 7):
    bj = json.load(t.extractfile(f"exp824/p14-B{i}.json"))
    meas = [blk for blk in bj["blocks"] if "arm" in blk]
    ref = meas[0]["toks"]
    blocks = [tok_agree(m["toks"], ref) for m in meas]
    g12 = sum(blocks) / len(blocks)
    g1 = (g12 * len(blocks) - 1) / (len(blocks) - 1)
    pairs = {}
    for m in meas:
        pairs.setdefault(m["pair"], {})[m["arm"]] = m["toks"]
    within = [tok_agree(v["A1"], v["A2"]) for v in pairs.values()]
    print(json.dumps({"B": i, "g1_frozen_convention": round(g1, 4),
                      "pair_mean": round(sum(within)/len(within), 4),
                      "pair_min": round(min(within), 4), "pair_max": round(max(within), 4)}))

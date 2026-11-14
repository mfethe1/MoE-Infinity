#!/usr/bin/env python3
"""verify821.py — independent re-derivation of exp821 from raw per-arm artifacts.
Own code paths (not a copy of the extractor). Completeness gate enumerates any
missing arm explicitly. EXP821_DIR overrides the artifact dir (portability).
--check-extractor additionally compares against extract821.json field by field.
"""
import json, os, sys

D = os.environ.get("EXP821_DIR", "/home/mfeth/exp821")
CONDS = ["L35", "L50", "L65", "S35", "S50", "S65"]
REPS = (1, 2, 3)

# completeness gate: refuse partial data, enumerate what is missing
missing = [f"p11-{c}_R{r}.json" for c in CONDS for r in REPS
           if not os.path.exists(f"{D}/p11-{c}_R{r}.json")]
if missing:
    print("MISSING ARMS:", *missing, sep="\n  ")
    sys.exit(2)

raw = {c: [json.load(open(f"{D}/p11-{c}_R{r}.json")) for r in REPS] for c in CONDS}
walls = {c: sorted(x["wall_ms_per_tok"] for x in v) for c, v in raw.items()}
mins = {c: w[0] for c, w in walls.items()}
pen = {p: round(mins[f"{tag}65"] - mins[f"{tag}50"], 1)
       for p, tag in (("lcnu", "L"), ("s3fifo", "S"))}
deltas = {r: round(mins[f"S{r}"] - mins[f"L{r}"], 1) for r in ("35", "50", "65")}

def agree(a, b):
    tot = hit = 0
    for ta, tb in zip(a, b):
        for x, y in zip(ta, tb):
            hit += (x == y); tot += 1
    return hit / tot

toks = {c: [x["toks_full"] for x in v] for c, v in raw.items()}
floor = sum(agree(toks["L50"][i], toks["L50"][j]) for i, j in ((0, 1), (0, 2), (1, 2))) / 3
s1 = {f"S{r}": sum(agree(toks[f"S{r}"][i], toks[f"L{r}"][j])
      for i in range(3) for j in range(3)) / 9 for r in ("35", "50", "65")}

# publication arithmetic (verbatim-paste source): both percentage directions per pair
pct = {}
for a, b in (("L65", "L50"), ("S65", "S50"), ("L50", "L35"), ("S50", "S35")):
    pct[f"{a}_vs_{b}"] = {
        f"{a} pct faster than {b}": round((mins[b] - mins[a]) / mins[b] * 100, 1),
        f"{b} pct slower than {a}": round((mins[b] - mins[a]) / mins[a] * 100, 1)}

res = {
    "mins_ms_per_tok": mins, "walls_sorted": walls,
    "penalty_65_over_50": pen, "delta_s3fifo_vs_lcnu": deltas,
    "s1_agreement_s_vs_l": {k: round(v, 4) for k, v in s1.items()},
    "s1_floor_l50_vs_l50": round(floor, 4),
    "G1_flat_under_s3fifo": pen["s3fifo"] <= 2,
    "G2_penalty_shrinks": pen["s3fifo"] <= pen["lcnu"] - 5,
    "S1_output_preserving": all(v >= floor - 0.005 for v in s1.values()),
    "S2_min_replicated_10pct": all(w[1] <= w[0] * 1.10 for w in walls.values()),
    "s2_fail_conds": [c for c, w in walls.items() if w[1] > w[0] * 1.10],
    "pct_directions": pct,
}
print(json.dumps(res, indent=1))

if "--check-extractor" in sys.argv:
    ex = json.load(open(f"{D}/extract821.json"))
    ok = all(ex[k] == res[k] for k in ("mins_ms_per_tok", "penalty_65_over_50",
             "delta_s3fifo_vs_lcnu", "s1_floor_l50_vs_l50",
             "G1_flat_under_s3fifo", "G2_penalty_shrinks",
             "S1_output_preserving", "S2_min_replicated_10pct"))
    ok &= all(abs(ex["s1_agreement_s_vs_l"][k] - res["s1_agreement_s_vs_l"][k]) < 5e-5
              for k in res["s1_agreement_s_vs_l"])
    print(f"cross_check_vs_extractor: {ok}")
    sys.exit(0 if ok else 1)

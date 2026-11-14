#!/usr/bin/env python3
"""verify820.py — independent re-derivation of every exp820 number from raw per-arm artifacts.
Portable: EXP820_DIR env overrides the default /home/mfeth/exp820.
Extracted-seal layout: seal dir contains p10-*.json flat."""
import json, os, sys

D = os.environ.get("EXP820_DIR", "/home/mfeth/exp820")
pols = ["LCNU", "ARC", "LIRS", "S3FIFO", "W_TINYLFU"]
rep_pairs = ((0, 1), (0, 2), (1, 2))

# completeness gate
missing = [f"p10-{p}_R{rep}" for p in pols for rep in (1, 2, 3) if not os.path.exists(f"{D}/p10-{p}_R{rep}.json")]
if missing:
    print("MISSING ARMS (refusing to adjudicate):", missing)
    sys.exit(1)

cond = {p: [json.load(open(f"{D}/p10-{p}_R{rep}.json")) for rep in (1, 2, 3)] for p in pols}
walls = {p: sorted(x["wall_ms_per_tok"] for x in v) for p, v in cond.items()}
mins = {p: v[0] for p, v in walls.items()}
best = min((v, p) for p, v in mins.items() if p != "LCNU")[1]

# agreement: independent implementation (enumerate flattened positions via zip-chaining)
def agree(a, b):
    pairs = [(x, y) for ta, tb in zip(a, b) for x, y in zip(ta, tb)]
    return sum(1 for x, y in pairs if x == y) / len(pairs)

lc = [x["toks_full"] for x in cond["LCNU"]]
floor = sum(agree(lc[i], lc[j]) for i, j in rep_pairs) / 3
s1 = {p: sum(agree([x["toks_full"] for x in cond[p]][i], lc[j]) for i in range(3) for j in range(3)) / 9
      for p in pols if p != "LCNU"}
g1 = (mins["LCNU"] - mins[best]) >= 5
g2 = mins[best] <= 79.9 * 1.02
s1g = all(v >= floor - 0.005 for v in s1.values())
s2 = all(v[1] <= v[0] * 1.10 for v in walls.values())

# direction discipline: both denominators vs lcnu at same ratio (within battery)
d = {p: {"pct_faster_than_lcnu": round((mins["LCNU"] - m) / mins["LCNU"] * 100, 1),
         "lcnu_pct_slower_than_p": round((mins["LCNU"] - m) / m * 100, 1)} for p, m in mins.items() if p != "LCNU"}
# cross-battery context: same condition (lcnu @ 0.65) in exp819 was 89.9 ms/tok (seal 0bcd983b)
cross = {"exp819_lcnu_065_min": 89.9, "exp820_lcnu_065_min": mins["LCNU"],
         "cross_battery_delta_ms": round(mins["LCNU"] - 89.9, 1),
         "note": "same condition measured in two batteries — cross-battery anchors are noisy; within-battery comparisons are the valid ones"}

out = {"walls_sorted": walls, "mins_ms_per_tok": mins, "best_alt": best,
       "delta_vs_lcnu": d, "cross_battery_lcnu_065": cross,
       "s1_agreement_vs_lcnu": s1, "s1_floor_lcnu_vs_lcnu": round(floor, 4),
       "G1_policy_win_ge5": g1, "G2_matches_050_sweet": g2,
       "S1_output_preserving": s1g, "S2_min_replicated_10pct": s2}
print(json.dumps(out))
if len(sys.argv) > 1 and sys.argv[1] == "--check-extractor":
    ext = json.load(open(f"{D}/extract820.json"))
    agree_keys = all(abs(ext["s1_agreement_vs_lcnu"][p] - s1[p]) < 1e-9 for p in s1)
    ok = (ext["walls_sorted"] == walls and ext["mins_ms_per_tok"] == mins and ext["best_alt"] == best
          and ext["G1_policy_win_ge5"] == g1 and ext["G2_matches_050_sweet"] == g2
          and ext["S1_output_preserving"] == s1g and ext["S2_min_replicated_10pct"] == s2
          and abs(ext["s1_floor_lcnu_vs_lcnu"] - round(floor, 4)) < 1e-9 and agree_keys)
    print("cross_check_vs_extractor:", ok)

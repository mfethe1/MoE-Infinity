#!/usr/bin/env python3
"""exp787 analyzer — frozen BEFORE launch. Arg: experiment ROOT (contains out/).

Arms (ratio 0.25, batch-1, uhw=on everywhere; only MOE_GROUPED_MOE_CFG differs):
  C = shipped launch table (default)
  W = WK=1 both projections  (1,8,1,2;1,8,1,2)  — K-split localization arm
  B = best probe hint         (1,2,4,4;1,1,8,2)

rc map (pooled mean per arm vs pooled C, 24 prompts x 2 reps):
  1 MAJOR-POS  delta >= +3.0%
  2 MILD-POS   +1.5% <= delta < +3.0%
  3 NO-MOVE    -1.5% < delta < +1.5%
  4 REGRESSION delta <= -1.5%
  9 DATA-FAIL  banner/identity/prompt-count violation in ANY cell
Verdict = best (lowest) rc among arms W and B (C is the reference arm).
Determinism: per arm, same out_sha count between rep a and rep b is REPORTED
as a descriptive finding (grouped kernels are known nondeterministic — exp786);
it is NOT a pass/fail gate in this experiment.
"""
import json, os, sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
out = os.path.join(root, "out")
cells = json.load(open(os.path.join(root, "cells787.json")))
ARMS = {"C": ["C25a", "C25b"], "W": ["W25a", "W25b"], "B": ["B25a", "B25b"]}
EXPECT_CFG = {"C": None, "W": "1,8,1,2;1,8,1,2", "B": "1,2,4,4;1,1,8,2"}

fails, rows_by_cell = [], {}
for c in cells:
    cid = c["id"]
    p = os.path.join(out, cid + ".json")
    if not os.path.exists(p):
        fails.append(f"{cid}: missing cell json"); continue
    d = json.load(open(p))
    rows = d.get("rows", [])
    summ = d  # engine writes banner fields at top level
    if summ.get("grouped_decode_effective") is not True:
        fails.append(f"{cid}: grouped_decode_effective not True")
    if str(summ.get("unvalidated_hw_env")) != "1":
        fails.append(f"{cid}: unvalidated_hw_env != 1")
    got = summ.get("grouped_cfg_env")
    exp = EXPECT_CFG[cid[:1]]
    if exp is None:
        if got not in (None, ""):
            fails.append(f"{cid}: grouped_cfg_env unexpectedly {got!r}")
    elif got != exp:
        fails.append(f"{cid}: grouped_cfg_env {got!r} != {exp!r}")
    if len(rows) != 24:
        fails.append(f"{cid}: {len(rows)} rows != 24")
    for r in rows:
        if r.get("n_new") != 32:
            fails.append(f"{cid}: n_new {r.get('n_new')} != 32"); break
    rows_by_cell[cid] = rows

def pooled(ids):
    xs = []
    for i in ids:
        for r in rows_by_cell.get(i, []):
            v = r.get("decode_tok_s")
            if isinstance(v, (int, float)):
                xs.append(float(v))
    return sum(xs) / len(xs) if xs else float("nan"), len(xs)

if fails:
    print("EXP787 rc=9 DATA-FAIL")
    for f in fails:
        print("  " + f)
    sys.exit(0)

cmean, cn = pooled(ARMS["C"])
print(f"C (shipped table) pooled mean {cmean:.3f} tok/s n={cn}")
best = 3
for arm in ("W", "B"):
    m, n = pooled(ARMS[arm])
    d = (m - cmean) / cmean * 100.0
    if d >= 3.0:   rc = 1
    elif d >= 1.5: rc = 2
    elif d > -1.5: rc = 3
    else:          rc = 4
    best = min(best, rc)
    print(f"{arm} ({EXPECT_CFG[arm] or 'default'}) pooled mean {m:.3f} tok/s n={n} -> {d:+.2f}% rc={rc}")

# determinism descriptive: rep a vs rep b same-position out_sha
for arm in ("C", "W", "B"):
    a, b = rows_by_cell.get(ARMS[arm][0], []), rows_by_cell.get(ARMS[arm][1], [])
    if a and b and len(a) == len(b):
        same = sum(1 for x, y in zip(a, b) if x.get("out_sha") == y.get("out_sha"))
        print(f"det[{arm}] same-sha across reps: {same}/{len(a)}")

print(f"EXP787 rc={best}")

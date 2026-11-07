#!/usr/bin/env python3
"""exp752 AMENDMENT1 coverage check. Usage: check_grouped.py OUTDIR. Read-only.
For every engine cell (H/R/RC), sums routing_delta.grouped_batches over rows. Any nonzero -> cell EXCLUDED-A1
(the patch does not touch the grouped retirement path, so such a cell does not test the intervention). Prints
'A1 ALL-PER-EXPERT' if every completed engine cell has 0, else lists offenders; the frozen VERDICT stands only if
the offenders are empty, otherwise analyze752's verdict is re-reported by hand excluding them (documented in the addendum)."""
import json, os, sys
O = sys.argv[1]
cells = json.load(open(os.path.join(O, "..", "cells.json")))
bad = []
for c in cells:
    if c["arm"] not in ("H", "R", "RC"):
        continue
    p = os.path.join(O, c["id"] + ".json")
    if not os.path.exists(p):
        print(f"{c['id']}: missing"); continue
    g = sum((r.get("routing_delta") or {}).get("grouped_batches", 0) for r in json.load(open(p))["rows"])
    print(f"{c['id']}: grouped_batches={g}")
    if g:
        bad.append(c["id"])
print("A1 ALL-PER-EXPERT" if not bad else f"A1 EXCLUDED {bad}")

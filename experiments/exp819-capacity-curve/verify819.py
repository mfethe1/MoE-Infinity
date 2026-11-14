#!/usr/bin/env python3
"""Independent re-derivation of exp819 numbers from raw per-arm artifacts.
Run against the frozen p9-*.json files; cross-checks extract819.json; all writeup
percentages must be pasted from THIS output (exp818 hard rule: script-computed).
"""
import json, glob, sys, hashlib, os

D = os.environ.get("EXP819_DIR", "/home/mfeth/exp819")
raw = {json.load(open(f))["tag"]: json.load(open(f)) for f in glob.glob(f"{D}/p9-R*_R*.json")}
measured = {t: d for t, d in raw.items() if not t.startswith("WARM")}
assert len(measured) == 12, f"need 12 measured arms, got {sorted(measured)}"

ratios = ["0.25", "0.35", "0.50", "0.65"]
walls = {r: sorted(measured[f"R{r.replace('.','')}_R{rep}"]["wall_ms_per_tok"] for rep in (1, 2, 3)) for r in ratios}
mins = {r: v[0] for r, v in walls.items()}
mems = {r: max(measured[f"R{r.replace('.','')}_R{rep}"]["peak_gpu_mem_mb"] for rep in (1, 2, 3)) for r in ratios}
s2 = {r: round(v[1] / v[0], 4) for r, v in walls.items()}

derived = {
    "walls_sorted": walls, "mins_ms_per_tok": mins, "peak_gpu_mem_mb": mems,
    "s2_secondmin_over_min": s2,
    "savings_025_to_065_ms_per_tok": round(mins["0.25"] - mins["0.65"], 1),
    "pct_slower_025_vs_065": round((mins["0.25"] / mins["0.65"] - 1) * 100, 1),
    "pct_slower_025_vs_050": round((mins["0.25"] / mins["0.50"] - 1) * 100, 1),
    "pct_slower_065_vs_050": round((mins["0.65"] / mins["0.50"] - 1) * 100, 1),
    "G1_slope_positive": mins["0.25"] >= mins["0.35"] >= mins["0.50"] >= mins["0.65"] - 1.0,
    "G2_capacity_wins_ge10": (mins["0.25"] - mins["0.65"]) >= 10,
    "S2_min_replicated_10pct": all(v <= 1.10 for v in s2.values()),
}
try:
    ext = json.load(open(f"{D}/extract819.json"))
    cross = all(derived[k] == ext.get(k) for k in ("walls_sorted", "mins_ms_per_tok", "peak_gpu_mem_mb",
                                                  "savings_025_to_065_ms_per_tok"))
    derived["cross_check_vs_extractor"] = cross
except FileNotFoundError:
    derived["cross_check_vs_extractor"] = "no extract819.json yet"
derived["raw_arm_sha256"] = {t: hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]
                             for t, d in sorted(measured.items())}
print(json.dumps(derived, indent=1))

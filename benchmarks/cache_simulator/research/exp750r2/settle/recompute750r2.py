#!/usr/bin/env python3
"""exp750r2 owner-independent recompute (NO import of classify750).
Independent implementation of PREREG/PREREG-R2 math from raw cell JSONs:
  d_p = median_reps((t64-t1)/63*1000); e_p = median_reps(t64/64*1000)
  D,E = median over 6 prompt rows
  quality = #prompts with (out_ids, top16_ids, top16_vals) == ref/exp749_b1_R.json
  G-T: every timed rep out_ids_64 == row out_ids; G-V: t64 > t1 > 0
  G-F (independent light reimpl): ollama>=1 in cell window OR >512MiB mem gain on
       a GPU not assigned to the cell (max-min within the cell's monitor window)
  _x replacement rule: dirty original -> its _x rerun must be present+clean
  s_b = D(S1)/D(R1), q_b = D(K2)/D(P2), u_b = D(S1)/D(P2)
  decisions per PREREG-R2 thresholds; pooled sensitivity over run1 b1,b2 + R2 b1..b3
"""
import json, re, statistics, sys
from pathlib import Path

R2 = Path(sys.argv[1])            # .../winnie-final-20261109T2339Z/x/exp750/out
REF = Path(sys.argv[2])           # ref/exp749_b1_R.json
R1OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else None   # run-1 out dir (pooled)

ARMS = ("R1", "S1", "S0", "P2", "K2", "C2", "H2")
GQ_ARMS = ("R1", "S1", "S0", "P2", "K2")
BLOCKS = (1, 2, 3)
CELLS = json.loads(Path(sys.argv[4]).read_text())  # cells750.json (arm/block/gpus per id)

def load(p):
    return json.loads(Path(p).read_text())

ref = load(REF)
ref_rows = [(r["out_ids"], r["top16_ids"], r["top16_vals"]) for r in ref["rows"]]

def rows_key(cell):
    return [(r["out_ids"], r["top16_ids"], r["top16_vals"]) for r in cell["rows"]]

def quality(cell):
    return sum(1 for a, b in zip(rows_key(cell), ref_rows) if a == b)

def g_t(cell):
    for r in cell["rows"]:
        for rep in r["timed"]:
            if list(rep.get("out_ids_64", [])) != list(r["out_ids"]):
                return False
    return True

def g_v(cell):
    for r in cell["rows"]:
        for rep in r["timed"]:
            t1, t64 = float(rep["t1_s"]), float(rep["t64_s"])
            if not (t64 > t1 > 0):
                return False
    return True

def cell_DE(cell):
    ds, es = [], []
    for r in cell["rows"]:
        dv = [(float(rep["t64_s"]) - float(rep["t1_s"])) / 63 * 1000 for rep in r["timed"]]
        ev = [float(rep["t64_s"]) / 64 * 1000 for rep in r["timed"]]
        ds.append(statistics.median(dv)); es.append(statistics.median(ev))
    return statistics.median(ds), statistics.median(es)

# ---- G-F light independent reimpl from monitor.csv ----
MEMSEG = re.compile(r"^(\d+),\s*(-?\d+)$")
def monitor_windows(outdir):
    """{cell: {gpu: [mem,...]}, ollama: [...]} from monitor.csv"""
    win = {}
    for line in (outdir / "monitor.csv").read_text().splitlines():
        parts = line.split(",", 2)
        if len(parts) < 3:
            continue
        cell = parts[1].strip()
        rest = parts[2]
        # rest = "0, MiB0;1, MiB1;,ollama"
        m = re.match(r"^(.*);,(-?\d+)$", rest.strip())
        if not m:
            continue
        seg_txt, oll = m.group(1), int(m.group(2))
        mem = {}
        for seg in seg_txt.split(";"):
            seg = seg.strip()
            if not seg:
                continue
            mm = MEMSEG.match(seg)
            if mm:
                mem[int(mm.group(1))] = int(mm.group(2))
        w = win.setdefault(cell, {"mem": {}, "oll": []})
        for g, v in mem.items():
            w["mem"].setdefault(g, []).append(v)
        w["oll"].append(oll)
    return win

WIN = monitor_windows(R2)

def foreign_light(cid, gpus_assigned):
    w = WIN.get(cid)
    if not w:
        return None, "no-monitor"
    reasons = []
    if any(o >= 1 for o in w["oll"]):
        reasons.append(f"ollama={max(w['oll'])}")
    for g, vals in w["mem"].items():
        if g not in gpus_assigned and (max(vals) - min(vals)) > 512:
            reasons.append(f"gpu{g}-gain={max(vals)-min(vals)}MiB")
    return bool(reasons), ";".join(reasons) if reasons else "clean"

# ---- per-cell table ----
cells = {}
for c in CELLS:
    cid = c["id"]
    assigned = set(int(x) for x in str(c["gpus"]).split(","))
    row = {"arm": c["arm"], "block": c["block"], "assigned": assigned}
    for suffix, tag in (("", "orig"), ("_x", "x")):
        p = R2 / f"{cid}{suffix}.json"
        if not p.exists():
            row[tag] = None
            continue
        cell = load(p)
        D, E = cell_DE(cell)
        fr, frwhy = foreign_light(cid + suffix, assigned)
        gt = g_t(cell); gv = g_v(cell)
        row[tag] = {
            "D": D, "E": E, "q": quality(cell),
            "gt": gt, "gv": gv,
            "foreign": fr, "frwhy": frwhy,
            "clean": (fr is False) and gt and gv,
        }
    cells[cid] = row

# effective cell per frozen replacement rule
eff = {}
dirty_used_replacement = []
for cid, row in cells.items():
    o = row["orig"]
    if o is not None and o["clean"]:
        eff[cid] = o
    elif row["x"] is not None and row["x"]["clean"]:
        eff[cid] = row["x"]
        dirty_used_replacement.append((cid, o["frwhy"] if o else "missing"))
    else:
        eff[cid] = None

print("== per-cell (independent recompute)")
for cid in sorted(cells, key=lambda k: (cells[k]["block"], cells[k]["arm"])):
    row = cells[cid]
    o, x = row["orig"], row["x"]
    def fmt(t):
        if t is None: return "ABSENT"
        return f"D={t['D']:.3f} E={t['E']:.3f} q={t['q']} GT={t['gt']} GV={t['gv']} FR={t['foreign']}({t['frwhy']}) clean={t['clean']}"
    print(f"  b{row['block']}_{row['arm']:2s} {cid}: orig[{fmt(o)}]" + (f"  x[{fmt(x)}]" if x else ""))
print("== replacements used:")
for cid, why in dirty_used_replacement:
    print(f"  {cid} -> {cid}_x  (orig dirty: {why})")

# ---- D per arm/block + decisions ----
def D(arm, b):
    for cid, row in cells.items():
        if row["arm"] == arm and row["block"] == b and eff.get(cid):
            return eff[cid]["D"]
    return None

missing = [(arm, b) for arm in ARMS for b in BLOCKS if D(arm, b) is None]
print("== missing effective cells:", missing if missing else "none")

ss = [D("S1", b) / D("R1", b) for b in BLOCKS if D("S1", b) and D("R1", b)]
qs = [D("K2", b) / D("P2", b) for b in BLOCKS if D("K2", b) and D("P2", b)]
us = [D("S1", b) / D("P2", b) for b in BLOCKS if D("S1", b) and D("P2", b)]
link = [D("S0", b) / D("S1", b) for b in BLOCKS if D("S0", b) and D("S1", b)]

def dec_d1(qs):
    if len(qs) != 3: return "INCOMPLETE"
    if all(q >= 1.10 for q in qs): return "FIX-FASTER"
    if all(q <= 0.91 for q in qs): return "WORKAROUND-FASTER"
    if all(0.95 <= q <= 1.05 for q in qs): return "EQUIVALENT"
    return "MIXED"

def dec_d2(ss):
    if len(ss) != 3: return "INCOMPLETE"
    if all(0.95 <= s <= 1.05 for s in ss): return "NOREGRESS-T"
    if all(s > 1.05 for s in ss): return "REGRESS-T"
    if all(s < 0.95 for s in ss): return "FASTER-T"
    return "UNRESOLVED-T"

def dec_d3(us):
    if len(us) != 3: return "INCOMPLETE"
    if all(u >= 1.10 for u in us): return "TWO-GPU-FASTER"
    if all(u <= 0.91 for u in us): return "TWO-GPU-SLOWER"
    return "NEUTRAL/MIXED"

print(f"D1 q=D(K2)/D(P2) per block: {qs} -> {dec_d1(qs)}")
print(f"D2 s=D(S1)/D(R1) per block: {ss} -> {dec_d2(ss)}")
print(f"D3 u=D(S1)/D(P2) per block: {us} -> {dec_d3(us)}")
print(f"link D(S0)/D(S1) per block: {link}")

# G-Q independent (gated arms, effective cells)
qfail = [f"{cid}" for cid, row in cells.items() if row["arm"] in GQ_ARMS
         and eff.get(cid) is not None and eff[cid]["q"] != len(ref_rows)]
qmiss = [cid for cid, row in cells.items() if row["arm"] in GQ_ARMS and eff.get(cid) is None]
print(f"G-Q(indep): {'QUALITY-FAIL(' + ','.join(sorted(qfail)) + ')' if qfail else ('INCOMPLETE' if qmiss else 'PASS')}"
      f"  (ref prompts={len(ref_rows)}); C2/H2 quality (descriptive): "
      + " ".join(f"{cid}:{cells[cid]['orig']['q'] if cells[cid]['orig'] else '-'}" for cid in sorted(cells) if cells[cid]['arm'] in ('C2','H2')))

# R1 noise floor
r1s = [D("R1", b) for b in BLOCKS]
m = statistics.mean(r1s)
print(f"noise floor: R1 across-block CV(D)={statistics.stdev(r1s)/m:.6f}")

# ---- pooled sensitivity (PREREG-R2 rule 2) ----
def load_run(outdir):
    data = {}
    cells1 = json.loads(Path(sys.argv[4]).read_text())
    for c in cells1:
        cid = c["id"]
        o = outdir / f"{cid}.json"
        x = outdir / f"{cid}_x.json"
        pick = None
        if o.exists():
            cell = load(o); D_, E_ = cell_DE(cell)
            pick = (cid, D_, quality(cell))
        if x.exists():
            cell = load(x); Dx, Ex = cell_DE(cell)
            # run-1 classifier used same replacement rule; take _x when present (frozen rule: replacement when orig dirty)
            pick = (cid + "_x", Dx, quality(cell))
        if pick:
            data[(c["arm"], c["block"])] = pick
    return data

if R1OUT and (R1OUT / "b1_R1.json").exists():
    r1 = load_run(R1OUT)
    # run-1 clean blocks for (R1,S1): 1,2 (b3 exhausted reruns FOREIGN per sealed record)
    s_r1 = [r1[("S1", b)][1] / r1[("R1", b)][1] for b in (1, 2)]
    s_r2 = ss
    def pooled(arm, blocks, src):
        vals = [src[(arm, b)][1] for b in blocks]
        return statistics.median(vals)
    # pooled D per arm over 5 blocks (run1 b1,b2 + R2 b1..b3)
    pD_s1 = statistics.median([r1[("S1", b)][1] for b in (1, 2)] + [D("S1", b) for b in BLOCKS])
    pD_r1 = statistics.median([r1[("R1", b)][1] for b in (1, 2)] + [D("R1", b) for b in BLOCKS])
    print(f"POOLED-SENSITIVITY: run1 s={s_r1} run2 s={s_r2} pooled s(D-median over 5 blocks)={pD_s1/pD_r1:.6f}")
    print(f"  (run-1 D(S1) blocks={ [r1[('S1', b)][1] for b in (1,2)] }, D(R1) blocks={ [r1[('R1', b)][1] for b in (1,2)] })")

#!/usr/bin/env python3
"""exp785 verdict. Single treatment: speculative_prefetch on/off (bf16, threads=4,
gpu-route on, lcnu, 24 prompts x 32 tok, 2 reps). Deltas per regime: d75 = mean(S75) -
mean(C75), d25 = mean(S25) - mean(C25), as relative tok/s change.
rc map: 1 MAJOR-POS (any regime delta >= +0.50) / 2 MILD-POS (>= +0.10) /
3 NO-MOVE (both |delta| < 0.10) / 4 REGRESSION (any regime delta <= -0.10) / 9 DATA-FAIL.
Determinism gate: within each config (id letter + spec + ratio), the two reps a/b must
produce identical out_sha multisets; any mismatch -> rc9 (with detail printed).
"""
import json, sys, os

root = sys.argv[1] if len(sys.argv) > 1 else "."
out = os.path.join(root, "out")
if not os.path.isdir(out):
    out = root  # allow running with out/ as root directly

problems = []
cells = {}
try:
    cells = {c["id"]: c for c in json.load(open(os.path.join(root, "cells785.json")))}
except FileNotFoundError:
    pass

rows = {}
for cid in ["C75a","S75a","C25a","S25a","C75b","S75b","C25b","S25b"]:
    p = os.path.join(out, cid + ".json")
    if not os.path.exists(p):
        problems.append(f"missing cell {cid}")
        continue
    d = json.load(open(p))
    rows[cid] = d

def det_ok(cfg_reps):
    # cfg_reps: list of (tag, [out_sha per row])
    sets = {}
    for tag, shas in cfg_reps:
        sets.setdefault(tag, []).append(sorted(shas))
    bad = []
    for tag, ss in sets.items():
        if len(ss) == 2 and ss[0] != ss[1]:
            bad.append(tag)
    return bad

det_bad = []
if not problems:
    tags = {}
    for cid, d in rows.items():
        cfg = cid[:3]  # e.g. C75, S25
        tags.setdefault(cfg, []).append((cid, [r["out_sha"] for r in d["rows"]]))
    for cfg, reps in tags.items():
        if len(reps) != 2:
            problems.append(f"{cfg}: expected 2 reps, got {len(reps)}")
            continue
        a = sorted(reps[0][1]); b = sorted(reps[1][1])
        if a != b:
            det_bad.append(cfg)
    if det_bad:
        problems.append(f"NONDET configs: {','.join(det_bad)}")

def arm_stats(pref):
    sel = [cid for cid in rows if cid.startswith(pref)]
    tps = []
    miss = hit = 0
    for cid in sel:
        for r in rows[cid]["rows"]:
            tps.append(r["decode_tok_s"])
            sd = r.get("stats_delta", {})
            miss += sd.get("policy_routed_misses", 0)
            hit += sd.get("policy_routed_hits", 0)
    n = len(sel)
    mean = sum(tps) / len(tps) if tps else 0.0
    return mean, miss, hit, n

if not problems:
    c75, m_c75, h_c75, n1 = arm_stats("C75")
    s75, m_s75, h_s75, n2 = arm_stats("S75")
    c25, m_c25, h_c25, n3 = arm_stats("C25")
    s25, m_s25, h_s25, n4 = arm_stats("S25")
    d75 = (s75 - c75) / c75 if c75 else 0.0
    d25 = (s25 - c25) / c25 if c25 else 0.0
    det = "ALL-DET" if not det_bad else "NONDET"
    rc = 9
    if not problems:
        if d75 >= 0.50 or d25 >= 0.50:
            rc = 1
        elif d75 >= 0.10 or d25 >= 0.10:
            rc = 2
        elif d75 <= -0.10 or d25 <= -0.10:
            rc = 4
        else:
            rc = 3
    print(f"EXP785 rc={rc} {det}")
    print(f"C75 mean={c75:.3f} tok/s miss={m_c75} n={n1}")
    print(f"S75 mean={s75:.3f} tok/s miss={m_s75} n={n2} d75={d75*100:+.2f}%")
    print(f"C25 mean={c25:.3f} tok/s miss={m_c25} n={n3}")
    print(f"S25 mean={s25:.3f} tok/s miss={m_s25} n={n4} d25={d25*100:+.2f}%")
else:
    print("EXP785 rc=9 DATA-FAIL")
    for p in problems:
        print("PROBLEM:", p)
    if det_bad:
        print("NONDET configs:", ",".join(det_bad))

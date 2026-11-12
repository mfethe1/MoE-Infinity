#!/usr/bin/env python3
"""exp788 probe analysis: det-mode bit-reproducibility + speed cost.
Reads /home/mfeth/exp788/p788_*.json (rows carry out_sha per prompt).
"""
import glob, hashlib, json, sys

base = "/home/mfeth/exp788"
tags = sorted(glob.glob(f"{base}/p788_*.json"))
data = {}
for f in tags:
    tag = f.split("p788_")[1][:-5]
    d = json.load(open(f))
    rows = d.get("rows", d if isinstance(d, list) else [])
    toks = [x["decode_tok_s"] for x in rows if "decode_tok_s" in x]
    shas = [x.get("out_sha", "") for x in rows]
    data[tag] = {"mean": sum(toks)/len(toks) if toks else 0.0,
                 "n": len(toks),
                 "shas": shas,
                 "run_sha": hashlib.sha256(json.dumps(shas).encode()).hexdigest()[:16]}

for t, v in sorted(data.items()):
    print(f"[{t}] mean={v['mean']:.3f} tok/s n={v['n']} run_sha={v['run_sha']}")

c = data.get("C"); t0 = data.get("T0")
det = [data[t] for t in data if t.startswith("D")]
if c and t0:
    print(f"\nT0 vs C bit-identical: {c['shas'] == t0['shas']}")
if len(det) >= 2:
    same = all(d["shas"] == det[0]["shas"] for d in det[1:])
    print(f"det same-sha across {len(det)} fresh processes: {same}")
    if same:
        print(f"det T0-vs-D identical (mode switch changes bits): {t0['shas'] == det[0]['shas'] if t0 else 'n/a'}")
if c and det:
    cost = (c["mean"] - sum(d["mean"] for d in det)/len(det)) / c["mean"] * 100
    print(f"det speed cost vs C: {cost:+.2f}%")
if t0 and det:
    cost = (t0["mean"] - sum(d["mean"] for d in det)/len(det)) / t0["mean"] * 100
    print(f"det speed cost vs T0: {cost:+.2f}%")

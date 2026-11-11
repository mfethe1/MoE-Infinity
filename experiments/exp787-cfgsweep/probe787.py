#!/usr/bin/env python3
"""exp787 probe: MOE_GROUPED_MOE_CFG sweep at batch-1, ratio 0.25, uhw=on.
Each config = fresh engine process (env is read once per process).
Usage: python3 probe787.py TAG=CFG [TAG=CFG ...]  (CFG 'none' = no env)
"""
import json, os, subprocess, sys

PY = os.path.expanduser("~/venvs/moei-engine/bin/python")
EXP = "/home/mfeth/exp786"
CFGS = [a.split("=", 1) for a in sys.argv[1:]]

base_env = dict(os.environ)
base_env.pop("MOE_GROUPED_MOE_CFG", None)
base_env["MOE_INFINITY_UNVALIDATED_HW"] = "1"
base_env["CUDA_VISIBLE_DEVICES"] = "1"

for tag, cfg in CFGS:
    env = dict(base_env)
    if cfg != "none":
        env["MOE_GROUPED_MOE_CFG"] = cfg
    out = f"{EXP}/p787_{tag}.json"
    env["PYTHONPATH"] = "/home/mfeth/exp759/src753"
    cmd = [
        PY, f"{EXP}/engine_arm786.py",
        "--model", os.path.expanduser("~/models/OLMoE-1B-7B-0125-Instruct"),
        "--offload", os.path.expanduser("~/moe-offload"),
        "--policy", "lcnu", "--ratio", "0.25",
        "--prompts", f"{EXP}/probe8.json", "--max-new", "24",
        "--out", out, "--threads", "4", "--gpu-route", "on",
        "--unvalidated-hw", "on",
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"[{tag}] RC={r.returncode}: {r.stderr.strip()[-200:]}")
        continue
    d = json.load(open(out))
    rows = d.get("rows", d if isinstance(d, list) else [])
    toks = [x["decode_tok_s"] for x in rows if "decode_tok_s" in x]
    sha_ok = all("out_sha" in x for x in rows)
    print(f"[{tag}] cfg={cfg} mean={sum(toks)/len(toks):.3f} tok/s n={len(toks)} rc=0")

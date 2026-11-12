#!/usr/bin/env python3
"""exp789 probe: 36-SM-tuned launch-config instantiations.
Each arm = fresh engine process; MOE_GROUPED_MOE_CFG selects config pairs
legal in the (now 12-entry) instantiation table.
Usage: python3 probe789.py TAG=/path/to/build:cfg   (cfg = 'default' or 'mt,wr,wk,u;mt,wr,wk,u')
Writes /home/mfeth/exp789/p789_TAG.json. Decision rule (declared pre-probe):
promote to frozen 24-prompt confirmatory iff pooled mean tok/s >= +2% vs C.
"""
import json, os, subprocess, sys

PY = os.path.expanduser("~/venvs/moei-engine/bin/python")
EXP = "/home/mfeth/exp789"
os.makedirs(EXP, exist_ok=True)
ENGINE = "/home/mfeth/exp786/engine_arm786.py"
ARMS = [a.split("=", 1) for a in sys.argv[1:]]

base_env = dict(os.environ)
base_env.pop("MOE_GROUPED_MOE_CFG", None)
base_env.pop("MOE_GROUPED_DETERMINISTIC", None)
base_env["MOE_INFINITY_UNVALIDATED_HW"] = "1"
base_env["CUDA_VISIBLE_DEVICES"] = "1"

for tag, spec in ARMS:
    ppath, cfg = spec.rsplit(":", 1)
    env = dict(base_env)
    env["PYTHONPATH"] = ppath
    if cfg != "default":
        env["MOE_GROUPED_MOE_CFG"] = cfg
    out = f"{EXP}/p789_{tag}.json"
    cmd = [
        PY, ENGINE,
        "--model", os.path.expanduser("~/models/OLMoE-1B-7B-0125-Instruct"),
        "--offload", os.path.expanduser("~/moe-offload"),
        "--policy", "lcnu", "--ratio", "0.25",
        "--prompts", "/home/mfeth/exp788/probe8.json", "--max-new", "24",
        "--out", out, "--threads", "4", "--gpu-route", "on",
        "--unvalidated-hw", "on",
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"[{tag}] RC={r.returncode}: {r.stderr.strip()[-250:]}")
        continue
    d = json.load(open(out))
    rows = d.get("rows", d if isinstance(d, list) else [])
    sp = [r.get("decode_tok_s") for r in rows if r.get("decode_tok_s")]
    print(f"[{tag}] cfg={cfg} n={len(sp)} pooled={sum(sp)/len(sp):.3f} tok/s")
print("DONE")

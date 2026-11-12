#!/usr/bin/env python3
"""exp788 probe: deterministic grouped epilogue (MOE_GROUPED_DETERMINISTIC).
Each arm = fresh engine process; build tree and det flag switch per arm.
Usage: python3 probe788.py TAG=/path/to/build:det   (det = on|off)
Writes /home/mfeth/exp788/p788_TAG.json (rows carry out_sha for det compare).
"""
import json, os, subprocess, sys

PY = os.path.expanduser("~/venvs/moei-engine/bin/python")
EXP = "/home/mfeth/exp788"
ENGINE = "/home/mfeth/exp786/engine_arm786.py"
ARMS = [a.split("=", 1) for a in sys.argv[1:]]

base_env = dict(os.environ)
base_env.pop("MOE_GROUPED_MOE_CFG", None)
base_env.pop("MOE_GROUPED_DETERMINISTIC", None)
base_env["MOE_INFINITY_UNVALIDATED_HW"] = "1"
base_env["CUDA_VISIBLE_DEVICES"] = "1"

for tag, spec in ARMS:
    ppath, det = spec.rsplit(":", 1)
    env = dict(base_env)
    env["PYTHONPATH"] = ppath
    if det == "on":
        env["MOE_GROUPED_DETERMINISTIC"] = "1"
    out = f"{EXP}/p788_{tag}.json"
    cmd = [
        PY, ENGINE,
        "--model", os.path.expanduser("~/models/OLMoE-1B-7B-0125-Instruct"),
        "--offload", os.path.expanduser("~/moe-offload"),
        "--policy", "lcnu", "--ratio", "0.25",
        "--prompts", f"{EXP}/probe8.json", "--max-new", "24",
        "--out", out, "--threads", "4", "--gpu-route", "on",
        "--unvalidated-hw", "on",
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"[{tag}] RC={r.returncode}: {r.stderr.strip()[-250:]}")
        continue
    d = json.load(open(out))
    rows = d.get("rows", d if isinstance(d, list) else [])
    toks = [x["decode_tok_s"] for x in rows if "decode_tok_s" in x]
    shas = [x.get("out_sha", "?")[:12] for x in rows]
    print(f"[{tag}] det={det} pp={os.path.basename(ppath)} "
          f"mean={sum(toks)/len(toks):.3f} tok/s n={len(toks)} rc=0 "
          f"sha0={shas[0] if shas else '?'}")

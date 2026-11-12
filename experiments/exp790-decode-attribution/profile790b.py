#!/usr/bin/env python3
"""exp790 v2: nsys-based decode-residual attribution (CUPTI-in-torch is dead in
this venv). Two capture modes, both after identical warmup, capture window
bracketed by cudaProfilerApi (nsys --capture-range=cudaProfilerApi):
  --mode prefill : 8 x gen(prompt, 1)   -> kernel-time scale A
  --mode full    : 8 x gen(prompt, 32)  -> kernel-time scale B
Decode contribution per kernel = B_totals - A_totals (nsys cuda_gpu_kern_sum,
parsed host-side by agg790.py). Question/decision rule unchanged from v1.
"""
import argparse, json, os, time

import torch

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--offload", required=True)
ap.add_argument("--prompts", required=True)
ap.add_argument("--max-new", type=int, default=32)
ap.add_argument("--mode", choices=["prefill", "full"], required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--threads", type=int, default=4)
a = ap.parse_args()

os.environ["MOE_INFINITY_UNVALIDATED_HW"] = "1"
os.environ.pop("MOE_GROUPED_DECODE", None)

from transformers import AutoTokenizer  # noqa: E402
from moe_infinity import MoE  # noqa: E402

tok = AutoTokenizer.from_pretrained(a.model)
cfg = {"offload_path": a.offload, "device_memory_ratio": 0.25,
       "expert_eviction_policy": "lcnu", "num_threads": a.threads,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
model = MoE(a.model, cfg)
dev = "cuda:0"


def gen_ids(p):
    return tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                   return_tensors="pt", return_dict=True)["input_ids"].to(dev)


def gen(ids, n):
    with torch.no_grad():
        model.generate(ids, max_new_tokens=n, min_new_tokens=n,
                       do_sample=False, pad_token_id=tok.eos_token_id)


gen(gen_ids("Say hello."), 8)  # warmup outside capture
prompts = json.load(open(a.prompts))
n = 1 if a.mode == "prefill" else a.max_new

torch.cuda.synchronize()
torch.cuda.profiler.start()  # nsys capture begins here
walls = []
for p in prompts:
    ids = gen_ids(p)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    gen(ids, n)
    torch.cuda.synchronize()
    walls.append(time.perf_counter() - t0)
torch.cuda.profiler.stop()
json.dump({"mode": a.mode, "n": n, "walls_s": walls}, open(a.out, "w"), indent=1)
print("DONE", a.mode, "walls:", [round(w, 2) for w in walls])

#!/usr/bin/env python3
"""exp791: expert-residency sweep — decompose the ~50% moe dispatch stall.

Hypothesis (from exp790): moe-block self-time 68% of decode wall, ~50% is
runtime dispatch. Two candidate components: (a) expert-weight fetch wait
(PCIe H2D under residency limits), (b) thread handoff/wake latency in the
dispatch_local -> pending_cv==0 -> wait_dispatch_local barrier.

Knob: device_memory_ratio (cfg, no rebuild): 0.25 (C, production), 0.5, 0.75,
0.9. Production config otherwise: MOE_GROUPED_DECODE=1, lcnu, topk 8,
gpu_only routing, legacy residency, spec-prefetch OFF.

DECISION RULE (pre-declared):
- Promote arm to frozen confirmatory iff pooled mean tok/s >= +2% vs C.
- Interpretation: monotone gain with ratio => stall fetch-wait-dominated
  (residency caching is the lever); flat (<1% best arm) => stall is
  handoff/barrier-dominated (barrier restructuring is the lever, C++ work).
Fresh engine process per arm; 8 prompts x 32 tok; CUDA_VISIBLE_DEVICES=1.
"""
import argparse
import json
import os
import time

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--offload", required=True)
ap.add_argument("--prompts", required=True)
ap.add_argument("--ratio", type=float, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--threads", type=int, default=4)
a = ap.parse_args()

os.environ["MOE_INFINITY_UNVALIDATED_HW"] = "1"
os.environ["MOE_GROUPED_DECODE"] = "1"
os.environ.pop("MOE_GROUPED_MOE_CFG", None)

import torch  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402
from moe_infinity import MoE  # noqa: E402

tok = AutoTokenizer.from_pretrained(a.model)
cfg = {"offload_path": a.offload, "device_memory_ratio": a.ratio,
       "expert_eviction_policy": "lcnu", "num_threads": a.threads,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
model = MoE(a.model, cfg)
dev = "cuda:0"

prompts = json.load(open(a.prompts))
res = {"ratio": a.ratio, "tok_per_s": [], "walls_s": []}
for p in prompts:
    ids = tok.apply_chat_template([{"role": "user", "content": p}],
                                  add_generation_prompt=True,
                                  return_tensors="pt", return_dict=True)["input_ids"].to(dev)
    model.generate(ids, max_new_tokens=8, min_new_tokens=8, do_sample=False,
                   pad_token_id=tok.eos_token_id)  # warm arm
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    model.generate(ids, max_new_tokens=32, min_new_tokens=32, do_sample=False,
                   pad_token_id=tok.eos_token_id)
    torch.cuda.synchronize()
    w = time.perf_counter() - t0
    res["walls_s"].append(round(w, 3))
    res["tok_per_s"].append(round(32 / w, 3))

res["pooled_mean"] = round(sum(res["tok_per_s"]) / len(res["tok_per_s"]), 3)
json.dump(res, open(a.out, "w"), indent=1)
print(json.dumps(res))

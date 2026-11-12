#!/usr/bin/env python3
"""exp795: inline work-stealing wait for grouped dispatch drain.

Hypothesis (exp794): at ratio 0.5 the remaining ~51% wait share is dominated
by thread-queue round trip (route worker -> exec_queue_ -> GPUExecFunc wake
-> cv notify), ~1.46 ms/call even when all experts are cache-resident.
Patch: WaitHiddenStates actively steals GROUPED exec items and runs
GroupedExec inline on the caller thread (kill-switch MOE_INLINE_WAIT=0).

ARMS (fresh engine process each, 8 prompts x 32 tok, CUDA_VISIBLE_DEVICES=1):
- C  binary d252620b (editable tree; the exact binary behind exp791/793/794).
- P  binary eba566fb (src795: exp752-dormant + inline patch) with
   MOE_INLINE_WAIT=0 (passive wait) — attribution control for binary lineage.
- A  binary eba566fb, inline steal ON (default) — treatment.

DECISION RULE (pre-declared):
- Gate 1 correctness: all 8 prompts' greedy 32-token IDs IDENTICAL across
  C, P, A. Any divergence = VOID (no perf interpretation).
- Gate 2 perf: promote iff pooled mean tok/s(A) >= pooled mean tok/s(C) x 1.05.
- Attribution: A vs P isolates the patch; P vs C measures binary-lineage
  drift. If P vs C delta > 1%, headline becomes A vs P with lineage note.
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
res = {"ratio": a.ratio, "tok_per_s": [], "walls_s": [], "token_ids": []}
for p in prompts:
    ids = tok.apply_chat_template([{"role": "user", "content": p}],
                                  add_generation_prompt=True,
                                  return_tensors="pt", return_dict=True)["input_ids"].to(dev)
    model.generate(ids, max_new_tokens=8, min_new_tokens=8, do_sample=False,
                   pad_token_id=tok.eos_token_id)  # warm arm
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    gen = model.generate(ids, max_new_tokens=32, min_new_tokens=32,
                         do_sample=False, pad_token_id=tok.eos_token_id)
    torch.cuda.synchronize()
    w = time.perf_counter() - t0
    res["walls_s"].append(round(w, 3))
    res["tok_per_s"].append(round(32 / w, 3))
    res["token_ids"].append(gen[0][ids.shape[1]:].tolist())

res["pooled_mean"] = round(sum(res["tok_per_s"]) / len(res["tok_per_s"]), 3)
json.dump(res, open(a.out, "w"), indent=1)
print(json.dumps(res))

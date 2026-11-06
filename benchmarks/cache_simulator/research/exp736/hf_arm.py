#!/usr/bin/env python3
"""exp726 native-HF baseline arm: identical protocol/metric to engine_arm.py, plain transformers bf16 on cuda:0."""
import argparse, hashlib, json, os, platform, time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--prompts", required=True)
ap.add_argument("--max-new", type=int, default=64); ap.add_argument("--warmup", type=int, default=1)
ap.add_argument("--out", required=True)
a = ap.parse_args()
prompts = json.load(open(a.prompts)); tok = AutoTokenizer.from_pretrained(a.model)
t0 = time.perf_counter()
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16, device_map="cuda:0").eval()
load_s = time.perf_counter() - t0
def gen(p, n):
    ids = tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                  return_tensors="pt", return_dict=True)["input_ids"].to("cuda:0")
    torch.cuda.synchronize(); t = time.perf_counter()
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=n, min_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    torch.cuda.synchronize()
    return ids.shape[1], out[0, ids.shape[1]:].tolist(), time.perf_counter() - t
for _ in range(a.warmup): gen("Say hello.", 8)
rows = []
for i, p in enumerate(prompts):
    n_in, _, t1 = gen(p, 1); n_in, new, tf = gen(p, a.max_new)
    rows.append({"i": i, "n_in": n_in, "n_new": len(new), "t_1tok_s": t1, "t_full_s": tf,
                 "decode_tok_s": (len(new) - 1) / max(tf - t1, 1e-9),
                 "out_sha": hashlib.sha256(json.dumps(new).encode()).hexdigest()[:16], "out_ids": new,
                 "stats_delta": {"policy_routed_hits": 0, "policy_routed_misses": 0}})
    print(f"[hf] prompt {i}: {rows[-1]['decode_tok_s']:.2f} tok/s", flush=True)
json.dump({"arm": "hf", "load_s": load_s, "rows": rows, "gpu": torch.cuda.get_device_name(0),
           "visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "host": platform.node(),
           "mem_alloc_gb": torch.cuda.max_memory_allocated() / 1e9, "torch": torch.__version__}, open(a.out, "w"), indent=1)
print("DONE", a.out, flush=True)

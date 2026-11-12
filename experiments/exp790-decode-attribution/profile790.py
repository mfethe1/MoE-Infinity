#!/usr/bin/env python3
"""exp790: decode-residual attribution on the grouped-decode build (e45b63fc).
Question: where do the ~82% non-grouped decode milliseconds go?
Method: per prompt, profile a 1-token (prefill) run and a 32-token run with
torch.profiler (CPU+CUDA, record_shapes); decode contribution per category =
full minus prefill. 8 prompts, one fresh process, CUDA_VISIBLE_DEVICES=1.
Decision rule (declared pre-run): next kernel target = top non-grouped
category if it holds >=25% of decode CUDA time.
"""
import argparse, json, os, platform, re, time

import torch

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--offload", required=True)
ap.add_argument("--prompts", required=True)
ap.add_argument("--max-new", type=int, default=32)
ap.add_argument("--out", required=True)
ap.add_argument("--threads", type=int, default=4)
a = ap.parse_args()

os.environ["MOE_INFINITY_UNVALIDATED_HW"] = "1"  # must precede moe_infinity import
os.environ.pop("MOE_GROUPED_DECODE", None)

from transformers import AutoTokenizer  # noqa: E402
from moe_infinity import MoE  # noqa: E402

CATS = [
    ("grouped", re.compile(r"grouped|gglm|pro6000|moe_grouped", re.I)),
    ("attention", re.compile(r"sdpa|scaled_dot_product|flash|fmha|attention|attn", re.I)),
    ("gemm_linear", re.compile(r"gemm|cutlass|matmul|nvjet|cublas|::mm|::bmm|::linear|::addmm", re.I)),
    ("norm", re.compile(r"layer_norm|rms_norm|rmsnorm|::norm", re.I)),
    ("copy_sync", re.compile(r"memcpy|memset|copy_|to_copy|cudaDeviceSynchronize|StreamSynchronize|elementwise_kernel", re.I)),
    ("index_gather", re.compile(r"index|gather|scatter|topk|sort|argmax|where|select", re.I)),
    ("other_elementwise", re.compile(r"activation|silu|gelu|mul|add|sub|div|exp|softmax|reduce", re.I)),
]


def cat(nm):
    for c, rx in CATS:
        if rx.search(nm):
            return c
    return "other"


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
    torch.cuda.synchronize()
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=n, min_new_tokens=n,
                             do_sample=False, pad_token_id=tok.eos_token_id)
    torch.cuda.synchronize()
    return out


def profile_run(ids, n):
    from torch.profiler import profile, ProfilerActivity
    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
                 record_shapes=True) as prof:
        gen(ids, n)
    rows = {}
    for ev in prof.key_averages(group_by_input_shape=False):
        cuda_us = getattr(ev, "device_time_total", 0) or getattr(ev, "cuda_time_total", 0)
        if cuda_us <= 0:
            continue
        rows[ev.key] = rows.get(ev.key, 0.0) + cuda_us
    return rows


gen(gen_ids("Say hello."), 8)  # warmup
prompts = json.load(open(a.prompts))
per_prompt = []
for i, p in enumerate(prompts):
    ids = gen_ids(p)
    torch.cuda.synchronize(); t0 = time.perf_counter()
    gen(ids, 1)
    t1 = time.perf_counter() - t0
    pre = profile_run(ids, 1)
    torch.cuda.synchronize(); t0 = time.perf_counter()
    gen(ids, a.max_new)
    tf = time.perf_counter() - t0
    full = profile_run(ids, a.max_new)
    wall_decode = tf - t1
    # decode-attributed CUDA us per op = full - pre
    dec = {}
    for k, v in full.items():
        d = v - pre.get(k, 0.0)
        if d > 0:
            dec[k] = d
    tot = sum(dec.values())
    per_prompt.append({"i": i, "wall_prefill_s": t1, "wall_full_s": tf,
                       "wall_decode_s": wall_decode,
                       "cuda_decode_us_total": tot,
                       "by_cat_us": {}, "top_ops": sorted(dec.items(), key=lambda x: -x[1])[:25]})
    for k, v in dec.items():
        c = cat(k)
        per_prompt[-1]["by_cat_us"][c] = per_prompt[-1]["by_cat_us"].get(c, 0) + v
    print(f"prompt {i}: wall decode {wall_decode:.2f}s, cuda decode {tot/1e6:.2f}s, "
          + ", ".join(f"{c}={v/tot*100:.0f}%" for c, v in sorted(per_prompt[-1]["by_cat_us"].items(), key=lambda x: -x[1])[:5]),
          flush=True)

# aggregate
agg = {}
for r in per_prompt:
    for c, v in r["by_cat_us"].items():
        agg[c] = agg.get(c, 0) + v
T = sum(agg.values())
shares = {c: round(v / T * 3, 4) for c, v in sorted(agg.items(), key=lambda x: -x[1])}
non_grouped = [(c, v / T) for c, v in agg.items() if c != "grouped"]
non_grouped.sort(key=lambda x: -x[1])
top_ng, top_share = non_grouped[0]
decision = "TARGET=" + top_ng if top_share >= 0.25 else "NO-CATEGORY>=25%"
res = {"model": a.model, "max_new": a.max_new, "torch": torch.__version__,
       "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
       "host": platform.node(), "aggregate_cat_share": shares,
       "decision_rule": "top non-grouped category >=25% of decode CUDA time",
       "decision": decision, "top_non_grouped": [top_ng, round(top_share, 4)],
       "per_prompt": per_prompt}
json.dump(res, open(a.out, "w"), indent=1)
print("AGGREGATE:", json.dumps(shares))
print("DECISION:", decision)

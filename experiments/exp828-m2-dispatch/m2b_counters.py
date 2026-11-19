import argparse
import json
import os
import time

ap = argparse.ArgumentParser()
ap.add_argument("--ratio", type=float, required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
assert 0.0 < a.ratio < 1.0, a.ratio

os.environ["CUDA_VISIBLE_DEVICES"] = "1"
os.environ["MOE_INFINITY_UNVALIDATED_HW"] = "1"
os.environ["MOE_GROUPED_DECODE"] = "1"
os.environ.pop("MOE_GROUPED_MOE_CFG", None)

import torch
from transformers import AutoTokenizer
from moe_infinity import MoE

MODEL = "/home/mfeth/models/OLMoE-1B-7B-0125-Instruct"
OFFLOAD = "/home/mfeth/moe-offload-olmoe-0125-r05"
PROMPTS = json.load(open("/home/mfeth/exp788/probe8.json"))
WARM_TOK = 8
MEAS_TOK = 32
ACCESSES_PER_STEP = 16 * 8
EXPERT_MB = 3 * 2048 * 1024 * 2 / 1e6

tok = AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token

cfg = {"offload_path": OFFLOAD, "device_memory_ratio": a.ratio,
       "expert_eviction_policy": "lcnu", "num_threads": 4,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
m = MoE(MODEL, cfg)
if hasattr(m, "eval"):
    m.eval()

eng = getattr(m, "engine", None)
assert eng is not None and hasattr(eng, "get_exposed_fetch_seconds"), type(m).__name__


def gpu_util():
    s = os.popen("/usr/lib/wsl/lib/nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i 1").read().strip()
    return int(s) if s.isdigit() else 99


def loadavg5():
    return float(open("/proc/loadavg").read().split()[1])


def wait_quiet():
    for attempt in range(30):
        if loadavg5() < 3 and gpu_util() < 5:
            return True
        time.sleep(60)
    return False


def enc_ids(p):
    e = tok.apply_chat_template([{"role": "user", "content": p}],
                                add_generation_prompt=True, return_tensors="pt")
    return e if isinstance(e, torch.Tensor) else e["input_ids"]


vram_after_load = {
    "torch_max_alloc_mb": round(torch.cuda.max_memory_allocated() / 1e6, 1),
    "smi_used_mib": int(os.popen("/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 1").read().strip()),
    "occupancy_bytes": float(eng.expert_occupancy_bytes),
    "num_offloaded_experts": int(eng.num_offloaded_experts),
}
time.sleep(30)

res = {"ratio": a.ratio, "vram_after_load": vram_after_load, "prompts": []}
for p in PROMPTS:
    ids = enc_ids(p).to("cuda:0")
    with torch.no_grad():
        m.generate(ids, max_new_tokens=WARM_TOK, min_new_tokens=WARM_TOK,
                   do_sample=False, pad_token_id=tok.eos_token_id)
    assert wait_quiet(), "quiet gate exhausted"
    eng.reset_exposed_fetch_seconds()
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = m.generate(ids, max_new_tokens=MEAS_TOK, min_new_tokens=MEAS_TOK,
                         do_sample=False, pad_token_id=tok.eos_token_id)
    torch.cuda.synchronize()
    wall_s = time.perf_counter() - t0
    ntok = int(out.shape[1] - ids.shape[1])
    fetch_s = eng.get_exposed_fetch_seconds()
    hit = float(eng.expert_cache_hit_rate)
    misses_est = (1.0 - hit) * ACCESSES_PER_STEP * ntok
    res["prompts"].append({
        "prompt": p[:40], "wall_s": round(wall_s, 3), "tok": ntok,
        "hit_rate": round(hit, 4),
        "exposed_fetch_ms": round(fetch_s * 1000.0, 1),
        "fetch_ms_per_tok": round(fetch_s * 1000.0 / max(ntok, 1), 2),
        "misses_est": int(round(misses_est)),
        "h2d_mb_est": round(misses_est * EXPERT_MB, 1),
        "occupancy_bytes": float(eng.expert_occupancy_bytes),
    })
    print("arm", a.ratio, p[:28], f"{wall_s:.2f}s hit={hit:.3f} fetch={fetch_s*1000:.0f}ms",
          flush=True)

walls = [pr["wall_s"] for pr in res["prompts"]]
toks = [pr["tok"] for pr in res["prompts"]]
res["pooled_tok_per_s"] = round(sum(toks) / sum(walls), 3)
res["median_fetch_ms_per_tok"] = sorted(pr["fetch_ms_per_tok"] for pr in res["prompts"])[len(res["prompts"]) // 2]
res["mean_hit_rate"] = round(sum(pr["hit_rate"] for pr in res["prompts"]) / len(res["prompts"]), 4)
json.dump(res, open(a.out, "w"), indent=1)
print("M2B_ARM_DONE", a.ratio, "pooled", res["pooled_tok_per_s"], flush=True)

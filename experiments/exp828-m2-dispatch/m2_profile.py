import os, sys, json, time
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
os.environ.setdefault("MOE_INFINITY_UNVALIDATED_HW", "1")
import torch
from torch.profiler import profile, ProfilerActivity
from transformers import AutoTokenizer
from moe_infinity import MoE

MODEL = "/home/mfeth/models/OLMoE-1B-7B-0125-Instruct"
NEW = 64
PROMPTS = [
    "Explain what a cache is in computing.",
    "Write a haiku about mountains.",
    "Summarize the water cycle.",
    "List three uses of copper.",
    "Describe a red-black tree.",
    "Give tips for better sleep.",
    "Explain why the sky is blue.",
    "Name the planets in order.",
]
EXPERT_MB = 3 * 2048 * 1024 * 2 / 1e6

tok = AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token

def quiet():
    la = float(open("/proc/loadavg").read().split()[1])
    smi = os.popen("/usr/lib/wsl/lib/nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i 1").read().strip()
    return la, (int(smi) if smi.isdigit() else 99)

m = MoE(MODEL, {"offload_path": "/home/mfeth/moe-offload-olmoe-0125-r05",
                "device_memory_ratio": 0.50, "expert_eviction_policy": "lcnu",
                "num_threads": 4, "gpu_only_expert_routing": True,
                "adaptive_resident_mode": "legacy", "speculative_prefetch": False})
if hasattr(m, "eval"):
    m.eval()

def enc_ids(p):
    e = tok.apply_chat_template([{"role": "user", "content": p}],
                                add_generation_prompt=True, return_tensors="pt")
    return e if isinstance(e, torch.Tensor) else e["input_ids"]

res = {"meta": {"expert_mb_estimate": EXPERT_MB}, "prompts": []}

# burn-in 2 prompts untimed
for p in PROMPTS[:2]:
    ids = enc_ids(p).to("cuda:0")
    with torch.no_grad():
        m.generate(ids, max_new_tokens=NEW, do_sample=False, pad_token_id=tok.eos_token_id)

time.sleep(30)  # settle: burn-in async prefetch tail can inflate GPU util
for p in PROMPTS[:4]:
    for attempt in range(30):
        la, gu = quiet()
        if la < 3 and gu < 5:
            break
        if attempt % 5 == 0:
            print(f"gate wait {la} {gu} attempt {attempt}", flush=True)
        time.sleep(60)
    assert la < 3 and gu < 5, f"quiet gate failed after 30 tries {la} {gu}"
    ids = enc_ids(p).to("cuda:0")
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
        with torch.no_grad():
            out = m.generate(ids, max_new_tokens=NEW, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        torch.cuda.synchronize()
    wall_ms = (time.perf_counter() - t0) * 1000.0
    ntok = int(out.shape[1] - ids.shape[1])
    ops = []
    h2d_cnt = h2d_us = d2h_cnt = d2h_us = 0
    for evt in prof.key_averages():
        ops.append({"op": evt.key[:120], "count": evt.count,
                    "cpu_us": round(evt.self_cpu_time_total, 1),
                    "cuda_us": round(getattr(evt, "self_device_time_total", 0.0), 1)})
        k = evt.key
        if "Memcpy HtoD" in k:
            h2d_cnt += evt.count; h2d_us += evt.self_device_time_total
        if "Memcpy DtoH" in k:
            d2h_cnt += evt.count; d2h_us += evt.self_device_time_total
    ops.sort(key=lambda x: -(x["cpu_us"] + x["cuda_us"]))
    res["prompts"].append({"prompt": p[:40], "wall_ms": round(wall_ms, 1), "tok": ntok,
                           "top_ops": ops[:40],
                           "memcpy": {"h2d_count": h2d_cnt, "h2d_cuda_us": round(h2d_us, 1),
                                      "h2d_mb_upper_bound_est": round(h2d_cnt * EXPERT_MB, 1),
                                      "d2h_count": d2h_cnt, "d2h_cuda_us": round(d2h_us, 1)}})
    print("profiled", p[:30], f"{wall_ms:.0f}ms {ntok}tok h2d={h2d_cnt}", flush=True)

res["meta"]["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open("/home/mfeth/exp825-s0/m2-profile.json", "w") as f:
    json.dump(res, f)
print("M2_DONE")

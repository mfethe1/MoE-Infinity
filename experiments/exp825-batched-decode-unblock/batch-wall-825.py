import os, json, time, random
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
os.environ.setdefault("MOE_INFINITY_UNVALIDATED_HW", "1")
import torch
from transformers import AutoTokenizer
from moe_infinity import MoE

MODEL = "/home/mfeth/models/OLMoE-1B-7B-0125-Instruct"
OFFLOAD = "/home/mfeth/moe-offload-olmoe-0125-r05"
cfg = {"offload_path": OFFLOAD, "device_memory_ratio": 0.50,
       "expert_eviction_policy": "lcnu", "num_threads": 4,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
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
NEW_TOK = 128

tok = AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token
tok.padding_side = "left"
m = MoE(MODEL, cfg)

def load5():
    with open("/proc/loadavg") as f:
        return float(f.read().split()[0])

def gpu1_util():
    out = os.popen("/usr/lib/wsl/lib/nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i 1").read().strip()
    try:
        return float(out)
    except ValueError:
        return 0.0

def wait_quiet(max_s=600):
    t0 = time.time()
    while time.time() - t0 < max_s:
        if load5() < 3.0 and gpu1_util() < 5.0:
            return {"waited_s": round(time.time() - t0, 1), "load5": load5(), "gpu1": gpu1_util()}
        time.sleep(15)
    return {"timeout": True, "load5": load5(), "gpu1": gpu1_util()}

def encode_b(b):
    enc = tok.apply_chat_template(
        [[{"role": "user", "content": p}] for p in PROMPTS[:b]],
        add_generation_prompt=True, padding=True, return_tensors="pt", return_dict=True)
    return enc["input_ids"].to("cuda:0")

out = {"meta": {"model": MODEL, "offload": OFFLOAD, "cfg": cfg, "new_tok": NEW_TOK,
                "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}
out["warm"] = wait_quiet()
with torch.no_grad():
    m.generate(encode_b(1), max_new_tokens=8, do_sample=False,
               pad_token_id=tok.eos_token_id)

arms = [b for b in (1, 2, 4, 8) for _ in range(3)]
random.seed(20261118)
random.shuffle(arms)
blocks = []
for b in arms:
    ids = encode_b(b)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        seq = m.generate(ids, max_new_tokens=NEW_TOK, do_sample=False,
                         pad_token_id=tok.eos_token_id)
    torch.cuda.synchronize()
    wall_ms = (time.perf_counter() - t0) * 1000.0
    blocks.append({"arm": b, "wall_ms": round(wall_ms, 1),
                   "n_gen": int(seq.shape[0]), "n_out_tok": int((seq.shape[1] - ids.shape[1]) * seq.shape[0])})
    print(json.dumps(blocks[-1]), flush=True)
out["blocks"] = blocks
out["meta"]["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open("/home/mfeth/exp825-s0/exp825-batchwalls.json", "w") as f:
    json.dump(out, f, indent=1)
print("WALLS_DONE")

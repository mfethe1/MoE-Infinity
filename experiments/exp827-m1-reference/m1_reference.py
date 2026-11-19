import os, sys, json, time
MODE = sys.argv[1]          # "ref" or "eng"
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
os.environ.setdefault("MOE_INFINITY_UNVALIDATED_HW", "1")
import torch
from transformers import AutoTokenizer

MODEL = "/home/mfeth/models/OLMoE-1B-7B-0125-Instruct"
NEW = 128
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

tok = AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token

def quiet():
    la = float(open("/proc/loadavg").read().split()[1])
    smi = os.popen("/usr/lib/wsl/lib/nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i 1").read().strip()
    return la, (int(smi) if smi.isdigit() else 99)

def enc_ids(p):
    e = tok.apply_chat_template([{"role": "user", "content": p}],
                                add_generation_prompt=True, return_tensors="pt")
    return e if isinstance(e, torch.Tensor) else e["input_ids"]

res = {"mode": MODE, "meta": {}, "blocks": []}

if MODE == "ref":
    from transformers import AutoModelForCausalLM
    try:
        m = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16,
                                                 device_map="cuda:0")
        res["meta"]["quant"] = "bf16"
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        try:
            m = AutoModelForCausalLM.from_pretrained(MODEL, load_in_8bit=True, device_map="cuda:0")
            res["meta"]["quant"] = "8bit-bnb"
        except Exception as e:
            res["meta"]["quant"] = "OOM-at-both"
            res["meta"]["error"] = repr(e)[:300]
            json.dump(res, open(f"/home/mfeth/exp825-s0/m1-{MODE}.json", "w"))
            print("REF_OOM_AT_LOAD"); sys.exit(3)
else:
    from moe_infinity import MoE
    m = MoE(MODEL, {"offload_path": "/home/mfeth/moe-offload-olmoe-0125-r05",
                    "device_memory_ratio": 0.50, "expert_eviction_policy": "lcnu",
                    "num_threads": 4, "gpu_only_expert_routing": True,
                    "adaptive_resident_mode": "legacy", "speculative_prefetch": False})
    res["meta"]["quant"] = "engine-bf16-offload0.50"
assert m is not None
if hasattr(m, "eval"):
    m.eval()

def gen_b1(p):
    ids = enc_ids(p).to("cuda:0")
    t0 = time.perf_counter()
    with torch.no_grad():
        out = m.generate(ids, max_new_tokens=NEW, min_new_tokens=NEW,
                         do_sample=False, pad_token_id=tok.eos_token_id)
    return (time.perf_counter() - t0) * 1000.0, int(out.shape[1] - ids.shape[1])

def gen_b8():
    seqs = [enc_ids(p)[0] for p in PROMPTS]
    maxlen = max(s.shape[0] for s in seqs)
    rows = []
    for s in seqs:  # LEFT pad (prereg): pad tokens prepend, generation continues from each prompt's real tail
        pad = torch.full((maxlen - s.shape[0],), tok.pad_token_id, dtype=s.dtype)
        rows.append(torch.cat([pad, s]))
    ids = torch.stack(rows).to("cuda:0")
    am = (ids != tok.pad_token_id).long()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = m.generate(ids, attention_mask=am, max_new_tokens=NEW, min_new_tokens=NEW,
                         do_sample=False, pad_token_id=tok.eos_token_id)
    return (time.perf_counter() - t0) * 1000.0, int(out.shape[0] * (out.shape[1] - ids.shape[1]))

def block(kind):
    la, gu = quiet()
    assert la < 3 and gu < 5, f"quiet gate failed {la} {gu}"
    if kind == "b1":
        walls, ntok = [], 0
        for p in PROMPTS:
            w, n = gen_b1(p)
            walls.append(w); ntok += n
        return {"kind": kind, "wall_ms": sum(walls), "tok": ntok, "per_prompt": walls}
    w, n = gen_b8()
    return {"kind": kind, "wall_ms": w, "tok": n}

# burn-in (untimed, not recorded)
for p in PROMPTS[:2]:
    gen_b1(p)
if MODE == "ref":
    gen_b8()

shapes = ["b1", "b8"] if MODE == "ref" else ["b1"]
for k in shapes:
    for rep in range(3):
        time.sleep(2)
        try:
            res["blocks"].append(block(k))
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            res["blocks"].append({"kind": k, "error": "OOM"})
            print(MODE, k, rep, "OOM", flush=True)
            break
        print(MODE, k, rep, "done", flush=True)

res["meta"]["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open(f"/home/mfeth/exp825-s0/m1-{MODE}.json", "w") as f:
    json.dump(res, f)
print("M1_DONE", MODE)

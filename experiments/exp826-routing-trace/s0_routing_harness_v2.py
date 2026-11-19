import os, json, time
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
os.environ.setdefault("MOE_INFINITY_UNVALIDATED_HW", "1")
import torch
from transformers import AutoTokenizer
from moe_infinity import MoE

MODEL = "/home/mfeth/models/OLMoE-1B-7B-0125-Instruct"
OFFLOAD = "/home/mfeth/moe-offload-olmoe-0125-r05"
cfg = {"offload_path": OFFLOAD, "device_memory_ratio": 0.50,
       "expert_eviction_policy": "lcnu", "num_threads": 4, "gpu_only_expert_routing": True,
       "adaptive_resident_mode": "legacy", "speculative_prefetch": False}
PROMPTS = [
    "Explain what a cache is in computing.",
    "Write a haiku about mountains.",
    "Summarize the water cycle.",
    "List three uses of copper.",
    "Describe a red-black tree.",
    "Give tips for better sleep.",
    "Explain why the sky is blue.",
    "Name the planets in order.",
    "Write a python function to reverse a list.",
    "What causes inflation?",
    "Explain how vaccines work.",
    "Translate 'good morning' to French.",
    "Describe the rules of chess.",
    "How does photosynthesis work?",
    "Write a limerick about the sea.",
    "Explain quantum entanglement simply.",
]
NEW_TOK = 64

tok = AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token
m = MoE(MODEL, cfg)
res = {"meta": {"model": MODEL, "new_tok": NEW_TOK, "n_prompts": len(PROMPTS),
                "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}

def find_hf(root, maxd=8):
    from collections import deque
    seen, q = set(), deque([(root, 0)])
    while q:
        o, d = q.popleft()
        if o is None or id(o) in seen or d > maxd:
            continue
        seen.add(id(o))
        if isinstance(o, torch.nn.Module) and any(
                n.endswith(".rotary_emb") for n, _ in o.named_modules()):
            return o
        dd = getattr(o, "__dict__", None)
        if isinstance(dd, dict):
            for v in list(dd.values()):
                q.append((v, d + 1))
    return None

hf = find_hf(m)
assert hf is not None, "HF model not found"
gates = []
for li, (n, mod) in enumerate([x for x in hf.named_modules() if x[0].endswith(".mlp.gate")]):
    gates.append((li, n, mod))
res["n_gates"] = len(gates)

trace = []
for li, n, gate in gates:
    orig = gate.forward
    def make_wrap(orig, layer_idx):
        def w(x):
            out = orig(x)
            with torch.no_grad():
                if torch.is_tensor(out):
                    idx = torch.topk(out, k=8, dim=-1).indices
                else:
                    idx = out[2]
                trace.append({"layer": layer_idx,
                              "top": idx.tolist()})
            return out
        return w
    gate.forward = make_wrap(orig, li)

def run_prompt(p):
    trace.clear()
    enc = tok.apply_chat_template([{"role": "user", "content": p}],
                                  add_generation_prompt=True, return_tensors="pt")
    ids = enc if isinstance(enc, torch.Tensor) else enc["input_ids"]
    ids = ids.to("cuda:0")
    with torch.no_grad():
        m.generate(ids, max_new_tokens=NEW_TOK, do_sample=False,
                   pad_token_id=tok.eos_token_id)
    per_layer_steps = {}
    for si, t in enumerate(trace):
        per_layer_steps.setdefault(t["layer"], []).append(t["top"])
    return {str(L): steps for L, steps in per_layer_steps.items()}

with torch.no_grad():
    m.generate(tok("warm", return_tensors="pt").input_ids.to("cuda:0"),
               max_new_tokens=8, do_sample=False, pad_token_id=tok.eos_token_id)

out = {}
for i, p in enumerate(PROMPTS):
    out[str(i)] = run_prompt(p)
    print("done", i, flush=True)
res["per_prompt_layer_experts"] = out
res["meta"]["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open("/home/mfeth/exp825-s0/exp826-routing.json", "w") as f:
    json.dump(res, f)
print("ROUTING_DONE")

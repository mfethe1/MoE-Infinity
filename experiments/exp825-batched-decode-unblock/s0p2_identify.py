import os, json
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
os.environ.setdefault("MOE_INFINITY_UNVALIDATED_HW", "1")
os.environ.setdefault("MOE_GROUPED_DECODE", "1")
import torch
from transformers import AutoTokenizer
from moe_infinity import MoE

MODEL = "/home/mfeth/models/OLMoE-1B-7B-0125-Instruct"
OFFLOAD = "/home/mfeth/moe-offload-olmoe-0125-r05"
cfg = {"offload_path": OFFLOAD, "device_memory_ratio": 0.50,
       "expert_eviction_policy": "lcnu", "num_threads": 4,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
tok = AutoTokenizer.from_pretrained(MODEL)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token
tok.padding_side = "left"
m = MoE(MODEL, cfg)
res = {"events": []}

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
res["hf_found"] = type(hf).__name__ if hf is not None else "NOT-FOUND"
if hf is not None:
    res["hf_first_param_device"] = str(next(hf.parameters()).device)
    rot = None
    for n, mod in hf.named_modules():
        if n.endswith(".rotary_emb"):
            rot = mod
            res["rotary_name"] = n
            break
    if rot is not None:
        res["rotary_inv_freq_device_at_rest"] = str(rot.inv_freq.device)
        orig_forward = rot.forward
        def logging_forward(x, position_ids, *a, **k):
            ev = {"x": str(x.device), "position_ids": str(position_ids.device),
                  "inv_freq": str(rot.inv_freq.device),
                  "x_shape": list(x.shape), "pos_shape": list(position_ids.shape)}
            res["events"].append(ev)
            return orig_forward(x, position_ids, *a, **k)
        rot.forward = logging_forward

def call(tag, prompts, n, explicit):
    enc = tok.apply_chat_template(
        [[{"role": "user", "content": p}] for p in prompts],
        add_generation_prompt=True, padding=True, return_tensors="pt", return_dict=True)
    ids = enc["input_ids"].to("cuda:0")
    n0 = len(res["events"])
    try:
        if explicit:
            mask = enc["attention_mask"].to("cuda:0")
            pos = (mask.cumsum(-1) - 1).clamp(min=0).to("cuda:0")
            with torch.no_grad():
                m.generate(ids, attention_mask=mask, position_ids=pos,
                           max_new_tokens=n, do_sample=False,
                           pad_token_id=tok.eos_token_id)
        else:
            with torch.no_grad():
                m.generate(ids, max_new_tokens=n, do_sample=False,
                           pad_token_id=tok.eos_token_id)
        res[tag] = "OK"
    except Exception as e:
        res[tag] = "CRASH:" + type(e).__name__
    res[tag + "_n_rotary_calls"] = len(res["events"]) - n0

call("PD_b1_bare", ["Say hello."], 8, False)
call("PB_b2_bare", ["Say hello.", "Say hi."], 8, False)
print("RESULT_JSON:" + json.dumps(res))

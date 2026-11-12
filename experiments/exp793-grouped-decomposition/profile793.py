#!/usr/bin/env python3
"""exp793: exp790 v4 decomposition on the PRODUCTION path: grouped decode ON
(MOE_GROUPED_DECODE=1 from launcher, no pop) at the promoted ratio 0.5.
Preregistered rule (before run): stall_est >=35% -> C++ barrier lane opens;
25-35% -> moderate, overlap target; <25% -> fetch-wait was the story, pivot churn.
Also corrects exp790 addendum (its "grouped" arm actually ran native: v4 popped
the env). Base: exp790 v4 self-time decomposition via CUDA events, SELF-time
(parent inclusive minus children inclusive), selective hooks (no expert-weight
modules -> low overhead). Buckets:
  embed/lm_head, norms, rotary, qkvo_proj, attn_core(attn self), router(gate),
  experts_native(OlmoeExperts.forward = native dispatch+grouped kernels),
  moe_glue(mlp self), layer_glue(decoder self), unaccounted = wall - sum.
Decode bucket = sum(32-tok) - sum(1-tok), one process, 8 prompts.
Decision rule (declared pre-run): next target = top non-grouped-kernel bucket
if >=25% of decode wall time. Note: experts_native INCLUDES host-side dispatch
stall inside forward; GPU-only grouped GEMM share is known ~18% from exp786.
"""
import argparse, json, os, re, time
from collections import deque

import torch

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--offload", required=True)
ap.add_argument("--prompts", required=True)
ap.add_argument("--max-new", type=int, default=32)
ap.add_argument("--out", required=True)
ap.add_argument("--threads", type=int, default=4)
ap.add_argument("--ratio", type=float, default=0.5)
a = ap.parse_args()

os.environ["MOE_INFINITY_UNVALIDATED_HW"] = "1"
assert os.environ.get("MOE_GROUPED_DECODE") == "1"  # exp793: launcher must set grouped ON

from transformers import AutoTokenizer  # noqa: E402
from moe_infinity import MoE  # noqa: E402

tok = AutoTokenizer.from_pretrained(a.model)
cfg = {"offload_path": a.offload, "device_memory_ratio": a.ratio,
       "expert_eviction_policy": "lcnu", "num_threads": a.threads,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
model = MoE(a.model, cfg)
dev = "cuda:0"


def _find_nn_module(root):
    seen, q = set(), deque([(root, 0)])
    while q:
        o, d = q.popleft()
        if o is None or id(o) in seen or d > 6:
            continue
        seen.add(id(o))
        if isinstance(o, torch.nn.Module) and any("layers" in n for n, _ in o.named_modules()):
            return o
        dd = getattr(o, "__dict__", None)
        if isinstance(dd, dict):
            for v in list(dd.values()):
                q.append((v, d + 1))
    return None


hf = _find_nn_module(model)
assert hf is not None

HOOK_RX = [
    ("qkvo_proj", re.compile(r"\.(q_proj|k_proj|v_proj|o_proj)$")),
    ("rotary", re.compile(r"rotary_emb$")),
    ("attn_mod", re.compile(r"\.self_attn$")),
    ("router_mod", re.compile(r"\.mlp\.gate$|\.mlp\.router$")),
    ("experts_mod", re.compile(r"\.mlp\.experts$")),
    ("moe_mod", re.compile(r"\.mlp$|^mlp$")),
    ("norm_mod", re.compile(r"norm$")),
    ("layer_mod", re.compile(r"^model\.layers\.\d+$")),
    ("lm_head", re.compile(r"lm_head$")),
    ("embed", re.compile(r"embed_tokens$")),
]
HOOKED = {}  # module_name -> bucket (also the parent map seed)
for name, mod in hf.named_modules():
    for b, rx in HOOK_RX:
        if rx.search(name):
            def _pre(m, i, _n=name):
                s, e = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                m._ev_s, m._ev_e = s, e
                s.record()
                return None  # never replace module inputs

            def _post(m, i, o, _n=name):
                m._ev_e.record()
                REC.append((_n, RUN[0], m._ev_s, m._ev_e))

            mod.register_forward_pre_hook(_pre)
            mod.register_forward_hook(_post)
            HOOKED[name] = b
            break
REC = []
RUN = ["x"]


def gen_ids(p):
    return tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                   return_tensors="pt", return_dict=True)["input_ids"].to(dev)


def gen(ids, n):
    with torch.no_grad():
        model.generate(ids, max_new_tokens=n, min_new_tokens=n,
                       do_sample=False, pad_token_id=tok.eos_token_id)


gen(gen_ids("Say hello."), 8)
REC.clear()
prompts = json.load(open(a.prompts))
walls = {}
for tag, n in (("pre", 1), ("full", a.max_new)):
    RUN[0] = tag
    ws = []
    for p in prompts:
        ids = gen_ids(p)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        gen(ids, n)
        torch.cuda.synchronize()
        ws.append(time.perf_counter() - t0)
    walls[tag] = ws
torch.cuda.synchronize()

incl = {t: {} for t in ("pre", "full")}
for name, tag, s, e in REC:
    incl[tag][name] = incl[tag].get(name, 0.0) + s.elapsed_time(e)


def children_of(name):
    pre = name + "."
    return [n2 for n2 in HOOKED if n2.startswith(pre) and "." not in n2[len(pre):]]


def self_times(tag):
    st = {}
    for name in HOOKED:
        kids = children_of(name)
        st[name] = incl[tag].get(name, 0.0) - sum(incl[tag].get(k, 0.0) for k in kids)
    return st


sp, sf = self_times("pre"), self_times("full")
BMAP = {
    "qkvo_proj": "qkvo_proj", "rotary": "rotary", "attn_mod": "attn_core",
    "router_mod": "router", "experts_mod": "experts_native", "moe_mod": "moe_glue",
    "norm_mod": "norm", "layer_mod": "layer_glue", "lm_head": "lm_head", "embed": "embed",
}
dec, cnt = {}, {}
for name in HOOKED:
    d = sf.get(name, 0) - sp.get(name, 0)
    if d > 0:
        b = BMAP[HOOKED[name]]
        dec[b] = dec.get(b, 0.0) + d
        cnt[b] = cnt.get(b, 0) + 1
wall_dec_ms = (sum(walls["full"]) - sum(walls["pre"])) * 1000
T = sum(dec.values())
dec["unaccounted"] = wall_dec_ms - T
order = sorted(dec.items(), key=lambda x: -x[1])
shares = {b: round(v / wall_dec_ms * 100, 1) for b, v in order}
gpu_math = sum(v for b, v in dec.items() if b in ("qkvo_proj", "rotary", "router"))
ng = [(b, v) for b, v in order if b != "experts_native"]
top_b, top_v = ng[0] if ng else ("none", 0)
decision = f"TARGET={top_b}" if top_v / wall_dec_ms >= 0.25 else "NO-BUCKET>=25%"
res = {"model": a.model, "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
       "decode_wall_ms": round(wall_dec_ms, 1),
       "decode_ms_self": {b: round(v, 1) for b, v in order},
       "shares_pct_of_wall": shares,
       "experts_native_share_pct": round(dec.get("experts_native", dec.get("moe_glue", 0)) / wall_dec_ms * 100, 1),
       "grouped_gemm_known_pct": 18.0,
       "dispatch_stall_est_pct": round(max(dec.get("experts_native", dec.get("moe_glue", 0)) / wall_dec_ms * 100 - 18.0, 0), 1),
       "decision_rule": "top non-experts bucket >=25% of decode wall",
       "decision": decision,
       "walls_pre_s": [round(w, 3) for w in walls["pre"]],
       "walls_full_s": [round(w, 3) for w in walls["full"]]}
json.dump(res, open(a.out, "w"), indent=1)
print(json.dumps({k: res[k] for k in ("decode_wall_ms", "decode_ms_self", "shares_pct_of_wall",
                                      "dispatch_stall_est_pct", "decision")}, indent=1))

#!/usr/bin/env python3
"""exp790 v3: decode-residual attribution via CUDA events on module forwards
(CUPTI dead in this WSL for both torch.profiler and nsys).
Pre/post forward hooks on all named modules + a wrapped F.sdpa; per-call
cudaEvent pairs; per-bucket decode time = sum(32-tok run) - sum(1-tok run)
in one process. Buckets (by module name):
  attn_proj  = q/k/v/o projections        sdpa = attention core
  moe_block  = whole sparse-MoE block (incl. router+experts+dispatch)
  router     = mlp.gate linear (subset of moe_block)
  norm       = all layernorms             lm_head/embed = head
  unaccounted= wall - sum(buckets)
Decision rule (declared pre-run, unchanged): next kernel target = top
non-grouped bucket if >=25% of decode stream time.
"""
import argparse, json, os, re, time

import torch
import torch.nn.functional as F

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--offload", required=True)
ap.add_argument("--prompts", required=True)
ap.add_argument("--max-new", type=int, default=32)
ap.add_argument("--out", required=True)
ap.add_argument("--threads", type=int, default=4)
a = ap.parse_args()

os.environ["MOE_INFINITY_UNVALIDATED_HW"] = "1"
os.environ.pop("MOE_GROUPED_DECODE", None)

from transformers import AutoTokenizer  # noqa: E402
from moe_infinity import MoE  # noqa: E402

tok = AutoTokenizer.from_pretrained(a.model)
cfg = {"offload_path": a.offload, "device_memory_ratio": 0.25,
       "expert_eviction_policy": "lcnu", "num_threads": a.threads,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
model = MoE(a.model, cfg)
dev = "cuda:0"


def _find_nn_module(root):
    """BFS the MoE wrapper's attribute graph for the underlying nn.Module tree."""
    from collections import deque
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
assert hf is not None, "no inner nn.Module with 'layers' found under MoE wrapper"
print("inner HF module:", type(hf).__name__, len(list(hf.named_modules())), "modules")

RECORDS = []  # (run_tag, bucket, start_ev, end_ev)
RUN = ["x"]


def mk_hooks(name):
    def pre(mod, inp):
        s = torch.cuda.Event(enable_timing=True)
        e = torch.cuda.Event(enable_timing=True)
        s.record()
        mod._ev_pair = (s, e)

    def post(mod, inp, out):
        s, e = getattr(mod, "_ev_pair", None) or (None, None)
        if s is None:
            return
        e.record()
        RECORDS.append((RUN[0], name, s, e))
    return pre, post


for name, mod in list(hf.named_modules()):
    if name == "":
        continue
    pre, post = mk_hooks(name)
    mod.register_forward_pre_hook(pre)
    mod.register_forward_hook(post)

_sdpa = F.scaled_dot_product_attention


def sdpa_timed(*args, **kw):
    s = torch.cuda.Event(enable_timing=True)
    e = torch.cuda.Event(enable_timing=True)
    s.record()
    out = _sdpa(*args, **kw)
    e.record()
    RECORDS.append((RUN[0], "__sdpa", s, e))
    return out


F.scaled_dot_product_attention = sdpa_timed


def gen_ids(p):
    return tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                   return_tensors="pt", return_dict=True)["input_ids"].to(dev)


def gen(ids, n):
    with torch.no_grad():
        model.generate(ids, max_new_tokens=n, min_new_tokens=n,
                       do_sample=False, pad_token_id=tok.eos_token_id)


BUCKET_RX = [
    ("router", re.compile(r"mlp\.gate$|\.gate$")),
    ("attn_proj", re.compile(r"(q_proj|k_proj|v_proj|o_proj)$")),
    ("attn_block", re.compile(r"self_attn$")),
    ("moe_block", re.compile(r"\.mlp$|^mlp$")),
    ("norm", re.compile(r"norm$")),
    ("head", re.compile(r"lm_head$|embed_tokens$")),
]


def bucket_of(name):
    if name == "__sdpa":
        return "sdpa"
    for b, rx in BUCKET_RX:
        if rx.search(name):
            return b
    return "other_mod"


gen(gen_ids("Say hello."), 8)  # warmup (records tagged 'warmup', excluded)
RECORDS.clear()
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

sums = {t: {} for t in ("pre", "full")}
counts = {t: {} for t in ("pre", "full")}
for tag, name, s, e in RECORDS:
    b = bucket_of(name)
    dt = s.elapsed_time(e)  # ms
    sums[tag][b] = sums[tag].get(b, 0.0) + dt
    counts[tag][b] = counts[tag].get(b, 0) + 1

dec = {}
for b in sums["full"]:
    d = sums["full"][b] - sums["pre"].get(b, 0.0)
    if d > 0:
        dec[b] = d
T = sum(dec.values())
wall_dec = sum(walls["full"]) - sum(walls["pre"])
shares = {b: round(v / T, 4) for b, v in sorted(dec.items(), key=lambda x: -x[1])}
ng = [(b, v / T) for b, v in dec.items() if b not in ("moe_block", "router")]
ng.sort(key=lambda x: -x[1])
top_b, top_s = ng[0] if ng else ("none", 0.0)
decision = f"TARGET={top_b}" if top_s >= 0.25 else "NO-BUCKET>=25%"
res = {"model": a.model, "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
       "decode_ms_stream": round(T, 1), "decode_ms_wall": round(wall_dec * 1000, 1),
       "stream_vs_wall": round(T / (wall_dec * 1000), 3),
       "decode_ms_by_bucket": {b: round(v, 1) for b, v in sorted(dec.items(), key=lambda x: -x[1])},
       "shares": shares, "counts_decode": {b: counts["full"].get(b, 0) - counts["pre"].get(b, 0)
                                           for b in dec},
       "decision_rule": "top non-grouped bucket >=25% of decode stream time",
       "decision": decision, "top_non_grouped": [top_b, round(top_s, 4)],
       "walls_pre_s": [round(w, 3) for w in walls["pre"]],
       "walls_full_s": [round(w, 3) for w in walls["full"]]}
json.dump(res, open(a.out, "w"), indent=1)
print(json.dumps({k: res[k] for k in ("decode_ms_stream", "decode_ms_wall", "stream_vs_wall",
                                      "shares", "decision")}, indent=1))

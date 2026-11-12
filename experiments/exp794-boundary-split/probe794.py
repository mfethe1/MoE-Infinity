#!/usr/bin/env python3
"""exp794: split the ~40% dispatch stall at the pybind boundary, zero rebuild.
Monkey-patch perf_counter timers around expert_executor.dispatch_local() and
wait_dispatch_local(). Two arms: ratio 0.25 vs 0.5 (grouped ON, production cfg).
Preregistered rule (before run): W(r) = wait_s / decode_wall at ratio r.
  fetch_wait_share ~= W(0.25) - W(0.5);  handoff_share ~= W(0.5).
  W(0.5) >= 15% -> handoff/barrier dominates -> C++ async-wait / cross-layer
  pipeline is the lever. W(0.5) < 8% with large delta -> prefetch lever instead.
  D(r) = dispatch(enqueue)_s / wall >= 10% at either arm -> enqueue path itself
  is a separate cost center.
No CUDA events; host timers only; decode = 32-tok gen minus 1-tok warm, 8 prompts.
"""
import argparse, json, os, time

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--offload", required=True)
ap.add_argument("--prompts", required=True)
ap.add_argument("--ratio", type=float, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--max-new", type=int, default=32)
a = ap.parse_args()

os.environ["MOE_INFINITY_UNVALIDATED_HW"] = "1"
assert os.environ.get("MOE_GROUPED_DECODE") == "1"

from transformers import AutoTokenizer  # noqa: E402
from moe_infinity import MoE  # noqa: E402
import torch  # noqa: E402

tok = AutoTokenizer.from_pretrained(a.model)
cfg = {"offload_path": a.offload, "device_memory_ratio": a.ratio,
       "expert_eviction_policy": "lcnu", "num_threads": 4,
       "gpu_only_expert_routing": True, "adaptive_resident_mode": "legacy",
       "speculative_prefetch": False}
model = MoE(a.model, cfg)
dev = "cuda:0"

# ---- find one expert_executor and instrument the shared instance ----
exec_obj = None


def find_exec(o, depth=0, seen=None):
    global exec_obj
    seen = seen if seen is not None else set()
    if o is None or id(o) in seen or depth > 6 or exec_obj is not None:
        return
    seen.add(id(o))
    ex = getattr(o, "expert_executor", None)
    if ex is not None and hasattr(ex, "dispatch_local"):
        exec_obj = ex
        return
    if isinstance(o, torch.nn.Module):
        for ch in o.children():
            find_exec(ch, depth + 1, seen)
        return
    dd = getattr(o, "__dict__", None)
    if isinstance(dd, dict):
        for v in list(dd.values()):
            find_exec(v, depth + 1, seen)


find_exec(model)
assert exec_obj is not None, "expert_executor not found"

ACC = {"dispatch_s": 0.0, "wait_s": 0.0, "calls": 0}
_d = exec_obj.dispatch_local
_w = exec_obj.wait_dispatch_local


def timed_dispatch(*args, **kwargs):
    t0 = time.perf_counter()
    r = _d(*args, **kwargs)
    ACC["dispatch_s"] += time.perf_counter() - t0
    ACC["calls"] += 1
    return r


def timed_wait():
    t0 = time.perf_counter()
    r = _w()
    ACC["wait_s"] += time.perf_counter() - t0
    return r


exec_obj.dispatch_local = timed_dispatch
exec_obj.wait_dispatch_local = timed_wait

# ---- prompts: same protocol as probe791 (8 prompts, warm 1-tok then 32-tok) ----
prompts = json.load(open(a.prompts))
if isinstance(prompts, dict):
    prompts = list(prompts.values())
texts = [p if isinstance(p, str) else p.get("prompt", p.get("text", "")) for p in prompts][:8]

walls, one_tok_walls = [], []


def gen(text, max_new):
    ids = tok(text, return_tensors="pt").to(dev)
    t0 = time.perf_counter()
    with torch.no_grad():
        model.generate(**ids, max_new_tokens=max_new, do_sample=False)
    return time.perf_counter() - t0


for t in texts:
    _ = gen(t, 1)          # warm / compile / resident settle
    one_tok_walls.append(gen(t, 1))
    walls.append(gen(t, a.max_new))

decode_wall = sum(walls) - sum(one_tok_walls)
res = {
    "ratio": a.ratio,
    "decode_wall_s": round(decode_wall, 3),
    "dispatch_s": round(ACC["dispatch_s"], 3),
    "wait_s": round(ACC["wait_s"], 3),
    "calls": ACC["calls"],
    "wait_share_pct": round(100 * ACC["wait_s"] / decode_wall, 1),
    "dispatch_share_pct": round(100 * ACC["dispatch_s"] / decode_wall, 1),
    "wait_ms_per_call": round(1000 * ACC["wait_s"] / max(ACC["calls"], 1), 2),
    "dispatch_ms_per_call": round(1000 * ACC["dispatch_s"] / max(ACC["calls"], 1), 2),
}
json.dump(res, open(a.out, "w"), indent=1)
print(json.dumps(res))

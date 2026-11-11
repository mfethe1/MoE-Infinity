"""exp779 engine arm B (manual decode loop, additive reworking of engine_arm776).
Identical envelope/flags/rows-schema to engine_arm776.py; the ONLY behavioral
change is gen(): HF model.generate(...) replaced by a minimal manual greedy
decode loop (prefill + argmax steps) over the SAME MoE-Infinity-wrapped model,
using transformers DynamicCache. Removes per-token generate machinery (logits
processors, stopping criteria, prepare_inputs_for_generation, sampler
dispatch) while keeping expert offload hooks (they live on module forwards).
arm field in res JSON: "B-manual-dynamic". Exit code 3 on B-arm-specific
setup failure (forward resolution / DynamicCache import) with B-ARM-ERROR
printed, so the runner records an honest cell failure instead of voiding.
"""
import argparse, hashlib, json, os, platform, subprocess, sys, time, inspect

import torch
from transformers import AutoTokenizer

try:
    from transformers.cache_utils import DynamicCache
except ImportError:
    print("B-ARM-ERROR: transformers.cache_utils.DynamicCache unavailable")
    sys.exit(3)


def find_stats(obj, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if obj is None or id(obj) in seen or depth > 4:
        return None
    seen.add(id(obj))
    g = getattr(obj, "get_expert_policy_stats", None)
    if callable(g):
        return g
    g = getattr(obj, "get_policy_stats", None)
    if callable(g) and depth > 0:
        return g
    for name in ("engine", "archer_engine", "prefetcher", "expert_prefetcher", "model_offload",
                 "offload_engine", "expert_executor", "dispatcher", "_engine"):
        r = find_stats(getattr(obj, name, None), depth + 1, seen)
        if r:
            return r
    return None


def _walk(obj, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if obj is None or id(obj) in seen or depth > 5 or isinstance(obj, (int, float, str, bytes, torch.Tensor)):
        return
    seen.add(id(obj)); yield obj
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        for v in list(d.values()):
            yield from _walk(v, depth + 1, seen)


def find_attr(root, method):
    for o in _walk(root):
        if callable(getattr(type(o), method, None)) or (type(o).__module__.startswith("moe_infinity._") and hasattr(o, method)):
            return o
    return None


def find_obj(root, name):
    for o in _walk(root):
        v = getattr(o, "__dict__", {}).get(name) if isinstance(getattr(o, "__dict__", None), dict) else None
        if v is not None:
            return v
    return None


def snap(getter):
    if getter is None:
        return {}
    try:
        return {str(k): int(v) for k, v in dict(getter()).items()}
    except Exception as e:  # report, never fabricate
        return {"_error": repr(e)}


def resolve_forward(model):
    """First candidate whose forward() accepts input_ids/past_key_values/use_cache."""
    cands = [model, getattr(model, "model", None), getattr(model, "archer_model", None),
             getattr(model, "inner_model", None)]
    for c in cands:
        f = getattr(c, "forward", None)
        if not callable(f):
            continue
        try:
            sig = inspect.signature(f)
        except (ValueError, TypeError):
            continue
        ps = sig.parameters
        if "input_ids" in ps and ("past_key_values" in ps or "past_key_values" in str(ps)):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--offload", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--ratio", type=float, required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--pidfile", default=None)
    ap.add_argument("--max-new", type=int, default=128)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--gpu-route", choices=["on", "off"], required=True)
    ap.add_argument("--spec-prefetch", choices=["on", "off"], required=True)
    ap.add_argument("--spec-overlap", choices=["on", "off"], required=True)
    ap.add_argument("--overlap-policy", choices=["off", "observe", "enforce"], required=True)
    a = ap.parse_args()

    from moe_infinity import MoE

    prompts = json.load(open(a.prompts))
    if a.pidfile: open(a.pidfile, 'w').write(str(os.getpid()) + '\n')
    tok = AutoTokenizer.from_pretrained(a.model)
    cfg = {"offload_path": a.offload, "device_memory_ratio": a.ratio,
           "expert_eviction_policy": a.policy, "num_threads": a.threads,
           "gpu_only_expert_routing": a.gpu_route == "on",
           "speculative_prefetch": a.spec_prefetch == "on",
           "speculative_prefetch_overlap": a.spec_overlap == "on",
           "overlap_prefetch_policy": a.overlap_policy}
    t0 = time.perf_counter()
    model = MoE(a.model, cfg)
    load_s = time.perf_counter() - t0
    fwd_model = resolve_forward(model)
    if fwd_model is None:
        print("B-ARM-ERROR: no forward candidate accepting input_ids/past_key_values")
        sys.exit(3)
    print(f"B-ARM forward host: {type(fwd_model).__module__}.{type(fwd_model).__name__}", flush=True)
    getter = find_stats(model)
    disp, acfg = find_attr(model, "get_routing_stats"), find_obj(model, "archer_config")
    rget = (lambda: disp.get_routing_stats()) if disp is not None else None
    eff_threads = getattr(acfg, "num_threads", None)
    dev = "cuda:0"

    LASTWIN = [0.0, 0.0]

    def gen(p, n):
        """Manual greedy decode: n tokens = 1 prefill forward + (n-1) step forwards."""
        ids = tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                      return_tensors="pt", return_dict=True)["input_ids"].to(dev)
        torch.cuda.synchronize()
        t = time.perf_counter(); w0 = time.time()
        tokens = []
        with torch.no_grad():
            cache = DynamicCache()
            out = fwd_model(input_ids=ids, past_key_values=cache, use_cache=True)
            nxt = int(out.logits[0, -1].argmax().item())
            tokens.append(nxt)
            for _ in range(n - 1):
                out = fwd_model(input_ids=torch.tensor([[tokens[-1]]], device=dev),
                                past_key_values=cache, use_cache=True)
                nxt = int(out.logits[0, -1].argmax().item())
                tokens.append(nxt)
        torch.cuda.synchronize()
        dt = time.perf_counter() - t
        LASTWIN[:] = [w0, time.time()]
        return ids.shape[1], tokens, dt

    for i in range(a.warmup):
        gen("Say hello.", 8)
    s0 = snap(getter)
    rows = []
    for i, p in enumerate(prompts):
        b = snap(getter)
        rb = snap(rget)
        n_in, _, t1 = gen(p, 1)
        n_in, new, tf = gen(p, a.max_new)
        e = snap(getter)
        re_ = snap(rget)
        rows.append({"i": i, "n_in": n_in, "n_new": len(new), "t_1tok_s": t1, "t_full_s": tf, "win_full": list(LASTWIN),
                     "decode_tok_s": (len(new) - 1) / max(tf - t1, 1e-9),
                     "out_sha": hashlib.sha256(json.dumps(new).encode()).hexdigest()[:16],
                     "out_ids": new,
                     "stats_delta": {k: e.get(k, 0) - b.get(k, 0) for k in e if not k.startswith("_")},
                     "routing_delta": {k: re_.get(k, 0) - rb.get(k, 0) for k in re_ if not k.startswith("_")}})
        print(f"[B-manual r={a.ratio} sp={a.spec_prefetch} so={a.spec_overlap} op={a.overlap_policy}] prompt {i}: {rows[-1]['decode_tok_s']:.2f} tok/s "
              f"hits+{rows[-1]['stats_delta'].get('policy_routed_hits')} "
              f"miss+{rows[-1]['stats_delta'].get('policy_routed_misses')}", flush=True)
    s1 = snap(getter)
    res = {"arm": "B-manual-dynamic", "policy": a.policy, "ratio": a.ratio, "model": a.model, "max_new": a.max_new,
           "load_s": load_s, "stats_getter": getattr(getter, "__qualname__", repr(getter)),
           "stats_start": s0, "stats_end": s1, "rows": rows,
           "torch": torch.__version__, "cuda": torch.version.cuda,
           "gpu": torch.cuda.get_device_name(0), "host": platform.node(),
           "visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
           "threads_requested": a.threads, "threads_effective": eff_threads, "gpu_route_requested": a.gpu_route, "gpu_route_effective": getattr(acfg, "gpu_only_expert_routing", None),
           "spec_prefetch_requested": a.spec_prefetch, "spec_prefetch_effective": getattr(acfg, "speculative_prefetch", None),
           "spec_overlap_requested": a.spec_overlap, "spec_overlap_effective": getattr(acfg, "speculative_prefetch_overlap", None),
           "overlap_policy_requested": a.overlap_policy, "overlap_policy_effective": getattr(acfg, "overlap_prefetch_policy", None),
           "overlap_ewma_effective": getattr(acfg, "overlap_prefetch_ewma_alpha", None),
           "overlap_safety_effective": getattr(acfg, "overlap_prefetch_safety_factor", None),
           "overlap_window_effective": getattr(acfg, "overlap_prefetch_max_window_bytes", None),
           "overlap_inflight_effective": getattr(acfg, "overlap_prefetch_max_inflight_bytes", None),
           "routing_getter": disp is not None,
           "env_unvalidated_hw": os.environ.get("MOE_INFINITY_UNVALIDATED_HW"),
           "env_grouped_decode": os.environ.get("MOE_GROUPED_DECODE"),
           "env_profile_io": os.environ.get("MOE_INFINITY_PROFILE_IO"),
           "env_profile_io_out": os.environ.get("MOE_INFINITY_PROFILE_IO_OUT"),
           "env_exp752_mode": os.environ.get("MOEI_EXP752_MODE"),
           "mem_alloc_gb": torch.cuda.max_memory_allocated(0) / 2**30}
    json.dump(res, open(a.out, "w"), indent=1)
    print("DONE", a.out, flush=True)


if __name__ == "__main__":
    main()

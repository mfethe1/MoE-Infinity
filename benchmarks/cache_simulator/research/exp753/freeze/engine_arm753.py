"""exp753 engine arm (from exp746/exp752 engine_arm.py; adds --arm-name banner,
--timing on|off -> set_overlap_compute_timing_enabled via existing engine hook,
CLOCK_MONOTONIC ns windows per row (win_mono, joins to C++ steady_clock trace),
trace env readback. Decode protocol, config keys and stats snapping unchanged:
1-token probe then full run; decode ms/tok = (t_full - t_1tok)/(n_new-1).

Runs MoE-Infinity (upstream 0337988 + exp753 instrumentation, private build) on a
fixed prompt set with greedy decoding; reports decode timing, output token ids and
policy/routing counters. Usage:
  python engine_arm753.py --model DIR --offload DIR --policy lcnu --ratio 0.75 \
      --prompts prompts.json --max-new 64 --out arm.json --arm-name B \
      --threads 4 --gpu-route on --timing off
"""
import argparse, hashlib, json, os, platform, subprocess, sys, time

import torch
from transformers import AutoTokenizer


def find_stats(obj, depth=0, seen=None):
    """Locate the native engine's get_expert_policy_stats() under the MoE object."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--offload", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--ratio", type=float, required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--max-new", type=int, default=128)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--gpu-route", choices=["on", "off"], required=True)
    ap.add_argument("--arm-name", required=True)
    ap.add_argument("--timing", choices=["on", "off"], default="off")
    a = ap.parse_args()

    trace_on = os.environ.get("MOEI_EXP753_TRACE") == "1"
    print(f"exp753 mode={a.arm_name} trace={'1' if trace_on else '0'} timing={a.timing}", flush=True)

    from moe_infinity import MoE

    prompts = json.load(open(a.prompts))
    tok = AutoTokenizer.from_pretrained(a.model)
    cfg = {"offload_path": a.offload, "device_memory_ratio": a.ratio,
           "expert_eviction_policy": a.policy, "num_threads": a.threads,
           "gpu_only_expert_routing": a.gpu_route == "on"}
    t0 = time.perf_counter()
    model = MoE(a.model, cfg)
    load_s = time.perf_counter() - t0
    getter = find_stats(model)
    disp, acfg = find_attr(model, "get_routing_stats"), find_obj(model, "archer_config")
    rget = (lambda: disp.get_routing_stats()) if disp is not None else None
    eff_threads = getattr(acfg, "num_threads", None)
    dev = "cuda:0"
    # R6 / ERRATUM-752-TR32: TF32 must be OFF; pin and record readback.
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    allow_tf32 = {"matmul": bool(torch.backends.cuda.matmul.allow_tf32),
                  "cudnn": bool(torch.backends.cudnn.allow_tf32)}

    # exp753: existing compute-timing hook (C arm). Setter is the pybind object
    # exposing set_overlap_compute_timing_enabled; enabling only starts event
    # pairs + sample capture (engine drains samples as in production).
    timing_setter_found = False
    timing_set_error = None
    if a.timing == "on":
        try:
            tset = find_attr(model, "set_overlap_compute_timing_enabled")
            if tset is None:
                timing_set_error = "setter-not-found"
            else:
                tset.set_overlap_compute_timing_enabled(True)
                timing_setter_found = True
        except Exception as e:
            timing_set_error = repr(e)
    print(f"exp753 timing_setter_found={timing_setter_found} err={timing_set_error}", flush=True)

    LASTWIN = [0, 0]  # CLOCK_MONOTONIC ns (same clock as C++ steady_clock on Linux)

    def gen(p, n):
        ids = tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                      return_tensors="pt", return_dict=True)["input_ids"].to(dev)
        torch.cuda.synchronize()
        t = time.perf_counter(); w0 = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=n, min_new_tokens=n, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        torch.cuda.synchronize()
        dt = time.perf_counter() - t
        w1 = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        LASTWIN[:] = [w0, w1]
        new = out[0, ids.shape[1]:].tolist()
        return ids.shape[1], new, dt, [w0, w1]

    for i in range(a.warmup):
        gen("Say hello.", 8)
    s0 = snap(getter)
    rows = []
    for i, p in enumerate(prompts):
        b = snap(getter)
        rb = snap(rget)
        # prefill-only probe (1 token) then full run; decode time = full - prefill probe.
        # Both CLOCK_MONOTONIC windows recorded (probe window is the trace join key
        # for the 1-token run; fix #8 — never overwritten silently).
        n_in, _, t1, win_probe = gen(p, 1)
        n_in, new, tf, win_full = gen(p, a.max_new)
        e = snap(getter)
        re_ = snap(rget)
        dt_raw = tf - t1  # fix #9: raw delta recorded; nonpositive is an anomaly
        rows.append({"i": i, "n_in": n_in, "n_new": len(new), "t_1tok_s": t1, "t_full_s": tf,
                     "t_full_minus_1tok_s": dt_raw,
                     "win_mono": win_full, "win_mono_probe": win_probe,
                     "decode_tok_s": (len(new) - 1) / dt_raw if dt_raw > 0 else None,
                     "out_sha": hashlib.sha256(json.dumps(new).encode()).hexdigest()[:16],
                     "out_ids": new,
                     "stats_delta": {k: e.get(k, 0) - b.get(k, 0) for k in e if not k.startswith("_")},
                     "routing_delta": {k: re_.get(k, 0) - rb.get(k, 0) for k in re_ if not k.startswith("_")}})
        ts = rows[-1]['decode_tok_s']
        print(f"[{a.policy} r={a.ratio}] prompt {i}: "
              f"{ts:.2f} tok/s " if ts is not None else f"[{a.policy} r={a.ratio}] prompt {i}: "
              f"DECODE-DELTA-NONPOSITIVE({dt_raw:.6f}s) "
              f"hits+{rows[-1]['stats_delta'].get('policy_routed_hits')} "
              f"miss+{rows[-1]['stats_delta'].get('policy_routed_misses')}", flush=True)
    s1 = snap(getter)
    res = {"arm": a.arm_name, "policy": a.policy, "ratio": a.ratio, "model": a.model, "max_new": a.max_new,
           "load_s": load_s, "stats_getter": getattr(getter, "__qualname__", repr(getter)),
           "stats_start": s0, "stats_end": s1, "rows": rows,
           "torch": torch.__version__, "cuda": torch.version.cuda,
           "allow_tf32": allow_tf32,
           "gpu": torch.cuda.get_device_name(0), "host": platform.node(),
           "visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
           "threads_requested": a.threads, "threads_effective": eff_threads,
           "gpu_route_requested": a.gpu_route, "gpu_route_effective": getattr(acfg, "gpu_only_expert_routing", None),
           "timing_requested": a.timing, "timing_setter_found": timing_setter_found,
           "timing_set_error": timing_set_error,
           "trace_env": os.environ.get("MOEI_EXP753_TRACE"),
           "trace_file_env": os.environ.get("MOEI_EXP753_TRACE_FILE"),
           "routing_getter": disp is not None,
           "env_unvalidated_hw": os.environ.get("MOE_INFINITY_UNVALIDATED_HW"),
           "env_grouped_decode": os.environ.get("MOE_GROUPED_DECODE"),
           "mem_alloc_gb": torch.cuda.max_memory_allocated(0) / 2**30}
    json.dump(res, open(a.out, "w"), indent=1)
    print("DONE", a.out, flush=True)


if __name__ == "__main__":
    main()

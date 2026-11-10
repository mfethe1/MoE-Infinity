"""exp750 engine arm runner (one arm per fresh process). Copy of engine_arm742.py with the exp750 timer fix.

The exp742 quality pass (64 greedy tokens with top-16 RAW logits capture) is kept verbatim and is NOT used for
any timing metric (its duration is stored as t_quality_s, informational only). The exp742 t_1tok/t_full/
decode_tok_s computation is dropped. After the quality pass, each prompt gets --timed-reps timed passes with no
capture hook active; every timing synchronizes ALL visible CUDA devices before and after the generate call
(exp742 synchronized only the current device). Usage:
  python engine_arm750.py --model DIR --offload DIR --policy lcnu --ratio 0.2 \
      --prompts prompts.json --max-new 64 --warmup 1 --timed-reps 3 --out arm.json
"""
import argparse, hashlib, json, os, platform, statistics, subprocess, sys, time

import torch
from transformers import AutoTokenizer


def sync_all():
    """Synchronize every visible CUDA device (exp742 synced only the current device)."""
    for d in range(torch.cuda.device_count()):
        torch.cuda.synchronize(d)


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


def snap(getter):
    if getter is None:
        return {}
    try:
        return {str(k): int(v) for k, v in dict(getter()).items()}
    except Exception as e:  # report, never fabricate
        return {"_error": repr(e)}


def top16(logits, tokens):
    """Per-step top-16 of the RAW logits -> (ids, float32 values, chosen_val). Each step is [vocab] or [1, vocab];
    chosen_val is the full step tensor's value at the generated token (taken before topk)."""
    ids, vals, chosen = [], [], []
    for step, t in zip(logits, tokens):
        full = step.reshape(-1).float()
        chosen.append(full[t].item())
        v, i = torch.topk(full, k=16)
        ids.append(i.tolist())
        vals.append(v.tolist())
    return ids, vals, chosen


def store_so():
    """Path of the loaded _store extension module, if importable; else None."""
    try:
        import moe_infinity._store as st
        return st.__file__
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--offload", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--ratio", type=float, required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--max-new", type=int, default=128)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--timed-reps", type=int, default=3)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from moe_infinity import MoE

    prompts = json.load(open(a.prompts))
    tok = AutoTokenizer.from_pretrained(a.model)
    cfg = {"offload_path": a.offload, "device_memory_ratio": a.ratio,
           "expert_eviction_policy": a.policy}
    t0 = time.perf_counter()
    model = MoE(a.model, cfg)
    load_s = time.perf_counter() - t0
    getter = find_stats(model)
    dev = "cuda:0"

    # Batch-1 MoE.generate takes the native GenerationEngine path (big_modeling.py), which ignores
    # output_logits/return_dict_in_generate and returns a plain tensor. There, record the raw logits
    # its greedy _sample() argmaxes over (no logits processors on that path) by wrapping _sample on
    # the instance; the engine itself is untouched. The HF path keeps using .sequences/.logits.
    cap = {"rec": None}
    native = getattr(model, "_native_generation_engine", None)
    if native is not None:
        orig_sample = native._sample

        def sample_rec(step_logits, params):
            if cap["rec"] is not None:
                cap["rec"].append(step_logits[-1].detach().float())
            return orig_sample(step_logits, params)

        native._sample = sample_rec

    def gen(p, n, logits=False):
        ids = tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                      return_tensors="pt", return_dict=True)["input_ids"].to(dev)
        extra = {"output_logits": True, "return_dict_in_generate": True} if logits else {}
        cap["rec"] = [] if logits else None
        sync_all()
        t = time.perf_counter()
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=n, min_new_tokens=n, do_sample=False,
                                 pad_token_id=tok.eos_token_id, **extra)
        sync_all()
        dt = time.perf_counter() - t
        rec, cap["rec"] = cap["rec"], None
        steps, src = None, None
        if logits and hasattr(out, "sequences"):
            seq, steps, src = out.sequences, out.logits, "hf_output_logits"
        elif logits:
            seq, steps, src = out, rec, "native_sample_hook"
        else:
            seq = out.sequences if hasattr(out, "sequences") else out
        new = seq[0, ids.shape[1]:].tolist()
        if logits and len(steps) != len(new):  # fail closed: one logit row per new token
            raise RuntimeError(f"logit steps {len(steps)} != new tokens {len(new)} ({src})")
        top = top16(steps, new) if logits else None
        return ids.shape[1], new, dt, top, src

    for i in range(a.warmup):
        gen("Say hello.", 8)
    s0 = snap(getter)
    rows = []
    for i, p in enumerate(prompts):
        b = snap(getter)
        # quality pass (exp742 path, with logits capture); its time is informational only (t_quality_s)
        n_in, new, tq, (top_ids, top_vals, chosen), src = gen(p, a.max_new, logits=True)
        e = snap(getter)
        # timed passes: no capture hook (gen(logits=False) sets cap["rec"]=None, so sample_rec only does a
        # None check and forwards to the original _sample); each gen() timing is sync_all/perf_counter/no_grad.
        timed = []
        for rep in range(a.timed_reps):
            _, _, t1, _, _ = gen(p, 1)
            _, new64, t64, _, _ = gen(p, a.max_new)
            timed.append({"t1_s": t1, "t64_s": t64, "out_ids_64": new64})
        # This arm's stored d_ms/e_ms below use len(out_ids_64)-1 / len(out_ids_64) and are informational
        # only: classify750.py recomputes d_p/e_p from the raw t1_s/t64_s with the PREREG literal /63 and /64.
        d_ms = (statistics.median((r["t64_s"] - r["t1_s"]) / (len(r["out_ids_64"]) - 1) * 1000
                                  for r in timed)
                if timed and all(len(r["out_ids_64"]) > 1 for r in timed) else None)
        e_ms = (statistics.median(r["t64_s"] / len(r["out_ids_64"]) * 1000 for r in timed)
                if timed and all(len(r["out_ids_64"]) >= 1 for r in timed) else None)
        rows.append({"i": i, "n_in": n_in, "n_new": len(new), "t_quality_s": tq,
                     "d_ms": d_ms, "e_ms": e_ms, "timed": timed,
                     "out_sha": hashlib.sha256(json.dumps(new).encode()).hexdigest()[:16],
                     "out_ids": new,
                     "top16_ids": top_ids, "top16_vals": top_vals, "chosen_val": chosen,
                     "logit_source": src,
                     "stats_delta": {k: e.get(k, 0) - b.get(k, 0) for k in e if not k.startswith("_")}})
        print(f"[{a.policy} r={a.ratio}] prompt {i}: d_ms={rows[-1]['d_ms']} e_ms={rows[-1]['e_ms']} "
              f"hits+{rows[-1]['stats_delta'].get('policy_routed_hits')} "
              f"miss+{rows[-1]['stats_delta'].get('policy_routed_misses')}", flush=True)
    s1 = snap(getter)
    import moe_infinity
    res = {"harness": "exp750", "timer": "exp750-syncall-nocapture", "timed_reps": a.timed_reps,
           "cuda_device_count": torch.cuda.device_count(),
           "cuda_device_order": os.environ.get("CUDA_DEVICE_ORDER"),
           "moe_infinity_file": moe_infinity.__file__, "store_so": store_so(),
           "policy": a.policy, "ratio": a.ratio, "model": a.model, "max_new": a.max_new,
           "load_s": load_s, "stats_getter": getattr(getter, "__qualname__", repr(getter)),
           "stats_start": s0, "stats_end": s1, "rows": rows,
           "torch": torch.__version__, "cuda": torch.version.cuda,
           "gpu": torch.cuda.get_device_name(0), "host": platform.node(),
           "visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
           "mem_alloc_gb": torch.cuda.max_memory_allocated(0) / 2**30}
    json.dump(res, open(a.out, "w"), indent=1)
    print("DONE", a.out, flush=True)


if __name__ == "__main__":
    main()

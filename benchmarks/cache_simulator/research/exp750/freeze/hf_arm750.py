"""exp750 calibrator arm H: plain Hugging Face transformers (no MoE-Infinity), bf16, device_map="auto".

Copy of hf_arm742.py with the exp750 timer fix. The exp742 quality pass (64-token run with output_logits,
max_new_tokens only so it stops at EOS) is kept verbatim and is NOT used for any timing metric (stored as
t_quality_s, informational only). The exp742 t_1tok/t_full/decode_tok_s computation is dropped. After the
quality pass, each prompt gets --timed-reps timed passes with no logits capture; every timing synchronizes ALL
visible CUDA devices before and after the generate call. Timed runs also use max_new_tokens only (EOS stop),
so a timed run produces the same token count as the quality pass. Usage:
  python hf_arm750.py --model DIR --prompts prompts.json --max-new 64 --warmup 1 --timed-reps 3 --out arm.json
"""
import argparse, hashlib, json, os, platform, statistics, sys, time

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer


def sync_all():
    """Synchronize every visible CUDA device (exp742 synced only the current device)."""
    for d in range(torch.cuda.device_count()):
        torch.cuda.synchronize(d)


def top16(logits, tokens):
    """Per-step top-16 of the RAW logits (row 0) -> (ids, float32 values, chosen_val). chosen_val is the full
    step tensor's value at the generated token (taken before topk)."""
    ids, vals, chosen = [], [], []
    for step, t in zip(logits, tokens):
        full = step[0].float()
        chosen.append(full[t].item())
        v, i = torch.topk(full, k=16)
        ids.append(i.tolist())
        vals.append(v.tolist())
    return ids, vals, chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--max-new", type=int, default=128)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--timed-reps", type=int, default=3)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    prompts = json.load(open(a.prompts))
    tok = AutoTokenizer.from_pretrained(a.model)
    t0 = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16, device_map="auto")
    model.eval()
    param_dtype = next(model.parameters()).dtype
    assert param_dtype == torch.bfloat16, f"H must load in bf16, got {param_dtype}"
    load_s = time.perf_counter() - t0
    dev = model.get_input_embeddings().weight.device

    def gen(p, n, logits=False, timed=False):
        ids = tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True,
                                      return_tensors="pt", return_dict=True)["input_ids"].to(dev)
        # quality (logits) and timed runs: max_new_tokens only (EOS stop, exp742 review finding 3);
        # warmup keeps min_new_tokens as before
        extra = ({"output_logits": True, "return_dict_in_generate": True} if logits
                 else {} if timed else {"min_new_tokens": n})
        sync_all()
        t = time.perf_counter()
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=n, do_sample=False,
                                 pad_token_id=tok.eos_token_id, **extra)
        sync_all()
        dt = time.perf_counter() - t
        seq = out.sequences if logits else out
        new = seq[0, ids.shape[1]:].tolist()
        if logits and len(out.logits) != len(new):  # fail closed: one logit row per new token
            raise RuntimeError(f"logit steps {len(out.logits)} != new tokens {len(new)}")
        top = top16(out.logits, new) if logits else None
        return ids.shape[1], new, dt, top

    for i in range(a.warmup):
        gen("Say hello.", 8)
    rows = []
    for i, p in enumerate(prompts):
        # quality pass (exp742 path, with logits capture); its time is informational only (t_quality_s)
        n_in, new, tq, (top_ids, top_vals, chosen) = gen(p, a.max_new, logits=True)
        # timed passes: no logits capture; each gen() timing is sync_all/perf_counter/no_grad
        timed = []
        for rep in range(a.timed_reps):
            _, _, t1, _ = gen(p, 1, timed=True)
            _, new64, t64, _ = gen(p, a.max_new, timed=True)
            timed.append({"t1_s": t1, "t64_s": t64, "out_ids_64": new64})
        # This arm's stored d_ms/e_ms below use len(out_ids_64)-1 / len(out_ids_64) and are informational
        # only: classify750.py recomputes d_p/e_p from the raw t1_s/t64_s with the PREREG literal /63 and /64
        # (an EOS-short run is not rescaled there; H2 is descriptive only and never feeds a decision).
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
                     "logit_source": "hf_output_logits",
                     "stats_delta": {}})
        print(f"[hf] prompt {i}: d_ms={rows[-1]['d_ms']} e_ms={rows[-1]['e_ms']}", flush=True)
    st = sys.modules.get("moe_infinity._store")  # never imported here; recorded for schema parity
    res = {"harness": "exp750", "timer": "exp750-syncall-nocapture", "timed_reps": a.timed_reps,
           "cuda_device_count": torch.cuda.device_count(),
           "cuda_device_order": os.environ.get("CUDA_DEVICE_ORDER"),
           "moe_infinity_file": None, "store_so": getattr(st, "__file__", None),
           "param_dtype": str(param_dtype), "transformers": transformers.__version__,
           "policy": "hf", "ratio": None, "model": a.model, "max_new": a.max_new,
           "load_s": load_s, "hf_device_map": {str(k): str(v) for k, v in model.hf_device_map.items()},
           "stats_start": {}, "stats_end": {}, "rows": rows,
           "torch": torch.__version__, "cuda": torch.version.cuda,
           "gpu": torch.cuda.get_device_name(0), "host": platform.node(),
           "visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
           "mem_alloc_gb": torch.cuda.max_memory_allocated(0) / 2**30}
    json.dump(res, open(a.out, "w"), indent=1)
    print("DONE", a.out, flush=True)


if __name__ == "__main__":
    main()

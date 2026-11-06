#!/usr/bin/env python3
"""exp736 decode-only main-thread op profile, HF vs engine.
Usage: prof2.py MODE(hf|engine) MODEL OFFLOAD RATIO OUT [device] [ntok]
Per-token = (profile of generate(1+ntok) - profile of generate(1)) / ntok, so prefill cancels.
Limit: torch.profiler records the calling (main) thread only; C++ worker-thread copies are not in it."""
import sys, json, time, statistics as st, collections, os
import torch
from torch.profiler import profile, ProfilerActivity
from transformers import AutoTokenizer, AutoModelForCausalLM
mode, model_p, off, ratio, outp = sys.argv[1:6]
dev = sys.argv[6] if len(sys.argv) > 6 else "cuda:0"; NT = int(sys.argv[7]) if len(sys.argv) > 7 else 16
tok = AutoTokenizer.from_pretrained(model_p)
if mode == "hf":
    m = AutoModelForCausalLM.from_pretrained(model_p, dtype=torch.bfloat16, device_map=dev).eval()
else:
    from moe_infinity import MoE
    m = MoE(model_p, {"offload_path": off, "device_memory_ratio": float(ratio), "expert_eviction_policy": "lcnu"})
p = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts.json")))[0]
ids = tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True, return_tensors="pt",
                              return_dict=True)["input_ids"].to(dev)
def sync():
    if dev.startswith("cuda"): torch.cuda.synchronize()
def g(n):
    m.generate(ids, max_new_tokens=n, min_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
def timed(n):
    sync(); t = time.perf_counter(); g(n); sync(); return time.perf_counter() - t
TORCH_FR = os.sep + "torch" + os.sep
def site_of(stack):
    for fr in stack or []:
        if TORCH_FR not in fr and "<built-in" not in fr: return fr
    return "?"
def owner(stack):
    s = " ".join(stack or [])
    return "engine" if ("moe_infinity" in s or "moe_store" in s) else ("hf" if "transformers" in s else "other")
def collect(pr):
    ops = collections.defaultdict(lambda: [0, 0.0]); sites = collections.defaultdict(lambda: [0, 0.0])
    own = collections.defaultdict(lambda: [0, 0.0]); buck = collections.defaultdict(int)
    for e in pr.events():
        if getattr(e, "device_type", None) is not None and "CUDA" in str(e.device_type): continue
        nm = e.name; sc = float(e.self_cpu_time_total)
        ops[nm][0] += 1; ops[nm][1] += sc
        if nm == "aten::copy_":
            stk = list(getattr(e, "stack", []) or [])
            k = site_of(stk); sites[k][0] += 1; sites[k][1] += sc
            o = owner(stk); own[o][0] += 1; own[o][1] += sc
            shp = (getattr(e, "input_shapes", None) or [[]])
            n = 1
            for dd in (shp[0] if shp and shp[0] else []): n *= int(dd)
            buck["le4K" if n <= 4096 else "le1M" if n <= 1 << 20 else "gt1M"] += 1
    return ops, sites, own, buck
with torch.no_grad():
    g(4); g(4)
    t1 = [timed(1) for _ in range(3)]; tN = [timed(1 + NT) for _ in range(3)]
    ms_tok = (st.median(tN) - st.median(t1)) / NT * 1e3
    acts = [ProfilerActivity.CPU]
    with profile(activities=acts, record_shapes=True, with_stack=True) as pa: g(1); sync()
    with profile(activities=acts, record_shapes=True, with_stack=True) as pb: g(1 + NT); sync()
A, B = collect(pa), collect(pb)
def diff(a, b):
    ks = set(a) | set(b)
    return {k: [(b.get(k, [0, 0])[0] - a.get(k, [0, 0])[0]) / NT, (b.get(k, [0, 0])[1] - a.get(k, [0, 0])[1]) / NT] for k in ks}
ops = diff(A[0], B[0]); sites = diff(A[1], B[1]); own = diff(A[2], B[2])
buck = {k: (B[3].get(k, 0) - A[3].get(k, 0)) / NT for k in set(A[3]) | set(B[3])}
aten = {k: v for k, v in ops.items() if k.startswith("aten::")}
res = {"mode": mode, "ratio": float(ratio) if mode != "hf" else None, "device": dev, "ntok": NT,
       "ms_per_tok_unprofiled": ms_tok, "t1_s": t1, "tN_s": tN,
       "aten_events_per_tok": sum(v[0] for v in aten.values()),
       "aten_selfcpu_ms_per_tok": sum(v[1] for v in aten.values()) / 1e3,
       "copy_per_tok": aten.get("aten::copy_", [0, 0])[0], "copy_selfcpu_ms_per_tok": aten.get("aten::copy_", [0, 0])[1] / 1e3,
       "copy_owner_per_tok": own, "copy_numel_buckets_per_tok": buck,
       "top_ops": sorted(([k, v[0], v[1] / 1e3] for k, v in aten.items()), key=lambda r: -r[2])[:30],
       "top_copy_sites": sorted(([k, v[0], v[1] / 1e3] for k, v in sites.items()), key=lambda r: -r[2])[:15],
       "torch": torch.__version__, "visible": os.environ.get("CUDA_VISIBLE_DEVICES")}
json.dump(res, open(outp, "w"), indent=1)
print("PROF2", mode, f"ms/tok={ms_tok:.1f} aten/tok={res['aten_events_per_tok']:.0f} copy/tok={res['copy_per_tok']:.1f} "
      f"copy_ms/tok={res['copy_selfcpu_ms_per_tok']:.1f} owner={ {k: round(v[0],1) for k, v in own.items()} }", flush=True)

# ---- pass 3: dispatch-level trace of copies (direction, Python call site, blocking wall time), main thread
import traceback
from torch.utils._python_dispatch import TorchDispatchMode
CP = {"aten.copy_.default", "aten._to_copy.default", "aten._local_scalar_dense.default", "aten.nonzero.default"}
def dev_of(x):
    return x.device.type if isinstance(x, torch.Tensor) else None
class Tr(TorchDispatchMode):
    def __init__(s): super().__init__(); s.rec = collections.defaultdict(lambda: [0, 0.0])
    def __torch_dispatch__(s, func, types, args=(), kwargs=None):
        kwargs = kwargs or {}; nm = str(func)
        if nm not in CP: return func(*args, **kwargs)
        if nm == "aten.copy_.default": d = f"{dev_of(args[1])}->{dev_of(args[0])}"
        elif nm == "aten._to_copy.default": d = f"{dev_of(args[0])}->{(kwargs.get('device') or args[0].device).type}"
        else: d = f"{dev_of(args[0])}->sync"
        fr = [f for f in traceback.extract_stack()[:-1] if TORCH_FR not in f.filename and "_python_dispatch" not in f.filename]
        site = f"{os.path.basename(fr[-1].filename)}:{fr[-1].lineno}:{fr[-1].name}" if fr else "?"
        t = time.perf_counter(); r = func(*args, **kwargs); dt = time.perf_counter() - t
        k = (nm.split(".")[1], d, site); s.rec[k][0] += 1; s.rec[k][1] += dt
        return r
PT = {}
def traced(n):
    tr = Tr(); sync(); t = time.perf_counter()
    with tr: g(n); sync()
    PT[n] = time.perf_counter() - t
    return tr.rec
with torch.no_grad():
    ra = traced(1); rb = traced(1 + NT)
cd = []
for k in set(ra) | set(rb):
    c = (rb.get(k, [0, 0])[0] - ra.get(k, [0, 0])[0]) / NT; w = (rb.get(k, [0, 0])[1] - ra.get(k, [0, 0])[1]) / NT * 1e3
    if c > 0.01 or w > 0.01: cd.append([k[0], k[1], k[2], round(c, 2), round(w, 3)])
cd.sort(key=lambda r: -r[4])
res["dispatch_copies_per_tok"] = cd[:40]
bydir = collections.defaultdict(lambda: [0.0, 0.0])
for r in cd: bydir[r[1]][0] += r[3]; bydir[r[1]][1] += r[4]
res["dispatch_by_direction_per_tok"] = {k: [round(v[0], 2), round(v[1], 3)] for k, v in bydir.items()}
res["dispatch_wall_ms_per_tok"] = round(sum(r[4] for r in cd), 3)
res["pass3_ms_per_tok"] = (PT[1 + NT] - PT[1]) / NT * 1e3
json.dump(res, open(outp, "w"), indent=1)
print("PROF2-DISPATCH", mode, json.dumps(res["dispatch_by_direction_per_tok"]), "top:", json.dumps(cd[:4]), flush=True)

# ---- pass 4 (engine only): inclusive wall time per ExpertExecutor method (nested calls are double counted by design)
if mode == "engine":
    import functools, inspect
    from moe_infinity.distributed import expert_executor as EXM
    W = collections.defaultdict(lambda: [0, 0.0]); ON = [False]
    def wrap(nm, fn):
        @functools.wraps(fn)
        def w(*a, **k):
            if not ON[0]: return fn(*a, **k)
            t = time.perf_counter()
            try: return fn(*a, **k)
            finally: W[nm][0] += 1; W[nm][1] += time.perf_counter() - t
        return w
    for cls in [c for _, c in inspect.getmembers(EXM, inspect.isclass) if c.__module__ == EXM.__name__]:
        for nm, fn in list(vars(cls).items()):
            if callable(fn) and not nm.startswith("__") and not isinstance(fn, (staticmethod, classmethod)):
                setattr(cls, nm, wrap(f"{cls.__name__}.{nm}", fn))
    def walled(n):
        W.clear(); ON[0] = True; sync(); t = time.perf_counter()
        try: g(n); sync()
        finally: ON[0] = False
        PT4[n] = time.perf_counter() - t
        return {k: list(v) for k, v in W.items()}
    PT4 = {}
    with torch.no_grad():
        wa = walled(1); wb = walled(1 + NT)
    wt = sorted(([k, round((wb.get(k, [0, 0])[0] - wa.get(k, [0, 0])[0]) / NT, 2),
                  round((wb.get(k, [0, 0])[1] - wa.get(k, [0, 0])[1]) / NT * 1e3, 3)] for k in set(wa) | set(wb)),
                key=lambda r: -r[2])
    res["executor_wall_per_tok"] = [r for r in wt if r[1] or r[2] > 0.01][:25]
    res["pass4_ms_per_tok"] = (PT4[1 + NT] - PT4[1]) / NT * 1e3
    json.dump(res, open(outp, "w"), indent=1)
    print("PROF2-EXEC", json.dumps(res["executor_wall_per_tok"][:8]), flush=True)

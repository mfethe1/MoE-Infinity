#!/usr/bin/env python3
"""exp747 model-free CUDA host-hop latency under CPU contention. Usage: micro2.py OUT.json [N]
All measured on one torch side stream of the current device (CUDA_VISIBLE_DEVICES set by runner).
  stall_hostfn   GPU-measured (cuda events) time of: tiny kernel, cudaLaunchHostFunc(no-op C fn), tiny kernel.
  stall_base     the same without the host func (both behind a ~0.8 ms matmul gate so spans are device-only). hostfn_stall = stall_hostfn - median(stall_base): how long the
                 STREAM is blocked by one host-callback round trip (what MoE-Infinity's route callback and per-expert
                 retirement callbacks cost the GPU). No Python/GIL in the callback (libc free(NULL)).
  kern_sync      host wall: tiny kernel + cudaStreamSynchronize (what eager Python routing pays per layer, roughly).
  mm_notify      host wall - GPU time for a ~1 ms bf16 matmul pair + sync (completion-notification latency).
Per-sample lists are summarised (median/p10/p90/p99, frac>250us, frac>1ms)."""
import ctypes, ctypes.util, json, os, platform, statistics as st, sys, time

import torch

N = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
import nvidia.cuda_runtime as _rt
rt = ctypes.CDLL(os.path.join(os.path.dirname(_rt.__file__), "lib", "libcudart.so.12"))
libc = ctypes.CDLL(ctypes.util.find_library("c"))
noop = ctypes.cast(libc.free, ctypes.c_void_p)
dev = torch.cuda.current_device()
s = torch.cuda.Stream(); S = ctypes.c_void_p(s.cuda_stream)
x = torch.zeros(1, device="cuda")
ns = time.perf_counter_ns


def chk(r):
    if r != 0:
        raise RuntimeError(f"cuda error {r}")


def summ(v):
    v = sorted(v); q = lambda f: v[int(f * (len(v) - 1))]
    return {"median_us": st.median(v), "p10_us": q(0.1), "p90_us": q(0.9), "p99_us": q(0.99), "min_us": v[0],
            "frac_gt_250us": sum(a > 250 for a in v) / len(v), "frac_gt_1ms": sum(a > 1000 for a in v) / len(v), "n": len(v)}


e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
A = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)


def gpu_span(with_hostfn):
    # A ~0.8 ms GPU "gate" runs first, so every later op is already enqueued when the GPU reaches e0:
    # e0->e1 then measures device-side time only (no host enqueue gaps). gate_overrun = base span > 50 us.
    with torch.cuda.stream(s):
        y = A @ A; y = y @ A
        e0.record(s); x.add_(1)
        if with_hostfn:
            chk(rt.cudaLaunchHostFunc(S, noop, None))
        x.add_(1); e1.record(s)
    chk(rt.cudaStreamSynchronize(S))
    return e0.elapsed_time(e1) * 1000.0


res = {}
for _ in range(100):
    gpu_span(True); gpu_span(False)
base, hf = [], []
for i in range(N):  # interleaved so drift hits both equally
    base.append(gpu_span(False)); hf.append(gpu_span(True))
b0 = st.median(base)
res["stall_base"] = summ(base)
res["stall_hostfn"] = summ(hf)
res["hostfn_stall"] = summ([h - b0 for h in hf])
res["gate_overrun_frac"] = {"frac_base_gt_50us": sum(b > 50 for b in base) / len(base)}


def kern_sync():
    with torch.cuda.stream(s):
        x.add_(1)
    chk(rt.cudaStreamSynchronize(S))


for _ in range(100):
    kern_sync()
ks = []
for _ in range(N):
    t = ns(); kern_sync(); ks.append((ns() - t) / 1000.0)
res["kern_sync"] = summ(ks)

w, g = [], []
for i in range(max(100, N // 5)):
    t = ns()
    with torch.cuda.stream(s):
        e0.record(s); y = A @ A; y = y @ A; e1.record(s)
    chk(rt.cudaStreamSynchronize(S))
    if i >= 20:
        w.append((ns() - t) / 1000.0); g.append(e0.elapsed_time(e1) * 1000.0)
res["mm_notify"] = summ([a - b for a, b in zip(w, g)])
meta = {"gpu": torch.cuda.get_device_name(dev), "visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "torch": torch.__version__,
        "cuda": torch.version.cuda, "host": platform.node(), "kernel": platform.release(), "x_final": float(x.item()),
        "loadavg_end": open("/proc/loadavg").read().split()[0]}
json.dump({"results": res, "meta": meta}, open(sys.argv[1], "w"), indent=1)
for k, v in res.items():
    print(k, {a: round(b, 3) for a, b in v.items()}, flush=True)
print("DONE", flush=True)

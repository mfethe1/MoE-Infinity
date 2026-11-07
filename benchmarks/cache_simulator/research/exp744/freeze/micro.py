#!/usr/bin/env python3
"""exp744 host-side CUDA primitive latency micro-benchmark (no model). Usage: micro.py OUT.json [N]
Measures, on the current CUDA device (one torch stream), median/p90 host wall time in microseconds of:
  launch_tiny        enqueue cost of one tiny torch kernel (x.add_(1) on 1 element), no sync (batched 200, per-op)
  sync_idle          cudaStreamSynchronize on an idle stream
  kern_sync          tiny kernel + cudaStreamSynchronize   (launch -> completion visible to host)
  kern_hostfn_sync   tiny kernel + cudaLaunchHostFunc(no-op) + cudaStreamSynchronize
  hostfn_sync        cudaLaunchHostFunc(no-op) + cudaStreamSynchronize on an idle stream
  kern_evpoll        tiny kernel + cudaEventRecord, then spin on cudaEventQuery until ready
  set_device         cudaSetDevice(current)
  mm_sync            ~1 ms bf16 matmul pair + sync: notify = host wall - GPU event time (completion-notification latency)
  torch_sync_after_tiny  tiny kernel + torch.cuda.synchronize (device-wide) for cross-check
The no-op host function is libc `free` called with NULL (a C function pointer: no Python/GIL in the callback path).
hostfn_cost = kern_hostfn_sync - kern_sync is the added latency of one host-callback hop in the stream."""
import ctypes, ctypes.util, json, os, platform, statistics as st, sys, time

import torch

N = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
import nvidia.cuda_runtime as _rt
rt = ctypes.CDLL(os.path.join(os.path.dirname(_rt.__file__), "lib", "libcudart.so.12"))
libc = ctypes.CDLL(ctypes.util.find_library("c"))
noop = ctypes.cast(libc.free, ctypes.c_void_p)  # free(NULL) is a no-op
dev = torch.cuda.current_device()
s = torch.cuda.Stream()
S = ctypes.c_void_p(s.cuda_stream)
x = torch.zeros(1, device="cuda")
ev = ctypes.c_void_p()
assert rt.cudaSetDevice(dev) == 0
assert rt.cudaEventCreateWithFlags(ctypes.byref(ev), 2) == 0  # cudaEventDisableTiming
ns = time.perf_counter_ns


def chk(r):
    if r != 0:
        raise RuntimeError(f"cuda error {r}")


def run(fn, n=N):
    for _ in range(max(50, n // 10)):
        fn()
    out = []
    for _ in range(n):
        t = ns(); fn(); out.append((ns() - t) / 1000.0)
    out.sort()
    q = lambda f: out[int(f * (len(out) - 1))]
    return {"median_us": st.median(out), "p10_us": q(0.1), "p25_us": q(0.25), "p75_us": q(0.75),
            "p90_us": q(0.9), "min_us": out[0], "frac_gt_1ms": sum(v > 1000 for v in out) / len(out), "n": n}


def tiny():
    with torch.cuda.stream(s):
        x.add_(1)


def launch_batch():
    with torch.cuda.stream(s):
        for _ in range(200):
            x.add_(1)
    chk(rt.cudaStreamSynchronize(S))


def kern_sync():
    tiny(); chk(rt.cudaStreamSynchronize(S))


def kern_hostfn_sync():
    tiny(); chk(rt.cudaLaunchHostFunc(S, noop, None)); chk(rt.cudaStreamSynchronize(S))


def hostfn_sync():
    chk(rt.cudaLaunchHostFunc(S, noop, None)); chk(rt.cudaStreamSynchronize(S))


def kern_evpoll():
    tiny(); chk(rt.cudaEventRecord(ev, S))
    while rt.cudaEventQuery(ev) != 0:
        pass


res = {}
# launch cost: time 200 enqueues only (sync excluded by measuring enqueue loop separately)
lt = []
for i in range(max(20, N // 100)):
    chk(rt.cudaStreamSynchronize(S))
    t = ns()
    with torch.cuda.stream(s):
        for _ in range(200):
            x.add_(1)
    lt.append((ns() - t) / 1000.0 / 200)
    chk(rt.cudaStreamSynchronize(S))
lt.sort(); res["launch_tiny"] = {"median_us": st.median(lt), "p90_us": lt[int(0.9 * len(lt))], "min_us": lt[0], "n": len(lt)}
res["sync_idle"] = run(lambda: chk(rt.cudaStreamSynchronize(S)))
res["kern_sync"] = run(kern_sync)
res["kern_hostfn_sync"] = run(kern_hostfn_sync)
res["hostfn_sync"] = run(hostfn_sync)
res["kern_evpoll"] = run(kern_evpoll)
# notification latency on a ~1 ms GPU workload: wall(launch->sync return) minus GPU-measured kernel time
A = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
walls, gpus = [], []
for i in range(max(100, N // 4)):
    t = ns()
    with torch.cuda.stream(s):
        e0.record(s); y = A @ A; y = y @ A; e1.record(s)
    chk(rt.cudaStreamSynchronize(S))
    w = (ns() - t) / 1000.0
    if i >= 20:
        walls.append(w); gpus.append(e0.elapsed_time(e1) * 1000.0)
lat = sorted(w - g for w, g in zip(walls, gpus))
res["mm_sync"] = {"wall_median_us": st.median(walls), "gpu_median_us": st.median(gpus),
                  "notify_median_us": st.median(lat), "notify_p10_us": lat[len(lat) // 10],
                  "notify_p90_us": lat[int(0.9 * (len(lat) - 1))], "n": len(lat)}
res["torch_sync_after_tiny"] = run(lambda: (tiny(), torch.cuda.synchronize()))
res["set_device"] = run(lambda: chk(rt.cudaSetDevice(dev)))
res["hostfn_cost_us"] = res["kern_hostfn_sync"]["median_us"] - res["kern_sync"]["median_us"]
meta = {"gpu": torch.cuda.get_device_name(dev), "visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "torch": torch.__version__, "cuda": torch.version.cuda, "host": platform.node(),
        "kernel": platform.release(), "x_final": float(x.item())}
json.dump({"results": res, "meta": meta}, open(sys.argv[1], "w"), indent=1)
for k, v in res.items():
    print(k, v if not isinstance(v, dict) else {a: round(b, 3) for a, b in v.items()}, flush=True)
print("DONE", flush=True)

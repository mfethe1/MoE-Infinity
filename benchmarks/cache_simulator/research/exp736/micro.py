#!/usr/bin/env python3
"""exp736 unit-cost microbenchmarks on cuda:0 (CUDA_VISIBLE_DEVICES selects the GPU). Usage: micro.py OUT [scale]"""
import json, sys, time, statistics as st, platform, os
import torch
out = sys.argv[1]; K = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
d = torch.device("cuda:0"); torch.cuda.init()
def tm(f, n, reps=5):
    n = max(int(n * K), 10); v = []
    for _ in range(reps):
        for _ in range(min(n, 50)): f()
        torch.cuda.synchronize(); t = time.perf_counter()
        for _ in range(n): f()
        torch.cuda.synchronize(); v.append((time.perf_counter() - t) / n * 1e6)
    return st.median(v)
r = {}
x = torch.ones(1, device=d)
r["launch_add_inplace_us"] = tm(lambda: x.add_(1), 5000)
h = torch.ones(1, 2048, dtype=torch.bfloat16, device=d)
r["mul_bf16_1x2048_us"] = tm(lambda: h * h, 5000)
r["rmsnorm_unfused_1x2048_us"] = tm(lambda: h * torch.rsqrt(h.float().pow(2).mean(-1, keepdim=True) + 1e-6).to(h.dtype), 2000)
r["empty_cached_alloc_1x2048_us"] = tm(lambda: torch.empty(1, 2048, dtype=torch.bfloat16, device=d), 5000)
def syncop(): x.add_(1); torch.cuda.synchronize()
r["launch_plus_sync_us"] = tm(syncop, 2000)
r["item_roundtrip_us"] = tm(lambda: x.item(), 2000)
s16 = torch.ones(64, 64, device=d); hs = torch.ones(64, 64); pin = torch.empty(64, 64).pin_memory()
r["d2h_16KB_pageable_us"] = tm(lambda: s16.cpu(), 2000)
r["d2h_16KB_pinned_sync_us"] = tm(lambda: pin.copy_(s16), 2000)
r["h2d_16KB_pageable_us"] = tm(lambda: hs.to(d), 2000)
r["h2d_16KB_pinned_nonblocking_us"] = tm(lambda: pin.to(d, non_blocking=True), 2000)
N = 3 * 2048 * 1024  # one OLMoE expert, bf16 = 12.58 MB
hb = torch.empty(N, dtype=torch.bfloat16); hp = torch.empty(N, dtype=torch.bfloat16).pin_memory()
db = torch.empty(N, dtype=torch.bfloat16, device=d)
B = N * 2
for nm, f in (("h2d_expert_pageable", lambda: db.copy_(hb)), ("h2d_expert_pinned", lambda: db.copy_(hp, non_blocking=True)),
              ("d2h_expert_pageable", lambda: hb.copy_(db)), ("d2h_expert_pinned", lambda: hp.copy_(db, non_blocking=True))):
    us = tm(f, 40); r[nm + "_us"] = us; r[nm + "_GBps"] = B / (us * 1e-6) / 1e9
r["meta"] = {"gpu": torch.cuda.get_device_name(0), "visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "torch": torch.__version__,
             "host": platform.node(), "scale": K}
json.dump(r, open(out, "w"), indent=1)
print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}))

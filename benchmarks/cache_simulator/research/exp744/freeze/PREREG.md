# exp744 PREREG — WSL CUDA host-notification latency, and does the engine's sync-free GPU routing matter?

Lane 79990, program STACK-1001-79990. Written 2026-11-06, BEFORE any exp744 cell. Namespace check: no exp744 directory on Mack
or Winnie, and no running.json or queue entry. Runs after exp743 (serial on GPU1).

## Why
exp738 (admitted #70) showed the engine's 61 ms/token gap over HF is insensitive to one-launch-per-layer grouping but
very sensitive to exec-thread count. That points at host-side handoff and notification paths, which run
on WSL2's paravirtualized GPU driver on Winnie. Two smokes of `micro.py` on Winnie GPU1 (NOT evidence, only motivation)
gave tiny-kernel+sync medians of **1648 µs and 57 µs**. The device states differed (GPU0 idle vs 100% from another lane).
A kernel followed by `cudaLaunchHostFunc` (the engine retires every expert this way) cost ~100 µs over plain sync, with
**25% of samples >1 ms**. If WSL notification latency is high or unstable, every per-layer or per-expert host hop costs
far more than on native Linux. That would be a platform term in the overhead budget, not an engine algorithm term.

Separately, the engine's `gpu_only_expert_routing` defaults to **on** (sync-free CUDA active-expert discovery). Turning it off
restores eager Python routing with a host sync per layer. This A/B prices one host sync per layer on this platform,
in the real engine.

## Cells (frozen), serial on Winnie GPU1, palindromic
micro_1, on_1, off_1, off_2, on_2, micro_2.
- micro: `micro.py out/ID.json 2000`. No model. Measures launch, idle sync, kernel+sync, kernel+hostfn+sync, hostfn+sync,
  event poll, ~1 ms bf16 matmul (notify = wall − GPU event time), and torch sync.
- on/off: engine_arm.py (exp743 base, + `--gpu-route on|off` → `gpu_only_expert_routing`, read back from archer_config as
  `gpu_route_effective`). OLMoE-1B-7B bf16, lcnu @ 0.75, threads 4, 6 prompts, max_new 64, warmup 1, no grouped env.
- NVML sampler (exp743 `nvsamp.py`) on every cell, with a 10 s idle baseline. quietwait ≤5400 s. The run starts after units
  exp740/741/742/743 are inactive.

## Exclusions
Same as exp743: pre-start GPU1 >1024 MiB, a loaded Ollama model or a failed probe; a mid-cell foreign process; idle baseline mean >5%;
any engine prompt window with <10 util samples; RC≠0.

## Decision rules (analyze.py, frozen; dry-run on slow/flat/unstable/parity-fail synthetic cases gave intended branches)
- PRIM: mean mm_notify over clean micro cells is >200 µs → NOTIFY-HIGH, <100 µs → NOTIFY-LOW, otherwise NOTIFY-MID. If the
  kern_sync medians of the two micro cells differ by >2×, append -UNSTABLE. HOSTFN: mean hostfn_cost >50 µs → COSTLY, otherwise CHEAP.
- ROUTE: off − on mean ms/token, |Δ|<3 → ROUTE:NO-CHANGE, otherwise ROUTE:OFF-SLOWER / ROUTE:OFF-FASTER. Requires
  gpu_route_effective to match the request in all engine cells (else INCONCLUSIVE). Output token ids must be identical across all
  engine cells, else "(PARITY-FAIL)" is appended.
- `VERDICT PRIM:<..>|HOSTFN:<..>|ROUTE:<..>`.

## Predictions (registered)
PRIM:NOTIFY-LOW (0.55; the 1648 µs smoke may be a clock or power-state artifact). HOSTFN:COSTLY (0.7). ROUTE:OFF-SLOWER (0.75;
16 per-layer syncs × ≥60 µs ≥ 1 ms/token; ≥3 ms needs ≥190 µs each — that magnitude is exactly what is uncertain).

## Consequences
- HOSTFN:COSTLY + gap insensitive to grouping → prototype per-layer (not per-expert) retirement: one host func per layer
  batch instead of one per expert. That is an upstream-able engine change, measured against this baseline.
- NOTIFY-HIGH or -UNSTABLE → the WSL platform term must be measured on native Linux (rented node or dual-boot) before any
  host-latency fix is claimed general. Record it in BELIEFS as platform-conditional.
- ROUTE:OFF-SLOWER by Δ → per-host-sync cost in the engine ≈ Δ/16 ms. Use it to price every remaining host hop in exp736's
  unattributed third.

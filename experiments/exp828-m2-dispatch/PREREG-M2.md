# PREREG-M2 — exp828: engine b1 step-time attribution (dispatcher counters)

Frozen 2026-11-19 (FREEZE-828.json). Rank-2 item of MYTHOS-ADJUDICATION-20261118.md §2,
sequenced by the PIVOT-A result of exp827 M1 (2.36x).

## Question
Engine b1 runs ~75 ms/step (13.28 tok/s) vs resident bf16 ~32 ms/step (31.39 tok/s).
WHERE do the extra ~43 ms/step go? Attribution decides #7 (in-engine dispatch elimination)
and the >VRAM-model streaming design.

## Design
- Engine arm only (moe_infinity, offload 0.50, same frozen config as M1 eng).
- 8 M1 prompts, b1, greedy; burn-in 2 prompts untimed.
- 4 profiled prompts x 64 new tokens under torch.profiler (CPU+CUDA activities,
  key_averages exported per prompt; memcpy events counted; expert-load bytes estimated
  as count x 12.6 MB (3 x 2048x1024 x bf16) — recorded as ESTIMATE).
- Per-prompt wall + token count recorded; per-step wall = wall/steps.
- Quiet gate per prompt (load5<3, gpu1 util<5); unit runs only in a cron-paused,
  Ollama-unloaded window.

## Frozen predictions (before run)
- P1: expert-GEMM CUDA time (names containing mm/gemm/silu/mul/add in expert path) is a
  MINORITY of engine step time (<50%); the majority is dispatch/memcpy/wait overhead.
- P2: expert load events per step are ~8-64 (top-8 routing x 16 layers, minus residency
  hits); H2D bytes per step >= 100 MB at cold start, < 50 MB steady-state if LCNU holds
  anything resident.
- P3: profiled per-step wall under profiler overhead stays within 1.5x of unprofiled
  engine step (~75 ms) — else attribution is protocol-confounded and rerun with fewer
  activities.

## Decision rule (for #7)
If dispatch/memcpy/wait >= 60% of step time: in-engine dispatch elimination (#7) proceeds —
target the top attributed component. If expert compute >= 60%: the 2.36x is compute-path
tax (quantized/batched kernels), #7 is dead, residency-first lane only.

## Non-goals
No b8. No engine code changes. No cross-run comparisons beyond M1's same-config arms.

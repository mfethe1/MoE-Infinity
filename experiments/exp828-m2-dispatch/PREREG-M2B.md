# PREREG-M2B — exp828 M2b: dispatcher counters at b1 (0.50/0.65) + exp791 rerun arms (0.75/0.90)

Frozen 2026-11-19 (FREEZE-828B.json) BEFORE any M2b data. Adjudication line 63 spec:
dispatcher counters at b1 — misses, accesses, H2D bytes per token at 0.50 and 0.65, read
outside the timed region; line 131: exp791 0.75/0.90 rerun with counters (engine build
note: current 0337988, not exp791's build10 — counters exist only in current build;
offload index r05, M1-consistent).

## Counter API (OffloadEngine, moe_infinity/runtime/model_offload.py)
- expert_cache_hit_rate (native prefetcher get_hit_rate)
- get_exposed_fetch_seconds / reset_exposed_fetch_seconds (sync-fetch stall accumulator)
- expert_occupancy_bytes, num_offloaded_experts
- KNOWN STUB: adaptive_memory_snapshot hardcodes accesses=100 — NOT real counts. Misses
  derived as (1-hit_rate) x 128 accesses/step x steps (16 layers x top-8), marked
  ESTIMATE. Expert bytes 12.6 MB (3 x 2048x1024 bf16).

## Design
- Fresh engine process per arm; ratios 0.50, 0.65, 0.75, 0.90.
- 8 prompts (exp788/probe8.json), b1 greedy: 8-tok warm + 32-tok measured
  (min_new_tokens=32 forced, actual-token denominators).
- Per prompt, OUTSIDE the timed region: reset fetch accumulator before generate; after
  wall-clock stop read hit_rate, exposed_fetch_seconds, occupancy_bytes,
  num_offloaded_experts. Per arm after load: torch.cuda.max_memory_allocated +
  nvidia-smi used MiB.
- Quiet gate (retry 30x60s) before each measured generate; settle sleep after load.

## Frozen predictions
- P1: mean hit_rate(0.50) < 0.85. If ~1.0: LCNU keeps hot set resident, engine b1 tax
  is NOT fetch-wait.
- P2: median exposed_fetch_ms_per_tok(0.50) < 15 ms (<20% of 75 ms/tok engine wall).
- P3: |wall(0.65)-wall(0.50)|/wall(0.50) < 5% AND hit_rate(0.65) >= hit_rate(0.50).
- P4: arm 0.90 completes (no crash); walls(0.90) >= walls(0.75); occupancy capped below
  requested bytes.

## Decision rule for #7 (in-engine dispatch elimination)
- P1 AND P2 confirm (fetch minority) -> the 2.36x tax is CPU dispatch/handoff/op-count
  (consistent with M2a ~35% CPU aten share) -> #7 proceeds as dispatch elimination.
- exposed_fetch >= 60% of engine step wall -> #7 pivots to prefetch/overlap design.

## Non-goals
No profiler this arm (M2a showed CUPTI/CUDA capture fails on this WSL box — cuda_us
uniformly 0). No b8. No engine code changes.

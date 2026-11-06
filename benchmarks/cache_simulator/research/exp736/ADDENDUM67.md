# exp736 ADDENDUM67 — per-token engine overhead budget (MoE-Infinity vs HF, same GPU1): frozen BUDGET verdict INVALIDATED by an instrument defect; corrected reading DIFFUSE (post-hoc); power plan ruled out for HF

Admission: **admitted with condition `INSTRUMENT-DEFECT-PASS4-2X`.** Freeze 4cfc6cf + AMENDMENT1 f0ae07b + AMENDMENT2 ef98cad +
AMENDMENT3 6f2f2e7 (all committed before any admitted cell; the first admitted cell started 2026-11-06T14:20:49Z).

## Sealed verdict (frozen analyze.py, exactly as printed)

Integrity: `sha256sum -c ARTIFACT.sha256` OK on Winnie; out/ + run.log pulled as one tar (sha256
256f66f0e87b299d473313683b37e260b2293c903a6d60dd02f192217e36d480), SHA256SUMS computed on both sides: 48/48 identical
(raw/SHA256SUMS). Frozen analyze.py sha256 afd30064… == ARTIFACT == RUN_SHA256. Re-run on Mack against the pulled out/:
verdict **byte-identical** to Winnie's verdict.txt (sha256 875fa671…).

```
m_g1_A: launch_add_inplace_us=17.27 mul_bf16_1x2048_us=22.69 rmsnorm_unfused_1x2048_us=164.79 empty_cached_alloc_1x2048_us=3.22 launch_plus_sync_us=64.11 item_roundtrip_us=75.29 d2h_16KB_pageable_us=70.39 d2h_16KB_pinned_sync_us=63.11 h2d_16KB_pageable_us=50.60 h2d_16KB_pinned_nonblocking_us=18.15 h2d_expert_pageable_us=1050.57 h2d_expert_pageable_GBps=11.98 h2d_expert_pinned_us=824.17 h2d_expert_pinned_GBps=15.27 d2h_expert_pageable_us=1326.83 d2h_expert_pageable_GBps=9.48 d2h_expert_pinned_us=812.13 d2h_expert_pinned_GBps=15.49 FLAGGED
m_g0_A: launch_add_inplace_us=18.29 mul_bf16_1x2048_us=18.21 rmsnorm_unfused_1x2048_us=219.28 empty_cached_alloc_1x2048_us=2.93 launch_plus_sync_us=258.79 item_roundtrip_us=56.59 d2h_16KB_pageable_us=103.49 d2h_16KB_pinned_sync_us=73.57 h2d_16KB_pageable_us=99.80 h2d_16KB_pinned_nonblocking_us=25.71 h2d_expert_pageable_us=15072.55 h2d_expert_pageable_GBps=0.83 h2d_expert_pinned_us=7468.48 h2d_expert_pinned_GBps=1.68 d2h_expert_pageable_us=7197.91 d2h_expert_pageable_GBps=1.75 d2h_expert_pinned_us=7009.44 d2h_expert_pinned_GBps=1.80 FLAGGED
m_g1_B: launch_add_inplace_us=13.78 mul_bf16_1x2048_us=13.33 rmsnorm_unfused_1x2048_us=146.17 empty_cached_alloc_1x2048_us=2.65 launch_plus_sync_us=43.72 item_roundtrip_us=55.29 d2h_16KB_pageable_us=81.02 d2h_16KB_pinned_sync_us=60.78 h2d_16KB_pageable_us=53.75 h2d_16KB_pinned_nonblocking_us=17.27 h2d_expert_pageable_us=1386.31 h2d_expert_pageable_GBps=9.08 h2d_expert_pinned_us=822.32 h2d_expert_pinned_GBps=15.30 d2h_expert_pageable_us=1402.85 d2h_expert_pageable_GBps=8.97 d2h_expert_pinned_us=810.99 d2h_expert_pinned_GBps=15.52
hf  ms/tok=33.7 aten/tok=3829 aten_cpu_ms/tok(profiled)=33.8 d2h-sync=0.00 d2d-casts=8.1
eng ms/tok=124.2 aten/tok=4189 aten_cpu_ms/tok(profiled)=68.3 | overhead vs hf = 90.6 ms/tok
eng pass4 ms/tok=120.7: wait_dispatch_local 73.1 (32 calls/tok, 61%) | dispatch_local 7.6 (6%)
eng pass3 ms/tok=197.8: end-of-step d2h sync 22.3 (11%) | d2d casts 9.1 (5%)
eng executor top: wait_dispatch_local 32 73.09 | dispatch_local 32 7.60 | _dispatch_native 32 3.92 | _maybe_route_ahead_prefetch 32 0.65 | _can_use_gpu_only_routing 32 0.20 | _apply_expert_drop 32 0.07
eng dispatch top: cuda->cpu big_modeling.py:879:_native_model_forward 1.0 22.26 | cuda->cuda modeling_olmoe.py:54:forward 65.0 3.44 | cuda->cuda modeling_olmoe.py:57:forward 65.0 3.02 | cuda->cuda olmoe.py:68:forward 16.0 0.93 | cuda->cuda olmoe.py:41:forward 16.0 0.86 | cuda->cpu expert_executor.py:415:_dispatch_native 16.0 0.81
component shares: EXPERT-WAIT-BARRIER=0.61 END-STEP-SYNC=0.11 DISPATCH-CALL=0.06 DTYPE-CASTS=0.01
power eng: Balanced [None, 9.31617647188339] HighPerf [9.390562282220568, 9.265212556152019]
power hf: Balanced [23.805378310607537, 24.29190188523195] HighPerf [24.048473694152285, 24.83682741341972]
parity engine vs hf (t1): 2/6 identical greedy outputs
FLAGGED: m_g0_A m_g1_A t1_A_eng
VERDICT BUDGET:EXPERT-WAIT-BARRIER(0.61;unexplained~0.21)|POWER-ENG:INCOMPLETE|POWER-HF:POWER-RULED-OUT(1.016) [COMPLETE]
```

### BUDGET verdict INVALIDATED by instrument defect (pass-4 double wrap)

The frozen BUDGET verdict `EXPERT-WAIT-BARRIER(0.61)` stands as the sealed output but **is invalidated**: its input is wrong
by a factor of 2. The frozen analyzer was not edited.

- Defect (found 2026-11-06 ~15:10Z, after the p_eng cell and before settlement): prof2.py pass 4 wraps every method of each
  class returned by `inspect.getmembers(expert_executor, isclass)`. In MoE-Infinity 0337988 `ExpertExecutor` is an alias of
  `DistributedExpertExecutor` (same class object), so every method is wrapped twice under the same key. Call counts and
  inclusive times in `executor_wall_per_tok` are 2x real (toy reproduction: 16 real calls → 32 counted, ratio 2.000).
- In-data corroboration (checked by corrected_shares.py): every pass-4 method is counted exactly 32/token, while OLMoE has
  16 MoE layers (one wait per layer), and the unwrapped pass-3 copy trace sees exactly 16 `_dispatch_native` cuda->cpu
  copies/token at expert_executor.py:415.
- Unaffected: `pass4_ms_per_tok` (one outer wall, 120.72), pass 3 (copy trace), the unprofiled ms/token, all t* cells,
  POWER and parity.
- The smoke-registered prediction in PREREG (wait 51.3 ms over 32 calls/token) used the same prof2.py and carried the same
  2x bug, so the "prediction held" reading is void too.
- Halving slightly over-states the real time (the outer wrapper's inclusive time = inner + wrapper overhead).

### Corrected shares (POST-HOC, not a preregistered rule) — `corrected_shares.py`, all checks OK

| component (per decode token) | sealed (2x) | corrected | share (frozen denominator) |
|---|---|---|---|
| wait_dispatch_local | 73.10 ms, 32 calls | **36.55 ms, 16 calls (~2.28 ms/layer)** | 36.55/120.72 = **0.30** |
| dispatch_local | 7.60 | 3.80 | 0.03 |
| _dispatch_native | 3.92 | 1.96 | (inside dispatch_local) |
| end-step logits D2H (pass 3) | 22.26 | 22.26 (unaffected) | 22.26/197.77 = 0.11 (0.18 of the unprofiled 124.24) |
| d2d casts excess vs HF (pass 3) | 1.03 | 1.03 | 0.01 |

**POST-HOC corrected BUDGET reading: DIFFUSE (largest = EXPERT-WAIT-BARRIER 0.30 < 0.35; unexplained ~0.55).** Under the
frozen consequence table DIFFUSE maps to "CUDA graph / whole-step capture". This reading is post-hoc; it is not the
sealed verdict and is not counted as a preregistered result.

Descriptive context: engine 124.24 vs HF 33.68 ms/token unprofiled (overhead 90.56). The corrected wait is 0.29 of engine
ms/token and equals 0.40 of the overhead. Pass-3 numbers are tracing-inflated (HF pass 3 = 96.7 vs 33.7 unprofiled), and
the components come from different instrumented passes, so they are not additive.

### Code-reading finding (MoE-Infinity 0337988, `core/parallel/expert_dispatcher.cpp`)

- The per-expert exec path (`OutputFunc`, L1660-1767) enqueues the expert kernels and `index_add_` on the exec stream,
  records a completion event, enqueues the retirement `cudaLaunchHostFunc`, then calls `CompleteOne(generation)` (L1766).
  The grouped path does the same after its retirement host func (L2019-2030).
- `CompleteOne` (L2382) decrements `pending_` and notifies waiters. `WaitHiddenStates` (L2088) waits only for
  `!route_pending_ && pending_ == 0`, then inserts `cudaStreamWaitEvent` on the caller stream (non-blocking for the CPU).
- So the layer wait is released when the exec threads have **enqueued** the work, not when the GPU finishes: the ~36.5 ms/token
  wait is CPU-side exec-thread handoff + launch time (~2.3 ms/layer, ~285 us per expert at top-8). The GPU trails the
  CPU, and the 22 ms blocking logits D2H at the end of each step (big_modeling.py:879) is that GPU backlog draining.
- Limit: the Python `wait_dispatch_local` method also runs prefetch finalization (`drain_compute_samples`,
  `correct_prefetch(layer+1)`) after the C++ wait. Pass 4 does not separate the C++ wait from this Python bookkeeping.

## POWER (frozen rule, clean cells only)

- **POWER-HF: POWER-RULED-OUT (1.016)** — HighPerf/Balanced mean of block medians; < 1.05.
- **POWER-ENG: INCOMPLETE** — t1_A_eng FLAGGED (foreign `gen.py` on GPU1 mid-cell; its per-prompt tok/s 1.10/2.30/9.64/
  9.77/0.99/1.27 show the contention), so Balanced has one clean block. Descriptive only (not the rule): HighPerf mean
  9.328 vs the one clean Balanced block 9.316 → 1.001.
- Reading: the Windows power plan is not a lever for HF decode on GPU1; for the engine the frozen rule could not decide,
  and the one clean pair is flat.

## Parity (correctness, reported)

Engine vs HF greedy outputs: 2/6 identical in t1 (frozen line). Post-hoc check: 2/6 in every block (t1..t4), and each arm
is self-identical across all 4 blocks (engine 4/4, HF 4/4). The 4 divergent prompts are a deterministic engine-vs-HF
numerical difference, not noise. Not a gate here.

## Flagged cells (contamination rule)

`m_g1_A`, `m_g0_A` (mid-cell Ollama model loaded), `t1_A_eng` (foreign `gen.py` on GPU1 mid-cell). All pre-start records
were QUIET (raw/out/precell.csv). p_hf and p_eng are clean, so the profile cells are not contamination-affected.

## Micro unit costs (descriptive, clean cell m_g1_B, GPU1, HighPerf)

Kernel launch (add in-place) 13.8 us; launch+sync 43.7 us; `.item()` round trip 55.3 us; cached alloc 2.7 us;
16 KB D2H pinned+sync 60.8 us; one ~12.6 MB expert H2D pinned 822 us (15.3 GB/s) vs pageable 1386 us (9.1 GB/s).
GPU0 (flagged cell, gen3 x2 link): expert H2D pinned 1.68 GB/s. At ~14 us/launch, the ~285 us per expert implies on the
order of 10-20 launches-equivalent of host work per expert (inference, not measured).

## Consequence and next experiment

- The sealed BUDGET verdict cannot drive the frozen consequence. The corrected (post-hoc) picture: no single component
  ≥ 0.35; the largest is the CPU-side expert handoff/launch path (~36.5 ms/token), and the GPU-backlog sync (~22 ms/token)
  is its downstream symptom.
- Next: instrument the exec-thread handoff/launch path directly — per-expert launch count and latency, host-func bubbles,
  exec-thread count, and the grouped path. exp738 (freeze 9900434, already frozen in this lane) covers the grouped decode
  path and the exec-thread ladder (1/4/8). Its pre-committed GROUPED-FLAT follow-up is the per-expert launch/host-func timing
  plus a CUDA-graph decode step, which is also the DIFFUSE consequence here. Any future profiler must dedupe classes by
  `id()` and assert call count == one known structural count (one wait per MoE layer) before reading times.

## Files

- `raw/out/` (48 files incl. run.log via raw/run.log; byte-identical to Winnie, raw/SHA256SUMS, paths relative to
  exp736/raw with `ARTIFACT.sha256` = ../ARTIFACT.sha256).
- `corrected_shares.py` — post-hoc correction with structural checks; exits nonzero on any failed check.

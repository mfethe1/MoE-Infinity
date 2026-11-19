# RESULTS-M2A — exp828 M2a: profiler attribution arm (partially VOID)

Run 2026-11-19T12:52-12:58Z, unit exp828-m2 (sha 6fa34f6024f612ee, FREEZE-828.json
correction 1). All numbers below script-computed from m2a-profile.json
(sha aca660d1cded02011e2e1d73bab6bf76ca5a8ed9c893e92bed864be4c0f67afd).

## Frozen-prediction outcomes
- P3 (profiled wall within 1.5x of 75 ms/tok): **FAIL / ambiguous**. Per-prompt walls:
  116.0, 118.8, 92.3, 96.4 ms/tok. PREREG did not pin a median convention for n=4;
  lower-middle 96.4 -> 1.28x (pass), upper-middle 116.0 -> **1.541x (fail)**. Spread
  92.3-118.8 (26%) is itself profiler noise. Conservative read: P3 fails -> M2a
  TIME-BASED claims are VOID per its own rule.
- P1/P2 (CUDA GEMM share, memcpy bytes): **NOT EVALUABLE** — cuda_us = 0 for every
  event in all 4 prompts: CUPTI/CUDA activity capture does not attach to this engine
  on WSL2. h2d_count=0/d2h_count=0 are capture artifacts, NOT zero traffic.

## Findings that survive (count-based, exact, not time-based)
1. **Op-count soup at b1 decode**: per 64-token prompt (count/64 = per step):
   aten::mul 213/step, aten::copy_ 200/step, aten::add 130/step, aten::mm 81/step,
   pow/rsqrt/cat/mean 65/step each, empty/zeros/fill ~200+/step combined, topk/_softmax/
   sum/scatter_ **exactly 16/step** (= one router call per layer per step, 16 layers).
   Roughly 700+ aten dispatches per decode step.
2. **Profiler CUDA attribution is dead on this box** (WSL2 CUPTI limitation): any CUDA
   time split needs counters or non-kineto tooling. This is why the adjudication
   specified dispatcher counters (M2b) rather than profiles — confirmed by measurement.
3. Context only (P3-confounded): prompt-3 top-40 self-CPU sum 2,066,380 us in a
   5,910,300 us wall (35.0%) — consistent with, but not proof of, a large CPU
   dispatch share; M2b counters + a clean unprofiled A/B decide.

## Consequence
The 2.36x localization question moves entirely to M2b (FREEZE-828B.json, running):
hit_rate, exposed_fetch_seconds, occupancy at 0.50/0.65/0.75/0.90 with counters read
outside the timed region.

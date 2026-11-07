# exp743 PREREG — is the engine's per-token overhead GPU-idle time (host-bound) or GPU-busy time?

Lane 79990, program STACK-1001-79990. Written 2026-11-06, BEFORE any exp743 cell. Namespace: exp739–742 are in use by
other lanes, and exp743 had no directory, running.json or queue entry when checked. Follows the pre-decided consequence of
exp738 (ADDENDUM68: GROUPED-FLAT, so per-expert launch count is not the lever; next, instrument the handoff path).

## Evidence carried in
- exp738 (admitted #70), clean cells on Winnie GPU1 (RTX 5060 Ti), OLMoE-1B-7B bf16, lcnu @ 0.75, decode ms/token:
  HF 31.3 | engine t4 (default) 92.1 | grouped decode kernel 93.1 (engaged: about 52.5k grouped experts per cell; parity OK)
  | t1 156.1 | t8 107.2. Engine gap = 60.8 ms/token. The thread count moves it a lot (t1 → t4 = −41%), and the one-launch-per-layer kernel does nothing.
- Code: `wait_expert` releases once exec threads have *enqueued* work (expert_dispatcher.cpp CompleteOne). exp736
  (corrected for its 2x wrapper defect) put ~36.5 ms/token in the per-layer wait and ~22 ms in the end-of-step D2H sync.
- None of this says whether the GPU is actually *working* during the gap. Thread sensitivity fits host-side work (weight
  fetch/H2D on misses, per-expert bookkeeping) or GPU-side copy/kernels that the threads feed. This run settles that split.

## Instrument
An NVML sampler (`nvsamp.py`, ctypes → WSL libnvidia-ml, 50 ms poll) records utilization.gpu for GPU1. utilization.gpu is the
percent of the driver's sample period with ≥1 kernel executing. It is tested on Winnie: the value refreshes ~every 6 polls,
so the effective driver period is ~0.3 s. Each cell's sampler starts 10 s before its model process, giving an idle baseline.
Each generate() call records its epoch window (`win_full`). Per prompt: busy_frac = mean util in the window,
busy_ms = ms/token × busy_frac, idle_ms = ms/token × (1 − busy_frac).
Limits, stated now: utilization.gpu counts copy engines only if a kernel is concurrently running. It can't see sub-period
interleaving. Windows include the prefill (≈0.1 s of ≈6–30 s). Interpretation is about magnitudes, not single-ms precision.

## Questions and predictions (registered)
- Q1 SPLIT: is the t4-vs-HF gap mostly GPU-idle time? **Prediction GAP-IS-GPU-IDLE** (confidence 0.7).
- Q2 GRP: grouped kernel vs t4 → **GRP:NO-CHANGE** (it did nothing to ms/token in exp738). Confidence 0.8.
- Q3 T1: t1 vs t4 → **T1:IDLE-UP**: fewer threads add GPU-idle time. Confidence 0.65.

## Design (frozen)
Winnie WSL, GPU1 only, same model, engine build, policy, ratio, prompts (6) and protocol as exp738. The exceptions are
max_new = min_new = 192 (longer windows for the coarse sampler) and warmup 1. 8 cells, serial, palindromic:
hf_1, t4_1, grp_1, t1_1, t1_2, grp_2, t4_2, hf_2. The grp arm uses `MOE_INFINITY_UNVALIDATED_HW=1 MOE_GROUPED_DECODE=1`, and the eng arms
unset it. The run starts after units exp738/740/741/742 are inactive. Quietwait is bounded at ≤5400 s, and the power plan is recorded, never changed.

## Exclusion rules
A cell is excluded from all comparisons if any of these hold: (a) pre-start GPU1 >1024 MiB, a loaded Ollama model, or a failed
probe; (b) mon.sh sees a mid-cell foreign GPU1 process or an Ollama load; (c) its idle-baseline util (first 8 s) has mean >5% or
is missing; (d) any prompt window has <20 util samples; (e) RC≠0.

## Decision rules (analyze.py, frozen; dry-run on synthetic idle/busy/dirty inputs gave the intended branches)
- Arm values are means over clean cells. gap = t4.ms − hf.ms, d_idle = t4.idle − hf.idle, d_busy = t4.busy − hf.busy.
  If d_idle ≥ 0.5·gap → GAP-IS-GPU-IDLE. Else if d_busy ≥ 0.5·gap → GAP-IS-GPU-BUSY. Else GAP-MIXED.
  No clean hf or t4 → SPLIT:INCONCLUSIVE.
- GRP/T1 vs t4: |Δms| < 3 → NO-CHANGE. Otherwise {IDLE|BUSY}-{UP|DOWN}, by whether |Δidle| ≥ |Δbusy|.
  Manipulation checks: threads_effective == requested, and grouped_experts > 0 only in grp. A failure makes that verdict INCONCLUSIVE.
- Verdict line: `VERDICT <SPLIT>|GRP:<..>|T1:<..>`.

## Consequences (decided now)
- GAP-IS-GPU-IDLE: the engine leaves the GPU waiting on host work. Next, add per-stage host timers inside the exec thread
  (fetch-wait vs launch vs callback) via the engine's existing compute-sample hook. Then test a CUDA-graph or
  persistent-launch decode step, and the miss-free condition (all experts resident) to separate fetch from bookkeeping.
- GAP-IS-GPU-BUSY: the GPU does extra work per token (copies, unfused small kernels). Next, count kernels and memcpy per token, and
  target the copy path (exp726: aten::copy_ was 46% of CPU-side ops).
- GAP-MIXED: run both follow-ups at half scope.

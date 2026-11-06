# exp738 PREREG — where does the engine's per-expert exec time go? Grouped decode kernel and exec-thread ladder

Lane 79990, program STACK-1001-79990, owner: Telegram thread 79990 session. Written 2026-11-06 (~15:40Z), BEFORE any exp738
cell, while exp736 is still running on Winnie GPU1. Namespace check: exp737 is taken (cron lane 7687a6bf1295,
`exp737-moei-multigpu-colocate-fix`), so this is exp738. It is reserved in running.json.

## Why (evidence carried in, and its limits)
- exp726 (admitted #68): MoE-Infinity at 0.75 runs at 10.39 tok/s. HF bf16 runs at 30.17 tok/s on the same GPU. The gap is engine overhead.
- exp736 (pass-4 profile, p_eng, admitted cell, NOT yet settled): `wait_dispatch_local` was counted at 73.1 ms/tok over 32
  calls/tok. A defect was found after that cell: prof2.py wraps both `ExpertExecutor` and its alias `DistributedExpertExecutor`
  (they are the same class), so each method is wrapped twice. Counts and times are exactly 2.000x real (toy
  reproduction: 16 real calls give 32 counted, ratio 2.000). The corrected figure is 36.5 ms/tok over 16 calls/tok (1 per layer, OLMoE has 16 layers),
  about 2.3 ms per layer. End-of-step logits D2H blocking accounts for 22.3 ms/tok.
- Code reading (MoE-Infinity 0337988, `core/parallel/expert_dispatcher.cpp`): the `pending_` decrement that releases
  `wait_expert` (`CompleteOne`) runs as soon as an exec thread has *enqueued* an expert's kernels and its retirement
  `cudaLaunchHostFunc`, not when the GPU finishes. The layer wait is therefore CPU-side handoff plus per-expert launch work
  (top-8 gives about 285 us per expert). The GPU trails behind, and the 22 ms end-step D2H is that backlog draining.
- The engine ships a batched grouped decode kernel (one launch per layer instead of per-expert work). Its gate is
  `hw::Gate::kRtxPro6000`. The 5060 Ti is SM120 (compute cap 12.0), and `_store.so` contains sm_120/sm_120a SASS. OLMoE shapes
  pass `grouped_moe_decode_pro6000_supported` (hidden 2048, inter 1024, %32 == 0, silu). The stock switch
  `MOE_INFINITY_UNVALIDATED_HW=1` lifts only the RTX-PRO-6000 gate, never SM120.

## Questions
- Q1 (GROUPED): does turning on the grouped decode path on the 5060 Ti cut engine decode ms/token, with correct output?
- Q2 (THREADS): does the exec-thread count (`num_threads` 1 / 4 = default / 8) change ms/token? If per-expert handoff is
  thread-serialized, more threads help. If it is serialized on the device launch path, they don't.

## Registered predictions
- Q1: **GROUPED-WINS**, and the grouped arm closes at least 25% of the base-vs-HF gap. Confidence about 0.6. Risks: grouped may not
  engage (residency or descriptor conditions), or the per-layer CPU-side routing work may dominate anyway.
- Q2: **THREADS-FLAT**. Confidence about 0.5. Launches into one device from multiple host threads serialize in the driver.

## Design (frozen)
- Host Winnie (WSL Ubuntu), GPU1 only (CUDA_VISIBLE_DEVICES=1), RTX 5060 Ti 16 GB. Model OLMoE-1B-7B-0125-Instruct, bf16.
  Engine: MoE-Infinity editable install (commit recorded in out/ENV.txt), policy lcnu, device_memory_ratio 0.75, offload
  ~/moe-offload. Prompts: exp736 prompts.json (6 prompts), greedy, max_new 64, min_new 64, warmup 1. One model per fresh process.
- 10 cells, serial, palindromic order (drift cancels):
  hf_1, base_1(t4), grp_1(t4, grouped), t1_1, t8_1, t8_2, t1_2, grp_2, base_2, hf_2.
  `eng` cells run with `MOE_INFINITY_UNVALIDATED_HW` unset. `grp` cells set `MOE_INFINITY_UNVALIDATED_HW=1 MOE_GROUPED_DECODE=1`.
- The power plan is never changed (it is recorded per cell only). Starts only after exp736/734/735/737 units are inactive.
- Contamination rule (same as AMENDMENT1+2 of the co-tenancy policy): each cell runs a bounded quietwait first (≤2700 s, 30 s poll).
  A cell is FLAGGED if, before start, GPU1 shows >1024 MiB, or Ollama /api/ps shows a loaded model, or the probe fails (-1).
  It is also FLAGGED if mon.sh sees a mid-cell foreign GPU1 process or an Ollama model load. FLAGGED cells are excluded from speed comparisons and kept for
  correctness and manipulation checks. A FAILED cell (RC≠0) is excluded everywhere.

## Metrics and rules (implemented in analyze.py, frozen)
- Cell metric: the median over the 6 prompts of decode ms/token = 1000 / decode_tok_s. decode_tok_s = (n−1) / (t_full − t_1tok).
- Arm metric: the mean of its CLEAN reps. noise = the max within-arm relative rep spread over the engine arms that have 2 clean reps.
  Threshold `thr = max(0.05, 2·noise)`.
- Manipulation checks: (a) `threads_effective == threads_requested` for every engine cell. If not, THREADS is INCONCLUSIVE.
  (b) `grouped_experts` delta > 0 in every grp cell, from the dispatcher's `get_routing_stats`. If not,
  `GROUPED:NOT-ENGAGED`. The base/t1/t8 total is reported and expected to be 0.
- Parity (grp): token-match fraction against hf_1 per prompt. CORRECT iff mean(grp vs hf) ≥ mean(base vs hf) − 0.05, and no prompt
  diverges from HF before token 8 unless base also diverges from HF before token 8 on that prompt.
- GROUPED: rel = (base − grp) / base. Not correct → GROUPED-INCORRECT. rel ≥ thr → GROUPED-WINS. rel ≤ −thr → GROUPED-SLOWER.
  Otherwise GROUPED-FLAT. Also reported: gap_closed = (base − grp) / (base − hf).
- THREADS: g41 = (t1 − t4) / t1 and g48 = (t4 − t8) / t4. If either ≥ thr: THREADS-HELP (or THREADS-MIXED if the other ≤ −thr).
  Otherwise, if either ≤ −thr: THREADS-HURT. Otherwise THREADS-FLAT.
- If an arm has no clean cells, the relevant verdict is INCONCLUSIVE. The verdict line is `VERDICT <GROUPED…>|<THREADS…>`.
- The analyzer dry run on synthetic inputs (win / flat / incorrect / not-engaged) gave the intended branches. Inputs were in scratch and were deleted.

## Consequences (decided now)
- GROUPED-WINS: propose upstream that the grouped decode gate be widened to SM120 consumer cards, with this data. That needs a
  separate fork post first. Then measure grouped + 2 GPUs (exp734 lane permitting).
- GROUPED-FLAT or NOT-ENGAGED: the per-layer cost is not per-expert launch. Next, instrument the routing/handoff path
  (`SetInputs` → `DispatchExperts` → exec-thread wakeup) with the engine's existing compute-timing hook
  (`SetOverlapComputeTimingEnabled`), and test a CUDA-graph decode step.
- GROUPED-INCORRECT: file a correctness note, and do not enable it.
- THREADS-HELP: retune the default. THREADS-FLAT: thread count is ruled out as a lever.

# exp736 PREREG — where does the engine's per-token overhead go? (overhead budget, rule-out ladder)

Lane 79990 (STACK-1001-79990). Written and frozen BEFORE any admitted cell. Follows exp726 (admitted #68):
engine@0.75 = 10.39 tok/s vs plain HF bf16 30.17 tok/s on the same GPU1 -> ~63 ms/token of engine overhead.

## Disclosure: smoke runs informed this design
Crash-only smoke (~/exp736-smoke on Winnie, NOT admitted, n=1, ntok 2-4) showed: HF and engine issue ~the same number of
tiny copies (191 vs 199/token), engine copies cost 5x more each; main-thread aten self-CPU is similar (73 vs 67 ms,
profiler-inflated); engine 127 ms/token split = wait_dispatch_local 51.3 (32 calls/token), end-of-step logits D2H sync
22.0, dispatch_local 8.2, d2d casts ~10. Micro: kernel launch 23 us, launch+sync 91 us, pinned H2D 15 GB/s on GPU1.
**Prediction registered from smoke: BUDGET = EXPERT-WAIT-BARRIER.** The admitted run tests whether it reproduces at
ntok=16, on a quiet-checked GPU, and with the frozen analyzer.

## Cells (cells.json, serial, Winnie, OLMoE-1B-7B-0125-Instruct bf16, MoE-Infinity 0337988 build)
- m_g1_A, m_g0_A, m_g1_B: micro.py unit costs (launch, sync, item, alloc, 16 KB and 12.6 MB-expert H2D/D2H pinned+pageable).
- p_hf, p_eng: prof2.py decode-only profile, ntok=16, prompt 0, difference of generate(17) and generate(1):
  pass 1/2 torch.profiler (CPU); pass 3 dispatch-mode copy trace (direction, Python site, blocking wall);
  pass 4 (engine) inclusive wall per ExpertExecutor method. Engine ratio 0.75, lcnu (same as exp726).
- t1..t4: ABBA Windows power plan (A=Balanced, B=High performance), arms eng (ratio 0.75) and hf, 6 prompts x 64 tokens,
  order A B B A, using exp726's engine_arm.py/hf_arm.py unchanged.

## Decision rules (frozen analyze.py)
1. BUDGET (primary): component shares of engine ms/token: EXPERT-WAIT-BARRIER = wait_dispatch_local/pass4 total;
   END-STEP-SYNC = logits D2H at _native_model_forward / pass3 total; DISPATCH-CALL = dispatch_local / pass4;
   DTYPE-CASTS = (engine d2d - hf d2d) / pass3. Verdict = largest if its share >= 0.35, else DIFFUSE.
   Consequence: EXPERT-WAIT-BARRIER -> next exp instruments the C++ side of the barrier (queue latency vs kernel time
   vs transfer wait). END-STEP-SYNC -> keep sampling on GPU / overlap next-step launch. DISPATCH-CALL -> Python
   dispatch-path trimming. DIFFUSE -> CUDA graph / whole-step capture.
2. POWER (secondary, per arm, clean cells only): ratio = mean(B)/mean(A) of block medians. POWER-SENSITIVE if >= 1.05 and
   min(B) > max(A); POWER-RULED-OUT if < 1.05; else POWER-AMBIGUOUS.
3. Parity (correctness, reported): engine vs hf greedy outputs, t1 block, per prompt.
4. Descriptive only (no gate): micro unit costs; launch cost x extra aten events; link bandwidth pinned vs pageable.

## Contamination (AMENDMENT-style rules built in)
Before each cell: quietwait.sh (<=2700 s) + pre-start record (GPU MiB, Ollama models, power plan, load). Flag if
GPU > 1024 MiB, Ollama model loaded (or probe failed), or power plan not applied. During each cell, mon.sh polls every
10 s for foreign gen.py/ollama/llama-server processes with the cell's GPU in CUDA_VISIBLE_DEVICES, or Ollama models,
and flags the cell. Flagged cells are excluded from POWER; the BUDGET is reported with a FLAGGED mark if p_* is flagged.
Load average and GitHub Actions Runner.Worker presence are logged per cell (covariate, no exclusion).

## Side effects (authorized by Michael, "Do the next steps")
The runner switches the Windows power plan between Balanced and High performance and restores Balanced on any exit
(trap). It does not pause or kill other processes; CPU contention is logged, not controlled.

## Admission
Counts as one admitted experiment on a complete or explicitly MISSING-marked sealed verdict.

# EXP-825 Stage 2 — batch amortization walls (prereg, frozen before run)

Question: with batched decode unblocked (rotary device guard, sha c7b55109…), what is
the measured wall-time amortization of batched greedy decode vs batch-1, un-instrumented?

## Harness (batch-wall-825.py)

- One process, model OLMoE-1B-7B-0125-Instruct via moe_infinity.MoE, offload
  `~/moe-offload-olmoe-0125-r05`, device_memory_ratio 0.50, lcnu, num_threads 4,
  gpu_only_expert_routing True, adaptive_resident_mode legacy, speculative_prefetch False.
- 8 fixed prompts (PROMPTS below), left padding, greedy, max_new_tokens 128,
  pad_token eos. Fixed length ⇒ Σtokens = 128 per prompt.
- Throwaway warmup arm (b1, 8 new tokens) before any measured arm.
- Measured arms: b ∈ {1, 2, 4, 8} × 3 rounds, interleaved in a seed-fixed shuffled
  order (seed 20261118), wall measured around m.generate only (time.perf_counter),
  tokens recorded per run. Batch-b arm uses the FIRST b prompts of the fixed set
  (prefix property: b=1 set ⊂ b=2 set ⊂ …).
- Quiet gate: loop (≤10 min) until load5 < 3.0 and GPU-1 util < 5% before measured arms.
- No shims, no monkeypatch, no instrumentation: the rotary guard is the installed file.
- Output: exp825-batchwalls.json {meta, warm, blocks: [{arm, round, prompts, wall_ms, n_tok, n_gen}]}

## Analysis plan (frozen)

- Per batch size: median wall over 3 rounds; tokens/s = (b×128)/median_wall.
- Speedup(b) = tokens/s(b) / tokens/s(1); per-prompt wall cost = median_wall/b.
- Only within-process (within-battery) comparisons are claimed. No cross-battery deltas.
- Expected: amortization ≥ 1.0; the exp810-observed 7.2× orchestration share predicts
  large headroom. No pass/fail gate — this is a measurement, reported as measured.

PROMPTS (fixed order):
1. "Explain what a cache is in computing."
2. "Write a haiku about mountains."
3. "Summarize the water cycle."
4. "List three uses of copper."
5. "Describe a red-black tree."
6. "Give tips for better sleep."
7. "Explain why the sky is blue."
8. "Name the planets in order."

Freeze: manifest FREEZE-825b lists sha256 of this file and batch-wall-825.py before launch.

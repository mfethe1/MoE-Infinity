# PREREG-M1 — exp827: all-resident reference vs streaming engine (pivot decider)

Frozen 2026-11-19 (see FREEZE-827.json). Design from MYTHOS-ADJUDICATION-20261118.md §2.

## Question
Does expert-offload streaming tax b1 decode relative to a no-engine, fully-resident
reference on the same GPU? This single measurement decides the program pivot:
- P1 (pivot-a): REF_b1 throughput >= 1.5x ENG_b1(0.50)  -> residency/dispatch taxes b1;
  pivot to quantized full residency for fit-able models + in-engine dispatch elimination (#7);
  move RAM-first benchmarking to a model >= 2x VRAM.
- P2 (stay-c): REF_b1 within 20% of ENG_b1  -> engine already at the residency floor;
  batching-repair (#6) is the only lever worth engine dev.
- P3 (context): REF_b8 recorded as the ceiling any multi-token repair (#6) aims for.

## Arms (separate processes; restart-flag rule)
- REF: plain HF transformers AutoModelForCausalLM, bf16 fully on GPU (fallback: 8-bit, recorded),
  greedy, min_new_tokens=128 forced (EOS disabled), 8 fixed prompts (MEASURE-825 set), b1 and b8.
- ENG: moe_infinity engine, device_memory_ratio 0.50 (frozen config), same prompts, b1 only.
- Interleave as process pairs: REF, ENG, REF, ENG ... 3 pairs (6 measured blocks per arm shape),
  each process burns in its arm shape once before its measured block.

## Measurement
- wall = time.perf_counter around generate() only, outside: load, tokenization, loadavg read.
- denominator = actual non-pad new tokens (min_new_tokens=128 forced; assert 128 per sequence).
- b8 = left-padded batch of the same 8 prompts (prefix property).
- Quiet gate at every block boundary: load5 < 3 and gpu1 util < 5 before the next block.
- Publish all blocks in run order; no cross-phase medians.

## Predictions frozen before run
- REF_b1 tok/s: unknown; decision by the P1/P2 thresholds above.
- REF_b8 expected >= 4x REF_b1 per-step amortization of dense compute (pure-GPU batch scales).
- ENG_b1 expected ~11.2 tok/s (exp825 fast phase).
- If bf16 REF OOMs: 8-bit fallback runs; P1/P2 evaluated against quantized-residency reference
  (favorable to pivot-a interpretation), recorded as such.

## Non-goals
No engine changes. No tok/s claims beyond these arms. No grouping inference.

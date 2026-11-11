# PREREG-779 — generation-loop overhead: behavioral wall test

Registered before any exp779 run. Prior: exp778 attributed 52% of non-LOAD
decode py-spy samples to the HF generate machinery (GENLOOP), with the stated
caveat that Python frames cannot split CPU work from GPU-wait.

## Question
Does removing the per-token generate machinery move decode wall, or was the
52% GPU-wait hiding under Python frames?

## Design (single variable)
- Same envelope as exp777/exp778: OLMoE-1B-7B-0125-Instruct via MoE-Infinity,
  src776 AS-BUILT (sha 3571f714c811e1c7), lcnu r=0.75, threads 4, gpu-route
  off, spec-prefetch on, spec-overlap off, overlap-policy off, 24 prompts
  x 64 tokens, warmup 1, CUDA_VISIBLE_DEVICES=1, py-spy 50 Hz + OS sampler.
- PY_A: engine_arm776.py — HF model.generate greedy baseline (exp777 R075
  configuration).
- PY_B: engine_arm779b.py — manual greedy decode loop (prefill + argmax
  steps) over the same wrapped model with transformers DynamicCache. Removes
  logits-processor chain, stopping criteria, prepare_inputs_for_generation,
  sampler dispatch. Expert-offload hooks (module forwards) untouched.
- W(arm) = sum over 24 rows of (t_1tok + t_full); delta = (W_A − W_B)/W_A.

## Frozen decision rule
- rc=9 IDENTIFY-FAIL: env/src/src776-sha/engineB-sha mismatch or PY_B json
  not arm B.
- rc=4 DATA-FAIL: BADIO non-empty; A nonzero RC, missing, <20 rows, or
  outside covariate gate [137.00, 228.33] (exp775 DB ref 182.66 ±25%);
  B nonzero RC/missing; B rows n_new != 64.
- rc=1 LARGE-MOVE: delta >= 0.15 — overhead is real Python cost; successor:
  productize manual/static decode path (then StaticCache step).
- rc=2 MILD-MOVE: 0.05 <= delta < 0.15.
- rc=7 NO-MOVE: delta < 0.05 — GENLOOP share was GPU-wait in disguise;
  decode compute/attention-bound; redirect to ATTN lane.

## Report-only (not gates)
- out_sha agreement A vs B (greedy; kernel-shape changes may diverge tokens).
- tok/s per arm; B n_new==64 check is a gate.
- py-spy traces of both arms retained for follow-up attribution.

Registered 2026-11-11, before staging/running. Failure discipline: a cell
with nonzero RC is recorded, not voided; VOID only for premise-false attempts.

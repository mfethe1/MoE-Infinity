# PREREG-781 — async double-buffer vs blocking topk (batch-1 manual-loop decode)

## Motivation (evidence chain)
- exp778 (py-spy): decode residual attributed GENLOOP 52% — later shown GPU-wait in Python frames.
- exp779: generate machinery NO-MOVE (manual loop = HF generate within +2.3%/token).
- exp780 (io.jsonl, 125,440 events): 82% of the 184.93 s decode wall sits in per-layer
  handoff machinery: expert_completion_handoff 59.24 s + sync_wait 59.45 s +
  expert_dispatch 16.87 s + gpu_route_fallback 16.62 s (routing 0.07 s).
- The running envelope (src776, EXP773_DB=1) ALREADY uses the async double-buffered
  topk copy (PR #358 mechanism, folded into the experiment lineage behind EXP773_DB).
- exp774 measured the same mechanism at batch 4x: -75% spec-prefetch wall overhead.
  Unknown: does it matter at batch-1 decode, and what does its absence cost?

## Question
Does the async double-buffered topk GPU->CPU copy move batch-1 manual-loop decode
wall time vs the blocking `.indices.cpu()` path?

## Design (single variable)
- Arm PY_ADBUF: src776 AS-BUILT, EXP773_DB=1 (async double buffer) — exact config of
  exp779/780 (their refs: W=190.00 / 184.93).
- Arm PY_BLOCK: identical engine, identical source, identical flags; EXP773_DB unset
  (blocking topk D2H in expert_prefetcher.speculative_prefetch).
- Engine engine_arm781.py = engine_arm779b (manual greedy loop, DynamicCache) retagged;
  both arms run the SAME file; engine records env EXP773_DB (env_db) and echoes
  "exp781 db=<0|1> ok=True".
- Envelope: OLMoE-1B-7B-0125-Instruct, lcnu r=0.75, threads 4, gpu-route off,
  spec-prefetch on, spec-overlap/overlap-policy off, 24 prompts x 64 tok, warmup 1,
  CUDA_VISIBLE_DEVICES=1, venv moei-engine, torch 2.11.0+cu128, transformers 5.22.1.
- W = sum over 24 prompts of (t_1tok_s + t_full_s) per arm.

## Decision rule (frozen)
delta = (W_block - W_adbuf) / W_block
- rc 1 OVERLAP-MATTERS: delta >= 0.15
- rc 2 MILD: 0.05 <= delta < 0.15
- rc 7 NO-MOVE: -0.03 < delta < 0.05
- rc 3 ADBUF-REGRESSION: -0.10 < delta <= -0.03
- rc 5 LARGE-REGRESSION: delta <= -0.10
- rc 9 DATA-FAIL: identify/banner/rc/n_new/env_db/covariate failures
- rc 4 DATA-FAIL (BADIO)
Covariate: W(adbuf) in [142.50, 237.50]. n_new must equal 64 on every row.
Report-only: out_sha agreement, tok/s, io.jsonl stage durations per arm.

## Predictions (pre-data)
- P(async saves >=15%) = 0.25 — the blocking path drains in-flight expert transfers
  ~16x/token; at batch-1 there is little other work to hide behind.
- P(MILD 5-15%) = 0.35, P(NO-MOVE) = 0.30, P(regression) = 0.10.
- If NO-MOVE: the sync_wait/handoff wall is expert WEIGHT transfer + handshake, not
  the tiny topk copy (64 longs); successor = transfer-overlap/quantization lane.
- If OVERLAP-MATTERS: PR #358's mechanism is a batch-1 lever too; successor = extend
  double-buffering to the remaining per-layer syncs.
- out_sha agreement expected 24/24 (prefetch list staleness affects residency, not math).

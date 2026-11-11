# PREREG-784 — FP8 vs BF16 ratio sweep in the miss-heavy regime

Date: 2026-11-11 (preregistered BEFORE any A/B cell run; qualification probes already run,
8 prompts x 32 tok, not sealed: bf16@0.25 = 10.07 tok/s, miss 46.7% (20,952 misses);
fp8@0.25 = 10.88 tok/s, miss 23.9% (10,702 misses) — regime knob WORKS; probe delta +8.0%.)

## Question
At device_memory_ratio 0.25 and 0.50 (miss-heavy / mixed regimes), does uniform-FP8 expert
residency raise batch-1 decode throughput vs BF16? Secondary: does the mechanism show up as
bytes-per-miss (speed scales with miss rate) or working-set shrink (fp8 miss COUNT halves,
per-miss cost unchanged)?

## Arms (same treatment pairing as exp783)
- B: ~/moe-offload (bf16 13.84 GB) + legacy   - F: ~/moe-offload-fp8 (7.41 GB) + uniform_fp8

## Cells (8, serial interleaved, quiet GPU1, greedy, warmup 1, 24 diverse prompts x 32 new)
B25a F25a B50a F50a B25b F25b B50b F50b   (a/b = repeats for within-config determinism)

## Build identity (gates)
PYTHONPATH=/home/mfeth/exp759/src753; HEAD b7f6ca4d2caa5229698d78deb03b454fc20947dd;
imported _store*.so sha in out/RUN_SHA256 (expect f54e5756ee18..., same as exp782/783);
engine_arm783.py byte-identical to exp783 (adds --resident-mode only); prompts24.json new
(24 diverse-topic prompts, sha in freeze) to widen the expert working set.
Analyzer gates: res.resident_mode, res.offload basename, res.ratio == cell ratio.

## Metrics (extraction over frozen out/ only)
per-config mean decode_tok_s (2 cells), miss counts/rates (policy_routed_hits/misses sums),
deltas d25, d50; within-config determinism (a==b out_sha sequences); util quiet gate (report).

## Verdict map (rc)
1 MAJOR-POS  max(d25,d50) >= +0.50
2 MILD-POS   +0.10 <= max < +0.50
3 NO-MOVE    max < +0.10 (bytes per miss do not set the wall even when misses dominate)
5 FP8-NONDET (any F config a!=b while B configs deterministic)
9 DATA-FAIL  (missing/short cell, mode/store/ratio gate mismatch, B config nondeterminism)

## Interpretation plan
- rc1/rc2 with misses_F ~ misses_B at matched tok/s gain scaling with miss rate -> bytes bound
  in the streaming regime -> FP8 = real speed lever for memory-constrained devices.
- rc2/rc3 with misses_F ~ 0.5x misses_B (probe pattern) -> working-set mechanism: fp8 buys
  fewer evictions, not faster transfers -> capacity lever only; per-miss cost latency floor.
- rc3 everywhere -> decode wall = fixed per-miss latency + dispatch overhead; next lever =
  batching/pipelining expert reads or GPU-side dispatch, not byte reduction at any residency.
- Quality drift: cross-arm out_sha diffs counted per ratio (exp783: 5/6 differ at 0.75);
  informational, no gate.

## Attempt budget: 3 (fresh prereg; exp783's attempt budget was its own). No post-hoc gate
edits on sealed data; premise-false attempt = VOID + fresh prereg.

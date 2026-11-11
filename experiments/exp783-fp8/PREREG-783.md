# PREREG-783 — FP8 quantized expert streaming (uniform_fp8 residency) vs BF16 store

Date: 2026-11-11 (preregistered BEFORE any A/B cell runs; smoke load-only probe already
performed: fp8 store converts 7.0G vs 13G bf16; uniform_fp8 mode activates; 48-tok cold
generate 7.35 tok/s, coherent text. No steady-state A/B data seen.)

## Motivation
exp781 profile: decode wall = 82% expert-weight handoff; bus math 10.33 tok/s x ~1.61 GB/token
~ 16.6 GB/s ~ PCIe gen4 x8 ceiling -> if bytes-bound, halving expert bytes must move the wall.
FP8 store (E4M3, block 128, dequant-to-BF16 or native sm_120 path) halves expert bytes.
Alternative: decode wall is latency/serialization-bound -> FP8 gain < +10% (possibly negative
from dequant overhead).

## Question
Does uniform-FP8 expert residency raise batch-1 decode throughput vs BF16 store, same build,
quiet GPU1?

## Arms (single treatment = store + resident mode, engine authors' intended pairing)
- B (baseline): ~/moe-offload (bf16), adaptive_resident_mode=legacy  [exact exp781/782 config]
- F (treatment): ~/moe-offload-fp8 (fp8 store), adaptive_resident_mode=uniform_fp8

## Cells (serial, interleaved, all quiet, CUDA_VISIBLE_DEVICES=1, greedy, warmup=1, 24 prompts x 64 new)
B1, F1, B2, F2  (repeats give within-arm determinism check + variance)

## Build identity (gates)
PYTHONPATH=/home/mfeth/exp759/src753 (moei-RC753); src753 HEAD b7f6ca4d2caa5229698d78deb03b454fc20947dd;
imported _store*.so sha recorded in out/RUN_SHA256; engine_arm783.py = exp782 engine_arm.py +
--resident-mode flag (diff recorded); torch 2.11.0+cu128; src753 contains FP8 machinery (0337988
"native FP8 on sm_120" is an ancestor of b7f6ca4). exp752 banner expected (mode=0) as build evidence.
Analyzer gates: res.resident_mode matches arm spec; res.offload basename contains fp8 (F) / not (B).

## Metrics (extraction over frozen out/ only)
per-cell mean decode_tok_s over 24 rows; arm mean = mean of its 2 cells; delta = F/B - 1;
within-arm out_sha sequence equality (B1==B2, F1==F2); cross-arm sha differences counted
(expected: all differ - numerics change); per-arm load_s; util_mean <= 20 quiet gate.

## Verdict map (rc, written by analyze783.py to out/verdict.json + verdict.txt)
1 MAJOR-POS  delta >= +0.50   (bytes-bound confirmed; FP8 streaming is a big lever)
2 MILD-POS   +0.10 <= delta < +0.50
3 NO-MOVE    delta < +0.10 (includes negative; latency-bound hypothesis favored)
5 FP8-NONDET (F1 != F2 while B deterministic)
9 DATA-FAIL  (missing/short cell, mode/store gate mismatch, or B-arm nondeterminism)

## Interpretation plan
- rc=1: BELIEFS += decode-bytes-bound; next: fp8 + prefetch depth/batching of reads.
- rc=2: bytes matter but another serial floor remains (per-read latency) -> hybrid lane.
- rc=3/negative: wall is per-call latency/serialization, not bandwidth -> next lever:
  batching/pipelining of expert reads or resident-set sizing, NOT byte reduction.
- rc=5: FP8 numerics nondeterministic under quiet greedy -> report, deprioritize.

## Attempt budget: 3 (this prereg = attempt 1 when launched fresh). No post-hoc gate edits
on sealed data; premise-false attempts are VOID and re-preregistered.

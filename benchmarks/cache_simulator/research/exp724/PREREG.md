# exp724 PREREG — real-engine decode throughput: does engine hit rate predict tok/s, and does PCIe link placement matter?

Frozen BEFORE any real run (ARTIFACT.sha256 + freeze commit). Sealed experiments are never edited or re-launched.
Lane 79990, program STACK-1001. Namespace: exp724 was free in ~/warp-work, running.json and experiment_queue.json
at registration (exp719-exp723 held by other lanes or in flight).

## Why this, now (Bayesian model, STACK-1001-79990/BELIEFS.json, 2026-11-05)
Since exp643, every policy result was measured in the simulator on hit rate. exp715 proved the C++ engine
policy equals the simulator (27/27), but no experiment has measured whether hit rate moves **decode tokens/s** in the
real engine. Posterior for `sim2real` = 0.64 (sd 0.25, n=2 weak). That direction gates the value of every remaining
policy experiment (FOLLOW C++ port, rings, tuning). `link_placement` (posterior 0.60, sd 0.26) is the top-ranked
candidate by expected gain per hour: exp720 showed Winnie GPU0 sits on PCIe gen3 x2 (1.56 GB/s, PCIe-bound) while
GPU1 has gen4 x8 (disk-bound ~3 GB/s). Every prior engine smoke ran on GPU0.

## Disclosed pre-freeze smoke (not data)
One engine_arm cell, GPU1, lcnu, ratio 0.2, 1 prompt, max_new 16: load 53.0 s, 9.92 decode tok/s, hits+1199 miss+2481,
capacity 272 experts (3.42 GB), out_sha 60c33bf2a92ca44b. smoke3 (GPU0, ratio 0.2, gen32 incl. prefill, different
method) gave ~2.0 tok/s. This smoke motivated H2 and is excluded from analysis.

## Host, model, engine
Winnie (WSL2 Ubuntu, 2x RTX 5060 Ti 16 GB sm_120; GPU0 PCIe gen3 x2, GPU1 gen4 x8), torch 2.11.0+cu128,
MoE-Infinity 0.2.3.dev58 (upstream main 0337988 + local build), OLMoE-1B-7B-0125-Instruct (16 layers x 64 experts,
top-8), offload ~/moe-offload. One fresh engine process per cell (one model per process).

## Design
- Arms: GPU1 x policy {lcnu, s3fifo, lru} x device_memory_ratio {0.12, 0.20, 0.35} (9) + GPU0 x {lcnu, s3fifo} x 0.20 (2).
- 3 blocks; each block runs all 11 arms in a fixed shuffled order (Random(724+block), cells.json); blocks in order.
  Serial: never two engine processes at once (shared disk/host memory would confound).
- Per cell: warmup 1 ("Say hello.", 8 tokens), then 6 fixed prompts (prompts.json), greedy, max_new = min_new = 64.
  Per prompt: 1-token probe then full run; decode_tok_s = 63 / (t_full - t_1tok). Engine counters
  policy_routed_hits/misses deltas per prompt via get_expert_policy_stats.
- Block statistic = median over the 6 prompts of decode_tok_s; arm statistic = mean over 3 blocks; CV over blocks.
- Cell miss rate = sum misses / sum (hits+misses) over the 6 prompts; arm miss rate = mean over blocks.

## Gates and hypotheses (analyze.py, frozen; verdict line printed verbatim)
- G0 CORRECTNESS: per prompt, greedy output sha identical across all 33 cells. FAIL -> verdict prefix CORRECTNESS-DIVERGE
  (timings still reported).
- V VALIDITY: >= 80% of complete arms have block CV <= 0.10. FAIL -> prefix NOISY.
- H1 SIM2REAL (GPU1 arms): within each ratio, demean miss rate and relative tok/s across policies; pooled Pearson r over the
  9 points. CONFIRMED if r <= -0.7 AND the lowest-miss policy is within 2% of the fastest at >= 2 of 3 ratios;
  MARGINAL if r <= -0.4; else REJECTED.
- H2 LINK: GPU1/GPU0 arm tok/s at ratio 0.20 for lcnu and s3fifo. CONFIRMED if min >= 1.20; MARGINAL if min >= 1.05;
  else REJECTED; INCOMPLETE if either arm missing.
- Descriptive: per GPU, OLS of per-token decode time on misses per token (ms/token intercept + ms per miss);
  tok/s vs ratio curves per policy.
- Verdict format: `VERDICT [CORRECTNESS-DIVERGE|][NOISY|]SIM2REAL:<H1>|LINK:<H2> [COMPLETE|INCOMPLETE(n missing)]`.

## Budget and failure handling
Expected ~2 min/cell GPU1, ~5 min/cell GPU0 -> ~1.5 h total; per-cell timeout 30 min. A failed cell is logged in
out/FAILED and the analysis reports INCOMPLETE; no re-runs of a failed cell inside exp724 (a follow-up gets a new number).
Resume after host interruption skips cells with existing output (no data overwritten).

## Bayesian update rule (applied after verdict, recorded in BELIEFS.json)
sim2real: CONFIRMED s=1, MARGINAL 0.5, REJECTED 0, weight 1.5 (real engine, prereg). link_placement: same mapping, w 1.5.
NOISY -> weight halved. CORRECTNESS-DIVERGE -> sim2real observation withheld pending diagnosis.

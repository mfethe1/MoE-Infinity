# exp726 PREREG — where does real-engine decode time go on the fast link? Engine floor vs native HF, same GPU

Frozen BEFORE any exp726 run. Lane 79990, STACK-1001. Namespace exp726 free at registration.

## Motivation (descriptive evidence from exp724 block 1, in flight, NOT adjudicated here)
On Winnie GPU1 (gen4 x8), lcnu/s3fifo/lru engine decode went 8.9-9.1 tok/s at miss 0.70 (ratio 0.12) to 10.4-11.1 tok/s
at miss 0.35-0.37 (ratio 0.35): halving misses gave only ~+20%. That implies a large per-token cost that is NOT
expert transfer. If so, the biggest speed lever on a good link is engine overhead, not eviction policy.
Prior smoke (exp716 smoke3, GPU0) cache-off full-GPU: 32 tokens in 2.18 s incl. prefill.

## Design (GPU1 only, CUDA_VISIBLE_DEVICES=1; starts only after exp724 and exp725 finish)
Same prompts/measurement as exp724 (engine_arm.py sha ec360baf21029ac1; prompts 6d06ff563dd9f24e; greedy, 64 new tokens,
warmup 1; decode_tok_s = 63/(t_full - t_1tok); block statistic = median over 6 prompts).
Arms: `engine lcnu @0.35` (exp724 reference point, re-measured same session), `engine lcnu @0.75` (~all 1024 experts
resident: 0.2 gave 272 experts/3.42 GB), `hf` = plain transformers 5.22.1 bf16 OlmoeForCausalLM fully on GPU
(hf_arm.py, same protocol). 3 blocks x 3 arms, shuffled Random(726+block). Afterwards, one descriptive torch.profiler
capture (prof_arm.py) of a 16-token engine @0.75 generate: top ops by self CPU and self CUDA time.

## Gates (analyze.py frozen)
- V: block CV <= 0.10 in every complete arm, else prefix NOISY.
- H (q = engine@0.75 / hf tok/s): ENGINE-OVERHEAD-DOMINANT if q <= 0.50; ENGINE-FLOOR-OK if q >= 0.80;
  else ENGINE-FLOOR-PARTIAL. INCOMPLETE if either arm missing (e.g. OOM at 0.75 or bf16 HF not fitting 16 GB).
- Descriptive: ms/token decomposition hf | engine@0.75 (overhead vs hf) | engine@0.35 (miss-driven vs @0.75).
  Outputs are not required to be identical across engine and HF (different kernels, bf16 numerics); out_sha is reported.
- Verdict: `VERDICT [NOISY|]<H> [COMPLETE|INCOMPLETE(n missing)]`.

## Consequence pre-committed
ENGINE-OVERHEAD-DOMINANT -> next = profile-driven overhead attack (the profile table names the targets: python hooks,
per-expert dispatch, synchronizations), each attempt its own preregistered experiment; policy work deprioritized.
ENGINE-FLOOR-OK -> transfer/miss is the remaining lever (placement, compression, prefetch).
No re-runs of failed cells inside exp726.

## Bayesian update (BELIEFS.json)
New direction `engine_overhead`: "On a fast link, non-transfer engine overhead is >= half of decode time".
OVERHEAD-DOMINANT s=1, PARTIAL 0.5, FLOOR-OK 0; weight 1.5; NOISY halves.

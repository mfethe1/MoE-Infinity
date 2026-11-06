# exp726 ADDENDUM66 — engine decode floor vs plain HF on the same GPU: ENGINE-OVERHEAD-DOMINANT (NOISY)

Sealed verdict, frozen analyze.py (sha256 dea31103…, == ARTIFACT == RUN_SHA256), reproduced byte-identical on Mack from
the pulled raw (exp726-final.tgz sha256 b1e500decfb7d69ef3ada15211acc97a0ec922715f09667ef0d839bfaa260d59; 23 files, SHA256SUMS 23/23 OK; ARTIFACT 10/10 OK on Winnie):

```
engine r=0.35 n=3 tok/s=  7.69 cv=0.465 blocks=[2.65, 9.85, 10.58]
engine r=0.75 n=3 tok/s= 10.39 cv=0.007 blocks=[10.35, 10.33, 10.5]
hf     r=None n=3 tok/s= 30.17 cv=0.028 blocks=[30.34, 29.05, 31.13]
floor ratio engine@0.75 / hf = 0.344
descriptive ms/token: hf 33.1 | engine@0.75 96.2 (overhead vs hf 63.1) | engine@0.35 130.0 (miss-driven vs @0.75 33.8)
VERDICT NOISY|ENGINE-OVERHEAD-DOMINANT [COMPLETE]
FLAGGED(AMENDMENT1): (none)
```

- Gate H uses engine@0.75 (CV 0.007) and hf (CV 0.028); both clean. NOISY comes only from engine@0.35 block 1
  (per-prompt 2.47/2.83/10.54/6.31/2.22/2.24 tok/s). Its pre-start record was quiet (GPU1 155 MiB, 0 Ollama models), so
  the AMENDMENT1 flag did not fire: contention started mid-cell. A foreign `~/wsp/*/gen.py` job (CUDA_VISIBLE_DEVICES=0/1)
  was observed on both GPUs at 2026-11-06T13:2xZ. Lesson: a pre-start check cannot catch mid-cell co-tenants; next
  preregs add a during-cell GPU monitor and a pre-registered per-cell exclusion rule.
- One outlier prompt in b1_engine_r75 (44.93 tok/s) comes from decode = 63/(t_full - t_1tok) when t_1tok is inflated by
  contention; block medians are unaffected (10.35).
- Pre-committed consequence (OVERHEAD-DOMINANT): profile-driven overhead attack, each attempt preregistered; policy work
  deprioritized. Plain transformers bf16 with the whole model on one 16 GB card is 2.9x faster than the offload engine
  even with ~all experts resident.
- Descriptive profile (prof_arm.py, engine@0.75, one 16-token generate): aten::copy_ = 46.4% of self CPU op time
  (3218 calls, 137 us avg, ~200/token); aten::_to_copy 2962 calls; per-op CPU cost of small elementwise ops 20-30 us.
  self_cuda = 0: CUDA activity is not captured by torch.profiler under WSL2 on this box (instrument gap, recorded).
- Cross-check (descriptive, not a gate): refit of exp724 GPU1 clean cells on decode-only misses/token gives
  ms/token = 78.2 + 0.349*miss (r = 0.981): fixed 70-85% of decode; marginal miss 0.35 ms (= 36 GB/s effective, above
  PCIe gen4 x8) so transfers are mostly hidden behind the fixed cost. exp724's original slope used a prefill-diluted miss
  fraction; the conclusion stands, the intercept rises from 71.6 to 78.2 ms.

Tier: real engine (MoE-Infinity 0337988 + local build fix), OLMoE-1B-7B-0125-Instruct bf16, Winnie RTX 5060 Ti GPU1
(gen4 x8), WSL2, torch 2.11.0+cu128, transformers 5.22.1. Not native Linux, not datacenter GPUs.
BELIEFS engine_overhead: s=1, w=1.5 halved to 0.75 (NOISY) -> posterior 0.67.
Next: exp736 overhead budget (HF vs engine op/stack diff, unit costs, Windows power-plan ABBA).

# ADDENDUM62 — exp724 settlement (real MoE-Infinity engine, Winnie RTX GPUs, OLMoE-1B-7B)

Freeze 3d8813f. 33/33 cells RC=0, frozen analyze.py run unmodified on Winnie. Raw rows, verdict, GPU monitor in `engine_results/`.

## Sealed verdict (frozen analyzer, verbatim)
`VERDICT NOISY|SIM2REAL:REJECTED|LINK:CONFIRMED [COMPLETE]`
- G0 correctness: identical greedy outputs across all 33 cells (1 distinct sha per prompt): engine policies are output-neutral.
- V validity FAILED: 8/11 arms CV<=0.10 (0.73 < 0.75).
- H1 SIM2REAL REJECTED under the frozen statistic (within-ratio pearson 0.007, best-miss agrees 1/3).
- H2 LINK CONFIRMED: GPU1 (PCIe gen4 x8) / GPU0 (gen3 x2) decode = x3.61 (lcnu) and x5.06 (s3fifo) at ratio 0.20.

## Descriptive, POST-HOC (not part of the sealed verdict; labelled as such)
Cause of V failure: a Windows-side co-tenant (Ollama llama-server, not ours, ~4-9 GB) loaded onto the same GPU during
4 GPU1 cells (all block 3): b3_g1_{lcnu_r20, lru_r35, lcnu_r35, lru_r20}. Same-GPU memory in those cells reached
15.5-15.9 GB vs <=12.9 GB for every other GPU1 cell (10 s `gpu_monitor.csv`); their tok/s fell to 2.8-8.7.
Excluding exactly those 4 cells (rule: same-GPU memory median >15 GB, chosen after seeing data):
- ratio 0.12: lcnu 9.15 (miss 0.656) > lru 8.97 (0.705) > s3fifo 8.77 (0.708)
- ratio 0.20: lcnu 10.02 (0.516) > s3fifo 9.64 (0.570) > lru 9.43 (0.595)
- ratio 0.35: lcnu 10.91 (0.352) > s3fifo 10.59 (0.373) > lru 10.49 (0.413)
The lowest-miss policy is fastest at 3/3 ratios, and the full miss order equals the full tok/s order at 3/3 ratios.
LCNU gain over LRU in real decode: +2.0% / +6.3% / +4.0%.
Linear fit over the 9 clean GPU1 arms: ms/token = 71.6 + 57.6 x miss_fraction. At miss 0 that gives a ~14 tok/s ceiling,
so on the fast link the fixed per-token cost is 65-78% of decode time at these ratios (LCNU miss 0.66-0.35). This is the motivation for exp726.

## Program consequences
1. Hit rate is a real but weak lever on GPU1. LCNU's ranking survives, but at 2-6% the policy track is near its ceiling.
2. The link dominates. GPU choice is a 3.6-5x lever; exp725 tests whether shipped round-robin placement spends it.
3. Non-transfer engine overhead (~72 ms/token) is now the largest measured cost; exp726 measures it against native HF.
4. Method fix: co-tenancy on Winnie is uncontrolled. Future preregs must include a same-GPU memory gate (cells whose
   same-GPU memory exceeds own-footprint + 1 GB are flagged before analysis).

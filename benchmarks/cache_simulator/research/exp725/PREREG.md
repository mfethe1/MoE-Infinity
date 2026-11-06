# exp725 PREREG — does shipped round-robin expert placement hurt decode on a mixed-PCIe-link multi-GPU host?

Frozen BEFORE any exp725 run. Lane 79990, STACK-1001. Namespace exp725 free at registration.

## Motivation (evidence, not results of this experiment)
- Upstream `core/model/model_topology.cpp` (main 0337988, ~L704) assigns every sparse (expert) node a home device
  round-robin: `target_device_id = (target_device_id + 1) % num_gpu`, independent of each GPU's host link bandwidth.
- Winnie GPU0 = PCIe gen3 x2, GPU1 = gen4 x8 (nvidia-smi). exp720 measured GPU0 transfer as PCIe-bound (1.56 GB/s).
- exp724 block 1 (in flight, disclosed descriptively, not adjudicated): GPU1 ~8.9-10.4 decode tok/s vs GPU0 ~2.0-2.2.
  If offload decode is link-bound, round-robin over both GPUs routes ~half of all expert misses through the slow link.

## Design
Engine/model/host/prompts/measurement identical to exp724 (engine_arm.py sha ec360baf21029ac1, prompts 6d06ff563dd9f24e):
OLMoE-1B-7B-0125-Instruct, greedy, 64 new tokens, warmup 1, decode_tok_s = 63/(t_full - t_1tok), policy lcnu.
Arms (CUDA_VISIBLE_DEVICES, device_memory_ratio, applied per visible GPU):
- `1 @0.2`, `1 @0.4`  (fast GPU alone)
- `0,1 @0.1`, `0,1 @0.2` (both GPUs, shipped round-robin placement)
Equal total expert-cache bytes pairs: (`0,1@0.1` vs `1@0.2`) and (`0,1@0.2` vs `1@0.4`).
3 blocks x 4 arms, shuffled within block by Random(725+block) (cells.json); serial; starts only after exp724 ends.

## Gates (analyze.py frozen)
- G0: identical greedy output sha per prompt across all cells, else prefix CORRECTNESS-DIVERGE.
- V: block CV <= 0.10 in >= 75% of complete arms, else prefix NOISY.
- H (q = both / GPU1-alone tok/s at equal total capacity, both pairs):
  RR-HARMS if max q <= 0.85; RR-HELPS if min q >= 1.05; RR-NEUTRAL if both q in [0.95, 1.05]; else RR-MIXED.
- Verdict: `VERDICT [CORRECTNESS-DIVERGE|][NOISY|]<H> [COMPLETE|INCOMPLETE(n missing)]`.

## Consequence pre-committed
RR-HARMS -> next experiment = link-weighted expert placement (engine change), and an upstream issue/PR proposing
bandwidth-aware placement. RR-HELPS -> extra VRAM outweighs link cost; next = measure weighted split anyway.
Failed cells are not re-run inside exp725.

## Bayesian update (BELIEFS.json)
New direction `placement`: "Link-aware expert placement beats round-robin on mixed-link hosts".
RR-HARMS s=1, RR-MIXED 0.5, RR-NEUTRAL/RR-HELPS 0; weight 1.5 (real engine, prereg); NOISY halves weight.

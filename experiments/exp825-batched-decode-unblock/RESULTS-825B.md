# EXP-825 Stage 2 results — batch amortization walls (2026-11-18)

Run: unit `exp825-walls`, started 2026-11-18T20:32:06Z, ended 21:31:16Z, 12/12 blocks.
Artifact: `exp825-batchwalls.json` sha256
`0fbdc4b56f81888a374e1bcc2d5bd2424ced4442de06429f753627dab5108234` (durable copy in
state dir). Prereg: MEASURE-825.md + FREEZE-825b.json @ commit 1d5d28c; deployed harness
sha 5d8ccebe… (verified identical). Rotary guard c7b55109… active. Quiet gate passed
(load5 2.15; recorded gpu1 41% is the run's own model-load activity after the gate).

## Raw walls (ms, per arm, in run order within arm)

| arm | round walls (ms) | median |
|---|---|---|
| b1 | 99981.2, 11330.8, 11447.6 | 11447.6 |
| b2 | 520368.6, 88282.7, 88289.7 | 88289.7 |
| b4 | 203550.1, 121972.1, 119065.6 | 121972.1 |
| b8 | 947261.9, 894245.0, 132848.9 | 894245.0 |

## Frozen analysis (medians)

| arm | tokens/s | ms/output-token | throughput vs b1 | per-token wall vs b1 |
|---|---|---|---|---|
| b1 | 11.181 | 89.4 | 1.000× | — |
| b2 | 2.900 | 344.9 | 0.259× | +285.6% |
| b4 | 4.198 | 238.2 | 0.375× | +166.4% |
| b8 | 1.145 | 873.3 | 0.102× | +876.5% |

b8 throughput is −89.8% vs b1; scaling efficiency 1.3% of linear at b8.

## Findings

1. **Amortization is negative.** End-to-end un-instrumented walls show batched greedy
   decode is 2.6×–9.8× SLOWER per token than b1 at every batch size ≥2 (medians).
   Even b8's fastest round (132848.9 ms → 7.71 tok/s) stays below b1's steady 11.18 tok/s.
   exp810's "batch-8 amortizes 7.2×" is refuted at end-to-end walls for this engine state
   (that number came from orchestration-share arithmetic, not walls).
2. **Cold/warm expert-residency dominates variance.** First occurrence of each batch
   size is 3.7–9.6× its steady rounds (b1 100 s → 11.3 s; b2 520 s → 88 s; b8 947/894 s
   → 133 s). Larger batches touch more experts per step (8 prompts × 8 experts/layer),
   so lcnu offload thrashes: the b8 rounds never stabilized within 3 rounds.
3. **Mechanism read (hypothesis, not measured here):** per-step expert traffic grows
   ~linearly with batch while GPU compute per step stays flat — orchestration (98.4% of
   decode time, exp810) multiplies rather than amortizes under expert offload.
4. **Consequence for the stack:** naive batching is the wrong lever on MoE-Infinity as
   it stands; batched serving needs expert-residency-aware grouping (batch prompts that
   share experts), not larger batches. That is the natural next experiment lane.

## Validity notes

- Within-process comparisons only (one process, interleaved seed-fixed order), per prereg.
- Fixed 128 new tokens per prompt ⇒ Σtoken denominators exact.
- Bare-ids calls (validated path); transformers emitted a pad==eos attention-mask
  warning for b>1 — cosmetic for walls (fixed-length greedy), flagged for honesty.
- 3 rounds/arm is insufficient for b8 steady-state (rounds disagree 6.7×); medians are
  reported as frozen, with per-round values above so the instability is visible.

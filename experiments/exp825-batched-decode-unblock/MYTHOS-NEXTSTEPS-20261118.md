# Local-MoE inference: what exp817/810/824/825 imply, and what to run next

2026-11-18. Reviewer: Mythos 5.2. Read: exp803, 794, 810, 817–821, 824, 825 (all files, raw JSON),
and Mack HEAD of `core/parallel/expert_dispatcher.cpp`, `core/model/model_topology.cpp`,
`moe_infinity/distributed/expert_executor.py`. `moe_store` is not in the checkout and Winnie runs a
different commit, so source statements are Mack-HEAD readings. Derived figures are arithmetic on
`exp825-batchwalls.json`; anything else is marked ESTIMATE.

## 1. Work-through

**The exp825 headline is confounded twice; the direction survives, the size and mechanism do not.**

- **Phase confound.** Run order was b8, b1, b2, b8, b4 | b4, b4, b1, b1, b2, b2, b8. The first five
  blocks are all slow (947, 100, 520, 894, 204 s; 2,665 s in total) and the last seven all fast,
  whatever the arm. b1's slow round ran _after_ a full b8 round containing the same prompt, so
  "first occurrence of each batch size is cold" does not explain it. This is a time-in-process
  effect (engine state, or co-tenant load: the quiet gate ran once, before model load). b8 drew
  two of its three rounds in the slow phase, so its median (894 s) is a slow-phase number set
  against b1's fast-phase median. "−89.8%" and "b8 never stabilized" are artifacts of that draw.
- **Fast-phase only** (wall ÷ 128 steps):

  | arm | ms per decode step | tok/s         |
  | --- | ------------------ | ------------- |
  | b1  | 88.5 / 89.4        | 11.30 / 11.18 |
  | b2  | 689.7 / 689.8      | 2.90          |
  | b4  | 930.2 / 952.9      | 4.30 / 4.20   |
  | b8  | 1,037.9 (n=1)      | 7.71          |

  Batching still loses to b1, but inside b≥2 throughput _rises_ with batch (2.90 → 4.2 → 7.71).
  The loss is one 7.8× jump in step cost between b1 and b2; from b4 to b8 four extra rows cost
  about 85–108 ms per step.

- **Path confound.** b1 and b≥2 do not run the same code. b1 takes the native loop and the
  dispatcher's `batch_size == 1` branch. b≥2 takes the HF loop (`big_modeling.py:1337-1340`) and
  the multi-token branch, which adds, per active expert per layer per step, a boolean-mask gather
  (`expert_dispatcher.cpp:1517-1520`) and `nonzero` + `index_add_` under `accum_mutex_`
  (`:1659-1666`); both force a host sync. On a full unmanaged cache, a miss does not evict: it
  queues for one transient "overload" slot and is dropped after use (`:1258-1270`, comment "only
  for prefill"), so misses serialize and re-pay PCIe every step. The predecessor design required
  an HF-loop batch-1 arm to separate this; stage 2 dropped it.

**Provenance of two priors** (correction, not re-litigation). `EXP-810.md` contains neither 98.4%
nor 7.2×. Both are in `EXP-803.md:26,31`: standalone attention math (1.976 ms) is 1.63% of the
in-vivo _attention bucket_ (121.17 ms, an instrumented number), and B8 attention _math_ amortizes
7.2× in a replay that never touched the engine. So the prior is "the attention bucket is ~98%
non-math", not "98.4% of decode time", and 7.2× was never an engine prediction. exp803/809/810
also ran on an RTX 6000 Ada (`EXP-810.md:5`), not the 4080 rig.

**Coherent mechanism.** The unit of cost is the _(layer, active expert) dispatch event_ and the
cache miss, not the token and not the FLOP. Each event is a queue hop to a fetch thread, a
possible transfer, a forward on its own stream, a mutexed accumulate and a completion event, and
each layer ends in a full-drain barrier. GPU math is a rounding error, so batching amortizes only
the per-layer fixed part while raising events per layer (up to 64 experts instead of 8) and the
working set. Nondeterminism is the same design seen from the output side: expert outputs are
added in completion order across concurrent streams, rounding differs, near-tie argmaxes flip,
and 128 free-running greedy steps amplify that to ~0.5 agreement. It also means two "identical"
arms route differently after the first flip, so wall noise has a routing component.

**The thesis.** Still open, and better located. b1 runs ~79–89 ms/tok un-instrumented while
capacity above 0.50 buys nothing measurable (exp821: 0.65 vs 0.50 within 1.5–2.7%). That points
at per-layer host control flow, not PCIe streaming, as the binding cost at b1; this is untested
causally (experiment 2).

## 2. Ranked experiments

Shared protocol: one fresh process per battery; burn-in to stationarity (§4); arms interleaved as
adjacent pairs with alternating order; statistic Σwall/Σtokens; no instrumentation; fixed 128 new
tokens. Block prices from exp825 fast phase: b1 11 s, b2 88 s, b4 122 s, b8 133 s. All costs and
effect sizes are ESTIMATE.

| #   | Experiment                                                                    | Hypothesis (falsifiable)                                                                                                                                | Arms and measurement                                                                                                                                                                                                 | Expected                                                            | Kill                                                                                  | Cost              | Updates                                                               |
| --- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------------- | --------------------------------------------------------------------- |
| 1   | **Path × batch decomposition** (orchestration)                                | Most of the b1→b2 jump is the code path, not the wider expert set                                                                                       | N1 (native b1); D2, D8 = _one prompt duplicated_ 2×/8× (multi-token path, b1's expert set); H2, H8 (distinct prompts). 6 rounds × 5 arms, 3 batteries. D2−N1 = path; H8−D8 = expert-set growth; D8−D2 = per-row cost | D2 ≥ 3× N1 per step; H8−D8 under 30% of H8                          | D2 ≤ 1.5× N1 in 3/3: path is innocent, skip #6, go to #3/#8                           | 3 × ~90 min       | "batching anti-amortizes" → which half is repairable                  |
| 2   | **All-hit floor at b1** (orchestration vs streaming)                          | At ratio 0.50 streaming is under 10% of b1 wall; the rest is host control flow                                                                          | SAME (one prompt repeated 8×, working set resident after pass 1) vs ROT (8 prompts), native b1, 6 pairs × 4 batteries; hit counters reported per block                                                               | SAME within 10% of ROT                                              | SAME ≥ 30% faster: streaming is binding, capacity/quantization lane reopens, #7 drops | 4 × ~40 min       | RAM-first as a _speed_ thesis; scopes exp794's 43.7 pts to low ratios |
| 3   | **Offline routing-trace study** (simulation)                                  | Prompts share enough experts that grouping cuts distinct experts per layer at b8 by ≥ 25% vs random grouping                                            | One trace run dumping router masks for ≥ 64 prompts; CPU analysis: per-prompt expert-set overlap, distinct experts per layer by batch composition, miss counts by capacity                                           | Small gain: exp796 found routing memoryless                         | Best grouping within 10% of random: residency-aware grouping DEAD at zero wall cost   | ~20 min GPU + CPU | The exp825 "natural next lane"                                        |
| 4   | **Slow-phase characterization**                                               | The 2,665 s slow phase is engine state set by a b≥2-first start, not host load                                                                          | b1 blocks for 60 min from start in (a) b1-first and (b) b8-first processes; loadavg at every block boundary                                                                                                          | Slow phase in (b) only                                              | Slow blocks track loadavg in both: it is contention, fix the gate instead             | 2 × ~75 min       | "cold rounds 3.7–9.6× steady"; sets the burn-in rule                  |
| 5   | **A/A estimator, new frozen attempt**                                         | With G1 removed, burn-in and a transfer-bytes covariate, identical arms give a CI including 0 in ≥ 5/6 batteries                                        | A1/A2 × 6 pairs × 6 batteries; step 0 (no GPU, uncredited) is a descriptive pass over exp824's sealed walls to size the noise                                                                                        | Yields the program's minimum detectable effect                      | CI excludes 0 in ≥ 2/6: no wall claim is admissible until fixed                       | ~3 h              | exp824 INCOMPLETE → validated or not                                  |
| 6   | **Repair the multi-token branch** (orchestration; needs #1 = path)            | Admitting misses through normal eviction and building per-layer index lists once cuts D2 step cost to ≤ 2× N1                                           | Patched vs unpatched D2/H8 as process pairs; equivalence by teacher-forced logit margin                                                                                                                              | 690 → under 180 ms/step at b2                                       | Under 20% gain in 3/4                                                                 | dev + 2 × ~2 h    | Whether batched serving is viable at all                              |
| 7   | **Resident-hit synchronous fast path** (orchestration; needs #2 = host-bound) | When every routed expert is resident, running the layer's experts as one call on the caller's stream, with no queues or barrier, saves ≥ 20% of b1 wall | Flag on/off process pairs, 6 pairs × 4                                                                                                                                                                               | 15–30% (exp794's ~33% host-drain share, discounted as instrumented) | Under 5% in 3/4                                                                       | dev + 4 × ~40 min | Turns "orchestration dominates" from attribution into a causal number |
| 8   | **Grouped vs random batches** (needs #3 alive and #6)                         | Grouping by trace overlap cuts step wall in proportion to the distinct-expert reduction                                                                 | H8-random vs H8-grouped, 6 pairs × 4                                                                                                                                                                                 | As #3 predicts                                                      | CI includes 0 in 3/4                                                                  | 4 × ~60 min       | Residency-aware grouping                                              |

Why #3 escapes exp724's failure: it predicts _counts_ (distinct experts, misses), which are a
function of tokens and weights, not timing; it is admitted only after its miss counts match the
dispatcher's own hit/access counters on three configs; and it can only kill a lane, never credit
a speedup. exp724 predicted walls.

## 3. Strategic critique

RAM-first is right as a _capacity_ thesis (it is how a model larger than VRAM runs at all) and
unproven as a _speed_ thesis. Within b1 the measured lever is not residency above 0.50; in
batches the cost is events and misses. Restate the goal as **minimize dispatch events and misses
per token**: streaming becomes the exception path, and an all-resident synchronous path the
common one. For this model, also price full residency with quantized experts before investing in
streaming (7B parameters at bf16 is ~14 GB, ESTIMATE; `uniform_fp8` exists in config).

Program changes:

- **Order lanes by dependency.** Mechanism decompositions (#1, #2, #4) come first, engine changes
  are admitted only behind a mechanism result, offline count studies pre-screen lanes, and an A/A
  runs whenever the harness changes.
- **Preregister discriminating predictions**, two hypotheses with different expected numbers,
  instead of threshold gates. exp819→821 spent three batteries on an effect below ±8% drift.
- **State the minimum detectable effect in every prereg**, and do not run an experiment whose
  expected effect is below it.
- **A confound arm named in design review cannot be dropped at freeze without a written reason.**
  The missing H1 arm cost exp825 its interpretation.
- **Keep a prior ledger**: each standing prior cites file:line, instrument, hardware and scope.
  The 98.4% drift shows why.
- **Count decisions changed, not experiments run**, toward the 1,000.

## 4. Measurement standard

- **Claim unit:** paired difference of Σwall/Σtokens between time-adjacent blocks, order
  alternated, ≥ 6 pairs per battery and ≥ 4 fresh-process batteries; bootstrap CI over pairs; a
  claim needs the same sign with CI excluding 0 in ≥ 3/4. Min-of-3 is reported as reference only.
- **Burn-in to stationarity, not a fixed warmup:** run every arm shape, then require two
  consecutive same-arm blocks within 10%. exp825's 8-token warmup preceded 44 minutes of slow blocks.
- **Publish every block in run order,** and never take a median across a phase change. Freeze a
  first-half vs second-half drift check.
- **Gate quiet at every block boundary** (loadavg read outside the timed region), record it, and
  flag breaches by a frozen rule rather than dropping blocks afterwards.
- **Carry an A/A pair in every battery** to keep a running noise ledger.
- **Absorb routing nondeterminism:** read the always-on counters after each block (cache
  access/hit, `expert_h2d_bytes_total_`; Python exposure to be confirmed) and report wall per
  token alongside bytes transferred per token as a covariate. Where the path allows, replay
  forced tokens so both arms execute the same route.
- **Output equivalence of an engine change:** single teacher-forced forward, logit differences
  against a margin calibrated on same-process repeat noise. Never free-running token agreement.
- **Assert the path per block** (native vs HF loop, grouped-kernel counter) outside the timed region.
- **Flags that need a restart** are compared as interleaved process pairs, each with its own
  burn-in. Cross-battery numbers are never compared.
- **Instrumented runs may produce counts** (ops, hits, routes), never walls.

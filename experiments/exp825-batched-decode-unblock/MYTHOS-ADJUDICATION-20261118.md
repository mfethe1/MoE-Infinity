# Adjudication of MYTHOS-NEXTSTEPS-20261118 — does the approach survive?

2026-11-18. Second reviewer: Mythos 5.2. Read: NEXTSTEPS, CORRECTION, RESULTS-825B, MEASURE-825,
`exp825-batchwalls.json`, `batch-wall-825.py`, exp824 results, both exp826 JSONs, the trace harness
(`~/.hermes/cache/scratch/exp825/s0_routing.py`), exp826 `STAGE0-20261119.md` + `analyze_routing.py`
(commit 5f9c9a5), EXP-791/794/817/819/821, `core/parallel/expert_dispatcher.cpp` (Mack HEAD).
"Recomputed" = my arithmetic on `exp826-routing-steps.json` with layer = i mod 16, step = i div 16.

**Short answer.** Reviewer #1's mechanism and standard hold, but the plan is ordered around the
batch lane while the thesis lives at b1, and its b1 test (#2) cannot work as designed. Do not pivot
yet: one ~15-minute reference measurement (§2) decides it. Three things change the evidence first.

## 0. Three corrections to the evidence state

1. **The "union Jaccard 1.0" fact is a harness artifact. Do not reason from it.**
   `s0_routing.py:80` passes `len(gates)` as the layer index, so all 16 layers are stored under one
   key `"16"`; the "per-layer" union is a union over all layers and saturates trivially.
   Recomputed per layer, 12 full-length prompts, 63 decode steps: a prompt touches **54.9 of 64**
   experts per layer on average (per-prompt means 49.0–57.2; lowest single layer 40); pairwise
   per-layer union Jaccard is **mean 0.833, min 0.574**. Uniform routing would give 63.99. So
   `STAGE0-20261119.md:23-24` (finding 5) is false, and finding 4 (`:20-22`, "near-uniform, no hot
   set") is wrong too: per layer the top-8 experts take 19–32% of slots (uniform 12.5%), the top-16
   take 36–51% (uniform 25%). Routing has temporal locality: adjacent steps share 2.92 of 8 experts
   (null 1.00); a b1 8-step window uses 30.4 experts per layer (null 42.0), a 16-step window 40.0
   (null 56.4).
2. **The harness also captured prefill wrongly.** `s0_routing.py:77` keeps `idx[0]`, the first
   position only. Step 0 is therefore the BOS token: identical across 13/16 prompts in 15.8/16
   layers. Prompt-token routing was never recorded, and STAGE0's "shared-prefix effect 0.995"
   (`:30`) is this artifact, not a finding.
3. **exp825 has a third confound: EOS padding.** `batch-wall-825.py:78` counts
   (sequence length − prompt length) × b as output tokens. In the trace, prompt 2 of the set
   ("Write a haiku…") stops at step 22 of 64 (prompts 9, 12, 15 at 18, 4, 46). In the b2 arm
   about 106 of 256 counted tokens are padding (ESTIMATE, from a different run): useful
   throughput ≈ 150 / 88.3 s = **1.70 tok/s, not 2.90** (ESTIMATE). `MEASURE-825.md:12` ("Σtokens
   = 128 per prompt") is false for b ≥ 2. Per-step milliseconds stand; the tok/s column for
   b ≥ 2 is an upper bound, and padded rows route a constant EOS token, so b ≥ 2 arms carried
   fewer distinct experts than a real batch.

What survives from exp826: random b8 activates **37.2** distinct experts per layer per step
(STAGE0 says ~38), i.e. 4.65× b1's dispatch events; b2 14.4, b4 24.3. Grouping is dead on better
evidence than STAGE0's: a 6+6 split chosen on steps 1–31 cuts distinct experts on steps 32–63 by
**0.5%** against random; the in-sample oracle over all 462 splits reaches 2.7%.

Source check of reviewer #1: the single transient overload slot with a 1 µs spin-wait
(`expert_dispatcher.cpp:1256-1270`), the mask gather (`:1517-1520`) and `nonzero` + `index_add_`
(`:1659-1666`) are as described. The overload comment says "only for prefill": **every b1
generation's prefill runs this branch too**, so it is not a batch-only path.

## 1. Verdict per lane

| #   | Experiment                                                                                                                     | Verdict                                           | Reason                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Path × batch                                                                                                                   | **MODIFY**, rank 3                                | Right experiment, wrong priority and oversized. The effect is 7.8×, so one battery of N1, D2, D8, H8 settles it (path: D2 ≥ ~500 ms/step; events: D2 ≤ ~135 ms). Add `min_new_tokens=128`, count non-pad tokens, assert D rows stay identical per block. Replicate only if D2 lands in 1.5–3× N1.                                                                                                                          |
| 2   | All-hit floor (SAME vs ROT)                                                                                                    | **REJECT design, keep question, rank 1**          | SAME is not all-hit: a prompt's footprint is ~880 of 1,024 experts in 63 steps (54.9 × 16) against a ~660-expert cache at 0.50 (ESTIMATE from cudaMalloc 6,733 → 11,473 MiB over 0.35 → 0.65, `EXP-819.md:32`, at 12 MiB per expert). Repeats also re-route after the first flip (exp824: 0.33–0.62 agreement). "SAME ≈ ROT" would be read as "streaming < 10%" and falsely kill the streaming lane. Replace with M1 + M2. |
| 3   | Offline routing study                                                                                                          | **MODIFY: closed for grouping, alive for sizing** | Step-local overlap was plausible enough to screen and has now been screened: cross-prompt same-step overlap is 1.51 of 8 (null 1.00). It did not meet its own admission terms (16 prompts not ≥ 64, no counter match, two harness bugs); the kill stands only because the oracle bound (2.7%) is far under the 10% line. Its live use is the b1 working-set curve for capacity sizing, under §3.                           |
| 4   | Slow-phase                                                                                                                     | **MODIFY**                                        | Add a third hypothesis: host page-in of the offload store (the RAM thesis's own cost). Log major faults and loadavg at every block boundary in every battery's burn-in, which is free, and run one b1-first battery instead of 2 × 75 min.                                                                                                                                                                                 |
| 5   | A/A estimator                                                                                                                  | **AGREE, promote to rank 2**                      | It gates every claim under ~2× (M2, #7). #1 does not need it.                                                                                                                                                                                                                                                                                                                                                              |
| 6   | Repair multi-token branch                                                                                                      | **MODIFY**                                        | Gate on #1 and first count overload-slot entries per step (zero dev). Measure prefill wall separately: the repair may pay at b1 time-to-first-token even if batching is never served.                                                                                                                                                                                                                                      |
| 7   | Synchronous resident fast path                                                                                                 | **AGREE**, gated on M1/M2 instead of #2           | Only causal test of "host dispatch binds".                                                                                                                                                                                                                                                                                                                                                                                 |
| 8   | Grouped vs random batches                                                                                                      | **REJECT (DEAD)**                                 | Held-out gain 0.5%; no wall spend.                                                                                                                                                                                                                                                                                                                                                                                         |
| M0  | **Missing: exp826 re-analysis and harness fix** (no GPU)                                                                       | rank 0                                            | Retract STAGE0 findings 4, 5 and the prefix claim; fix `:77`, `:80`.                                                                                                                                                                                                                                                                                                                                                       |
| M1  | **Missing: all-resident reference**                                                                                            | rank 1                                            | §2.                                                                                                                                                                                                                                                                                                                                                                                                                        |
| M2  | **Missing: dispatcher counters at b1** (misses, accesses, H2D bytes per token at 0.50 and 0.65, read outside the timed region) | rank 1                                            | Resolves the tension in §2 at zero wall cost; also the admission test for any simulator.                                                                                                                                                                                                                                                                                                                                   |

So: #1 is a sound first move for the _batch_ lane but not the program's first move, and #2 as
written is not a valid second.

## 2. Pivot question

**Recommendation: (c) stay the course is not justified as a speed thesis on this model, but do
not pivot before M1.** My expectation (ESTIMATE, low confidence) is a split outcome: (b) becomes
the engine's common path, (a) becomes the deployment answer for any model that fits when
quantized, and streaming is kept as the exception path for models larger than VRAM.

Two facts drive this. First, the test model is the wrong size for a capacity thesis: ~6.9B
parameters is ~13.8 GB at bf16 on a 16 GB card, and experts are ~93% of it (ESTIMATE), so 8-bit
experts give ~7.4 GB fully resident. RAM-first is being scored where its competitor is nearly
free. Second, in-engine full residency has never been measured cleanly and probably cannot be at
bf16: the engine's cudaMalloc grows ~15.8 GiB per unit ratio on top of ~4.9 GiB torch-reserved
(`EXP-819.md:32`), so ratio ≥ ~0.75 overcommits the card (ESTIMATE). That is the likeliest reading
of exp791's regress at 0.75/0.90 (9.83 and 9.38 against 11.08 tok/s, `EXP-791.md:17-21`), not
"LCNU churn".

There is also an unresolved tension. An unadmitted LRU count on the trace gives 14–26 misses per
b1 step at 640–512 cached experts, out of 128 accesses (ESTIMATE); at 12 MiB each that is hundreds
of MB per step over PCIe. Yet exp821 saw 0.50 → 0.65 move the wall by only 1.2–2.2 ms/tok
(`EXP-821.md:32`). Either misses are far cheaper than that arithmetic or the real cache does not
miss like the simulation. M2 answers which, and reviewer #1's "streaming under 10%" expectation is
not yet supported either way.

**Single cheapest discriminating measurement (M1):** the same model, same prompts,
`min_new_tokens=128`, fully on the GPU with no streaming engine (plain HF bf16 if it fits, else
8-bit experts), at b1 and b8, interleaved with engine b1 at 0.50. About 15 minutes (ESTIMATE). I
found no such reference in exp791–826.

- Reference b1 ≥ 1.5× engine b1: residency or dispatch is taxing b1. Pivot to (a) for fit-able
  models, do #7 in-engine, and move the RAM-first benchmark to a model ≥ 2× VRAM.
- Reference b1 within 20% of engine b1: the engine is already at the residency floor. Stay (c);
  neither (a) nor (b) buys much at b1, and #6 is the only lever.
- Either way reference b8 is the ceiling #6 is repairing toward.

## 3. Simulation trust rules (admission criteria)

1. **Counts only**: distinct experts, events, misses, bytes. Never ms, tok/s or wall ratios.
2. **Trace integrity, asserted in code before analysis**: explicit true layer id and position id
   per row; number of distinct layer keys = number of layers; rows per forward = tokens in that
   forward; row count = layers × steps × rows; EOS policy stated and lengths equalized; trace and
   harness sha sealed. exp826 fails the first three.
3. **Null beside every statistic**: uniform routing and a popularity-preserving shuffle. A
   statistic equal to its null is not a finding (the union "fact" matched the 63.99 null).
4. **Counter match for anything policy-dependent**: simulated misses and accesses within ±10% of
   the dispatcher's own counters on ≥ 3 configs spanning the decision (ratio 0.35/0.50/0.65 at b1
   plus one b8), using traces from the same blocks the counters were read on, because another run
   is another route. Until then only policy-free counts (distinct experts, events) are usable.
5. **Held-out selection**: fit groupings, hot sets or predictors on one half of steps or prompts,
   score on the other, and publish the in-sample oracle as the upper bound.
6. **Sample**: ≥ 64 prompts, ≥ 128 steps, ≥ 2 independent trace runs with between-run spread.
7. **Authority**: a simulator may kill a lane (oracle bound under the kill line) or size an
   experiment. It may not credit a speedup or reorder lanes on a heuristic's result.
8. **Revalidate** on any change of engine commit, cache policy or capacity accounting; record
   which commit (Winnie differs from Mack) produced the trace.
9. **Ledger**: log predicted-count vs measured-counter correlation per simulator, replacing
   exp724's 0.007 as the standing record.

## 4. Rerun list

| Result                                   | Status                                                                                           | Action                                                                                                                             |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| exp825 stage 2                           | Headline void; fast-phase ms/step stand as descriptive (n ≤ 2); tok/s for b ≥ 2 are upper bounds | Rerun as modified #1: burn-in, forced length, non-pad denominator, D arms, blocks published in run order. One battery.             |
| exp826 stage 0                           | Findings 1–3 stand; 4, 5 and the prefix claim retracted                                          | No GPU. Re-analyse; fix harness. New trace (≥ 64 prompts, 128 steps) only when M2 needs it.                                        |
| exp791 ratios 0.75/0.90                  | Not reliable: one probe, GPU0 contention, probable overcommit                                    | **The one old result worth GPU time**: rerun inside M2 with the cudaMalloc hook and counters, stopping where the card overcommits. |
| exp819/821                               | Stands only as "0.35 is too small"; ratio tuning stays closed                                    | No rerun as tuning; superseded by M2.                                                                                              |
| exp794 (43.7 pts fetch-wait, ~33% drain) | Instrumented shares at ratios 0.25/0.5: demote to hypotheses                                     | No rerun; M1, M2, #7 replace it.                                                                                                   |
| exp803 (98.4%, 7.2×)                     | Retire as engine priors                                                                          | No rerun.                                                                                                                          |
| exp817                                   | Stands, within-battery, unreplicated; 4.4 ms/tok is under the ±8% cross-battery drift            | No rerun (814/815 dead regardless).                                                                                                |
| exp818 prefetch                          | DEAD stands, and the trace agrees: the previous step predicts 2.92 of the next 8 experts         | No rerun.                                                                                                                          |
| exp820 eviction                          | Relabel "unresolved below noise", not "second-order"                                             | No rerun until #5 gives a detectable-effect size.                                                                                  |
| exp824                                   | INCOMPLETE stands                                                                                | New frozen attempt = #5.                                                                                                           |

Total new GPU spend before any engine change: M1 (~15 min), M2 with the exp791 rerun (~1 h),
#5 (~3 h), #1 (~90 min). All ESTIMATE.

## 5. Program structure

I agree with all six of reviewer #1's changes (the brief says five; the report lists six). Changes:

- **Modify the minimum-detectable-effect rule**: scale replication to effect size. The 4-battery
  3-of-4 standard is for claims under ~2×; a 7.8× effect needs one clean battery.
- **Add: a reference-baseline rule.** Every speed thesis carries an all-resident, no-engine
  reference on the same hardware. Its absence is why the pivot question is still open after
  > 1,000 experiments.
- **Add: an artifact audit before a result becomes a prior.** Schema assertions plus a null model.
  The Jaccard-1.0 claim reached a commit message (5f9c9a5) and this brief within minutes of the
  run, and reviewer #1's kill line was then applied to an analysis that had not met its
  admission terms.
- **Add: a useful-token denominator rule** (non-pad tokens, forced equal lengths in batch arms).
- **Add to the prior ledger: hardware.** `EXP-791.md:4` says RTX 5060 Ti; NEXTSTEPS `:47` says "the
  4080 rig"; exp803/810 ran on an RTX 6000 Ada. I could not resolve which card the 16 GB results
  belong to.
- **Add: a test-model rule.** A capacity thesis is scored on a model that does not fit VRAM when
  quantized; a model that fits is scored against full residency.
- **Cut nothing.** "Count decisions, not experiments" matters most: by that count exp819–821
  changed one decision in three batteries, and exp826 changed one (grouping) for 90 seconds of GPU.

Limits of this review: the trace is one run of 16 prompts (12 full-length) on a nondeterministic
engine at Winnie's commit; my LRU miss counts are unadmitted under §3 rule 4; I did not verify
that `uniform_fp8` exists in config (reviewer #1's claim) or that plain HF bf16 fits the card.

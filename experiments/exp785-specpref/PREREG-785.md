# PREREG-785 — speculative expert prefetch vs decode wall
**Registered BEFORE the sealed A/B run.** (Post-prereg edits: none allowed; verdict map frozen.)

## Question
Does `archer_config.speculative_prefetch=True` (layer-L+1 expert prefetch fired from
layer-L router logits) change batch-1 decode throughput of OLMoE-1B-7B on MoE-Infinity
(src753 build b7f6ca4), versus default off, in two residency regimes?

## Why this lever
Confirmed wall (exp781/783/784): decode is dominated by per-expert-access dispatch
latency, not bytes. Speculative prefetch is the one shipped engine feature that
*directly attacks access latency* (fires next layer's expert fetches during current
layer compute) and has never been A/B'd on this stack. Grouped decode
(`MOE_GROUPED_DECODE`) is hardware-gated to RTX PRO 6000 and cannot be forced on
sm_120 (survey 2026-11-11); `gpu_only_expert_routing` (sync-free dispatch) is already
default-on in our baselines — so config-level dispatch surface = {speculative_prefetch,
num_threads}.

## Qualification probes (disclosed, NOT sealed; engine sha 08c1883997699d48)
- Baseline bf16 @0.75 threads=4: ~10.6 tok/s (exp783/784 sealed); @0.25: 10.07 tok/s.
- Probe spec=ON @0.75: **4.01 tok/s** (−62% vs 10.6) — spec_prefetch_effective=True read back.
- Probe spec=ON @0.25: **4.49 tok/s** (−55% vs 10.07), miss rate 47.7% unchanged-ish.
- Probe threads=16 @0.75: **4.67 tok/s** (−56%) — oversubscription; recorded, not A/B'd.
- Mechanism hypothesis (from config.py help text): speculative prefetch path falls back
  to eager Python routing (conflicts with native sync-free `gpu_only_expert_routing`),
  dragging per-layer dispatch through Python.

## Design
8 cells, bf16 store both arms, threads=4, gpu-route on, lcnu, 24 prompts × 32 tok,
greedy, warmup 1, GPU1: C75a/S75a/C25a/S25a/C75b/S75b/C25b/S25b (2 interleaved reps).
Primary deltas: d75 = mean(S75)−mean(C75) relative; d25 likewise.

## Verdict map (frozen)
rc=1 MAJOR-POS (any regime ≥ +0.50) / rc=2 MILD-POS (≥ +0.10) / rc=3 NO-MOVE (both
|Δ|<0.10) / **rc=4 REGRESSION (any regime ≤ −0.10)** / rc=9 DATA-FAIL (missing cell,
nonzero engine RC, or nondeterminism within any config).

## Predictions (frozen)
- d75 ≤ −0.40 and d25 ≤ −0.40 (both regimes regress massively; probes: −0.62/−0.55).
- Output determinism: greedy decode identical out_sha within config across reps.
- Miss counts: similar order of magnitude S vs C per regime (prefetch changes timing,
  not routing probabilities).

## Acceptance
Sealed evidence for "the shipped config-level dispatch levers regress on consumer
sm_120 hardware; the wall requires native/kernel-level batching work (grouped decode
is pro6000-gated)". Either direction (regression confirmed or surprisingly not)
updates BELIEFS. Receipt #101 target.

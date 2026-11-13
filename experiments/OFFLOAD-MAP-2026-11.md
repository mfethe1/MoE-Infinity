# Where Local MoE Decode Time Actually Goes — a measured map of expert-offload bottlenecks

A practitioner-oriented summary of a sealed experiment series (Nov 2026) on sparse-MoE LLM decode under expert offload. Every number below comes from a preregistered, sealed experiment with a published receipt; none from memory. Failed gates are kept alongside the wins.

## 1. Setup (envelope)

- Engine: MoE-Infinity (EfficientMoE), model OLMoE-1B-7B-0125-Instruct, bf16, greedy, topk 8
- Host: WSL2, 12 logical CPUs, 2× RTX 5060 Ti 16 GB (bench GPU = GPU1 via `CUDA_VISIBLE_DEVICES`; the other GPU hosts unrelated workloads)
- Workload: 8 prompts × 32 decode tokens, fresh process per arm, warmup arm before every measured arm
- Discipline: gates frozen before each run; per-arm load gates (pre + post); arms run only in verified-quiet windows; extraction only via frozen scripts on frozen artifacts

## 2. What we shipped upstream

1. **Async device-buffer chain (PR #358, MERGED).** Measured chain exp771–775 (receipts #86–#90).
2. **Inline work-stealing drain in the dispatch wait (PR #359, open, CI green at head `97e66c9`).** +68/−7 across two files; `MOE_INLINE_WAIT=0` kill-switch. Framed as a jitter fix — deliberately NOT a throughput claim.

## 3. The map: decode wall time under expert offload

Sealed decomposition (exp790/793/794, receipts #106/#109/#110):

- MoE block self: ~58–68% of decode wall
- Dispatch stall: ~40–50%
- Of the stall boundary: fetch-wait ≈ 43.7 points; CPU handoff ≈ 33 points; enqueue ruled out
- Earlier envelope (exp777, receipt #93): with async load-on-use, budget/eviction sweeps bought <0.1% — misses overlap when the async path is healthy

## 4. Residency: one sharp peak, then a cliff

- exp791 (receipt #107): expert-residency ratio 0.50 → **+31.08%** (3× confirm, perfect separation)
- exp792 (receipt #108): fine sweep — 0.50 is a sharp peak; above it, churn cliff (~8 GB expert-budget boundary) costs ~10%
- Practical guidance: budget experts to the 0.50 residency point on this class of model/hardware; more residency is not monotone improvement once forced churn begins. (See §5 — cliff size is condition-sensitive and shrinks under work-stealing.)

## 5. Does work-stealing move the cliff? (exp801, receipt #117)

2×2 (ratio {0.50, 0.60} × wait {passive, steal}), same binaries, env-toggle arms, n=4/cell, preregistered gates, load-gated arms, sealed analyzer (commit `fe9b374`).

- **The variance collapse is ratio-specific.** At 0.60, passive wait is the noisy mode (CV 4.51%) and steal is 2.4× calmer (1.90%) — but it missed the preregistered 0.4 collapse bar (ratio 0.422). At 0.50 the direction even reversed on this night (P50 1.80% vs S50 4.80%, n=4). Don't advertise the exp799 3.9× collapse as ratio-independent.
- **The cliff itself shrinks under steal** — the interesting interaction (Δ4.48 pp, preregistered gate met): passive pays +2.78% at 0.60, steal pays −1.7% (slightly faster). With queues drained by stealing, extra residency is ~free; the ~10% cliff of exp792 also failed to fully replicate under passive on this night (2.78%), so treat cliff size as condition-sensitive, not a constant.
- Steal still costs mean wall time at 0.50 (−3.85%, gate G2 fail) — consistent with §6's jitter-not-throughput framing.
- Practical guidance update: the 0.50 sweet spot is a *passive-wait* sweet spot. If you ship work-stealing, the residency budget can likely go higher without paying the churn cliff.

## 6. Variance, not just mean (the PR #359 story)

- exp799 (receipt #115): CV 0.68% vs 2.65% — 3.9× collapse (n=5); the passive-wait arm was bimodal (0.86 s mode gap); steal collapses it to the fast mode
- exp798 (receipt #114): mechanism supported — −7.8% wall in the paired gate; variance collapse secondary confirmation
- exp795/797: first two attempts VOID/NO-MOVE (divergence floor; load contamination) — retained as method lessons, not findings

## 7. A methodological warning for anyone verifying MoE inference

exp796 (receipt #112): 85/256 decode tokens diverge bit-exactly across identical reruns — intrinsic nondeterminism; the engine's determinism flag does not fix it. Bit-exact token comparison is UNUSABLE as a correctness gate for this stack. Use logits/margins or divergence floors.

## 8. Limitations (kept honest)

- Small decode budget (8×32 tokens), single model, single host class, WSL2
- n=4–5 per cell; every mean claim gated at ≥3%; findings are directional for practitioners, not universal laws
- All seals, commit hashes, and raw artifacts are published (see §9)

## 9. Receipts

Per-experiment records live in `experiments/exp7*/` and `experiments/exp80*/` in this repo (EXP files, analyzer JSON, raw probe logs, seal shas), with summary receipts posted in the PR #353 comment thread on EfficientMoE/MoE-Infinity: #86–#90 (async chain), #93 (eviction sweeps), #106–#110 (decomposition + residency), #112 (nondeterminism), #114–#115 (steal mechanism + variance), #117 (steal × residency interaction). Upstream PRs: #358 (merged), #359 (open).

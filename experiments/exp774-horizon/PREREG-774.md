# PREREG-774 — 4×-horizon replicate of the async double-buffer fix + residual attribution

**Hypothesis (Q1).** exp773's async double-buffered indices reclaimed
R = 0.6989 of the SPEC−LGC wall gap (frozen 0.7 RECOVER gate missed by
0.001) while collapsing the `speculative_prefetch` leaf to 0.07×. At a 4×
horizon (24 prompts × 64 tok vs 6) per-arm wall noise averages down, so if
the true recovery is at or above 0.7 the replicate should clear the gate;
if the true recovery is materially below 0.7 the verdict will say so. This
also tests horizon-scaling: the queue-drain serialization should be
per-step, hence proportionally invariant.

**Hypothesis (Q2).** The residual (W_DB − W_LGC at exp773 = 2.55 s, of
which 0.34 s remained in the prefetch leaf) is carried by one of:
staleness-driven eager dispatch (CPU leaf `_dispatch_eager_local`),
prefetch bookkeeping (`prefetch_experts_list` / `plan_candidates`), or the
added per-call GPU topk-64. If no single leaf carries ≥ max(1.5 s, 30% of
the net positive DB−LGC delta), the residual is diffuse/noise-consistent.

**Intervention.** None beyond exp773's — `src774` = cp -a src753 +
patch773.py verbatim (marker `exp773 async-dbuf`, the replicated
intervention), gated by `EXP773_DB=1`. This experiment changes only the
horizon: `prompts774.json` = the 6 exp769-lineage prompts + 18 new
instruction prompts of the same style (file pinned by sha in FREEZE).

**Cells.** `PY_LGC` (src753, off/off/off), `PY_SPEC` (src753, on/off/off),
`PY_DB` (src774, on/off/off, EXP773_DB=1). Envelope otherwise verbatim
from exp769–773 (OLMoE-1B-7B, lcnu r=0.75, threads 4, gpu-route off,
CUDA_VISIBLE_DEVICES=1, py-spy spawn 50 Hz raw, engine byte-identical
1f119bd017985083, sampler 9c39353053718c1c, warmup 1, per-cell timeout
3600 s).

**Frozen decision rule** (analyze774.py; battery 11/11 pre-staging).
τ_w = 5.0 s (≈0.15 of the expected 4×-scaled D≈34 s; noise does not scale
4×). D = W(SPEC)−W(LGC); R = 1−(W(DB)−W(LGC))/D; rows gate 24.
- rc=9 IDENTIFY-FAIL: SRC_HEAD ≠ b7f6ca4 or ENV lacks moei-774 line
- rc=4 DATA-FAIL: missing/short (rows<24, samples<2000, BADIO non-empty)
- |D| ≤ τ_w → rc=5 NO-BASELINE-SIGNAL
- W(DB)−W(SPEC) > τ_w → rc=8 REGRESS
- rc=1 RECOVER: R ≥ 0.7 AND specleaf(DB) ≤ 0.5·specleaf(SPEC)
- rc=2 PARTIAL: 0.3 ≤ R < 0.7 (or R ≥ 0.7 with leaf gate failing)
- rc=7 NO-GAIN: R < 0.3
Attribution section (appended in every data-complete verdict, informational
for rc but frozen): RESIDUAL-CARRIER iff top DB−LGC positive leaf delta ≥
max(75 samples, 0.3 × net positive); else RESIDUAL-DIFFUSE.

**Void conditions.** Any post-freeze change to analyzer/engine/sampler/
src774 patch/prompts774.json; py-spy version ≠ PYSPY.txt; interference gate
tripped (busy roster exp746…exp767 + exp771 + exp772 + exp773 + exp774).

**Success criterion.** rc=1 → exp773's fix confirmed at 4× horizon:
upstream-able patch; successor = upstream PR + hit-rate retention study.
rc=2/7 with RESIDUAL-CARRIER → successor targets that carrier (ring depth 2
for staleness-driven dispatch; GPU-side trim for topk cost). rc=7 with
RESIDUAL-DIFFUSE and |W_DB−W_LGC| within noise → exp773's R was
noise-limited; the honest reading is "serialization removed, feature
overhead ≈ residual".

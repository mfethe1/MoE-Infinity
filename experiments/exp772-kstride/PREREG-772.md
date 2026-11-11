# PREREG-772 — k-stride speculative prediction (amortize the per-token D2H)

**Hypothesis.** exp771 named the spec-prefetch cost: `expert_prefetcher.py:450`
(`.indices.cpu()`) = a per-token GPU→CPU sync on the main thread (+4.92 s of
the +5.30 s function total; net DcpuS +4.90 s). Adjacent-token router top-k
sets are sticky, so recomputing the prediction every k-th decode step should
keep prefetch usefulness while cutting the sync count ~k×.

**Intervention.** `src772` = byte-copy of src753 with ONE guard inserted in
`ExpertPrefetcher.speculative_prefetch` before the topk block: with
`EXP772_K=k>1`, calls 1, k+1, 2k+1, … compute fresh topk (pay the sync);
intermediate calls reuse `self._last_speculative_prediction` via the same
downstream paths (`plan_candidates` / `prefetch_experts_list`). `EXP772_K=1`
(or unset) is a no-op passthrough. No other line touched; HEAD identical to
src753 (b7f6ca4); marker string `exp772 k-stride` in the file.

**Cells.** `PY_LGC` (src753, off/off/off), `PY_SPEC` (src753, on/off/off),
`PY_K4` (src772, on/off/off, EXP772_K=4). Envelope otherwise verbatim from
exp769/770/771 (OLMoE-1B-7B, lcnu r=0.75, threads 4, 6 prompts × 64 tok,
warmup 1, py-spy spawn 50 Hz raw, engine byte-identical 1f119bd017985083).
Reuse path skips `_record_prediction` (instrumentation-only; noted).

**Frozen decision rule** (analyze772.py; battery 8/8 pre-staging).
τ_w=2.0 s; D = W(SPEC)−W(LGC); R = 1−(W(K4)−W(LGC))/D.
- rc=9 IDENTIFY-FAIL: SRC_HEAD ≠ b7f6ca4 or ENV lacks moei-772 line
- rc=4 DATA-FAIL: missing/short (rows<6, samples<2000, BADIO non-empty)
- |D| ≤ τ_w → rc=5 NO-BASELINE-SIGNAL
- W(K4)−W(SPEC) > τ_w → rc=8 REGRESS
- rc=1 RECOVER: R ≥ 0.7 AND specleaf(K4) ≤ 0.5·specleaf(SPEC)
- rc=2 PARTIAL: 0.3 ≤ R < 0.7 (or R ≥ 0.7 with leaf gate failing)
- rc=7 NO-GAIN: R < 0.3

**Void conditions.** Any post-freeze change to analyzer/engine/sampler/
src772 patch; py-spy version ≠ PYSPY.txt; interference gate tripped
(busy roster exp746…exp767 + exp771 + exp772).

**Success criterion.** rc=1 → the k-stride guard is an upstream-able
mitigation for the `.indices.cpu()` per-token sync; successor sweeps k∈{2,8}
and measures hit-rate retention. rc=7 → fall back to pinned/non-blocking copy
or device-resident indices.

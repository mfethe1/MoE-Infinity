# PREREG-773 — async double-buffered expert indices (remove the D2H serialization)

**Hypothesis.** exp771 located the spec-prefetch cost at
`expert_prefetcher.py:450` (`.indices.cpu()`): a GPU→CPU sync inside
`ExpertPrefetcher.speculative_prefetch` on the GIL-holding main thread
(+4.92 s leaf; net sampled CPU delta +4.90 s). exp772 REFUTED frequency
amortization (4× fewer syncs, leaf ratio 0.94): the time is a queue-drain
serialization — the main thread stops launching kernels while the GPU
backlog drains, adding GPU idle bubbles to the decode step. Removing the
block from the critical path should reclaim most of the SPEC−LGC wall gap:
consume the indices copy issued by the PREVIOUS speculative_prefetch call
(one expert-layer of GPU drain time, far more than the sub-step backlog)
and issue the current topk asynchronously into the other pinned buffer.

**Intervention.** `src773` = byte-copy of src753 with ONE env-gated block
replacing the topk computation in `ExpertPrefetcher.speculative_prefetch`.
With `EXP773_DB=1`, each call: (a) synchronizes the cudaEvent armed by the
previous call and reads that pinned buffer (full top-k sorted descending,
sliced to the current k — identical values to `topk(logits, k)` by
construction), falling back to the original blocking path on the first
call; (b) issues `torch.topk(logits, num_experts).indices` into the OTHER
pinned buffer via `copy_(…, non_blocking=True)` + event record; (c) swaps
slots. The consumed prediction is one speculative call staler (exp772:
staleness is cheap — k=4-stale predictions cost ~0.1 s of wall).
`EXP773_DB=0`/unset is a verbatim passthrough of the original block. No
other line touched; HEAD identical to src753 (b7f6ca4); marker string
`exp773 async-dbuf`.

**Cells.** `PY_LGC` (src753, off/off/off), `PY_SPEC` (src753, on/off/off),
`PY_DB` (src773, on/off/off, EXP773_DB=1). Envelope otherwise verbatim from
exp769–772 (OLMoE-1B-7B, lcnu r=0.75, threads 4, 6 prompts × 64 tok,
warmup 1, py-spy spawn 50 Hz raw, engine byte-identical 1f119bd017985083).
Prefetch-list changes affect only which experts are pre-loaded (dispatch
loads missing experts on demand); model outputs are unaffected.

**Frozen decision rule** (analyze773.py; battery 9/9 pre-staging).
τ_w=2.0 s; D = W(SPEC)−W(LGC); R = 1−(W(DB)−W(LGC))/D.
- rc=9 IDENTIFY-FAIL: SRC_HEAD ≠ b7f6ca4 or ENV lacks moei-773 line
- rc=4 DATA-FAIL: missing/short (rows<6, samples<2000, BADIO non-empty)
- |D| ≤ τ_w → rc=5 NO-BASELINE-SIGNAL
- W(DB)−W(SPEC) > τ_w → rc=8 REGRESS
- rc=1 RECOVER: R ≥ 0.7 AND specleaf(DB) ≤ 0.5·specleaf(SPEC)
- rc=2 PARTIAL: 0.3 ≤ R < 0.7 (or R ≥ 0.7 with leaf gate failing)
- rc=7 NO-GAIN: R < 0.3

**Void conditions.** Any post-freeze change to analyzer/engine/sampler/
src773 patch; py-spy version ≠ PYSPY.txt; interference gate tripped
(busy roster exp746…exp767 + exp771 + exp772 + exp773).

**Success criterion.** rc=1 → async double-buffering is the upstream-able
fix for the line-450 serialization; successor measures prefetch hit-rate
retention under one-call-stale predictions. rc=7 with specleaf collapsed →
the wait moved to a new sink: profile-attribute the next function. rc=7
with specleaf intact → serialization is not mediated by this sync; re-examine
the queue composition. rc=8 → event/pinned-copy overhead dominates at this
envelope.

# exp765 prefetch-cost repair

The measured +7.53 s/cell self-time, 5.31 s waiting saving, +6.11 s eager-dispatch shift, and 21.2% throughput loss are accepted as ground truth. The supplied source supports a small allocation repair, but does not establish a large Python bookkeeping bottleneck within this method. Function-level samples cannot apportion that time to individual statements or distinguish synchronization charged to a Python caller. No claim of recovering 7.53 seconds is justified from these files alone.

All line references below refer to the frozen src-ref files.

## Call points and costs

- Executor lines 206–212 forward logits directly. Lines 856–880 issue after dispatch in overlap mode; otherwise lines 1008–1019 issue the deferred prediction after correction. No call point is changed.
- Prefetcher lines 404–418 handle explicit route-ahead IDs, used by executor lines 317–322. GPU-route off does not by itself prove which branch every invocation takes.
- Lines 430–440 perform a few policy checks and attribute accesses; these are constant-size work, not per-token loops.
- Lines 445–452 execute `torch.topk(router_logits.float().view(-1, self.num_experts).mean(0), num_experts_to_prefetch).indices.cpu().tolist()`. Conversion and mean traverse token/expert data in native kernels; top-k selects experts; CPU transfer can synchronize accelerator work. This is the strongest source-level candidate for substantial cost, but is not a Python per-token loop. Per-line attribution is unavailable. Preserve arithmetic, dtype, reduction, top-k, and synchronization position to avoid numerical/tie or timing changes.
- Lines 454–459 execute `np.array(router_logits).reshape(-1, self.num_experts).mean(0)` followed by `np.argsort(logits_np)[-num_experts_to_prefetch:][::-1].tolist()`. A plain ndarray is unnecessarily copied before a read-only reduction. Sorting is native NumPy work. Partial selection could alter ties, so sorting stays unchanged.
- Line 461 constructs `set(topk_indices)`. Line 471 constructs another set, and `_record_prediction` lines 390–393 copies it again. Explicit route-ahead similarly constructs a set at line 417 before that helper copies it. Only the intermediate temporary is removed; initial publication and post-issuance recording stay in place.
- Lines 462–470 invoke overlap planning or issuance. `prefetch_experts_list` lines 305–317 has an expert loop, tuple-key dictionary lookup per selected expert, and either one native batched call or per-expert fallback calls. Default selection is only two experts. No lock churn or incremental candidate-set computation exists inside speculative_prefetch. Overlap planning can add loops and native calls (lines 546–610); no overlap setting was supplied, so its contribution is unknown.

## Changes and expected reduction per call

1. Pass the existing ID list to `_record_prediction`, retaining its owned set construction. Update its annotation to List[int]; both supplied callers pass lists. This removes one temporary set allocation and K insertions per successful recording call. Expected saving: O(K) small Python allocation work, typically sub-microsecond to a few microseconds for small K, an unmeasured estimate, not an experiment result. The initial set at line 461 is intentionally retained: issuance callbacks or exceptions can observe that state.
2. For exactly `np.ndarray`, reduce the existing array directly; other input types and ndarray subclasses retain `np.array` conversion. This eliminates one full input copy/allocation per NumPy invocation, approximately input_bytes / effective_copy_bandwidth plus allocation overhead. No numerical time estimate is defensible without input size and bandwidth. Expected saving on the Torch path: zero.

Neither change memoizes predictions, logits, mutable policy settings, tensor maps, or residency. Such caches would require invalidation and could change decisions. This patch is unlikely on its own to recover a multi-second Torch-path regression.

## Decision identity and risks

The same source values, reshape, mean, top-k or argsort, selected order, target layer, priority, phase, call count, and call positions are retained. Set ownership remains in the recording helper; callers cannot mutate saved predictions via their lists. Initial and final prediction publication still occur on either side of issuance. No eviction, admission, threading, or native scheduler behavior changes.

The NumPy fast path assumes logits are stable during this synchronous read. Concurrent mutation could differ from the old copied snapshot; if concurrent writers are permitted, retain the original copy. No thread-model change is introduced. Custom ndarray subclasses retain old conversion semantics. Torch ties and floating-point reduction order are untouched. Wall-clock issuance may occur earlier due to reduced work; logical issuance points remain identical.

## Verification and limits

Full patched file parses with Python ast. No model or GPU execution, imports of the inference engine, git operations, or commits were performed. CPU-only differential method tests compare issuance arguments, return values, and prediction state across explicit IDs, phase gates, boundaries, overlap, ties, ndarray/list inputs, and duplicate explicit IDs (288 cases passed). Exception paths were inspected but not executed. These establish control-flow identity for the exercised cases, not native runtime performance. The frozen source is left unchanged.

# exp766 transfer-restructure — conditional pre-design

Status: measurement gate; no implementation patch. exp765 remains running and no models were run for this design. The frozen +7.53 s/cell attribution is inclusive host frame time, not demonstrated transfer bandwidth cost.

## Source findings

References below are to the frozen src-ref files.

- expert_executor.py:684–692 accepts router_logits without a type annotation, assertion, conversion, or device check. The GPU checks at 703–708 concern router_mask, not router_logits. Thus these two source files cannot establish the actual decode logits type or device. The upstream model/router producer is absent. A CUDA tensor is plausible, but not proven.
- expert_executor.py:206–212 forwards the same object unchanged. At 856–880 the overlap flag selects immediate synchronous invocation after routing; route-ahead success bypasses legacy prediction entirely (850–855). Otherwise the original object is retained in _pending_prefetch (881–890).
- expert_executor.py:916–942 unpacks that retained object. At 993–1019, successful completion first corrects the previous prediction, then calls speculative_prefetch with those same logits. Failure-safe branches preserve their exception handling. These branches must remain in place.
- expert_prefetcher.py:442 selects the tensor-like branch using hasattr(topk), not a CUDA/type check. Torch CPU tensors also use this branch. The NumPy branch (453–459) runs for objects without topk; the executor neither creates nor excludes such objects. Its actual decode incidence cannot be established here. Do not optimize it on an assumption that it is hot or unreachable.
- expert_prefetcher.py:446–451 already computes float conversion, mean, and top-k on the tensor device and transfers ONLY K indices, normally 8*K bytes for torch int64. There is no full-logits D2H transfer in this branch. Default K is two (438–440); phase policy supplies K otherwise (430–437).
- Host indices are immediately consumed for prediction state (461), candidate planning (462–466), or prefetch issuance (468–471). prefetch_experts_list immediately maps Python IDs to tensor IDs and calls the native engine (296–317). There is no useful independent work between transfer and consumption within this function.

## Synchronization interpretation

For CUDA input, the blocking CPU copy waits for the copy and its ordered producer dependencies on the applicable CUDA stream. This can charge earlier queued GPU work to the .cpu() host frame; it is not evidence of a device-wide synchronization across all streams. Later work is not inherently included. CPU input has no CUDA D2H synchronization here. Cross-stream dependencies and native engine stream behavior are outside these files.

PyTorch documents automatic synchronization for CPU/GPU copies and the requirement to synchronize asynchronous GPU-to-CPU copies before host reads:
https://docs.pytorch.org/docs/stable/notes/cuda
https://docs.pytorch.org/tutorials/intermediate/pinmem_nonblock.html
The installed PyTorch version and native CUDA trace must determine the exact runtime calls.

## Exact conditional restructure

The only local, decision-preserving transfer experiment worth considering after exp765 is:

1. Retain every guard, phase choice, arithmetic operation and torch.topk invocation exactly, on the original current stream. Keep the resulting indices tensor alive.
2. For verified dense CUDA int64 indices only, acquire an exclusively owned pinned CPU buffer of matching K and dtype. Allocate outside timed cells; pool by device and K with bounded ownership, never one unguarded shared slot.
3. On the SAME current CUDA stream, copy indices into that buffer with copy_(indices, non_blocking=True), then record a completion event immediately after the copy.
4. Synchronize that event BEFORE tolist(), prediction-state mutation, plan_candidates, or prefetch_experts_list. Release the slot only after list materialization; retain all source/buffer/event objects through completion, including exception paths.
5. Leave CPU, NumPy, non-CUDA, explicit expert_ids, phase, overlap, priority, return-value, correction, and failure behavior unchanged. Never use stale indices on failure.

This deliberately has no deferred issuance. It may reduce pageable allocation/staging overhead through buffer reuse, but it cannot hide producer latency: the host must wait immediately. An event is a narrower completion marker, not a way to eliminate required dependencies. Additional event/pool overhead may make this slower for a 16-byte default payload. There is no basis to forecast recovery of +7.53 seconds.

A separate copy stream is not proposed: it needs producer-event waits, allocator lifetime management, and confirmed stream interactions, and still has no host overlap window here. Moving selection/copy earlier into dispatch_local could overlap expert execution for the deferred path, but changes computation timing and needs executor edits, upstream immutability proof, and exact stream-order evidence. Moving issuance later violates the required call points. Neither is authorized as an identity-proven local patch by current evidence.

## Identity argument and limits

A completed byte-for-byte copy of the SAME topk result yields the same list and set, including that invocation's tie selection; no new sorting, dtype conversion, reduction, caching, or top-k algorithm is introduced. Events must complete before any host read. Keep original order as well, since engine priority can depend on it even though the acceptance constraint permits set equivalence.

The conditional algorithm preserves selection under normal execution. A production full-file patch is withheld because actual tensor/device/stream path, pool lifetime/concurrency requirements, and a useful savings mechanism have not been established. No mean caching: stable-looking logits do not prove invariant top-k, especially at ties or margins.

## Measurement gate before implementation

Use exp765 results first; do not launch another model run as part of this pre-design.

Required evidence from the existing run or a separately authorized measurement:

- Per actual speculative call: Python type, device, dtype, shape, phase, layer, K, overlap flag, and branch counts. Include explicit-ID and route-ahead bypass counts. Obtain upstream producer source and establish logits mutation/lifetime and producer/current streams.
- Native timeline separating queued producer work, float/mean/topk kernels, D2H bytes/duration, host allocation, cudaStreamSynchronize/event waits, and native expert work. Measure end-to-end cell wall time too: moving a wait out of this frame alone is not a saving.
- Show whether expert execution shares the current stream and whether any independent CPU work exists before the original consumer point. With the shown local function there is none.
- If staging overhead is material, compare the conditional pinned-buffer path against the baseline on identical captured inputs without running models: exact lists/sets and all phase/call traces, CPU and NumPy fallbacks, ties, noncontiguous input behavior, exceptions, repeated calls, multi-device and concurrent/reentrant callers. Do not weaken baseline errors or silently recover using stale data.
- Accept only zero decision/call-point/phase differences and improved cell wall time. Revert the experiment by restoring the unmodified source; introduce no policy toggles that silently select different decisions.

No git commands, commits, source mutations, or model execution were performed. Only this design artifact was added.

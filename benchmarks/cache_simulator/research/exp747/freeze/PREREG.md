# exp747 PREREG — how long does one CUDA host callback stall the GPU stream on WSL2, and does CPU contention inflate it?

Lane 79990, program STACK-1001-79990. Written 2026-11-06 ~21:50 EST, BEFORE any exp747 cell. Namespace check: no exp747 on Mack
or Winnie, and no running.json or queue entry. Model-free. Runs after exp746 (serial on GPU1).

## Why
- **Mechanism (source, MoE-Infinity 0337988 `core/parallel/expert_dispatcher.cpp`).** With `gpu_only_expert_routing=True` (the default),
  `DispatchExperts` copies the active-expert flags D2H asynchronously, then inserts `cudaLaunchHostFunc(RouteReadyCallback)` into the
  compute stream. The callback pushes to `route_queue_`, and the `RouteFunc` thread enqueues the experts. Every expert is also
  retired through a host callback. With routing off, Python does one `.cpu()` sync per layer and enqueues directly. A host function
  blocks its stream until a CPU thread has run it, so the GPU pays its full round trip. At ~16 route plus ~128 retirement callbacks per
  token, the callback round trip is a candidate for the engine's GPU-idle time, its ~4× higher load sensitivity than HF (exp744 raw:
  ~5.2 vs ~1.4 ms/token per load unit), and the provisional exp744 finding that routing-off is faster.
- **Smoke (motivation, NOT evidence; GPU0, foreign loadavg ~21–22, 2 CI workers active, N=300).** The first version without a gate
  measured enqueue gaps, so it was discarded and the gate was added. The gated version measured a device-side host-callback stall of
  median **551 µs** (p10 474, min 332, p99 1907), against tiny-kernel+sync host wall 95 µs and an empty base span of 6 µs. exp744's
  "hostfn_cost ~95 µs" was a host-wall difference on an idle GPU, which is a different quantity.

## Measurement (micro2.py, frozen)
Behind a ~0.8 ms bf16 matmul gate on a side stream, cuda events time [tiny kernel → cudaLaunchHostFunc(libc free(NULL), no GIL)
→ tiny kernel] against the same sequence without the host func, interleaved, N=1500 each. hostfn_stall = sample − median(base).
Also measured: kern_sync host wall (tiny kernel + cudaStreamSynchronize) and matmul completion-notify latency.

## Cells (frozen), serial, GPU1, palindromic: k0_1, k6_1, k12_1, k18_1, k18_2, k12_2, k6_2, k0_2
Before each cell, ONE combined bounded wait (≤5400 s) holds until all of these are true at the same moment: GPU1 ≤1024 MiB, no
Ollama model loaded, loadavg1 <3.0, and no Runner.Worker. Then K bash busy-loop spinners start (PIDs recorded; only those PIDs are
killed afterwards), there is a 30 s settle, and micro2 runs. mon2.sh samples every 2 s.

## Exclusions
Pre-start GPU >1024 MiB or Ollama; any Runner.Worker sample; Ollama loaded or probe failed; GPU1 memory >3000 MiB mid-cell; load mean
>K+4; median live-spinner count ≠K; gate overrun (>5% of base spans >50 µs); <5 monitor samples; RC≠0.

## Decision rules (analyze.py, frozen; a dry-run on 6 synthetic cases produced the intended branches and every exclusion fired)
- QUIET (spin 0): hostfn_stall median / kern_sync median ≥2 → HOSTFN-STALL-EXCEEDS-SYNC; ≤1 → HOSTFN-CHEAP; otherwise COMPARABLE.
- CONTENTION: r_h = hostfn_stall(spin12)/hostfn_stall(spin0), r_s likewise for kern_sync. r_h ≥2 and r_h ≥1.5·r_s → HOSTFN-FRAGILE;
  r_h <1.3 → HOSTFN-ROBUST; otherwise MIXED.
- The PROJ lines (144 serialized callbacks/token × stall) are descriptive upper bounds only.
- `VERDICT QUIET:..|CONTENTION:..`

## Predictions (registered)
QUIET:HOSTFN-STALL-EXCEEDS-SYNC, p=0.75. CONTENTION:HOSTFN-FRAGILE, p=0.55. Contention may not be needed: the smoke's 551 µs could
reflect WSL's paravirtual callback path even when quiet.

## Consequences
- HOSTFN-STALL-EXCEEDS-SYNC → the engine's per-expert retirement and per-layer route callbacks are a priced WSL cost (≥ several
  hundred µs each). Next comes an engine change measured against exp744/746: retire per layer with ONE host func, or poll completion
  events from the exec thread instead of host funcs. This is upstream-relevant (MoE-Infinity), but it must be checked on native Linux
  before anyone claims it holds generally.
- HOSTFN-FRAGILE → host contention amplifies it, which explains the engine's load sensitivity. Recommend `gpu_only_expert_routing=False`
  on WSL until retirement no longer uses host funcs, and only if exp746 ROUTE-Q also says OFF-FASTER.
- HOSTFN-CHEAP → the smoke was a contention artifact; host funcs are not the GPU-idle term, so look at exec-thread queuing instead.

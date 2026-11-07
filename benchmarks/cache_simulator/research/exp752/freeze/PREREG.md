# exp752: remove `cudaLaunchHostFunc` from the MoE-Infinity decode hot path (retire-by-event)

Pre-registered 2026-11-07, before any exp752 timing data exists. The roadmap called this "exp748: replace per-expert callbacks",
but exp748 had already been used as a name, so this experiment takes exp752.

## Why now (from sealed evidence)
- **exp747 (#74).** On Winnie/WSL, one `cudaLaunchHostFunc` stalls the stream for 522 µs on the device side, against 46 µs for a
  kernel+sync round trip.
- **exp751 (#75, ADDENDUM73).**
  - The native-Linux stall is 108.5 µs, so it is mostly WSL.
  - The engine-vs-HF gap persists natively at 38.5 ms/tok, with an engine/HF ratio of 2.72 native vs 2.74 on WSL.
  - On WSL the gap is about 60 ms/tok, 61% of it GPU-idle (exp746).
  - Native turning routing off with `gpu-route` off gains −6.75 ms/tok, which shows the host-callback path costs real time.
- **Decode hot path at Winnie HEAD `0337988`** (per-expert path; `MOE_GROUPED_DECODE` unset):
  - `ExecFunc` enqueues one `ExpertReadyToRetireCallback` per routed expert: OLMoE has 16 layers × top-8, so about 128 per token.
  - `Wait` enqueues one `CompletionWaitsConsumedCallback` per layer on the caller stream: 16 per token.
  - Each host function makes the stream wait for a host thread round trip.

## Intervention (`exp752.patch`, 133 lines, `core/parallel/expert_dispatcher.{cpp,h}`)
The runtime switch `MOEI_EXP752_MODE` is read once, and the process prints `exp752 mode=N` to stderr.

- **H** (unset or `H`): byte-identical upstream behaviour.
- **R:** per-expert retirement records a pooled `cudaEvent` on the exec stream and pushes the retire item straight onto the
  existing retirement queue.
  - `RetirementFunc` polls `cudaEventQuery` (10 µs sleep) before doing the same retirement work.
  - The pending counter is decremented after the work, so the destructor drain stays correct.
  - No host function is enqueued on the exec stream.
- **RC:** R, plus the per-layer completion events are no longer released by a caller-stream host function.
  - After `cudaStreamWaitEvent` they go through upstream's existing query path (`QueueUnwaitedEventsForQuery`).
  - This is safe under CUDA semantics: once `cudaStreamWaitEvent` returns, a later re-record of the event cannot affect the
    wait already enqueued.
- Untouched: the grouped path, the route-ready callback, and all retirement semantics (IDLE publish order, lease release,
  cache-waiter notify).
- Source shas:
  - orig cpp `339b0fe4…`, h `863de318…` (equal to Winnie's live `~/moei-engine` files)
  - patched cpp `694f2892…`, h `cce6cdde…`
- Build: private copy `~/exp752/src`, rebuilding `moe_infinity._store` only. `~/moei-engine` is untouched. The `.so` sha is
  recorded in `out/RUN_SHA256`.

## Design
- **Hardware:** Winnie (WSL2, RTX 5060 Ti 16 GB), **GPU1** (PCIe gen4 x8, the same GPU as the exp746/exp747 baselines). GPU0 sits on
  gen3 x2 and hosts Ollama, so it is not used. A foreign process found on GPU1 (by index or UUID) is never killed; the cell waits
  (allquiet) or is FLAGGED. (A pre-freeze draft said GPU0; it was changed before any data existed.)
- **Workload:** OLMoE-1B-7B-0125-Instruct, lcnu, ratio 0.75, threads 4, gpu-route on, 6 prompts × 64 new tokens, warmup 1,
  greedy. This is the exp746 quiet-on configuration.
- **Arms:** hf, H, R, RC with 3 replicates each, 12 cells. The rotated order (`cells.json`) is H R RC hf / R RC hf H / RC hf H R,
  so each arm takes each position once and drift is spread across arms.
- **Gates and exclusions** (inherited from exp746 AMENDMENT1 and exp751):
  - Combined quiet wait (`allquiet746.sh`) on GPU1: ≤1 GB used, no Ollama model, 1-min load <3.0, no Runner.Worker.
  - Precell record: GPU memory, Ollama, load, runners, and the count of compute processes on other GPUs.
  - Exclude a cell for any of: FLAGGED (foreign process on GPU1 by index or UUID, Ollama model loaded, or >1 GB at start);
    util baseline >5%; mean load >4.0; any Runner.Worker; manipulation failure; fewer than 10 NVML samples in a row window.
- **Manipulation check:** an engine cell is valid only if its log contains exactly one mode banner and that banner matches the
  arm, and `gpu_route_effective` is True. The banner exists only in the patched build, so it also proves the private `.so` was
  loaded.
- **Covariate:** foreign processes on other GPUs (GPU1 `gen.py`) are recorded per cell. If clean cells differ in this
  covariate, the verdict is re-reported restricted to the majority stratum, and both are published. The sealed verdict does not
  change.

## Pre-registered analysis (`analyze752.py`)
Per-cell decode ms/token is the median over prompts. Each arm uses the mean over clean cells and needs n≥2, otherwise
INCONCLUSIVE.
- **PARITY** (correctness, gating; uses every completed engine cell that passes the manipulation check, clean or not):
  - The H cells must agree with each other on greedy token ids; if they don't, parity is NA.
  - If H is self-consistent, any R or RC cell whose ids differ from H makes that arm UNSAFE(PARITY-FAIL), whatever its speed.
- **RETIRE** compares R with H; **COMPL** compares RC with R; **TOTAL** compares RC with H.
  - Δ = mean(new) − mean(ref).
  - FASTER: Δ ≤ −3 ms/tok and complete separation (every clean new cell beats every clean ref cell; one-sided permutation
    p = 0.05 at 3v3).
  - SLOWER: the mirror image.
  - NO-CHANGE: |Δ| < 3.
  - MIXED: anything else.
- **Descriptive:** the idle/busy split of each Δ, and the fraction of the H−hf gap closed by the best patched arm.

## Predictions (written before data)
- **Prior.** Up to 128 × 0.522 = 67 ms/tok if every callback stall serialized, but the callbacks overlap across 4 exec streams
  and the whole on-WSL gap is about 60 ms.
- **RETIRE:** P(FASTER) = 0.60, expected Δ between −8 and −30 ms/tok, mostly from GPU-idle. P(NO-CHANGE) = 0.30, which would mean
  the stalls are hidden behind other critical-path work. P(SLOWER) = 0.10, through retirement latency delaying cache reuse.
- **COMPL:** P(FASTER) = 0.30, with at most about 16 × 0.52 = 8 ms possible; P(NO-CHANGE) = 0.60.
- **PARITY:** expected OK, since retirement only gates host bookkeeping; P(FAIL) = 0.05.

## Decision rules
- **RETIRE:FASTER with PARITY OK:** promote the patch to a PR candidate after an independent review plus the native-Linux check,
  then run grouped-path and route-callback variants next.
- **NO-CHANGE:** host functions are not the critical path on decode. Re-rank toward the remaining idle sources: Python
  per-layer orchestration and route-ready sync (exp753 candidate: per-layer host timeline with NVTX).
- **SLOWER or UNSAFE:** drop polling retirement. The next candidate is a dedicated retirement worker per exec stream using
  `cudaEventSynchronize` (blocking sync flag).

## Pre-freeze smoke (disclosed; untimed, not evidence for any timed claim)
`smoke752.sh` ran 2 prompts × 16 tokens per mode on GPU1 before freeze. Raw output is in `smoke_pre/`.
- **What it showed:**
  - Every mode exited 0, and every log has exactly one banner matching its mode.
  - Greedy tokens are identical: R == H and RC == H.
  - `gpu_route_effective` is True in all three.
- **Speed is uninformative and must not be read.**
  - The quiet wait was released manually (load about 24 from construct-pro CI; see `smoke_pre/NOTE`).
  - A foreign `gen.py` (another lane's correctness eval, pinned to GPU1 by UUID) started at about 19:48Z, after H finished. It
    overlapped both R and RC at 99% GPU1 utilization.
  - Observed tok/s: H 8.89/4.47, R 2.39/0.59, RC 0.79/0.88.
- **Consequence:** the predictions above stand unchanged. The SLOWER branch is now plausible a priori, but under contamination
  the smoke cannot tell it apart from foreign-GPU interference. The gated timed run settles it.

## Amendments
Any change after the first timed cell starts gets an AMENDMENTn.md written before the affected data, as in exp751.

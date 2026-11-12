# EXP-795 — DESIGN (preregistered before implementation)

## Hypothesis
Of the ~1.46 ms/call host-side drain latency (exp794, ratio 0.5), the majority
is thread-queue round-trip: route worker -> exec_queue_ -> GPUExecFunc wake ->
GroupedExec -> pending decrement -> cv notify -> caller wake. For cache-hit
groups (no fetch needed) the whole detour is overhead.

## Patch (expert_dispatcher.cpp ONLY, tree copy src795 from src788 build10)
WaitHiddenStates(): replace passive cv-wait with ACTIVE work-stealing wait:
  while (route_pending_ || pending_ > 0):
    if exec_queue_[dev].TryPop(args): run GroupedExec(args) INLINE on caller
    thread (same stream/event discipline as GPUExecFunc), decrement pending
    bookkeeping exactly as the worker does; else cv_wait short timeout.
Fetch-side items (misses) still go to workers — steal only steals exec items,
so mixed hit/miss layers keep making progress. Env kill-switch
MOE_INLINE_WAIT=0 restores passive wait.

## Gates (pre-declared)
- A correctness: all 8 probe prompts produce IDENTICAL greedy token IDs
  (32 tokens) vs unpatched C build, ratio 0.5. Any divergence = VOID.
- B performance: promote iff pooled mean tok/s >= +5% vs C at ratio 0.5
  (3 reps, perfect-separation check as in exp791 confirmatory).
- Instrument: reuse probe794 timers (wait_s/call expected to drop).

## Envelope
OLMoE-1B-7B, grouped ON, ratio 0.5, lcnu, topk 8, GPU1, 8 prompts x 32 tok.

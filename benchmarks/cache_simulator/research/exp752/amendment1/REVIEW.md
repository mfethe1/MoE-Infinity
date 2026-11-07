# exp752 independent patch review
Reviewed by a gpt-6.1-sol subagent, read-only, on 2026-11-07 (367 s). The subagent's summary is reproduced here. Line numbers refer
to `freeze/src_patched/expert_dispatcher.cpp` unless the finding says otherwise. This file replaces a truncated first copy in
commit 18f3424.

**Verdict: RUN-SAFE: yes. No blockers.**

1. **MINOR, :1749/:1759. R branch can miss a decrement.**
   - `pending_retirement_callbacks_` is incremented, and then `AcquireCompletionEvent(gpu_id)` can throw (its `CUDA_CHECK` sits
     outside the inner try).
   - The counter is then never decremented, `retire` leaks, and `~ExpertDispatcher` blocks on `retirement_callback_cv_`.
   - This happens only if CUDA event creation fails.
   - Fix: acquire and record the event before the `fetch_add`, or wrap the acquire in a try.
   - Every other R exit path is balanced, nothing is decremented twice, and the drain is stronger than in H.
2. **MINOR, :2881-2883 with .h:235. RC can leak events at teardown.**
   - NotReady re-pushes into a closed `completion_retirement_queue_` are silently dropped.
   - The handles leak only at process teardown; there is no deadlock.
   - Fix: route these to `destructor_fallback_events_`, or drain with `cudaEventSynchronize`.
3. **MINOR (performance only), :2933-2940. Head-of-line blocking.**
   - A single retirement thread polls items in CPU-enqueue order across 4 exec streams, so one slow stream delays every later
     retirement.
   - The 10 µs sleep really lasts ≥60 µs because of timer slack.
   - Deadlock is impossible.
   - This is the "SLOWER via retirement latency" mechanism.
4. **NIT, :2939-2941.** When `cudaEventQuery` returns an error, the event goes back to the pool before the throw. Harmless.
5. **NIT, :2984-2999. H is not literally byte-identical.**
   - H prints the banner once and adds a static-guard branch.
   - `ExpertRetireArgs` grows by one pointer that defaults to nullptr, and every user is in `_store`, which is rebuilt fresh.
   - Otherwise H runs the upstream code paths.
6. **INFO, :1839-1845. Coverage.** The grouped path still uses `GroupReadyToRetireCallback` in R and RC, so check
   `grouped_batches == 0` per cell. AMENDMENT1 does this with `check_grouped.py`.

**Answers to the specific questions**
- **RC event release is safe.** `cudaStreamWaitEvent` captures the most recent record at call time; re-recording or destroying
  the event afterwards does not affect the wait.
- **No other state depends on the callback path.** `completion_events_outstanding_` and `completion_events_retired_` are updated
  on both paths.
- **`cudaEventQuery` without `cudaSetDevice` is valid.**
- **R shutdown:** no deadlock except through finding 1, and no leaked retire events.

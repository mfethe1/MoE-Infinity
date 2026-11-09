# exp752-fixups — review-defect fixes for the retire-by-event upstream patch

Date: 2026-11-08. Owner: 79990 conversation lane. Scope: fixes the two MINOR
defects found in the exp752 independent review (`deleg_2bb582b0`, RUN-SAFE
verdict) that gate the retire-by-event upstream post. exp752 stays sealed —
these apply **on top of** `exp752/freeze/src_patched/` sources.

## Defect D1 — R-mode teardown hang (review minor #1)

`ExpertDispatcher.cpp` (exp752 R-mode branch, `Exp752Mode() >= 1`):
`pending_retirement_callbacks_.fetch_add(...)` runs, then
`AcquireCompletionEvent(gpu_id)` can throw (CUDA event pool creation). The
surrounding try/catch covered `cudaEventRecord` and `retirement_queue_.Push`
failures but not the acquisition itself → missed `fetch_sub` →
`~ExpertDispatcher` waits forever on `retirement_callback_cv_` → teardown hang.

**Fix (fixups-expert_dispatcher.cpp.patch):** wrap the acquisition in
try/catch with the same cleanup as the sibling failure paths (`fetch_sub`,
`delete retire`, rethrow). Behavior otherwise unchanged.

## Defect D2 — RC-mode closed-queue re-push drop → event-handle leak (review minor #2)

`CompletionRetirementFunc` re-pushes not-ready batches into
`completion_retirement_queue_` (`ThreadSafeQueue<std::vector<CompletionRetireItem>>`).
`ThreadSafeQueue::Push` **silently returns when `closed_`** (engine
`core/utils/threadsafe_queue.h:19-27`), so a re-push racing the destructor's
`Close()` dropped the batch on the floor: its `cudaEvent_t` handles were never
`ReleaseCompletionEvent`'d nor routed to `destructor_fallback_events_` → leak
at teardown (counters drift, handles destroyed late/not at all).

**Fix (fixups-expert_dispatcher.{cpp,h}.patch):** serialize the re-push against
`Close()` with a dedicated `completion_repush_mutex_` + `completion_repush_closed_`
flag (set flag and Close under the same lock). A re-push is then either:

1. accepted before Close — the queue drains remaining items even when closed
   (`Pop` returns items while non-empty), so the batch is processed normally; or
2. rejected after Close — the batch is moved into `destructor_fallback_events_`,
   which `~ExpertDispatcher` synchronizes and destroys (`.h:256-262`).

No engine-wide header change; no shared-utility API change.

## Test plan (pre-upstream)

1. Compile gate: private `_store` build with exp752.patch + these fixups (RC=0).
2. `dispatch_stress.py` mode=2: two clean exits, node_integrity=pass ×2,
   FIXED_FAULTS={PUSH_IN_FLIGHT,...} (exp752's original pre-run gate set).
3. Destructor-storm: repeated construct/teardown loops on GPU1 with
   `MOEI_EXP752_MODE=1` and `=2` (≥50 iterations each), assert process exit 0
   and no `pending_retirement_callbacks_` wait (bounded runtime).
4. Fault injection: force `cudaEventCreateWithFlags` failure path
   (EXP752_TEST_FAULT=RETIREMENT_CALLBACK_LAUNCH for D1's sibling path; a new
   acquire-failure injection is NOT added — the guard is exercised by the
   teardown-storm under memory pressure in step 3's variant).

Runtime steps 2–3 require Winnie GPU1 quiet (exp753's lane currently uses it).

## Upstream status

Folds into the approval-gated retire-by-event upstream post (POSTING-LEDGER
#253/#254: exact text + branch need Michael's approval). Draft v3
(fix737+740+749, sha256 e672c2b1eb14…33a1) remains APPROVAL-GATED separately.

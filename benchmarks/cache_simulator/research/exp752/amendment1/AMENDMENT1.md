# exp752 AMENDMENT1 (pre-data: written 2026-11-07 ~20:10Z, before any timed cell started)

The runner launched at 20:01:11Z. It is still in the first combined quiet wait: GPU1 is occupied by another lane's `gen.py`,
and load is about 24. `out/` contains only ENV.txt and RUN_SHA256. No timing, util or token data exists yet. This amendment
adds a coverage check; it changes no analysis rule.

## Source
An independent code review of `exp752.patch` (gpt-6.1-sol subagent, read-only) concluded **RUN-SAFE: yes, no blockers**.
Its findings are summarized in `REVIEW.md`.

## Change 1: coverage manipulation check (added)
Review INFO finding: the patch changes only the per-expert retirement path. Grouped batches still retire through
`GroupReadyToRetireCallback` in every mode.
- `check_grouped.py OUTDIR` is run after `analyze752.py`.
- An engine cell with `routing_delta.grouped_batches > 0` in any row is EXCLUDED-A1.
- Smoke evidence: R showed `grouped_batches=0` and `route_batches=272`, so no exclusions are expected.

## Change 2: interpretation note (no rule change)
Review MINOR finding 3: R polls on a single retirement thread in CPU-enqueue order across 4 exec streams, and its 10 µs sleep
really lasts ≥60 µs because of timer slack.
- So **SLOWER or NO-CHANGE for R does not mean "host functions are free"**: it may mean polling retirement adds latency to
  IDLE publish and cache-waiter wakeup.
- In that case the pre-registered next candidate (a dedicated per-stream worker using blocking `cudaEventSynchronize`) is
  the direct test.
- RC versus R (COMPL) is not affected by this mechanism.

## Known non-run-affecting defects (to fix before any PR; not fixed now, so the frozen .so stays frozen)
- R: a throw from `AcquireCompletionEvent` between the `fetch_add` and the try leaves the pending count up and the destructor
  hangs. This only happens if CUDA event creation fails.
- RC: events re-pushed after `completion_retirement_queue_` closes leak at teardown.
- Both lie off the success path of a normal run.

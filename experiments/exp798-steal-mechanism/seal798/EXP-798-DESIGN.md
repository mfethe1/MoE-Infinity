# EXP-798 — DESIGN (preregistered BEFORE run)

## Question
Does the inline steal actually remove the dispatch round-trip cost
(mechanism), independent of throughput noise? Instrument: probe794.py
verbatim (sha 073e8f51ad375ff3) — monkeypatch timers at the pybind seam
around dispatch_local / wait_dispatch_local.

## Important measurement note (pre-declared)
With steal ON, the stolen execution happens INSIDE wait_dispatch_local, so
wait_share may NOT drop even on success — the work moves inline. The
mechanism therefore reads from WALL time; wait/enqueue shares classify
where the time went.

## Arms (binary eba566fb; ratio 0.5; grouped; fresh process each;
        CUDA_VISIBLE_DEVICES=1; 8 prompts x 32 tok)
- N1 N2: steal ON (MOE_INLINE_WAIT unset)
- F1 F2: passive (MOE_INLINE_WAIT=0)
Order: N1, F1, N2, F2 (interleaved).

## Decision rules (pre-declared)
- G1 mechanism CONFIRMED: pooled decode wall(N) <= 0.97 x wall(F) (>=3%
  wall reduction, matching exp795's quiet-host +6.8% direction).
- G2 REFUTED: wall(N) >= wall(F).
- Between: inconclusive.
- Wait/enqueue shares + per-call ms reported as mechanism classification
  (idle-wait collapse vs work-moved-inline).
- Environment gate: 1-min loadavg < 2.5 at each arm launch, else park
  without interpretation.

## ADDENDUM (after attempt 2, before attempt 3 — gates UNCHANGED)
Attempt 2 result: N1 wall 27.897 s vs N2/F1/F2 18.7-19.1 s; env gate passed
(load <= 1.61). Diagnosis: first-arm cold page cache (attempt 1 failed at
the env assert before any model load, so attempt-2 N1 was the first load of
the ~14 GB weights + offload shards that day; per-prompt 1-tok warm does
not warm later-token expert fetches). Order artifact invalidates the N mean
-> attempt 3 (final under 3-attempt rule): throwaway warm process W first,
then F1, N1, F2, N2 (each treatment gets one early and one late slot).
Gate text untouched: G1 confirm wall(N) <= 0.97*wall(F); G2 refute
wall(N) >= wall(F); else inconclusive.

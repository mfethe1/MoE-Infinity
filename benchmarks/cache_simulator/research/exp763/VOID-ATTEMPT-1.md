# VOID-ATTEMPT-1 — 2026-11-10T22:3xZ
Attempt-1 (FREEZE-763: PREREG a2658ea9, analyzer af352ac6) ran clean rc=0 but the
verdict DIAGNOSIS-D1-OVER-FETCH-DOMINATED is VOID:
- PREMISE FALSE: every expert_dispatch event in all 12 cells carries bytes=0 (traffic
  uninstrumented in this build) -> bytes_ratio=inf -> D1 armed on vacuum.
- Secondary: stage event durations overlap in time (sum of stage durations exceeds wall),
  so share deltas are not compositional evidence either.
- Discipline: premise error != gate waiver (exp753 rule). No settlement on D1.
- Attempt-1 output preserved verbatim: out/verdict.txt (Winnie /home/mfeth/exp763).
- Attempt-2 re-specification (written BEFORE any dispatch-count or interval-coverage
  computation on real data): traffic estimated as N_dispatch x on-disk per-expert weight
  bytes (measured at freeze, no GPU); attribution via merged [ts,ts+dur] interval
  coverage per stage class; contrasts in ABSOLUTE seconds; same D1/D2/D3 thresholds.
  Counts and coverage have NOT been computed on real traces at write time (only schema,
  zero-bytes fact, and per-stage dur sums from attempt-1 output above).

# PREREG-M2 ADDENDUM — rank misstatement + scope split (M2a / M2b)

Written 2026-11-19 after VERIFICATION GATE FAIL (legitimate). Not a silent edit of the
frozen PREREG-M2.md (sha `72b8118269cbb9542f8dc9cce367367e0ddd31bca1cb32062e6ae9defce62217`
in FREEZE-828.json); that file stands as frozen before any data existed.

## Error owned
PREREG-M2.md line 3 says "Rank-2 item of MYTHOS-ADJUDICATION-20261118.md §2".
The adjudication's table (lines 61-62 of the report) gives M1 = rank 1 and M2 = rank 1
(M0 = rank 0). Citation error, no effect on the executed measurement protocol.

## Scope split
The adjudication's M2 spec (verbatim, report line 62):
> M2 | Missing: dispatcher counters at b1 (misses, accesses, H2D bytes per token at 0.50
> and 0.65, read outside the timed region) | rank 1

and line 130: exp791 ratios 0.75/0.90 "rerun inside M2 with the cudaMalloc hook and
counters".

- **M2a** (what FREEZE-828.json froze and Winnie is running, unit exp828-m2, sha
  `5d032454f165b7e2`): profiler attribution arm at 0.50 only — where does engine b1 step
  time go (expert GEMM vs dispatch/memcpy/wait). Valid as executed; a strict subset of
  the adjudication's M2.
- **M2b** (NEW, separate prereg + freeze before its run): dispatcher counters at b1 —
  misses, accesses, H2D bytes per token — at device_memory_ratio 0.50 AND 0.65, counters
  read OUTSIDE the timed region; plus the exp791 0.75/0.90 rerun with cudaMalloc hook
  and counters. Answer's §2's tension directly (exp821 saw 0.50→0.65 move walls only
  1.2-2.2 ms/tok — why, if per-token H2D is tens of MB?).

## M2a decision rule unchanged
The 60% attribution rule from PREREG-M2.md applies to M2a results as written.

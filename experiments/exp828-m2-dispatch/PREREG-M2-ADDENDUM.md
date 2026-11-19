# PREREG-M2 ADDENDUM — rank misstatement + scope split (M2a / M2b)

Written 2026-11-19 after VERIFICATION GATE FAIL (legitimate); citations corrected after a second gate FAIL (0-based index off-by-one, bold markers, stale sha). Not a silent edit of the
frozen PREREG-M2.md (sha `72b8118269cbb9542f8dc9cce367367e0ddd31bca1cb32062e6ae9defce62217`
in FREEZE-828.json); that file stands as frozen before any data existed.

## Error owned
PREREG-M2.md line 3 says "Rank-2 item of MYTHOS-ADJUDICATION-20261118.md §2".
The adjudication's table (1-based lines 62-63 of the report; line 61 = M0) gives
M1 = rank 1 and M2 = rank 1. Citation error, no effect on the executed protocol.

## Scope split
The adjudication's M2 spec (report line 63, wording reproduced incl. source bold):
> | M2  | **Missing: dispatcher counters at b1** (misses, accesses, H2D bytes per token
> at 0.50 and 0.65, read outside the timed region) | rank 1 ...

and line 131: exp791 ratios 0.75/0.90 "rerun inside M2 with the cudaMalloc hook and
counters".

- **M2a** (frozen in FREEZE-828.json, unit exp828-m2): profiler attribution arm at
  0.50 only. Original launch sha `5d032454f165b7e2` (aborted: quiet gate hard-fail);
  after FREEZE-828.json correction 1 (gate retry + settle, commit 207e916) the deployed
  and running sha is `6fa34f6024f612ee` — where does engine b1 step
  time go (expert GEMM vs dispatch/memcpy/wait). Valid as executed; a strict subset of
  the adjudication's M2.
- **M2b** (NEW, separate prereg + freeze before its run): dispatcher counters at b1 —
  misses, accesses, H2D bytes per token — at device_memory_ratio 0.50 AND 0.65, counters
  read OUTSIDE the timed region; plus the exp791 0.75/0.90 rerun with cudaMalloc hook
  and counters. Answer's §2's tension directly (exp821 saw 0.50→0.65 move walls only
  1.2-2.2 ms/tok — why, if per-token H2D is tens of MB?).

## M2a decision rule unchanged
The 60% attribution rule from PREREG-M2.md applies to M2a results as written.

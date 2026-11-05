# exp717 PREREG — realizable LCNU/S3-FIFO arbiter (FOLLOW) on 3 full real decode traces

Frozen before the full run. Smoke (SMOKE=1, 65536-access prefixes, 2 caps per trace) only exercised the code; no smoke number enters a bar.

## Why
exp715 (ADDENDUM58): the shipped default LCNU is within 0.5pp of the best of 13 policies in only 17/27 cells.
It loses to S3-FIFO in a contiguous upper-capacity tail of every trace, and best-of{LCNU,S3-FIFO} == best-of-13 in 27/27.
Static normalizers don't line up: the first-loss ratio is 0.71x distinct on granite vs 0.20-0.25x on qwen30b.
The sealed CostFit arbiter (exp667, policies_costfit.py sha 3121d056) picks between the two online, but it credits hits
to whichever full-capacity inner is chosen. That is an optimistic bound: two resident sets and a switch that migrates instantly.

FOLLOW (follow.py) is the realizable version: ONE real set of C slots. CostFit runs unmodified as metadata-only ghosts,
and a real miss evicts a resident key that the current leader ghost does not hold. Migration is lazy and demand-only.

## Inputs (pinned)
- Traces/caps/geometry: common.py == exp715 common.py (sha 802c5093), i.e. the sealed exp704 streams and grids.
- Upstream simulator ref/ == exp715 ref/ (UPSTREAM_SHA), policies.py sha 4439f698, policies_costfit.py sha 3121d056 (unmodified).
- Comparators: exp715-engineparity.json (published 023617d) per-cell C++ hit counts for all 13 policies.
- WS20 sealed (exp707): granite 1228, hi 3396, lo 4662.

## Bars
- **P0 validity (all required, else verdict INVALID):** ghost LCNU hits == exp715 lcnu and ghost S3-FIFO hits == exp715 s3fifo in 27/27 cells.
  Also: fallbacks == 0 in 27/27, the D invariant holds (asserted every 65536 accesses and at the end), recomputed distinct/WS20 == sealed values,
  and a rerun of cap index 4 on each trace is bit-identical.
- **F1 headline:** FOLLOW within 0.5pp of best-of-13 in >=25/27 cells (the LCNU default scored 17/27).
- **F2 no regression:** FOLLOW >= LCNU - 0.25pp in 27/27 cells.
- **F3 realizability cost:** FOLLOW >= CostFit(credited) - 0.5pp in 27/27 cells.
- **S static leave-one-trace-out**, for each normalizer n in {distinct, ws20}, with the threshold set on the two training traces:
  - Per trace, the crossover ratio = sqrt(c_last * c_first) / n, where c_first is the first cap with s3fifo > lcnu and c_last is the cap before it.
  - Threshold x = the geometric mean of the training traces' ratios. Rule: S3-FIFO if cap/n >= x, else LCNU.
  - PASS if held-out regret vs best-of-13 is <= 0.5pp in >=25/27 held-out cells.

Verdict = INVALID | FOLLOW-SHIPPABLE (F1&F2&F3) | FOLLOW-SAFE (F2&F3, not F1) | FOLLOW-REFUTED, plus STATIC-distinct:PASS/FAIL, STATIC-ws20:PASS/FAIL.

## Prior (recorded before run)
- F1/F2 likely pass: CostFit tracked best-of-two within ~0.1pp in exp667 on synthetic traffic.
- Smoke hi@2048 FOLLOW 58526 vs CostFit 58507, so lazy migration can even beat the credited bound.
- Both static rules expected to FAIL: the crossover ratios disagree by ~3x.

## Scope / disclosure
Simulation only. Overhead is descriptive (Python wall time; engine C++ cost would be ~2 policy updates per access plus set ops, i.e. roughly 2-3x LCNU's <=685 ns).
Ghost metadata is keys only. No latency claim. Real-engine measurement is exp716 on Winnie.

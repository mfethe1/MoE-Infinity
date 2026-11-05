# ADDENDUM59 — exp717: a realizable LCNU/S3-FIFO arbiter (FOLLOW) on 3 full real decode traces

**Verdict (PREREG frozen at c738bed): `FOLLOW-SHIPPABLE|STATIC-distinct:FAIL|STATIC-ws20:FAIL`**

exp715 showed the shipped LCNU default within 0.5pp of the best of 13 policies in only 17/27 cells; S3-FIFO wins the
upper capacity tail. FOLLOW keeps ONE real set of C expert slots, runs the sealed CostFit control law over metadata-only
LCNU and S3-FIFO ghosts, and on a miss evicts a resident expert the current leader ghost does not hold (lazy, demand-only migration).

## Bars
- **P0 validity: PASS.** Ghost LCNU / S3-FIFO hits == exp715 C++ hits 27/27 each; 0 fallbacks; D-invariant asserted every 65536 accesses;
  distinct/WS20 recomputed == sealed; 3 reruns bit-identical.
- **F1 within 0.5pp of best-of-13: 27/27 (PASS; LCNU default 17/27).** Worst FOLLOW gap 0.191pp at lo@2048.
  FOLLOW *exceeds* the best single shipped policy in 10/27 cells (max +0.479pp at lo@1152):
  the lazily migrated set is a hybrid of the two ghosts, not a copy of either. This is descriptive, not a pre-registered bar.
- **F2 never worse than LCNU by >0.25pp: PASS.** Worst FOLLOW-LCNU -0.099pp at lo@1024; best +3.076pp at lo@2048.
- **F3 realizability cost vs optimistic CostFit >= -0.5pp: PASS.** FOLLOW-CostFit min -0.020 / median +0.000 / max +0.127pp.
- **Static leave-one-trace-out rules:**
  - distinct: crossover ratios {'granite': 0.657, 'hi': 0.238, 'lo': 0.186}, held-out thresholds {'granite': 0.21, 'hi': 0.35, 'lo': 0.396}, within 0.5pp 15/27, worst 9.25pp -> FAIL
  - ws20: crossover ratios {'granite': 0.676, 'hi': 0.358, 'lo': 0.233}, held-out thresholds {'granite': 0.289, 'hi': 0.397, 'lo': 0.491}, within 0.5pp 17/27, worst 9.25pp -> FAIL

## Per cell (pp; best = best of 13 shipped policies, exp715)
| trace@cap | best-FOLLOW | best-LCNU | FOLLOW-LCNU | FOLLOW-CostFit | switches | mean lag |D| |
|---|---|---|---|---|---|---|
| granite@128 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| granite@192 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| granite@256 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| granite@384 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| granite@512 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| granite@640 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| granite@768 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| granite@896 | -0.084 | 0.022 | +0.106 | -0.000 | 1 | 0.2 |
| granite@1024 | 0.111 | 0.235 | +0.124 | +0.001 | 1 | 0.4 |
| hi@768 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| hi@896 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| hi@1024 | -0.040 | 0.000 | +0.040 | +0.127 | 2 | 3.6 |
| hi@1152 | -0.323 | 0.000 | +0.323 | -0.000 | 3 | 0.4 |
| hi@1280 | -0.394 | 0.797 | +1.191 | -0.007 | 1 | 0.5 |
| hi@1408 | -0.240 | 1.411 | +1.650 | -0.004 | 1 | 1.0 |
| hi@1536 | 0.001 | 1.790 | +1.789 | -0.015 | 3 | 2.3 |
| hi@1792 | 0.056 | 1.828 | +1.772 | -0.011 | 3 | 2.8 |
| hi@2048 | 0.009 | 1.727 | +1.718 | +0.006 | 1 | 0.7 |
| lo@768 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| lo@896 | 0.000 | 0.000 | +0.000 | +0.000 | 0 | 0.0 |
| lo@1024 | 0.099 | 0.000 | -0.099 | +0.127 | 4 | 7.0 |
| lo@1152 | -0.479 | 0.068 | +0.547 | -0.012 | 3 | 0.6 |
| lo@1280 | -0.325 | 1.138 | +1.463 | -0.020 | 3 | 1.3 |
| lo@1408 | -0.340 | 1.794 | +2.134 | -0.010 | 1 | 0.8 |
| lo@1536 | -0.206 | 2.316 | +2.523 | -0.008 | 1 | 0.6 |
| lo@1792 | -0.058 | 2.942 | +3.001 | -0.005 | 1 | 1.1 |
| lo@2048 | 0.191 | 3.267 | +3.076 | +0.002 | 3 | 5.7 |

## Independent cross-check
xcheck_brute.py re-implements the real-set bookkeeping by brute force: it recomputes R minus the leader every step and orders victims by explicit timestamps.
It matched FOLLOW's hits and switches on 6 runs (xcheck.log), 3 of them full streams.
The first version mismatched granite@1024 by 6 hits. The cause was the brute's same-step tie order, not FOLLOW: two keys left the leader in the same step and were ordered differently.
Tie-breaking was fixed to the ghost eviction order, and all 6 runs then match.

## Scope
Simulation of the decode stream only. Python wall time per access is not an engine cost; in C++ FOLLOW costs two policy updates plus O(1) set ops per access.
Ghost metadata is keys only (no expert weights). Real-engine measurement: exp716 on Winnie.

## Provenance
- result exp717-follow.json sha256 da9268203f8043fa51c4d786ab7982d875028383e500df3b5e8b11bcf40a0ae7; frozen ARTIFACT.sha256 (== c738bed):
```
bbee447d1276893ef403c3211a175b960f6deea787d60a4534413071c75bfff2  PREREG.md
eb7e5272ad05b4c38c80ee656c9b944ce6de424a08b2ed1b95100bbea9f4819d  follow.py
9bd6a50d37efdd40b309abfc2067a627130bd26a7f9b3910dc4b2069509d40bd  run_follow.py
802c509399786c3776354b5a8f4fe8789c594bbedff715c055b7bb651c766b34  common.py
4439f698df398742b6237f9c5f91006779aa844b4504c73b3c2e0094ab52f337  ref/benchmarks/cache_simulator/policies.py
3121d056d855ceb751dc02a12bf432dda421a12da7ca8e2f73a928456654167f  ref/benchmarks/cache_simulator/research/policies_costfit.py
```
- gen_addendum59.py recomputes all bars from raw cells; 116 checks PASS; runner wall 67s.

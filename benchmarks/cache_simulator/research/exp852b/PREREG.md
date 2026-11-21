# exp852b PREREG — shared-state N-way metadata PAYOFF on a busy host: paired, interleaved, fresh-process CPU-time cost of shared metadata views (successor of exp852; exp718 H3')

Status: R3 — Jean's method/code review (stack1001-exp852b-method-code-review-20261121-JEAN.md) with Cable's
cross-family leg (stack1001-exp852b-method-code-review-20261121-CABLE.md) folded by Jean: PASS WITH
CHANGES, 6 binding items, all folded here (section "Review fold" at the end). Frozen only
after Jean's PASS on the frozen shas, a clean post-review smoke and ARTIFACT.sha256 (PREREG.md,
run_paired.py, smoke.log, sealed_deps.sha256). No real run before freeze.

## Why a successor, not a relaunch
exp852 (PREREG sha ad62acf77018265d…, runner ea7b65b3e9e02616…) waited for quiet windows
(loadavg(1) < 1.5 at group start, < 2.5 at end). Mack never reached them: exp852 run.log has 540
loadavg samples, min 2.94, median 6.68, p90 15.78, zero below 1.5 or 2.5. exp718 got 0/8 quiet groups
for the same reason. Relaunching the frozen design would settle ECONOMICS-TIME-UNMEASURED again after
~24 h. exp852 was also killed by a peer lane after 10.5 h (2 of 8 groups measured, both unquiet,
nothing persisted because results were written only at the end). exp852 stays sealed and untouched;
it is retired as SUPERSEDED-BY-exp852b (receipt in STACK-1001-79990/receipts/).

## Question (H3', unchanged)
What does the shared metadata view cost in replay time versus the per-key base, for the N=3 family
(costfit3 -> shared_costfit3; R3, decision family) and the N=2 family (costfit -> shared_costfit; R2,
reported)? Ladder thresholds unchanged: <= 1.10 PAYOFF-CONFIRMED, <= 1.35 PAYOFF-MARGINAL, > 1.35
PAYOFF-REJECTED.

Prior (informational only, not a result): exp718 unquiet per-group point ratios (single median-of-5
per arm, arms run sequentially, loadavg 3.8-6.2) were R3 1.245-1.569 and R2 1.085-1.613
(exp718-econ.json pass2_groups, 7 of 8 groups). These are confounded by load drift between arms;
exp852b is designed to remove that confound.

## Design
- Streams, policies, caps, groups: identical to exp852 (qwen30b and granite full streams, cache-on;
  costfit, costfit3, shared_costfit, shared_costfit3; caps 256, 1024, 4096, 262144; 8 groups in
  frozen order qwen30b x caps, then granite x caps).
- Blocks: per group K blocks, K fixed BEFORE freeze by the pilot rule: smoke S13 runs a 6-block
  pilot of granite|256 (full stream, E-cores); if its sd of log R3 (cpu) > 0.12 then K = 20, else
  K = 12; the smoke fails if the runner's K differs from the rule. Pilot rows are smoke, never a
  result. Each block runs 5 timed arms, each in its OWN fresh interpreter
  (`python -I run_paired.py --worker ...`), strictly one at a time: the 4 policies plus an A/A
  control arm `costfit3_AA` (a second independent costfit3 process). Arm order within a block is a
  seeded permutation, `random.Random(f"852002|{group}|{block}")` — deterministic, independent of
  resume position, and different across blocks (counterbalances position/drift effects).
- Timing window (same as sealed CEN._measure): stream loaded and policy built BEFORE the clock; the
  window wraps `CEN._replay(fresh_policy, accesses)` only (sealed function, unmodified).
- Core type fixed (B2): every timed worker is launched as `/usr/sbin/taskpolicy -b python -I ...`
  (background QoS => E-cores only on Apple Silicon; Mack = 4 P + 6 E). Verified on Mack before
  freeze with proc_pid_rusage(RUSAGE_INFO_V6): a normal process ran 91% of its CPU time on P-cores,
  the same code under `taskpolicy -b` 0% (all time accounted as background QoS). Each timed row
  records the V6 P-core share; V4 below gates it. Consequence: absolute times are E-core times
  (~2.4x fewer instructions/s than P in the probe); only ratios are decision-grade.
- Metrics per timed row: PRIMARY `cpu_s` = getrusage(RUSAGE_SELF) (ru_utime + ru_stime) delta over
  the window; SECONDARY `wall_s` = perf_counter delta over the same window. Also recorded:
  thread_time delta and cpu_s − thread_cpu_s, involuntary/voluntary context switches, maxrss,
  loadavg at start/end, pid, UTC; from rusage V6: P-core share, background-QoS share,
  instructions, cycles, runnable time.
- Paired statistic per group and family: l_k = ln(t_shared,k / t_base,k) over the K blocks;
  G = exp(mean l); one-sided upper bound U95 = exp(mean + t(0.95, K-1)·se); one-sided lower bound for
  rejection L = exp(mean − t(1 − 0.05/8, K-1)·se) (Bonferroni over 8 groups); se = sd/sqrt(K).
  t quantiles computed in-runner (regularized incomplete beta; smoke S8 checks published values).
- Concurrency: the runner parent is idle while one worker runs; never more than 2 processes of this
  experiment on Mack (charter rule: Mack at most 2 workers). Host load from other lanes is NOT gated;
  it is recorded (loadavg per row) and is the busy-host condition this design is built for.
- Wall budget 30 h per attempt (E-core workers), re-timed from the S13 pilot (see delta 9). Smoke S13b
  projects the full run from the pilot's s/block, scaled per stream by access count and per-access CPU
  (S2 rows), and fails unless the projection is <= 0.85 x budget. Worker timeout 1800 s; one retry of a
  failed worker process, recorded (`worker_attempt`).

## Validity anchors (correctness gates)
- V0 SEALED: the 13 files in sealed_deps.sha256 (byte-identical copy of exp852's, sha c2fd75e4…)
  re-hashed at run start and end; runner refuses to start unless ALL 4 frozen files (PREREG.md,
  run_paired.py, smoke.log, sealed_deps.sha256; names normalized) match ARTIFACT.sha256 (Cable B3);
  the frozen shas are recorded in the result (artifact_sha256).
- V1 PER-GROUP ANCHORS: (a) full-state parity_pair per family at the group cap on the full stream
  (hits, misses, hit_rate, switches, choice_switches, choice, _mass, _sw_mass, resident order);
  (b) one sealed CEN._measure row per policy (fresh spawned process, repeats=1): tables accounting
  (costfit 5 / costfit3 10 / shared 1), base-vs-shared hit_rate equal, byte fields for drift/ceiling.
- V2 ANCHOR CONSISTENCY: every timed row's hit_rate and accesses equal its policy's V1 row exactly,
  and (hits, misses, hit_rate, accesses) are identical across all blocks for the same policy
  (including costfit3_AA vs costfit3). Base-vs-shared equality is part of V2 (Cable B1): the V1
  family hit_rates must be equal and the timed (hits, misses, hit_rate, accesses) of base and shared
  must be equal; a mismatch is PARITY-FAIL (rung 1), never masked by INCOMPLETE-BUDGET.
- V3 PARITY SMOKE: sealed CEN.parity_smoke() at run start.
- V4 CORE POLICY (B2): every timed row has a V6 P-core share <= 0.01 (none missing).

## Drift and ceiling gates (exp718/exp852 rungs, formulas unchanged)
Stage-A anchors re-parsed at runtime from research/census_exp675-{stream}.csv. struct_ratio within
0.05 relative, terminal within 0.10 at overlap caps 256/1024/4096; ceiling: struct_ratio(262144) <=
1.05 x struct_ratio(4096) per family and stream. Inputs: V1 rows.

## Verdict ladder (first hit wins; primary metric cpu_s, decision family R3)
1. PARITY-FAIL: V3 false, any V1 parity inequality, or any V2 mismatch.
2. INCOMPLETE-BUDGET: wall budget exceeded, a group with fewer than 12 complete blocks, or no stats.
3. ACCOUNTING-FAIL: V1 tables accounting wrong or V1 base-vs-shared hit_rate differs.
3b. CORE-POLICY-FAIL: V4 fails (a timed row ran with P-core share > 0.01, or V6 data missing).
4. ECONOMICS-DRIFT. 5. CEILING-DRIFT.
6. NOISE-FLOOR-FAIL (Jean B1 + Cable B4): in any group, the A/A (costfit3_AA / costfit3) two-sided
   Bonferroni interval [exp(m − t(1−0.05/8)·se), exp(m + t(1−0.05/8)·se)] lies WHOLLY outside
   [1/1.05, 1.05] (systematic bias the pairing did not remove), OR the A/A sd of log ratios exceeds
   0.15 (precision floor). No point-estimate test on the A/A gmean. A point-estimate band
   was rejected in review: at sd_log 0.10, K=12 pure noise would fail it ~50% of the time over 8 groups.
7. PAYOFF-CONFIRMED: max over the 8 groups of U95(R3) <= 1.10.
8. PAYOFF-MARGINAL: max over groups of U95(R3) <= 1.35.
9. PAYOFF-REJECTED: max over groups of L(R3) > 1.35.
10. PAYOFF-INCONCLUSIVE: otherwise (some group's interval straddles 1.35).
FINAL VERDICT (Cable B5): the cpu ladder above, except that a CONFIDENT contradiction with the wall
ladder (cpu CONFIRMED/MARGINAL while wall REJECTED, or cpu REJECTED while wall CONFIRMED/MARGINAL)
settles PAYOFF-INCONCLUSIVE. Rationale: CPU time does not charge arm-dependent kernel work (e.g.
memory compression) to the process. Any other cpu/wall disagreement is reported only.
Rungs 7-8 are intersection-union claims ("every cap is within the bound") so per-group 95% one-sided
bounds need no multiplicity correction; rung 9 is a union claim ("some cap exceeds") so it uses the
Bonferroni bound.

Secondary, reported, never the verdict: the same ladder for R3 on wall_s, for R2 on cpu_s and wall_s;
the exp852-style point ratio (max over groups of median(shared)/median(base)); per-group loadavg
summary; a CPU-vs-wall disagreement is reported, not adjudicated. Diagnostics per group (reported,
never gated): mean arm position and A/A ratio split by which costfit3 ran first (N2); correlation of
log R3 with the shared-minus-base loadavg difference (N4); instruction and cycle ratios from V6;
max cpu_s − thread_cpu_s.

## Deltas from exp852 (every one disclosed)
1. Quiet gate removed (unreachable on Mack); replaced by within-block pairing of fresh processes and
   load recorded per row. Consequence: absolute ns/access is a busy-host number; only the paired
   RATIO is decision-grade.
2. Verdict statistic: exp852 used max over quiet groups of median-of-5 ratio (point estimate, quiet
   groups >= 6 of 8). exp852b uses per-group paired geometric means with one-sided t bounds over 12
   blocks, all 8 groups required; adds PAYOFF-INCONCLUSIVE and NOISE-FLOOR-FAIL rungs; removes the
   ECONOMICS-TIME-UNMEASURED rung (no quiet requirement).
3. Primary metric CPU time (getrusage user+sys) instead of perf_counter wall time; wall is kept as a
   secondary ladder. Rationale: on a shared host, wall time includes descheduled time from other
   lanes; CPU time removes most of it (cache/memory contention remains and hits both arms of a pair).
4. Timed rows come from a fresh-interpreter worker that calls the same sealed build_policy +
   CEN._replay with the same timing window, one replay per process, instead of CEN._measure with
   repeats=5 in one process (which also performs an untimed tracemalloc replay first). No warm-up
   replay in the worker, same for every arm. V1 structural rows still use CEN._measure unchanged.
5. Cross-pass peak/terminal-bytes jitter check (exp852 V2, PASS_JITTER 0.01) dropped: timed workers
   do not run tracemalloc. V2 keeps the exact hit_rate/accesses/hits/misses checks.
6. A/A control arm added (costfit3 twice per block).
7. Persistence: every timed row is appended to rows.jsonl with fsync as it completes; each finished
   group is appended to groups.jsonl; status.json after each group; final result exp852b-paired.json.
8. Resume: at most ONE resume (`--resume`) of an interrupted run, counted from attempts.jsonl, which
   each attempt writes FIRST (B3: an attempt that dies before its first row still counts); groups already complete under the
   same PREREG sha are kept, partial groups are re-measured from block 0 under the new attempt id;
   rows of the interrupted attempt stay in rows.jsonl (attempt-tagged, excluded). Disclosed in result.
9. Budget 30 h per attempt (exp852: 24 h with 3 h/group quiet waits; exp852b draft: 16 h). Re-timed
   after the post-review smoke r4 (2026-11-21, all 17 checks true, log kept as
   smoke-r4-budget-retime.log): pilot granite|256 459 s/block on E-cores; qwen30b has 1,424,640 vs
   638,208 accesses and 1.23x the per-access CPU, so ~1,257 s/block; projected 12 x 4 x (459 + 1,257) s
   ~= 22.9 h, over the 16 h budget (qwen30b runs first, so granite would never be measured). Only the
   budget constant and the S13b projection check changed; the design, K rule and ladder did not.
10. Timed workers pinned to E-cores via `taskpolicy -b` (B2); V4 gate and CORE-POLICY-FAIL rung added.
11. On a crash the runner writes an INCOMPLETE-BUDGET result with the error before exiting (N3).

## Scope limit (stated before the result)
Estimand: the COLD-PROCESS ratio — one replay per fresh interpreter, no warm-up, E-cores, busy host.
exp718/exp852 measured warm medians (repeats in one process after an untimed tracemalloc replay).
The two estimands can differ; exp852b does not claim the warm ratio.
This measures a pure-Python cache simulator (~2-26 µs per access). A ratio here is evidence about the
data-structure cost of the shared view in this implementation, not about a compiled engine. A
PAYOFF-REJECTED here does not prove a C/C++ shared table would cost >35%; a PAYOFF-CONFIRMED is a
stronger statement (no material cost even where interpretive overhead amplifies extra indirection).

## What each outcome changes
- PAYOFF-CONFIRMED: adopt shared metadata views in the expert-cache policy (memory saving struct
  x0.34-0.57 at N=3 per exp675a/exp718, no measured time cost).
- PAYOFF-MARGINAL: adopt only where metadata memory binds (N=3, large key counts); bounded time cost
  (<= 35%) recorded as a known trade.
- PAYOFF-REJECTED: drop shared views from time-critical paths in the Python policy; keep the memory
  finding; any further time claim needs a compiled implementation.
- PAYOFF-INCONCLUSIVE / NOISE-FLOOR-FAIL: the busy-host pairing could not resolve the 1.35 boundary;
  the H3' question is closed as not resolvable on shared hardware at this cost; no policy change.

## Provenance
- Host/interpreter: Mack (M4, 10 cores, macOS 15.6), exp650 venv
  (~/warp-work/exp650-moei-granite3b-trace-pr/.venv, py 3.14.8, torch 2.15.0) — same as exp718/exp852.
  Cost $0, local CPU only; no GPU, no network.
- Lineage shas are re-computed at runtime into the result (exp852 PREREG/runner/ADJUDICATION,
  exp718 PREREG and result).
- Owner: Beast (research lead), board row 509 (li-exp852-rerun-20261120); authorization Michael in
  chat 2026-11-20 ~19:35 ET (fresh exp852 attempt, $0 local). Registry: running.json entry
  exp852b-moei-shared-payoff-paired at launch; result file exp852b-paired.json.

## Review fold (Jean, PASS WITH CHANGES, stack1001-exp852b-method-code-review-20261121-JEAN.md)
- B1 A/A gate on the Bonferroni interval, not the point -> ladder rung 6 (run_paired.py aa_interval_ok).
- B2 core-type invariance -> `taskpolicy -b` for every timed worker, V6 P-share per row, V4 gate,
  rung 3b, cpu_s − thread_cpu_s recorded. Option chosen: E-only (Jean's recommendation); budget
  re-timed by the S13 pilot.
- B3 attempts counted from attempts.jsonl, written first.
- N1 S8b checks t(0.99375, 11) by independent Simpson integration. N2 position report (no Williams
  design: 5 arms need 10-sequence Williams squares, K is 12 or 20; seeded random order kept, position
  reported). N3 crash writes an INCOMPLETE result. N4 load-difference diagnostic. N5 running.json
  registration at launch.
- K adequacy: the pilot rule above (Jean: raise K if sd_log > 0.12).
- Cable cross-family leg (Gemini, folded by Jean into the same review file, 6 binding items total):
  (1) A/A gate = Bonferroni interval wholly outside band OR sd_log(AA) > 0.15 (rung 6);
  (2) core type pinned (above); (3) attempts from attempts.jsonl + S12 now tests the resume filter
  (complete + same prereg sha) and the attempt limit; (4) base-vs-shared equality moved into V2 /
  PARITY-FAIL (S14 tests it); (5) freeze check covers all 4 artifact files, artifact_sha256 recorded;
  (6) confident cpu/wall contradiction -> PAYOFF-INCONCLUSIVE (S8d tests it). Smoke coverage of the
  new ladder cases: S6 (rungs incl. CORE-POLICY-FAIL), S8c (A/A gate incl. sd cap and boundaries),
  S8d (contradiction combiner).

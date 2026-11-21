# ADJUDICATION — exp852b-moei-shared-payoff-paired — 2026-11-21

Controller lane STACK-1001/79990 follow-up fire (monitor change 2026-11-21T12:45Z).
Monitor labeled this experiment CRASHED; ground truth from run.log tail is a clean
finish (`wrote exp852b-paired.json`, `settled verdict=PAYOFF-REJECTED`, `RUN_EXIT=0`,
all 8 groups complete at 2026-11-21T12:41:57Z). False-CRASHED label (pid-liveness
detector), same class as the exp702 precedent.

## Freeze integrity (V0) — verified, not trusted
- ARTIFACT.sha256 re-hashed live and matched for all four frozen files:
  PREREG.md e2ab0c5305e638df…, run_paired.py b846a7151016e929…, smoke.log
  ce9b41bef6448336…, sealed_deps.sha256 c2fd75e4a8c63f01….
- Result JSON `artifact_sha256` block equals the live ARTIFACT.sha256 file hash;
  `rows_jsonl_sha256` equals the live rows.jsonl hash; `sealed_post_ok` true;
  exactly one attempt (a1-2026-11-21T03:11:25Z) in attempts.jsonl — the single
  permitted resume was never consumed.

## Independent recomputation (no hand math)
Python adjudicator (kept at publication: research/exp852b/, plus exp852b-adjudication.json)
recomputed from raw rows.jsonl (480 rows = 8 groups x 5 arms x 12 blocks, all one attempt):
- V2 counters identical across blocks per (group,arm); base vs shared equality for R2, R3;
  costfit3_AA counters identical to costfit3 — 24/24 equality checks.
- V4: 0 missing V6 rows; max P-core share 5.56e-05 (gate <= 0.01).
- t quantiles re-derived via regularized incomplete beta: t(0.95,11)=1.7958848187,
  t(0.99375,11)=2.9808724301 — equal to the runner's.
- All 240 paired statistics (8 groups x {R3,R2,AA} x {cpu_s,wall_s} x 5 quantities)
  recomputed and equal to the stored values within 1e-9.

## Ladder walk (frozen PREREG, first hit wins; primary cpu_s, decision family R3)
- Rung 1 PARITY-FAIL: no (V3 parity_smoke true; V1 parity_ok 8/8, pairs equal, no
  diff_fields; V2 recompute clean).
- Rung 2 INCOMPLETE-BUDGET: no (complete=true, budget_exceeded=false, 12/12 blocks
  per group, wall 34232 s of the 30 h/attempt budget).
- Rung 3 / 3b ACCOUNTING / CORE-POLICY: no (accounting_ok 8/8; core_ok 8/8).
- Rungs 4-5 DRIFT: no (drift_fail=[], ceiling_fail=[]).
- Rung 6 NOISE-FLOOR-FAIL (cpu): no — every A/A cpu interval inside [1/1.05,1.05]
  (max upper_bonf 1.0824), max A/A sd_log 0.0889 <= 0.15.
- Rungs 7/8: no — max_g U95(R3,cpu) = 1.5739 (granite|4096) > 1.35.
- Rung 9 PAYOFF-REJECTED: YES — max_g Lbonf(R3,cpu) = 1.46259 > 1.35
  (granite|4096 Lbonf 1.4626; granite|262144 1.4562).
- Wall ladder (secondary, reported only): NOISE-FLOOR-FAIL (A/A wall sd_log 0.3177
  qwen30b|256, 0.1837 qwen30b|262144, 0.1763 granite|1024 > 0.15) — wall ratios are
  not decision-grade on this busy host, disclosed per PREREG.
- FINAL (Cable B5): no confident cpu/wall contradiction (wall not
  CONFIRMED/MARGINAL) -> **PAYOFF-REJECTED**, equal to the runner's settled verdict.

Checks: 94 total, 0 failed.

## Pre-registered consequence (PREREG "What each outcome changes", REJECTED branch)
Drop shared metadata views from time-critical paths in the Python policy; keep the
memory finding (exp675a/exp718); any further time claim needs a compiled
implementation. Consistent with, and now paired-design-confirmed under a busy host:
exp723 REJECTED (x1.6059 point), adopted lineage exp729 FusedCostFit3
(PAYOFF-CONFIRMED + SAVING) and exp732 FusedCostFit (CONFIRMED speed, no saving).
exp852 stays sealed/SUPERSEDED (crash-2, recovery consumed, no verdict, no relaunch).

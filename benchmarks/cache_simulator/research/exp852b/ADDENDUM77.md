# ADDENDUM77 — exp852b: shared metadata views, paired fresh-process payoff (E-core CPU-time) — PAYOFF-REJECTED

Successor of exp852 (sealed, crash-2, superseded — no verdict, no relaunch). Question H3'
(frozen PREREG sha e2ab0c5305e638df…): does a shared metadata-view policy
(shared_costfit3 / shared_costfit) hold shared-state CPU-time cost under 35%
(G_ci <= 1.35) on a busy general-purpose host, measured as paired interleaved
fresh-process CPU time on efficiency cores?

## Design (as frozen)
5 arms x K=12 blocks per group, paired by block index within one attempt (a1-2026-11-21T03:11:25Z,
single process per measurement, taskpolicy E-core pinning): costfit, costfit3,
costfit3_AA (A/A control arm), shared_costfit, shared_costfit3. 8 groups
(qwen30b and granite3b at caps 256/1024/4096/262144). Host macOS-15.6-arm64-arm-64bit-Mach-O,
Python 3.14.8, torch 2.15.0. Elapsed
9.51 h of the 30 h/attempt budget. Load recorded not gated:
recorded per group in exp852b-paired.json (groups[].loadavg_rows), not gated.

## Verdict ladder (first hit wins; primary cpu_s, decision family R3)
- V0 freeze: PREREG/run_paired/smoke/sealed_deps shas match ARTIFACT.sha256 (recomputed).
- V1 parity (V3 traces identical), V2 counters (base vs shared equal, AA==costfit3),
  V3 accounting, V4 core policy (max P-core share 5.56e-05 <= 0.01): all pass.
- Rungs 4-5: drift_fail=[] ceiling_fail=[].
- Rung 6 (cpu): A/A gate clean — max A/A sd_log 0.0889 <= 0.15, max A/A
  upper_bonf 1.0824 (every interval meets [1/1.05, 1.05]).
- Rung 7/8: no — max_g U95(R3,cpu) = 1.57390 > 1.35.
- **Rung 9: PAYOFF-REJECTED — max_g L_bonf(R3,cpu) = 1.46259 > 1.35
  (worst granite|4096).**
- Secondary wall ladder: NOISE-FLOOR-FAIL (A/A wall sd_log > 0.15 in 3 groups) —
  wall ratios reported, not decision-grade on this host; no confident cpu/wall
  contradiction (final = cpu ladder, per Cable B5).

## Per-group shared/base ratios (R3 = shared_costfit3/costfit3)
| group | cpu gmean | cpu U95 | cpu L_bonf | wall gmean (sec.) | A/A cpu sd_log |
|---|---|---|---|---|---|
| qwen30b|256 | 1.2143 | 1.2386 | 1.1750 | 1.1407 | 0.0660 |
| qwen30b|1024 | 1.2719 | 1.2996 | 1.2274 | 1.2870 | 0.0251 |
| qwen30b|4096 | 1.3145 | 1.3447 | 1.2657 | 1.3376 | 0.0250 |
| qwen30b|262144 | 1.3423 | 1.4073 | 1.2410 | 1.2746 | 0.0889 |
| granite|256 | 1.3583 | 1.3858 | 1.3138 | 1.4177 | 0.0144 |
| granite|1024 | 1.4494 | 1.5179 | 1.3425 | 1.3863 | 0.0829 |
| granite|4096 | 1.5311 | 1.5739 | 1.4626 | 1.5694 | 0.0363 |
| granite|262144 | 1.5119 | 1.5464 | 1.4562 | 1.4966 | 0.0389 |

R2 (shared_costfit/costfit) cpu: gmean range 1.2346–1.5241,
max U95 1.5687 — same direction, larger spread, consistent with R3.
Point (exp852-style max ratio): cpu shared_costfit 1.5520,
shared_costfit3 1.5212; wall 1.6051 /
1.5346.

## Consequence (pre-registered REJECTED branch)
Drop shared metadata views from time-critical paths in the Python policy; keep the
memory finding (exp675a/exp718); any further time claim needs a compiled
implementation. Lineage: exp723 shared-view REJECTED (point x1.6059), exp729
FusedCostFit3 CONFIRMED + SAVING (adopted), exp732 FusedCostFit CONFIRMED speed.
This paired, A/A-gated run independently confirms the exp723 verdict under a busy
host with block-pairing.

## Provenance
All numbers in this addendum recomputed by gen_addendum77.py from rows.jsonl +
exp852b-paired.json with 263 runtime asserts (0 failed); independent controller
adjudication: exp852b-adjudication.json (94/94 checks) and
ADJUDICATION-20261121-exp852b-payoff-rejected.md. Freeze: PREREG.md
e2ab0c5305e638df16b9af87d4e43d10c7f8f13b7834609b9f45c9612b3bd2e2, run_paired.py b846a7151016e9299b55d0da61a3f2dc06a9e9e1c90287999ea035acb5e73a6c, smoke.log
ce9b41bef6448336…, sealed_deps.sha256 c2fd75e4a8c63f01…,
rows.jsonl eaa4289c2602fc5d62f17e28f87804f1fc019dc67ae8b5165a76c3452dbe8654. Local compute, $0. Attempt a1-2026-11-21T03:11:25Z,
finished 2026-11-21T12:41:57Z.

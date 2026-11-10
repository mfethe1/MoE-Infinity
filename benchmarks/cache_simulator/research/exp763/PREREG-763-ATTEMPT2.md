# PREREG-763 ATTEMPT-2 — count-traffic + interval-coverage diagnosis

Written 2026-11-10T22:4xZ, after attempt-1 was VOIDED (bytes=0 in all dispatch events;
stage durations overlap so shares are not compositional). See VOID-ATTEMPT-1.md.
NOT yet computed on real data at write time: dispatch counts, count ratios, interval
coverage, unattributed time. (Known from attempt-1: per-stage dur sums and shares,
wall times — both preserved in out/verdict.txt attempt-1.)

## Premise (structural, verifiable)
name_id_map.json lists 3072 expert tensors = 16 layers × 64 experts × 3 projections;
MoE experts are homogeneous (identical shapes per projection). Therefore per-expert
weight bytes are constant and:
  traffic ratio (SPEC/LGC) = N_dispatch ratio (EXACT under homogeneity)
  h* (traffic break-even) = 1 − N_LGC/N_SPEC
Limitation: if expert sizes differed per layer, ratios would be approximate (same
prompts and order across arms, so the layer mix is matched; effect negligible).

## Metrics (per cell, from <cell>.io.jsonl + <cell>.json)
- N = count of expert_dispatch events; per-stage counts
- cov_x = UNION coverage seconds of merged intervals [ts_ns, ts_ns+dur_ns] per stage x
  (overlap-aware attribution — fixes attempt-1's non-compositional shares)
- wall = sum(n_new / decode_tok_s) over rows (as attempt-1)
- unattrib = wall − union coverage of ALL stages combined

## Contrasts (SPEC vs LGC, paired by cell index i)
- count_ratio_i = N_SPEC_i / N_LGC_i
- Δcov_sync_i, Δcov_handoff_i, Δunattrib_i (absolute seconds)
Threshold unit: τ_i = 0.05 × wall_LGC_i

## Decision tree (fixed now)
- D1 OVER-FETCH-DOMINATED: med(count_ratio) ≥ 1.15 AND med(Δcov_sync) ≤ med(τ)
  AND med(Δunattrib) ≤ med(τ)
- D2 STALL-DOMINATED: med(Δcov_sync) > med(τ) AND med(count_ratio) < 1.15
  AND med(Δunattrib) ≤ med(τ)
- D3 HANDOFF-DOMINATED: med(Δcov_handoff) > med(τ) AND neither D1 nor D2
  AND med(Δunattrib) ≤ med(τ)
- D4 POLICY-CPU-DOMINATED: med(Δunattrib) > med(τ) AND med(count_ratio) < 1.15
  (regression lives in time not attributed to any traced stage — the prefetch
  policy's own compute/scheduling; feeds exec-path-handoff thread)
- MIXED: med(count_ratio) ≥ 1.15 AND (med(Δcov_sync) > med(τ) OR med(Δunattrib) > med(τ))
- else INCONCLUSIVE
Also reported: OVR-vs-SPEC recovery of each Δ (does overlap shrink sync coverage or
unattributed time?); h* median [min,max].

## Exit codes
0 = DIAGNOSIS-<label>; 3 = INCONCLUSIVE; 4 = DATA-FAIL (missing/malformed);
9 = IDENTIFY-FAIL (io sha mismatch vs IO-TRACES-SHA256.txt).

## Gates
- Identity: recomputed sha of each io.jsonl must match the manifest (as attempt-1).
- Every event stage ∈ 5-stage vocabulary; zero malformed lines.
- Descriptive class (w=0.5): no performance claim; feeds candidate ranking only.

## Freeze
FREEZE-763B.txt records sha256 of this prereg + analyze763b.py BEFORE the run on
Winnie; analyzer immutable after; re-adjudication only via pre-registered settlement
rule + independent review.

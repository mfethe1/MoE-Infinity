# PREREG-763 — I/O-trace diagnosis of the spec-prefetch regression (exp762 follow-up)

Written 2026-11-10T22:1xZ BEFORE any aggregate statistic was computed from the traces.
Known at write time: event schema {ts_ns, stage, layer, expert, dur_ns, bytes}; stage
vocabulary {expert_completion_handoff, expert_dispatch, gpu_route_fallback, routing,
sync_wait}; 12 cells (LGC/SPEC/OVR/ENF × 3, interleaved, identical prompts); per-cell
decode ms/tok exist in out/*.json (exp762 verdict NO-GAIN: LGC 83.64 / SPEC 101.39 /
OVR 91.40 / ENF 93.28 pooled). No per-stage sums, ratios, or contrasts have been
computed or viewed.

## Question
Why does speculative prefetch cost 21.2% (SPEC vs LGC), and under what measurable
condition would a prefetch policy break even? Zero-GPU descriptive study on the
captured exp762 traces (340,800 events, sha-frozen in IO-TRACES-SHA256.txt).

## Metrics (per cell, from <cell>.io.jsonl)
- N_x, D_x = count and total dur_ns of stage x ∈ {dispatch, handoff, sync_wait,
  routing, fallback} (prefix-matched on stage name)
- B = total bytes of expert_dispatch events
- wall = decode wall time from <cell>.json (rows: sum n_new / decode_tok_s)
- shares: sh_x = D_x / wall; bandwidth = B / D_dispatch (GiB/s)

## Contrasts (paired within interleaved cell index i ∈ {1,2,3}, arm A vs arm C)
- bytes_ratio = B_SPEC_i / B_LGC_i (prefetch extra-traffic factor)
- Δsync_i = sh_sync_SPEC_i − sh_sync_LGC_i (added stall share)
- Δhandoff_i = sh_handoff_SPEC_i − sh_handoff_LGC_i
- Δfallback_i = sh_fallback_SPEC_i − sh_fallback_LGC_i

## Break-even derivation (per cell pair, descriptive)
rate_i = (B_SPEC_i − B_LGC_i) / (T_SPEC_i − T_LGC_i)   [GiB/s implied by added traffic per added second]
h*_i = 1 − B_LGC_i / B_SPEC_i  — the fraction of SPEC's expert traffic that must be
USEFUL (not re-fetched / wasted) for SPEC to move no more bytes than LGC. Reported as
median [min,max] over i. This is a traffic break-even, a necessary (not sufficient)
condition for time break-even; stated as such.

## Decision tree (primary cause of the SPEC regression; thresholds fixed now)
- D1 OVER-FETCH-DOMINATED: median bytes_ratio ≥ 1.15 AND median Δsync ≤ 0.05
- D2 STALL-DOMINATED: median Δsync > 0.05 AND median bytes_ratio < 1.15
- D3 HANDOFF-DOMINATED: median Δhandoff > 0.05 AND neither D1 nor D2
- MIXED: D1 and D2 both armed (bytes_ratio ≥ 1.15 AND Δsync > 0.05)
- else INCONCLUSIVE.
Follow-up mapping: D1→prefetch-policy-break-even candidate (policy lever);
D2→scheduling; D3→exec-path-handoff thread; MIXED→policy+scheduling joint.

## Exit codes (frozen analyzer)
0 = DIAGNOSIS-<label> with all contrasts + h* printed; 3 = INCONCLUSIVE (no branch);
4 = DATA-FAIL (missing/malformed cell file or schema mismatch); 9 = IDENTIFY-FAIL
(cell/traces sha mismatch vs IO-TRACES-SHA256.txt).

## Gates
- Identity: every <cell>.io.jsonl sha256 must match IO-TRACES-SHA256.txt (recomputed).
- Completeness: 12 cells × all 5 stages present in vocabulary; zero malformed lines.
- No aggregation shortcut may use exp762's pooled verdicts as inputs — only per-cell
  jsons and io traces.
- Descriptive evidence class (w=0.5 in BELIEFS) — no performance claim, no admission
  of a speedup; output feeds the prefetch-policy-break-even candidate and the
  exec-path thread ranking only.

## Freeze protocol
PREREG sha256 recorded below at launch; analyze763.py sha256 frozen in FREEZE-763.txt
on Winnie BEFORE run; analyzer immutable after; any re-adjudication requires a
pre-registered settlement rule + independent review (exp762 protocol).

# SETTLEMENT-763 — prefetch diagnosis (zero-GPU descriptive on exp762 frozen traces)

Status: DRAFT pending independent review. Date: 2026-11-10T22:5xZ.

## What ran
- Attempt-1: PREREG-763.md (sha a2658ea9…) + analyze763.py (af352ac6…), FREEZE-763.txt on
  Winnie /home/mfeth/exp763. rc=0 but VOID — see VOID-ATTEMPT-1.md: every expert_dispatch
  event carries bytes=0 in this build (traffic uninstrumented) so bytes_ratio=inf armed
  D1 on vacuum; stage-dur shares are non-compositional (durations overlap).
- Attempt-2: PREREG-763-ATTEMPT2.md (sha f6c2714c…) + analyze763b.py (6440dbde…),
  FREEZE-763B.txt written BEFORE the run; prereg written BEFORE any dispatch-count or
  interval-coverage computation. Fixture suite 8/8 PASS (D1/D2/D3/D4/MIX/INC +
  IDENTIFY-FAIL rc9 + DATA-FAIL rc4) on Mack before freeze.
- Identity gate: all 12 io.jsonl sha256 match IO-TRACES-SHA256.txt (the exp762 frozen
  manifest, regenerated in /home/mfeth/exp762/out — byte-identical hashes of the same
  files committed in e3507c7).

## Attempt-2 output (verbatim numbers from out/verdict-attempt2.txt, script-extracted)
- Per-cell: LGC wall 28.50/28.75/27.87 s; SPEC 34.40/35.08/34.05; OVR 31.00/30.80/31.13;
  ENF 31.60/32.94/30.92. N_disp = 5680 in ALL 12 cells (identical).
- CONTRAST SPEC-vs-LGC: count_ratio med=1.000; Δcov_sync=+0.22 s; Δcov_handoff=+0.22 s;
  Δunattrib=+7.82 s (τ=1.42 s).
- h* = 1 − N_LGC/N_SPEC = 0.000 [0.000, 0.000] — ZERO excess expert traffic.
- Dispatch coverage DROPS in SPEC: 4.34→2.45 s/cell (LGC→SPEC) — prefetch warms the
  same reads (demand-dispatch wait shrinks ~1.9 s).
- OVR recovery vs SPEC: Δcov_sync −2.56/−2.34/−2.49 s; Δunattrib −1.23/−2.66/−1.17 s;
  ΔN_disp +0 in all cells.
- VERDICT: DIAGNOSIS-D4-POLICY-CPU-DOMINATED (rc=0).

## Interpretation (descriptive, w=0.5 — no performance claim)
1. OVER-FETCH IS DEAD as the explanation: the spec-prefetch policy issues exactly the
   same 5680 expert dispatches as lazy — zero excess expert-dispatch traffic under
   the homogeneity premise (h*=0; usefulness of individual transfers not assessed).
   Traffic break-even is trivially satisfied; the prefetch-policy-break-even
   candidate's traffic premise is falsified for this implementation.
2. The −21.2% SPEC regression is entirely UNTRACED time: +7.82 s/cell (median;
   7.82/28.50 = 27.4% of median LGC wall) invisible to all five traced io stages.
   Untraced = wall − union(all traced stages). This is consistent with — but does not
   independently demonstrate — the speculation policy's own CPU work (spec head,
   verification, batch reshaping); exp764 (py-spy stack attribution) tests that
   mechanism directly. Prefetch itself HELPS io (dispatch coverage −1.9 s; overlap
   hides sync −2.5 s + untraced time −1.2..−2.7 s vs SPEC).
3. Follow-up ranked by evidence: exec-path-handoff thread (#1, 9.49) now has a
   measured motive — the cost lives in untraced time, not expert traffic.
   prefetch-policy-break-even closes (premise falsified: zero EXCESS expert-dispatch
   traffic under the stated homogeneity premise; usefulness of individual transfers
   was not assessed — that distinction is exp764's to test if it matters).

## Independent review
deleg_59f589be (gpt-6.1-sol, 2026-11-10T23:3xZ, read-only, transcript
~/.hermes/cache/delegation/live/deleg_59f589be/task-0.log): VERDICT FAIL with three
quoted contradictions — ALL VALID, all in this file's prose (verdict itself confirmed):
(1) denominator: "+7.8 s (~23% of LGC wall)" used the SPEC wall; corrected to
7.82/28.50 = 27.4% of LGC wall. (2) mechanism overstated: analyzer measures UNTRACED
time (wall − union), not measured CPU; policy-CPU is a hypothesis exp764 tests —
qualified above. (3) "no wasted traffic" stronger than equal counts; qualified to
"zero excess expert-dispatch traffic under the homogeneity premise". Reviewer
independently re-parsed all 12 rows (N_disp 5680 throughout; unattributed deltas
+6.74/+8.67/+7.82), executed the analyzer's predicates (D1–D3/MIXED False, D4 True),
and confirmed the attempt-1 void reading from the code. Reviewer's own conclusion:
"requires correction, not another gate run." Corrections applied 2026-11-10T23:4xZ;
frozen analyzers/verdicts untouched.

SETTLEMENT FINAL: DIAGNOSIS-D4-POLICY-CPU-DOMINATED — admitted (descriptive, w=0.5),
with mechanism claims qualified as above.

## Chain of custody
- Traces: exp762 out/ (12 io.jsonl, 340,800 events) — sha-gated against the manifest
  committed at e3507c7; raw traces stay on Winnie.
- Verdicts: out/verdict.txt (attempt-1, VOID), out/verdict-attempt2.txt (attempt-2).
- Copied to Mack: FREEZE-763.txt, FREEZE-763B.txt, verdict.txt.attempt1 (33ff8d96…),
  verdict-attempt2.txt.attempt2 (5911e094…).

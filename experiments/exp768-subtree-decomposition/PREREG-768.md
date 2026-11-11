# PREREG-768 — named-subtree decomposition of the spec-prefetch wall cost (native attribution)

**Type:** preregistered re-analysis of exp767's SEALED native stacks. NO new cells.
**Input (sealed, read-only):** `/home/mfeth/exp767/out/NAT_{LGC,SPEC}.pyspy` (py-spy 0.4.3, `record --native -r 100 -f raw`, spawn mode), `SRC_HEAD.txt` (expected `b7f6ca4d2caa…`), `ENV.txt`.
**Analyzer:** `analyze768.py` (this sha recorded in FREEZE-768). Runs with argv1 = sealed exp767 dir, argv2 = exp768 output dir (verdict never written into the sealed dir).

## Question
exp763 measured +7.82 s unprofiled wall cost of spec-prefetch (5 runs, zero excess dispatch traffic). exp764 attributed it to component self-times (+7.53 s spec-prefetch; eager +6.11 s; wait −5.31 s) — but with NON-native stacks. exp767 refuted the headline (+7.53 s → +1.88 s subtree under native). Does the remaining wall cost live in the three NAMED subtrees (speculative_prefetch, _dispatch_eager_local, wait_dispatch_local) under correct native attribution?

## Premise probe (2026-11-11T04:01Z, read-only on the sealed stacks)
- Literals exist and parse: `DistributedExpertExecutor._dispatch_eager_local (moe_infinity/…expert_executor.py:`, `…wait_dispatch_local (…`, `speculative_prefetch (…` ✓ (family-map rule satisfied).
- Subtree sample floors: EAGER ≥ 1792/arm, WAIT ≥ 2265/arm ✓ (floor set at 500/arm).
- Probe magnitudes informed FLOORS only; τ fixed a priori at 2.0 s (same materiality bar as exp767), independent of probe values.

## Frozen decision rule (tau = 2.0 s; thread-seconds at 100 Hz; De/Ds/Dw = SPEC-arm − LGC-arm subtree totals)
- rc=9 IDENTIFY-FAIL: SRC_HEAD ≠ b7f6ca4
- rc=4 DATA-FAIL: missing/empty pyspy files
- rc=3 INCONCLUSIVE: combined samples < 30,000 OR any named subtree < 500 samples in an arm
- rc=1 **D1 EAGER-COST**: De ≥ τ → successor exp769 eager-path restructure (t3 design)
- rc=2 **D2 MIGRATION**: (¬D1) ∧ Ds ≥ τ ∧ Dw ≤ −τ → successor exp769 spec-subtree native repair
- rc=5 **D3 NET-NULL**: |De|, |Ds|, |Dw| all < τ → wall cost invisible to in-process 100 Hz native sampling → successor exp769 **unprofiled OS-counter differential** (page-faults, ctx-switches, per-thread CPU, RSS)
- rc=6 **D4 MIXED**: otherwise → successor exp769 ranked by magnitude

Covariates (reported, no gates): whole-process per-family deltas; total attributed delta. Observation-only: no wall-clock claims vs unprofiled runs; py-spy samples all threads, so "secs" = thread-seconds.

## Fixture battery (fixtures768.py, run pre-freeze on Mack)
Synthetic mini-stacks, hand-computed ground truths: D1, D2, D3, D4, INCONCLUSIVE (floor), IDENTIFY-FAIL, DATA-FAIL → expect rc ∈ {1,2,5,6,3,9,4} in that order. Battery must be all-PASS before freeze.

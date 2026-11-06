# ADDENDUM 65 — exp732: FusedCostFit — exp729's fused per-key record ported to the N=2 CostFit head

Verdict: **PAYOFF-CONFIRMED + NO-SAVING** (frozen ladder rung 5 + economics qualifier). Holding the 5 per-key fields of the N=2 CostFit arbiter (LCNU last/ema/count/first + S3-FIFO freq) in ONE list record per key (FusedCostFit) costs **x0.9681** per-thread CPU time vs the sealed per-key-dict costfit at its WORST cell qwen30b @256 (IQR [0.9639, 0.9734]) — faster at all 8 cells — under a valid A/A null (pooled x0.9954, cells [0.9741, 1.0052]). The economics qualifier FAILS: struct bytes x0.587–x0.951 of costfit, 5/8 cells <= 0.80 (fail: granite|256, granite|262144, granite|4096). 8/8 rounds, 2864s, exit 0, freeze fc36c8c; host loadavg 3.50–6.88 throughout (not gated, disclosed).

Independent follow-up adjudication: **109/109 checks pass** (gen_addendum65.py), re-derived from the 512 raw per-replay ns timings, the exp718 PASS-1 hit-rate oracle parsed here, the 16 round-0 parity/census records, run.log, sealed-dep shas, the freeze commit and an AST byte-compare of the leaf classes against exp729's sealed policies_fused.py, plus a LIVE third-process re-run of the fused2 argmax cell. Re-derived verdict == stored.

## Decision-grade result

- **rung 1**: every timed replay (512/512) reproduced the exp718 PASS-1 costfit hit rate exactly; round-0 terminal FULL STATE of all 16 B arms == sealed costfit; A-arm census == sealed structure_census 16/16. Fused leaf methods are byte-identical to exp729's (AST class-source compare), NSLOT 10 -> 5.
- **A/A null (validity gate)**: pooled x0.9954 (bar [0.97, 1.03]); per-cell medians qwen30b@256 0.9960, qwen30b@1024 0.9920, qwen30b@4096 1.0041, qwen30b@262144 0.9949, granite@256 0.9741, granite@1024 1.0052, granite@4096 0.9931, granite@262144 0.9994. 0/64 individual null units deviated > 10%.
- **Per-thread CPU-time ratio fused2/costfit (median over 8 rounds, [q25, q75]); struct-bytes ratio; C AoS/SoA; exp729 N=3 fused for reference**:
  - qwen30b @256: x0.9681 [0.9639, 0.9734]; struct x0.723; C AoS/SoA x0.793 (keys 5948, S3-occupied 256); exp729 N=3 fused x0.9556, struct x0.461
  - qwen30b @1024: x0.9366 [0.9272, 0.9446]; struct x0.691; C AoS/SoA x0.773 (keys 5948, S3-occupied 1024); exp729 N=3 fused x0.9233, struct x0.440
  - qwen30b @4096: x0.9640 [0.9549, 0.9662]; struct x0.587; C AoS/SoA x0.703 (keys 5948, S3-occupied 4096); exp729 N=3 fused x0.9605, struct x0.374
  - qwen30b @262144: x0.9199 [0.9190, 0.9405]; struct x0.587; C AoS/SoA x0.667 (keys 5948, S3-occupied 5948); exp729 N=3 fused x0.9033, struct x0.374
  - granite @256: x0.9464 [0.9268, 0.9486]; struct x0.951 (> 0.80); C AoS/SoA x0.769 (keys 1262, S3-occupied 256); exp729 N=3 fused x0.9339, struct x0.627
  - granite @1024: x0.9373 [0.9257, 0.9567]; struct x0.713; C AoS/SoA x0.688 (keys 1262, S3-occupied 1024); exp729 N=3 fused x0.9516, struct x0.471
  - granite @4096: x0.9339 [0.9233, 0.9407]; struct x0.856 (> 0.80); C AoS/SoA x0.667 (keys 1262, S3-occupied 1262); exp729 N=3 fused x0.9055, struct x0.564
  - granite @262144: x0.9317 [0.9152, 0.9467]; struct x0.856 (> 0.80); C AoS/SoA x0.667 (keys 1262, S3-occupied 1262); exp729 N=3 fused x0.9185, struct x0.564
- fused2: 64/64 individual ABBA units < 1.0 (max unit x0.9884); cheapest cell x0.9199 @ qwen30b/262144. Per-key tables [5] -> [1].

## N-dependence (descriptive)

- Median CPU saving across the 8 cells: N=2 fused2 6.3% vs N=3 fused (exp729) 7.1% — the speed win survives at N=2 (fewer lookups saved, smaller but still positive).
- Struct economics are N-dependent: at N=3 every cell cleared 0.80 (x0.374–x0.627); at N=2 the fixed per-record list overhead weighs against 5 instead of 10 fields; granite cells sit at x0.713–x0.951, qwen30b at x0.587–x0.723 (cause not isolated here).
- C-level model (frozen formula, a byte ESTIMATE, not a measurement): AoS/SoA x0.667–x0.793. Every seen key is LCNU-metadata-resident (keys == LCNU occupancy at 8/8 cells), so per key SoA pays 40 B (LCNU) + 8 B x S3-occupied fraction (0.043–1.000 here) and AoS pays 32 B, both at load 0.75. AoS < SoA at 8/8 cells.

## Descriptive (non-gating)

- Clock robustness: process_time fused2 worst x0.9681 @ ['qwen30b', 256], null x0.9954; wall fused2 worst x0.9656 @ ['qwen30b', 256], null x0.9919.
- Leave-one-round-out ladder: ['PAYOFF-CONFIRMED'] in 8/8 drops.
- LIVE third-process re-run of qwen30b @256 (one ABBA unit per arm, sealed worker() in round-0 mode, loadavg 4.11→4.29): null x1.0078, fused2 x0.9818; hit rates == oracle 8/8; full-state parity 2/2; fused2 struct ratio == stored.
- Prediction check (PREREG, stated pre-smoke): (a) CONFIRMED with F in [0.90, 1.02] — HELD (F x0.9681); (b) struct in [0.60, 0.90] at all cells, P(SAVING)~0.5 — MISSED (x0.5871–x0.9506; NO-SAVING landed); (c) C AoS/SoA in [0.75, 1.00] — MISSED (x0.6667–x0.7932).

## Consequence (pre-registered branch: CONFIRMED + NO-SAVING)

- Speed only at N=2: the fused record is never slower than the per-field dicts (identical decisions, verified full state), but the Python per-key byte saving misses the 0.80 bar at 3/8 cells. Per PREREG the N=2 layout choice becomes a C-level question decided by the AoS byte model: AoS/SoA x0.667–x0.793 -> AoS recommended for the engine at N=2.
- The AoS figure is the frozen descriptive byte formula applied to measured occupancies — an estimate, not a measured C layout; any engine-side layout claim needs its own measurement.

## Integrity

- PREREG/runner/policies/smoke.log/sealed_deps byte-exact in freeze commit fc36c8c == ARTIFACT.sha256 == disk == running.json registration; freeze precedes the result; 16/16 sealed deps unchanged and recorded in the result JSON; ladder self-test 15/15 ran before measurement; sealed artifacts untouched; nothing re-launched. run.log is force-added (repo .gitignore has *.log) as primary evidence.

## Check list

- [x] ARTIFACT.sha256 lists PREREG, runner, policies, sealed_deps, smoke.log
- [x] artifact sha PREREG.md — c4695858967c
- [x] freeze commit fc36c8c carries PREREG.md byte-exact
- [x] artifact sha run_fused2.py — 1958fe4a836c
- [x] freeze commit fc36c8c carries run_fused2.py byte-exact
- [x] artifact sha policies_fused2.py — f9597ed0138f
- [x] freeze commit fc36c8c carries policies_fused2.py byte-exact
- [x] artifact sha sealed_deps.sha256 — 14cc199753dc
- [x] freeze commit fc36c8c carries sealed_deps.sha256 byte-exact
- [x] artifact sha smoke.log — cfe8bbc65df0
- [x] freeze commit fc36c8c carries smoke.log byte-exact
- [x] published copy PREREG.md == run dir copy
- [x] published copy run_fused2.py == run dir copy
- [x] published copy policies_fused2.py == run dir copy
- [x] published copy sealed_deps.sha256 == run dir copy
- [x] published copy smoke.log == run dir copy
- [x] published copy exp732-fused2.json == run dir copy
- [x] published copy run.log == run dir copy
- [x] committed ARTIFACT.sha256 == local ARTIFACT.sha256
- [x] freeze commit time precedes result mtime — freeze 1793954150 < result 1793957024
- [x] running.json registration shas == ARTIFACT (PREREG + runner)
- [x] sealed dep census_shared_costfit.py unchanged — 8001024c6280
- [x] result JSON records sealed dep census_shared_costfit.py
- [x] sealed dep policies_shared_costfit.py unchanged — e50379fce393
- [x] result JSON records sealed dep policies_shared_costfit.py
- [x] sealed dep policies_costfit.py unchanged — 4bfff5bd4ada
- [x] result JSON records sealed dep policies_costfit.py
- [x] sealed dep policies_costfit3.py unchanged — 23bd944aa491
- [x] result JSON records sealed dep policies_costfit3.py
- [x] sealed dep policies_rothead.py unchanged — 01c79a2fdebc
- [x] result JSON records sealed dep policies_rothead.py
- [x] sealed dep policies.py unchanged — b38c55b86b70
- [x] result JSON records sealed dep policies.py
- [x] sealed dep run_policies_real.py unchanged — 46690edaaddf
- [x] result JSON records sealed dep run_policies_real.py
- [x] sealed dep census_exp675-qwen30b.csv unchanged — 546f0059d7d2
- [x] result JSON records sealed dep census_exp675-qwen30b.csv
- [x] sealed dep census_exp675-granite.csv unchanged — a147cc8e819b
- [x] result JSON records sealed dep census_exp675-granite.csv
- [x] sealed dep exp675a-shared-costfit.json unchanged — 64a39b9909d2
- [x] result JSON records sealed dep exp675a-shared-costfit.json
- [x] sealed dep stream_qwen30b.pt unchanged — 08732f27ce6b
- [x] result JSON records sealed dep stream_qwen30b.pt
- [x] sealed dep stream_granite3b.pt unchanged — 7f8e4303927d
- [x] result JSON records sealed dep stream_granite3b.pt
- [x] sealed dep run_bo.py unchanged — 35b2498a49a1
- [x] result JSON records sealed dep run_bo.py
- [x] sealed dep exp718-econ.json unchanged — 392128938508
- [x] result JSON records sealed dep exp718-econ.json
- [x] sealed dep run_econ.py unchanged — 3d92941ebf82
- [x] result JSON records sealed dep run_econ.py
- [x] sealed dep policies_fused.py unchanged — 050aa1b53538
- [x] result JSON records sealed dep policies_fused.py
- [x] 16 sealed deps (incl. exp729 policies_fused.py)
- [x] run.log RUN_EXIT=0
- [x] run.log sealed deps ok (16 files)
- [x] run.log ladder self-test 15/15 before measurement
- [x] run.log settled verdict + economics == JSON — PAYOFF-CONFIRMED NO-SAVING
- [x] stored ladder_selftest 15/15
- [x] PREREG claim: _FusedLCNU and _FusedS3 class source byte-identical to exp729 sealed policies_fused.py
- [x] module-global NSLOT 10 -> 5
- [x] FusedCostFit carries no parameter override (MARGIN/GAMMA/HALF_LIFE absent from policies_fused2.py)
- [x] design == PREREG (8 rounds, min 5, caps incl. ceiling, streams, seed 732, 5.5h, null bars, 1.10/1.35, 0.80)
- [x] C-model constants == PREREG (load 0.75; SoA last 8/ema 16/count 8/first 8/freq 8; AoS 32 B)
- [x] 16 worker records = 8 rounds x 2 streams
- [x] Random(732) stream/cap schedule reproduced exactly (16/16 records)
- [x] every worker replayed the FULL stream (qwen30b 1,424,640 / granite 638,208)
- [x] every worker QOS rc == 0
- [x] every unit: fixed null/fused2 order, 4 reps, ABBA even / BAAB odd (128/128 units)
- [x] budget not hit; elapsed < 5.5h — 2863.9
- [x] rung 1: every timed replay hit_rate == exp718 PASS-1 costfit exactly (512/512)
- [x] stored hit_rate_mismatches empty
- [x] round-0 census complete: 16/16 (2 streams x 4 caps x 2 units), only in round 0
- [x] rung 1: round-0 terminal FULL STATE of every B arm == sealed costfit A (16/16) — 16
- [x] rung 1: A-arm census == sealed structure_census (16/16)
- [x] A-arm (costfit) census identical across the 2 units of each cell (8/8)
- [x] struct ratios re-derived from census == stored (16/16, |d| <= 1e-15) — 0.0e+00
- [x] null struct ratio == 1.0 at all cells
- [x] economics qualifier re-derived (fused2/costfit struct_bytes <= 0.80 at all 8 cells) == stored — NO-SAVING; 5/8 cells <= 0.80; max 0.9506 @ granite|256
- [x] C model granite|4096 re-derived == stored — AoS/SoA 0.6667
- [x] C model granite|262144 re-derived == stored — AoS/SoA 0.6667
- [x] C model granite|1024 re-derived == stored — AoS/SoA 0.6883
- [x] C model granite|256 re-derived == stored — AoS/SoA 0.7688
- [x] C model qwen30b|4096 re-derived == stored — AoS/SoA 0.7032
- [x] C model qwen30b|262144 re-derived == stored — AoS/SoA 0.6667
- [x] C model qwen30b|1024 re-derived == stored — AoS/SoA 0.7734
- [x] C model qwen30b|256 re-derived == stored — AoS/SoA 0.7932
- [x] fused2 census: one record per key == LCNU occupancy (every seen key is LCNU-resident in metadata)
- [x] 16 cells (2 streams x 4 caps x 2 units), n=8 rounds each
- [x] stored cell stats == re-derived from raw ns (16 cells x 3 clocks x 3 stats, |d| <= 1e-12) — max |d| 0.00e+00
- [x] rung 2: complete rounds 8 >= MIN 5
- [x] rung 3 null pooled in [0.97,1.03] — 0.9954
- [x] rung 3 every cell null median in [0.93,1.07] (8/8) — range 0.9741-1.0052
- [x] gate input null_pooled re-derived == stored null_pooled — 0.995417
- [x] gate input F re-derived == stored R3 — 0.968150
- [x] gate input F_q25 re-derived == stored R3_q25 — 0.963933
- [x] gate input F_q75 re-derived == stored R3_q75 — 0.973395
- [x] fused2 argmax cell re-derived == stored — ('qwen30b', 256)
- [x] rung 4: fused2 argmax IQR does not straddle 1.10 or 1.35 — [0.9639,0.9734]
- [x] rung 5: F <= 1.10 — 0.9681
- [x] independent ladder boundary self-test 16/16
- [x] independent economics qualifier self-test 4/4
- [x] re-adjudicated verdict == stored verdict — PAYOFF-CONFIRMED
- [x] descriptive: leave-one-round-out verdict stable (8/8 == stored) — ['PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED']
- [x] exp729 sealed result parsed: 8 N=3 fused cells + 8 struct ratios
- [x] LIVE qwen30b@256: 8/8 fresh replays hit_rate == exp718 oracle
- [x] LIVE qwen30b@256: full-state parity 2/2 units + A census == sealed structure_census
- [x] LIVE fused2 struct ratio == stored qwen30b|256 — 0.7226
- [x] LIVE qwen30b@256 fused2 thread ratio <= 1.10 (single ABBA unit, descriptive) — null 1.0078, fused2 0.9818

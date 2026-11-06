# ADDENDUM 64 — exp729: fused shared-state CostFit3 — A/A-gated paired CPU-time payoff + metadata economics

Verdict: **PAYOFF-CONFIRMED + SAVING** (frozen ladder rung 5 + economics qualifier). Holding all 10 per-key fields of the N=3 CostFit arbiter in ONE shared list record per key (FusedCostFit3) costs **x0.9605** per-thread CPU time vs the sealed per-key-dict costfit3 at its WORST cell qwen30b @4096 (IQR [0.9482, 0.9735]) — i.e. it is faster everywhere, under a valid A/A null (pooled x0.9991, cells [0.9909, 1.0187]) — while cutting per-key struct bytes to x0.374–x0.627 of costfit3 at all 8 cells (bar <= 0.80). 8/8 rounds, 12447s, exit 0, freeze 534c2f5; host loadavg 4.15–7.79 throughout (not gated, disclosed).

Independent follow-up adjudication: **95/95 checks pass** (gen_addendum64.py), re-derived from the 1024 raw per-replay ns timings, the exp718 PASS-1 hit-rate oracle parsed here, the 32 round-0 parity/census records, run.log, sealed-dep shas and the freeze commit, plus a LIVE third-process re-run of the fused argmax cell. Re-derived verdict == stored.

## Decision-grade result

- **rung 1**: every timed replay (1024/1024) reproduced the exp718 PASS-1 costfit3 hit rate exactly; round-0 terminal FULL STATE (arbiter, every leaf's order/hits/misses, every LCNU and S3-FIFO per-key field) of all 32 B arms == sealed costfit3; A-arm census == sealed structure_census 32/32. Fused parity is verified, not by construction.
- **A/A null (validity gate)**: pooled x0.9991 (bar [0.97, 1.03]); per-cell medians qwen30b@256 0.9980, qwen30b@1024 1.0063, qwen30b@4096 1.0002, qwen30b@262144 0.9909, granite@256 1.0093, granite@1024 0.9948, granite@4096 0.9956, granite@262144 1.0187. 0/64 individual null units deviated > 10%.
- **Per-thread CPU-time ratio arm/costfit3 (median over 8 rounds, [q25, q75]); struct-bytes ratio**:
  - qwen30b @256: fused x0.9556 [0.9507, 0.9578] struct x0.461; lean x1.1773 struct x0.401; floor x1.0930; (exp723 sealed shared views x1.2207)
  - qwen30b @1024: fused x0.9233 [0.9102, 0.9322] struct x0.440; lean x1.3369 struct x0.383; floor x1.1984; (exp723 sealed shared views x1.3839)
  - qwen30b @4096: fused x0.9605 [0.9482, 0.9735] struct x0.374; lean x1.5011 struct x0.326; floor x1.2695; (exp723 sealed shared views x1.5489)
  - qwen30b @262144: fused x0.9033 [0.8964, 0.9163] struct x0.374; lean x1.4668 struct x0.326; floor x1.2124; (exp723 sealed shared views x1.5475)
  - granite @256: fused x0.9339 [0.9276, 0.9400] struct x0.627; lean x1.2714 struct x0.536; floor x1.1773; (exp723 sealed shared views x1.3534)
  - granite @1024: fused x0.9516 [0.9426, 0.9531] struct x0.471; lean x1.5507 struct x0.402; floor x1.2787; (exp723 sealed shared views x1.6059)
  - granite @4096: fused x0.9055 [0.8912, 0.9193] struct x0.564; lean x1.4502 struct x0.483; floor x1.2471; (exp723 sealed shared views x1.4842)
  - granite @262144: fused x0.9185 [0.9062, 0.9260] struct x0.564; lean x1.4362 struct x0.483; floor x1.2361; (exp723 sealed shared views x1.5393)
- Fused: 63/64 individual ABBA units < 1.0 (max unit x1.5022); cheapest cell x0.9033 @ qwen30b/262144. Per-key tables [10] -> [1].

## Attribution of exp723's cost (descriptive)

- floor (private dict-like Python views, no sharing): x1.093–x1.279; lean (shared __slots__ records minus live counter): x1.177–x1.551; exp723 sealed views x1.221–x1.606. Most of exp723's ~1.2–1.6x is per-access Python view dispatch (floor alone pays ~1.2–1.3x with zero sharing); removing the dispatch layer and re-expressing the leaf methods over one record (fused) turns the cost into a saving.

## Descriptive (non-gating)

- Clock robustness: process_time fused worst x0.9605 @ ['qwen30b', 4096], null x0.9991; wall fused worst x0.9635 @ ['qwen30b', 4096], null x0.9979.
- Leave-one-round-out ladder: ['PAYOFF-CONFIRMED'] in 8/8 drops.
- LIVE third-process re-run of qwen30b @4096 (one ABBA unit per arm, sealed worker() in round-0 mode, loadavg 5.98→5.23): null x1.0155, floor x1.2717, lean x1.4898, fused x0.9654; hit rates == oracle 16/16; full-state parity 4/4; fused struct ratio == stored.
- Prediction check (PREREG, stated pre-run): (a) CONFIRMED + SAVING with F in [0.85, 1.05] — HELD (F x0.9605); (b) floor cells x1.10–1.45 — MISSED (x1.0930–x1.2787), lean cells x1.25–1.55 — MISSED (x1.1773–x1.5507); (c) fused struct 0.45–0.65 at all cells — MISSED (x0.3742–x0.6271; qwen30b cells save more than predicted). exp718 N=3 struct ratios for reference x0.342–x0.566 (exp675 shared design).

## Consequence (pre-registered branch)

- PAYOFF-CONFIRMED + SAVING: FusedCostFit3 is proposed as the N-way metadata layout for the CostFit heads — identical decisions (verified full state), lower per-access CPU, and a 37–63% per-key metadata cut. This closes the exp675 -> exp718 -> exp723 -> exp729 shared-state line in the simulator.
- Next (pre-registered): port the fused record to the 2-trace joint-BO head and produce a C-level array-of-struct estimate for the engine.

## Integrity

- PREREG/runner/policies/smoke.log/sealed_deps byte-exact in freeze commit 534c2f5 == ARTIFACT.sha256 == disk == running.json registration; freeze precedes the result; 15/15 sealed deps unchanged and recorded in the result JSON; ladder self-test 15/15 ran before measurement; sealed artifacts untouched; nothing re-launched. run.log is force-added (repo .gitignore has *.log) as primary evidence.

## Check list

- [x] ARTIFACT.sha256 lists PREREG, runner, policies, sealed_deps, smoke.log
- [x] artifact sha PREREG.md — d64f92afa952
- [x] freeze commit 534c2f5 carries PREREG.md byte-exact
- [x] artifact sha run_fused.py — 86b6fb662aac
- [x] freeze commit 534c2f5 carries run_fused.py byte-exact
- [x] artifact sha policies_fused.py — 050aa1b53538
- [x] freeze commit 534c2f5 carries policies_fused.py byte-exact
- [x] artifact sha sealed_deps.sha256 — 21f8cb6cce03
- [x] freeze commit 534c2f5 carries sealed_deps.sha256 byte-exact
- [x] artifact sha smoke.log — a18b8dff1331
- [x] freeze commit 534c2f5 carries smoke.log byte-exact
- [x] published copy PREREG.md == run dir copy
- [x] published copy run_fused.py == run dir copy
- [x] published copy policies_fused.py == run dir copy
- [x] published copy sealed_deps.sha256 == run dir copy
- [x] published copy smoke.log == run dir copy
- [x] published copy exp729-fused.json == run dir copy
- [x] published copy run.log == run dir copy
- [x] committed ARTIFACT.sha256 == local ARTIFACT.sha256
- [x] freeze commit time precedes result mtime — freeze 1793939991 < result 1793952463
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
- [x] 15 sealed deps
- [x] run.log RUN_EXIT=0
- [x] run.log sealed deps ok (15 files)
- [x] run.log ladder self-test 15/15 before measurement
- [x] run.log settled verdict + economics == JSON — PAYOFF-CONFIRMED SAVING
- [x] stored ladder_selftest 15/15
- [x] design == PREREG (8 rounds, min 5, caps incl. ceiling, streams, seed 729, 5.5h, null bars, 1.10/1.35, 0.80)
- [x] 16 worker records = 8 rounds x 2 streams
- [x] Random(729) stream/cap schedule reproduced exactly (16/16 records)
- [x] every worker replayed the FULL stream (qwen30b 1,424,640 / granite 638,208)
- [x] every worker QOS rc == 0
- [x] every unit: fixed null/floor/lean/fused order, 4 reps, ABBA even / BAAB odd (256/256 units)
- [x] budget not hit; elapsed < 5.5h — 12446.7
- [x] rung 1: every timed replay hit_rate == exp718 PASS-1 costfit3 exactly (1024/1024)
- [x] stored hit_rate_mismatches empty
- [x] round-0 census complete: 32/32 (2 streams x 4 caps x 4 units), only in round 0
- [x] rung 1: round-0 terminal FULL STATE of every B arm == sealed costfit3 A (32/32) — 32
- [x] rung 1: A-arm census == sealed structure_census (32/32)
- [x] A-arm (costfit3) census identical across the 4 units of each cell (8/8)
- [x] struct ratios re-derived from census == stored (32/32, |d| <= 1e-15) — 0.0e+00
- [x] null and floor struct ratio == 1.0 at all cells (no sharing)
- [x] economics qualifier re-derived (fused/costfit3 struct_bytes <= 0.80 at all 8 cells) == stored — SAVING; fused max 0.6271
- [x] 32 cells (2 streams x 4 caps x 4 units), n=8 rounds each
- [x] stored cell stats == re-derived from raw ns (32 cells x 3 clocks x 3 stats, |d| <= 1e-12) — max |d| 0.00e+00
- [x] rung 2: complete rounds 8 >= MIN 5
- [x] rung 3 null pooled in [0.97,1.03] — 0.9991
- [x] rung 3 every cell null median in [0.93,1.07] (8/8) — range 0.9909-1.0187
- [x] gate input null_pooled re-derived == stored null_pooled — 0.999115
- [x] gate input F re-derived == stored R3 — 0.960520
- [x] gate input F_q25 re-derived == stored R3_q25 — 0.948157
- [x] gate input F_q75 re-derived == stored R3_q75 — 0.973538
- [x] gate input lean_max re-derived == stored R2 — 1.550661
- [x] fused argmax cell re-derived == stored — ('qwen30b', 4096)
- [x] rung 4: fused argmax IQR does not straddle 1.10 or 1.35 — [0.9482,0.9735]
- [x] rung 5: F <= 1.10 — 0.9605
- [x] independent ladder boundary self-test 16/16
- [x] independent economics qualifier self-test 4/4
- [x] re-adjudicated verdict == stored verdict — PAYOFF-CONFIRMED
- [x] descriptive: leave-one-round-out verdict stable (8/8 == stored) — ['PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED', 'PAYOFF-CONFIRMED']
- [x] exp723 sealed result parsed: 8 N=3 cells
- [x] LIVE qwen30b@4096: 16/16 fresh replays hit_rate == exp718 oracle
- [x] LIVE qwen30b@4096: full-state parity 4/4 units + A census == sealed structure_census
- [x] LIVE fused struct ratio == stored qwen30b|4096 — 0.3742
- [x] LIVE qwen30b@4096 fused thread ratio <= 1.10 (single ABBA unit, descriptive) — null 1.0155, floor 1.2717, lean 1.4898, fused 0.9654

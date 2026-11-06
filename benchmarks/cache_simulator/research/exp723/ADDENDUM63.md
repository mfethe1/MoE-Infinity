# ADDENDUM 63 — exp723: contention-robust paired CPU-time payoff of shared-state N-way metadata

Verdict: **PAYOFF-REJECTED** (frozen ladder rung 7). The A/A null control certified the measurement under contention (pooled null x0.9968, every cell in [0.9775, 1.0164] vs the frozen [0.93, 1.07]), and the shared-key-table views cost **x1.6059** per-thread CPU time vs the per-key-dict originals at the argmax cell granite @1024 (IQR [1.5731, 1.6380], clear of both thresholds), above the 1.35 REJECTED bar. 8/8 rounds complete, 8920s, exit 0, freeze fcba7bb; host loadavg 5.03–10.57 throughout (not gated, disclosed).

Independent follow-up adjudication: **73/73 checks pass** (gen_addendum63.py), re-derived from the 768 raw per-replay ns timings, the exp718 PASS-1 hit-rate oracle parsed here, run.log, sealed-dep shas and the freeze commit, plus a LIVE third-process re-run of the argmax cell. Re-derived verdict == stored.

## Decision-grade result

- **rung 1**: every timed replay (768/768) reproduced the exp718 PASS-1 hit rate exactly — each timing ran the sealed decision path; shared == base hit rate in all 16 (stream,cap,family) pairs.
- **A/A null (validity gate)**: pooled x0.9968 (bar [0.97, 1.03]); per-cell medians qwen30b@256 0.9968, qwen30b@1024 0.9775, qwen30b@4096 0.9926, qwen30b@262144 1.0164, granite@256 0.9968, granite@1024 0.9941, granite@4096 1.0100, granite@262144 1.0075. 5/64 individual null units deviated > 10% (e.g. contention spikes); the per-cell median absorbs them, which is what the gate certifies.
- **Per-thread CPU-time ratio shared/base (median over 8 rounds, [q25, q75])**:
  - qwen30b @256: N=3 x1.2207 [1.2177, 1.2758]; N=2 x1.2329 [1.2286, 1.2540]
  - qwen30b @1024: N=3 x1.3839 [1.3490, 1.4497]; N=2 x1.3503 [1.3147, 1.3625]
  - qwen30b @4096: N=3 x1.5489 [1.5021, 1.5950]; N=2 x1.5228 [1.4899, 1.5334]
  - qwen30b @262144: N=3 x1.5475 [1.4960, 1.5719]; N=2 x1.5085 [1.4631, 1.5362]
  - granite @256: N=3 x1.3534 [1.3295, 1.3877]; N=2 x1.3471 [1.3276, 1.4783]
  - granite @1024: N=3 x1.6059 [1.5731, 1.6380]; N=2 x1.5966 [1.5836, 1.6168]
  - granite @4096: N=3 x1.4842 [1.4425, 1.5501]; N=2 x1.5111 [1.4939, 1.5385]
  - granite @262144: N=3 x1.5393 [1.5083, 1.5644]; N=2 x1.5272 [1.5150, 1.5458]
- R3 (N=3, flagship) x1.6059 @ granite/1024; R2 (N=2) max x1.5966. Cheapest cells: N=3 x1.2207 @ qwen30b/256, N=2 x1.2329 @ qwen30b/256; 16/64 individual N=3 units were <= 1.35.

## Descriptive (non-gating)

- Clock robustness: process_time R3 x1.6059 @ ['granite', 1024], null x0.9968; wall R3 x1.6259 @ ['granite', 1024], null x0.9953 — single-threaded replay, so thread/process/wall agree.
- Leave-one-round-out ladder: ['PAYOFF-REJECTED'] in 8/8 drops.
- LIVE third-process re-run of granite @1024 (one ABBA unit per family, sealed worker(), loadavg 3.49→4.91): N=3 x1.5918, N=2 x1.5874, null x0.9616; hit rates == oracle 12/12.
- Prediction check (PREREG, stated pre-run): (a) MARGINAL or REJECTED — HELD; (b) max cell at eviction-heavy caps 256/1024 — HELD (argmax 1024); (c) CPU ratios modestly below loaded wall ratios — MISSED: flagship CPU R3 x1.6059 vs exp718 loaded wall R3 x1.245–x1.569 (median x1.408).

## Consequence (pre-registered branch)

- PAYOFF-REJECTED: the shared-key-table views cost x1.22–x1.61 per-thread CPU time (N=3 cell medians) as implemented. The metadata cut (exp718 N=3 struct-bytes ratio x0.34–x0.57) is real but not free; it is NOT proposed for adoption in the N-way CostFit heads as is.
- Next (pre-registered): profile the shared-table hot path (record lookup + live counter) and test an array-of-struct redesign against the same oracle and the same A/A-gated paired CPU-time design.

## Integrity

- PREREG/runner/smoke.log/sealed_deps byte-exact in freeze commit fcba7bb == ARTIFACT.sha256 == disk; freeze precedes the result; 15/15 sealed deps unchanged and recorded in the result JSON; ladder self-test 15/15 ran before measurement; sealed artifacts untouched; nothing re-launched.

## Check list

- [x] artifact sha PREREG.md — da27c7c7f76a
- [x] freeze commit fcba7bb carries PREREG.md byte-exact
- [x] artifact sha run_cpupair.py — e518c6757d3f
- [x] freeze commit fcba7bb carries run_cpupair.py byte-exact
- [x] artifact sha smoke.log — b04a5fab9ba3
- [x] freeze commit fcba7bb carries smoke.log byte-exact
- [x] artifact sha sealed_deps.sha256 — 21f8cb6cce03
- [x] freeze commit fcba7bb carries sealed_deps.sha256 byte-exact
- [x] committed ARTIFACT.sha256 == local ARTIFACT.sha256
- [x] freeze commit time precedes result mtime — freeze 1793929496 < result 1793938428
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
- [x] 15 sealed deps (13 exp718 + run_econ.py + exp718-econ.json)
- [x] run.log RUN_EXIT=0
- [x] run.log sealed deps ok (15 files)
- [x] run.log ladder self-test 15/15 before measurement
- [x] run.log settled verdict == JSON verdict — PAYOFF-REJECTED
- [x] stored ladder_selftest 15/15
- [x] design == PREREG (8 rounds, min 5, caps, streams, seed 723, 5.5h, null [0.97,1.03]/[0.93,1.07], 1.10/1.35)
- [x] 16 worker records = 8 rounds x 2 streams
- [x] Random(723) stream/cap schedule reproduced exactly (16/16 records)
- [x] every worker replayed the FULL stream (qwen30b 1,424,640 / granite 638,208)
- [x] every worker QOS rc == 0
- [x] every unit: fixed fam2/fam3/null order, 4 reps, ABBA even / BAAB odd rounds (192/192 units)
- [x] budget not hit; elapsed < 5.5h — 8920.0
- [x] rung 1: every timed replay hit_rate == exp718 PASS-1 exactly (768/768)
- [x] stored hit_rate_mismatches empty
- [x] oracle: shared == base hit_rate in all 16 (stream,cap,family) pairs
- [x] 24 cells (2 streams x 4 caps x 3 units), n=8 rounds each
- [x] stored cell stats == re-derived from raw ns (24 cells x 3 clocks x 3 stats, |d| <= 1e-12) — max |d| 0.00e+00
- [x] rung 2: complete rounds 8 >= MIN 5
- [x] rung 3 null pooled in [0.97,1.03] — 0.9968
- [x] rung 3 every cell null median in [0.93,1.07] (8/8) — range 0.9775-1.0164
- [x] gate input null_pooled re-derived == stored — 0.996827
- [x] gate input R3 re-derived == stored — 1.605863
- [x] gate input R3_q25 re-derived == stored — 1.573100
- [x] gate input R3_q75 re-derived == stored — 1.637971
- [x] gate input R2 re-derived == stored — 1.596610
- [x] argmax cell re-derived == stored — ('granite', 1024)
- [x] rung 4: argmax IQR does not straddle 1.10 or 1.35 — [1.5731,1.6380]
- [x] independent ladder boundary self-test 15/15
- [x] re-adjudicated verdict == stored verdict — PAYOFF-REJECTED
- [x] descriptive: leave-one-round-out verdict stable (8/8 == stored) — ['PAYOFF-REJECTED', 'PAYOFF-REJECTED', 'PAYOFF-REJECTED', 'PAYOFF-REJECTED', 'PAYOFF-REJECTED', 'PAYOFF-REJECTED', 'PAYOFF-REJECTED', 'PAYOFF-REJECTED']
- [x] LIVE granite@1024: 12/12 fresh replays hit_rate == exp718 oracle
- [x] LIVE granite@1024 fam3 thread ratio > 1.35 (single ABBA unit, descriptive) — fam3 1.5918 fam2 1.5874 null 0.9616

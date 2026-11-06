# ADDENDUM 61 — exp718: shared-state N-way metadata economics at the cap ceiling (exp675 stage B)

Verdict: **INCOMPLETE-BUDGET** (frozen ladder rung 2). The 6 h wall budget ran out after 7 of 8 quiet-gated timing groups: Mack never reached loadavg(1) < 1.5 (group-start loads 4.20–6.20); every group waited the full 45 min, so 0/8 groups were quiet and the granite @262144 group (costfit, costfit3, shared_costfit, shared_costfit3) never ran. Parity (rung 1) held. Elapsed 24393s, exit 0, freeze 0a042de.

Independent follow-up adjudication: **60/60 checks pass**, computed by gen_addendum61.py from the result JSON raw rows, run.log, the sealed stage-A CSVs (parsed here) and sha-checked sealed inputs, plus a LIVE third-process re-check through the sealed code. Re-derived verdict == stored.

## What is decision-grade (load-independent)

- **H1' parity HOLDS, including the never-tested cap ceiling 262144**: 16/16 full-state tuples (hits, misses, hit_rate, switches, choice_switches, choice, _mass, _sw_mass, resident order) exactly equal on both real decode streams × 4 caps × N=2/N=3; sealed synthetic event-sequence smoke True; every parity hit_rate equals the census hit_rate for base AND shared cells.
  - Disclosed: [('qwen30b', 4096, 'costfit3')] report resident_len 0 (base AND shared both expose an empty resident list at that cell; cause not investigated here), so resident order is vacuous there; all other state fields were equal.
- **N-way metadata reduction** (PASS-1 census, struct bytes shared/base):
  - qwen30b costfit: 256: x0.6432 (records 24048→5948), 1024: x0.6148 (records 24816→5948), 4096: x0.5226 (records 27888→5948), 262144: x0.5226 (records 29740→5948)
  - qwen30b costfit3: 256: x0.4208 (records 48096→5948), 1024: x0.4023 (records 49632→5948), 4096: x0.3420 (records 55776→5948), 262144: x0.3420 (records 59480→5948)
  - granite costfit: 256: x0.8292 (records 5304→1262), 1024: x0.6223 (records 6072→1262), 4096: x0.7464 (records 6310→1262), 262144: x0.7464 (records 6310→1262)
  - granite costfit3: 256: x0.5664 (records 10608→1262), 1024: x0.4250 (records 12144→1262), 4096: x0.5098 (records 12620→1262), 262144: x0.5098 (records 12620→1262)

## Descriptive only (rung 2 fired before these gates)

- H4' accounting: tables 1/5/10 on 32/32 cells; cross-pass exact struct fields 28/28 available cells, peak/terminal jitter worst 0.000052 (≤1%). The frozen accounting flag is False ONLY because the 4 granite @262144 PASS-2 rows were cut by the budget.
  - LIVE re-measure of those 4 cells (fresh spawned processes, sealed _measure, repeats=1): 4/4 exact struct fields vs PASS-1, worst peak/terminal jitter 0.000073; granite @262144 parity re-run 2/2 equal. Fills the gap descriptively; the frozen verdict is not changed.
- H2' drift vs stage A (Winnie, py3.12) — 12/12 within tolerance: max |struct ratio drift| 0.0000 (≤0.05), max |terminal drift| 0.0224 (≤0.10). Struct ratios replicate cross-host:
  - qwen30b costfit @256: struct A 0.6432 / B 0.6432; terminal A 0.8079 / B 0.8149
  - qwen30b costfit @1024: struct A 0.6148 / B 0.6148; terminal A 0.8279 / B 0.8333
  - qwen30b costfit @4096: struct A 0.5226 / B 0.5226; terminal A 0.8464 / B 0.8495
  - qwen30b costfit3 @256: struct A 0.4208 / B 0.4208; terminal A 0.6407 / B 0.6443
  - qwen30b costfit3 @1024: struct A 0.4023 / B 0.4023; terminal A 0.6982 / B 0.7010
  - qwen30b costfit3 @4096: struct A 0.3420 / B 0.3420; terminal A 0.7712 / B 0.7728
  - granite costfit @256: struct A 0.8292 / B 0.8292; terminal A 1.1049 / B 1.1297
  - granite costfit @1024: struct A 0.6223 / B 0.6223; terminal A 0.9922 / B 1.0064
  - granite costfit @4096: struct A 0.7464 / B 0.7464; terminal A 1.0466 / B 1.0650
  - granite costfit3 @256: struct A 0.5664 / B 0.5664; terminal A 0.9175 / B 0.9315
  - granite costfit3 @1024: struct A 0.4250 / B 0.4250; terminal A 0.8912 / B 0.8989
  - granite costfit3 @4096: struct A 0.5098 / B 0.5098; terminal A 0.9124 / B 0.9224
- H5' ceiling 4/4: qwen30b costfit x0.5226 vs 4096 x0.5226; qwen30b costfit3 x0.3420 vs 4096 x0.3420; granite costfit x0.7464 vs 4096 x0.7464; granite costfit3 x0.5098 vs 4096 x0.5098
- Ladder counterfactual (if the cut group had been present and matched): ECONOMICS-TIME-UNMEASURED — i.e. memory gates would pass and the payoff would STILL be unmeasured (0/8 quiet groups).

## Timing — INFORMATIONAL ONLY (every group loaded; NOT a payoff claim)

- qwen30b @256 (load 4.86→4.33): R3 x1.2449, R2 x1.0854
- granite @256 (load 4.31→5.82): R3 x1.3835, R2 x1.3355
- qwen30b @1024 (load 5.93→5.68): R3 x1.4077, R2 x1.2698
- granite @1024 (load 6.2→3.83): R3 x1.5546, R2 x1.5844
- qwen30b @4096 (load 6.15→5.56): R3 x1.3344, R2 x1.5024
- granite @4096 (load 4.79→5.41): R3 x1.4958, R2 x1.6130
- qwen30b @262144 (load 4.2→5.21): R3 x1.5691, R2 x1.5368
- loaded R3 range x1.245–x1.569, median x1.408; R2 median x1.502. Wall-clock perf_counter medians under loadavg 4–6 with many co-tenant agent sessions.

## Consequence (pre-registered branch + attribution)

- INCOMPLETE-BUDGET is not a payoff verdict. The memory side of the 3x-to-1x claim is now replicated cross-host and extended to the ceiling (descriptive, all gates would pass); the payoff (R3) is unmeasured for the second time (stage A: Winnie loadavg ~23; stage B: Mack loadavg 4–6).
- Root cause is the measurement design, not the host window: a loadavg quiet gate on a shared agent fleet host never opens. Next = exp723: timing-only completion with a contention-robust paired design (interleaved ABBA, process CPU time, A/A null control as a validity gate) — the PREREG's 'quiet-window re-run of timing only' branch, with the gate redesigned so it can actually fire.

## Integrity

- ARTIFACT.sha256 (PREREG/runner/smoke/sealed_deps) matches on disk; PREREG/runner/sealed_deps byte-exact in freeze commit 0a042de (smoke.log was .gitignored there, its sha is in the committed ARTIFACT.sha256); 13/13 sealed deps unchanged and recorded in the result JSON; sealed artifacts untouched; nothing re-launched.

## Check list

- [x] artifact sha PREREG.md — 1ce6dfaa93a2
- [x] freeze commit 0a042de carries PREREG.md byte-exact
- [x] artifact sha run_econ.py — 3d92941ebf82
- [x] freeze commit 0a042de carries run_econ.py byte-exact
- [x] artifact sha smoke.log — aaacb8dec612
- [x] smoke.log absent from freeze commit only via .gitignore *.log; its sha is in the committed ARTIFACT.sha256 and the repo copy matches (disclosed; force-added at publish)
- [x] artifact sha sealed_deps.sha256 — c2fd75e4a8c6
- [x] freeze commit 0a042de carries sealed_deps.sha256 byte-exact
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
- [x] run.log RUN_EXIT=0
- [x] run.log settled verdict matches JSON
- [x] runner sealed-deps assertion passed at start
- [x] design matches PREREG (caps/policies/budget/repeats/quiet)
- [x] PASS-1 census 32/32 cells present — 32/32
- [x] budget exhausted (elapsed > 6h) with groups missing — elapsed 24392.7s > 21600s; missing groups [('granite', 262144)]
- [x] missing group cut by budget, not spawn error — last group logged at 24393.0s
- [x] runner state flags agree with re-derivation
- [x] H1' 16/16 parity pairs present — 16
- [x] H1' all full-state tuples equal (no diff_fields)
- [x] H1' sealed synthetic parity_smoke True (log + JSON)
- [x] H1' parity hit_rate == PASS-1 census hit_rate (base cells, frozen gate)
- [x] H1' parity hit_rate == PASS-1 census hit_rate (shared cells, stronger)
- [x] H4' tables 1/5/10 on all 32 PASS-1 cells
- [x] H4' cross-pass exact struct fields on 28/28 available cells — 28/28
- [x] H4' cross-pass peak/terminal <=1% on available cells — worst 0.000052
- [x] H4' frozen accounting_ok False ONLY because PASS-2 rows missing (agrees with runner) — missing PASS-2 [('granite', 262144, 'costfit'), ('granite', 262144, 'costfit3'), ('granite', 262144, 'shared_costfit'), ('granite', 262144, 'shared_costfit3')]
- [x] stored ratios == re-derived from raw PASS-1 rows (16 keys x 3 metrics, exact)
- [x] H2' drift 12/12 within struct 5% / terminal 10% (descriptive) — max ds 0.0000 max dt 0.0224
- [x] H5' ceiling 4/4 struct(262144) <= 1.05 x struct(4096) (descriptive)
- [x] H3' quiet groups 0/8 (re-derived from per-group loadavg) — 0 quiet; loadavg starts [4.86, 4.31, 5.93, 6.2, 6.15, 4.79, 4.2]
- [x] ladder boundary self-test 12/12
- [x] re-adjudicated verdict == stored verdict — INCOMPLETE-BUDGET
- [x] LIVE granite@262144 parity 2/2 equal and hit_rate == stored
- [x] LIVE granite@262144 cross-run (vs PASS-1) exact struct fields 4/4 (fills the cut PASS-2 gap, descriptive) — 4/4
- [x] LIVE granite@262144 cross-run peak/terminal <=1% — worst 0.000073

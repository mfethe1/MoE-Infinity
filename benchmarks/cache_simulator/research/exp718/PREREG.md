# exp718 PREREG — shared-state N-way metadata economics at cap ceiling, quiet-host timing (exp675 stage B)

Frozen BEFORE any real run (ARTIFACT.sha256). Sealed experiments are never edited or re-launched.

## Lineage and question
exp675a (stage A, ADDENDUM26, verdict SHARED-STATE-VALIDATED) proved parity-exact shared-key-table
CostFit (N=2: 5 per-key dicts -> 1 table) and CostFit3 (N=3: 10 dicts -> 1 table; census records
49,632 -> 5,948 on qwen30b @1024 = the 3x-to-1x per-key metadata multiplicity claim), with struct
x0.34-0.57 (N=3) / x0.52-0.83 (N=2) and terminal x0.64-0.92 / x0.81-1.10, BUT its wall-time numbers
(ns/access ratio x1.13-1.67, mean x1.33) were measured on Winnie under loadavg ~23 and were declared
INFORMATIONAL only. exp714's frozen consequence (NO-TRAIN-HEADROOM) closed the CostFit tuning line
and pre-registered shared-state N-way metadata economics as the next question.

exp718 asks, decision-grade, on a QUIET host:
1. H1' parity: does base-vs-shared full-state parity hold on BOTH real decode streams at all four
   caps INCLUDING the cap ceiling 262144 (a regime stage A never tested)?
2. H2' drift: do the stage-A struct/terminal ratios replicate within tolerance at the overlapping
   caps {256,1024,4096} (cross-host: ratios only, absolute bytes are build-dependent)?
3. H5' ceiling: does the N-way metadata reduction hold at the ceiling (no-eviction,
   metadata-dominated regime)?
4. H3' payoff: what is the CLEAN wall-time cost of the shared views (quiet-gated medians)?

## Host and interpreter
Mack (M4, macOS, python 3.14.8, exp650 venv, torch for .pt trace loading). Stage A anchor host was
Winnie WSL py3.12.3 — therefore ALL cross-experiment comparisons are RATIOS (struct/terminal/time),
never absolute bytes. Timing cells are quiet-gated: loadavg(1) < 1.5 at group start and < 2.5 at
group end, else the group's time ratios are recorded but EXCLUDED from the payoff gate. Memory /
structure / parity measurements are load-independent (deterministic byte and state comparisons) and
run at any load; per-cell loadavg is recorded for disclosure.

## Sealed inputs (sha256 in ARTIFACT.sha256; imported by path/package, never copied or edited)
- census_shared_costfit.py 8001024c… (stage-A machinery: _measure spawn cells, structure_census,
  parity_smoke, _replay) — reused as-is.
- policies_shared_costfit.py e50379fc…, policies_costfit.py 4bfff5bd…, policies_costfit3.py
  23bd944a…, policies_rothead.py 01c79a2f…, policies.py b38c55b8…, run_policies_real.py 46690eda…
- exp669 run_bo.py 35b2498a… (MODELS stream/base paths only; runner asserts its stream paths match
  the sealed .pt files below).
- Stage-A anchors: census_exp675-qwen30b.csv 546f0059…, census_exp675-granite.csv a147cc8e…,
  exp675a-shared-costfit.json 64a39b99…
- Streams: data/belady/stream_qwen30b.pt 08732f27… (1,424,640 accesses, 5,948 distinct keys),
  benchmarks/cache_simulator/data/handcrafted8-greedy512/belady/stream_granite3b.pt 7f8e4303…
  (638,208 accesses, 1,262 distinct keys).

## Design (frozen)
Cells: streams {qwen30b, granite} x caps {256, 1024, 4096, 262144} x policies {costfit,
shared_costfit, costfit3, shared_costfit3}. Distinct keys << 262144, so the ceiling is the
no-eviction regime (disclosed: granite is already no-eviction at 4096; its ceiling cell is an
economics near-duplicate and a fresh parity cell; qwen30b's ceiling is genuinely new: 5,948
residents > 4,096).

- PASS A (any load): (a) sealed parity_smoke() once (synthetic stream, instrumented victim/evict
  event sequences, N=2 and N=3); (b) per (stream, cap, family): full-stream replays of base and
  shared, exact equality of the full state tuple (hits, misses, hit_rate, switches,
  choice_switches, choice, _mass, _sw_mass, resident order) — 16 pairs; (c) census PASS-1 rows:
  sealed _measure in a fresh spawned process per (policy, cap, stream), repeats=1 (byte fields).
- PASS B (quiet-gated, per (stream, cap) group): wait <=45 min for loadavg(1) < 1.5, then _measure
  repeats=5 for the 4 policies back-to-back in one window (median ns/access per cell; byte fields
  re-measured for cross-pass determinism).
- Wall budget 6 h; heartbeat lines per cell; on exhaustion the run stops and reports
  INCOMPLETE-BUDGET with all completed cells (no fabricated rows).

## Gates (computed in python; every ratio re-derived from raw rows at adjudication)
- H1' parity: all 16 full-state tuples exactly equal AND parity_smoke True AND each parity hit_rate
  exactly equals the PASS-1 census hit_rate for the same (policy, cap, stream).
- H4' accounting: census tables == 1 for shared cells, == 5 (costfit) / == 10 (costfit3) for base
  cells; PASS-1 vs PASS-2 exact equality of (hit_rate, tables, records, slots, struct_bytes) and
  <=1% relative difference of (peak_bytes, terminal_bytes).
- H2' drift (vs stage-A anchor CSVs, overlapping caps, both streams, both families):
  |struct_ratio_B / struct_ratio_A - 1| <= 0.05 AND |terminal_ratio_B / terminal_ratio_A - 1| <= 0.10.
- H5' ceiling: struct_ratio(262144) <= 1.05 x struct_ratio(4096) measured in THIS run (same
  stream+family).
- H3' payoff: R3 = max over QUIET groups of (shared_costfit3 ns/acc) / (costfit3 ns/acc);
  R2 likewise for the 2-way family (reported; R3 is the flagship gate).

## Frozen verdict ladder (first match wins)
1. PARITY-FAIL — any H1' violation (hard fail regardless of completeness).
2. INCOMPLETE-BUDGET — any cell missing because the 6 h budget or a spawn error stopped the run.
3. ACCOUNTING-FAIL — any H4' violation.
4. ECONOMICS-DRIFT — any H2' violation (stage-A ratios did not replicate; investigate before any
   payoff claim).
5. CEILING-DRIFT — any H5' violation.
6. ECONOMICS-TIME-UNMEASURED — fewer than 6 of 8 groups quiet-completed (no honest payoff verdict
   possible on this host window; re-run timing elsewhere, memory verdicts still stand as reported).
7. PAYOFF-CONFIRMED — R3 <= 1.10: the 3x-to-1x metadata reduction costs <=10% clean wall time.
8. PAYOFF-MARGINAL — R3 <= 1.35: real but bounded time cost; adoption only where memory-bound.
9. PAYOFF-REJECTED — R3 > 1.35: shared views are intrinsically too slow; profile the
   SharedFieldView hot path before any adoption.

## Pre-registered consequences
- PAYOFF-CONFIRMED -> shared-table metadata becomes the default candidate for the engine-line
  (C++) metadata design; next = engine-port feasibility brief (Winnie lane, separate prereg).
- PAYOFF-MARGINAL -> adopt only in memory-bound regimes (ceiling-scale deployments); next =
  SharedFieldView hot-path profiling to see if the gap closes.
- PAYOFF-REJECTED / ECONOMICS-TIME-UNMEASURED -> next = overhead profile (or quiet-window re-run of
  timing only); no adoption.
- PARITY-FAIL / ACCOUNTING-FAIL / ECONOMICS-DRIFT / CEILING-DRIFT -> stop the shared-state line,
  attribute against stage A, no adoption; report honestly.

## Disclosures / non-goals
- No new policies: N>3 head compositions (new arbiters) are a product-design decision and a
  separate prereg; this experiment measures the EXISTING sealed N=2/N=3 shared classes.
- Real-stream parity is full-state-tuple equality (no event-sequence instrumentation on 1.4M-access
  streams for memory reasons); event-sequence parity is covered once by the sealed synthetic smoke.
- Absolute ns/access and byte values are host/build-specific; only ratios are claims.
- Children reload the stream per census cell (sealed _measure behavior; unchanged).
- Smoke runs (SMOKE=1) are disclosed in smoke*.log and sha-frozen; a smoke may exercise machinery
  at reduced limits — its numbers are never results.

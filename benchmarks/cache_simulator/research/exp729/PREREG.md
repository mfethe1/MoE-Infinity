# exp729 — fused shared-state CostFit3: A/A-gated paired CPU-time payoff + metadata economics (PREREG, frozen before any real run)

Lane 79990, program STACK-1001. Follows exp723 (PAYOFF-REJECTED: sealed shared-key-table views cost x1.22–x1.61
per-thread CPU time vs per-key dicts, flagship x1.6059 @ granite/1024, under a valid A/A null x0.9968). exp723's
pre-registered REJECTED branch: profile the shared-table hot path and test a redesign under the same oracle and the
same A/A-gated paired CPU-time design. This is that experiment.

## Question
Can the per-key metadata of the N=3 CostFit arbiter (2 LCNU x [last, ema, count, first] + 2 S3-FIFO x [freq] = 10
per-key fields across 4 leaf inners) be held in ONE shared record per key at no more than +10% per-thread CPU time,
while keeping the exp675/exp718 metadata saving? And how much of exp723's cost is (a) pure Python-view dispatch,
(b) the sealed design's bookkeeping?

## Arms (all keep the SEALED CostFit3 arbiter; all subclass the SEALED leaf policies; policies_fused.py, frozen here)
- `null`  : costfit3 (A) vs costfit3 (A') — A/A null control, validity gate.
- `floor` : costfit3 vs FloorCostFit3 — per-key dicts wrapped in private Python dict-like views, NO sharing. Measures
  the dispatch floor of any view design (descriptive).
- `lean`  : costfit3 vs LeanCostFit3 — one shared Key -> `__slots__` record table (the exp675 design) minus the
  per-record `live` counter and setitem probe (dead weight in CostFit families: every accessed key gets LCNU slots,
  which are never deleted). Descriptive.
- `fused` : costfit3 vs FusedCostFit3 — **PRIMARY**. One shared Key -> list[10] record; the leaf methods that touch
  per-key state (LCNU `_record_access`/`_probs`, S3-FIFO `_on_hit`/`_evict_main`/`_evict_small`/`_on_miss`) are
  re-expressed over the record with the same statement order and the same float expressions; absent = None.
  Parity is NOT by construction for `fused` — it is verified (rung 1).

## Design (exp723 sealed machinery, arms swapped; run_fused.py generated from exp723's run_cpupair.py)
- Streams: qwen30b (1,424,640 accesses) and granite (638,208), full; caps 256, 1024, 4096, 262144 (ceiling).
- 8 rounds (MIN 5 complete for a verdict), wall budget 5.5 h, seed 729 shuffles cap order per round and stream
  order per round. Per round x stream: one fresh spawned worker (QOS user-interactive requested, disclosed) loads the
  stream once; for every cap, the 4 units run in fixed order null, floor, lean, fused, each as ABBA (even rounds) /
  BAAB (odd rounds). Each timed replay builds a fresh policy (untimed), gc.collect() (untimed), then times
  `census_shared_costfit._replay` with thread_time_ns (PRIMARY), process_time_ns and perf_counter_ns (descriptive).
- Pair ratio per unit = (B1+B2)/(A1+A2) on thread CPU time. Per cell (stream, cap, unit): median + q25/q75
  (linear interpolation) over rounds.
- Round 0 only, untimed, after each unit's 4 timed replays: terminal FULL STATE of the last B policy must equal the
  last A (sealed costfit3) policy exactly — arbiter choice/switches/choice_switches/decayed masses/credited; every
  leaf's resident order, hits/misses; LCNU visits, by_layer, every per-key (last, ema, count, first); S3-FIFO
  small/main/ghost order and every per-key freq. Struct census (getsizeof of per-key containers, values excluded,
  sorted-key walk == exp675a methodology; the A-arm census must equal the sealed `structure_census`).
- Sealed deps (15 files incl. the exp718 result JSON as hit-rate oracle) asserted by sha256 at start
  (sealed_deps.sha256).

## Verdict ladder (frozen, first match wins; same code + 15-case boundary self-test as exp723)
Let F = median thread ratio of the `fused` unit at its argmax cell (max median over the 8 stream x cap cells),
[F_q25, F_q75] its IQR.
1. SEALED-FAIL — any sealed-dep drift, any timed replay hit_rate != exp718 PASS-1 costfit3 (stream, cap), any
   round-0 full-state mismatch (any arm), or the round-0 census incomplete.
2. INCOMPLETE-BUDGET — fewer than 5 complete rounds (both streams).
3. TIME-INVALID — null pooled (median of 8 per-cell null medians) outside [0.97, 1.03] or any cell null median
   outside [0.93, 1.07].
4. PAYOFF-UNRESOLVED — F_q25 <= t < F_q75 for t in {1.10, 1.35} (half-open: q75 == t is not a straddle).
5. PAYOFF-CONFIRMED — F <= 1.10.
6. PAYOFF-MARGINAL — F <= 1.35.
7. PAYOFF-REJECTED — otherwise.

Economics qualifier (frozen, reported alongside the verdict): SAVING if fused/costfit3 struct_bytes <= 0.80 at all
8 cells, else NO-SAVING. Adoption is proposed only for PAYOFF-CONFIRMED + SAVING.

## Disclosed pre-freeze exploration (this informs the predictions — it is not a result)
Before writing this PREREG a single unpaired exploratory probe ran on a 60,000-access granite prefix at caps 256
and 4096 on the loaded host (one replay per arm): all three arms hit-rate- and full-state-equal to costfit3;
thread-time ratios floor x1.15/x1.34, lean x1.28/x1.40, fused x0.96/x0.88; struct ratios lean 0.51/0.46,
fused 0.60/0.54, floor 1.00.

## Predictions (stated before the real run)
- (a) Verdict PAYOFF-CONFIRMED + SAVING: fused argmax cell F in [0.85, 1.05].
- (b) floor cells x1.1–x1.45 (any Python dict-view pays this), lean cells x1.25–x1.55 (between floor and exp723's
  sealed design) — i.e. most of exp723's cost is dispatch, not sharing.
- (c) fused struct ratio 0.45–0.65 at all cells.

## Consequence (pre-registered)
- CONFIRMED + SAVING: propose FusedCostFit3 as the N-way metadata layout; next = port the fused record to the 2-trace
  joint-BO head and a C-level struct (array-of-struct) estimate for the engine.
- MARGINAL / REJECTED: Python-level record fusion is not enough; metadata sharing waits for a C-level layout.
- NO-SAVING with CONFIRMED: the fused layout is a speed-only refactor, not a memory lever.

## Integrity
PREREG.md, run_fused.py, policies_fused.py, sealed_deps.sha256 and smoke.log are committed (freeze commit) and their
sha256 written to ARTIFACT.sha256 before the real run. A disclosed machinery smoke (SMOKE=1: 40,000-access prefix,
2 rounds, caps 256/4096; self-consistency + full-state parity only, never a result) runs before the freeze.

Smoke disclosure (run 2026-11-05 ~23:50 EST, before freeze): SMOKE_OK=True, 4 records, 16 cells, deterministic,
ladder self-test 15/15, full-state parity 16/16 (parity_bad=0). The smoke's `economics=NO-SAVING` is an artefact of
the smoke covering 4 of the 8 cells (the qualifier requires all 8) — smoke struct ratios fused 0.41–0.59, lean
0.35–0.51, floor/null 1.00. Smoke timing ratios are never a result.

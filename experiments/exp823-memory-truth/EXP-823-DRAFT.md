# EXP-823 (amended) — True engine GPU memory vs the torch counter

**STATUS: DRAFT — NOT READY TO RUN.** Per COORDINATOR-DIRECTIVES.md 2026-11-14T21:32 ET,
this pre-registration is written once as DRAFT; no freeze, no hash-gate, no launch until
(a) a corrected method review passes and is bound to this file's SHA256, and (b) the
pre-registration's cache coverage is checked. Every tolerance, cadence, budget and gate
below is **PROPOSED — PENDING REVIEW** and is not tuned after results.

- **Supersedes:** exp822 (VOID 2026-11-16: nvidia-smi per-process compute-apps returns
  nulls on this WSL host; G0 aborted before any measured arm) and the failed
  SCIENTIFIC-CONTRACT.md design of 2026-11-14 (SHA256 aa17eec4…, method review verdict
  conceptual FAIL, ROW14-JEAN-METHOD-REVIEW.md 169bdb19…).
- **Amendment source:** three-model panel + Mythos 5.2 review 2026-11-18
  (`scratch/mythos-review-20261118.md`, section E item 1): make the allocation-hook
  total the primary instrument; treat exp823 as the credited confirmation of pilot C1v3.
- **Pilot evidence (C1v3, no credit):** torch reserved peak 4,948 MiB flat across
  0.35/0.65/0.35 cells; engine raw cudaMalloc total at end of decode 6,733 / 11,473 /
  6,901 MiB; growth 0.35→0.65 = 4,740 MiB (source predicted 4,893); hook totals over all
  libraries 11,681 / 16,421 / 11,849 MiB. BELIEFS `c0_gpu_memory_instruments_wsl`,
  keys `measured_2026-11-15_C1v3_no_credit`, cell.json sha256s recorded there.

## R1 — Estimand and decision rule

For each ratio r ∈ {0.35, 0.50, 0.65}: the cell's **true engine GPU memory T(r)** =
allocation-hook total (sum of every `cudaMalloc` byte recorded by `libcudahook3.so`,
all libraries, own process) at the `decode` phase mark, in a fresh process after the
fixed probe8 workload. Secondary estimand: U(r) = T(r) − torch reserved peak (the
torch-counter blind spot). Per-ratio statistic: **median of 3 cells** (unit of analysis
R5 = the fresh-process cell). Decision rule: the PROPOSED gates K1, G1, G2, S below,
evaluated by a script over the frozen cell records only.

## Arms

3 ratios × 3 fresh-process cells (9 measured cells) + 1 throwaway warm cell run before
the first measured cell (battery-level warmup discipline). Config identical to C1v3 /
`e0_cell.py`: policy lcnu, num_threads 4, gpu_only_expert_routing true,
adaptive_resident_mode legacy, model OLMoE-1B-7B-0125-Instruct (offload dir
`/home/mfeth/moe-offload-olmoe-0125-r05`, verified on disk), probe8 (8 prompts), greedy,
`min_new_tokens=128` (**B3: fixed generation length; token lists recorded per prompt**).

## Instruments (B2)

1. **Primary — allocation hook** `libcudahook3.so` (LD_PRELOAD; binary sha256
   15424e1b7122767bb5d436930c9248745bd0a7cd1f7d2a92cd57e490e3cabeb7, source
   `cudahook3.c` 11aebacc388a94fdb795846308e1944bccd19f73659877f0405f19f7f468b5c6):
   event log of every cudaMalloc/cudaFree → totals have **no sampling blind spot by
   construction** (the C0 finding "20 ms sampler saw no spike < 3 ms" concerns the
   sampler, not this event log).
2. Secondary — `sampler_thread_v3.py` (sha256 b77438f63b2962e3bf40c5f568c6bbdcfa90eef61d3a71167ebef6ae8ed5c6ea;
   v3-certified per ROW14-C0-INSTRUMENT-RULING-v2 rule 2): 20 ms cudaMemGetInfo +
   torch reserved trace, in-process only.
3. Per phase tag — outside `nvidia-smi` (device-wide; includes contexts/tenants) +
   holders list (**R3 contamination proof** per cell; standing surya-ocr tenant noted).

## PROPOSED gates (PENDING REVIEW — fixed before run, not tuned after)

- **K1 (metric calibration — fixes blocking finding B1 "direction, not size"):**
  reuse the C1 pilot's existing self-test, not a fresh authoring: `k1_selftest.py`
  (sha256 bbac123b3503318608ff930b336bc677289f82e64d7bd40502a87bf8d35cf883) under
  LD_PRELOAD allocates known raw fills {1 MiB+1, 64, 256, 1536, 4096 MiB} through the
  interposed symbol (ctypes.CDLL(None), C1v2-7 lesson) and records the hook delta;
  `run_k1.sh` (sha256 7e6fc30f19f863a8b9afc26763beac9efb41ba71f76c6d2d5dcacd7f4ad81dc9)
  additionally builds the `-DCUDAHOOK_HALF` mutant as a negative control. Gate: hook
  delta equals requested size within ±2% for the 1536 MiB fill (others recorded),
  AND the HALF mutant must fail the same check; else INFRA-ABORT + VOID (same abort
  semantics as exp822's G0). Sampler source saved with the battery (fixes the exp822
  "no saved sampler source" defect, CD:75).
- **G1 (torch undercount):** median U(r) = hook total − torch reserved peak ≥ 500 MiB
  at EVERY ratio.
- **G2 (true growth):** median T(0.65) − median T(0.35) ≥ 2,000 MiB (pilot: 4,740).
- **S (replication spread — R2 residual tolerance):** per-ratio cell spread
  (max−min)/median ≤ 5%.
- **Ceiling / overcommit (R4 budget bounds):** per cell, record failed-cudaMalloc
  count and lowest in-process free; flag OVERCOMMIT if any hook total ≥ 16,311 MiB
  (WSL grants beyond the card silently — C0: 16,421 MiB on a 16,311 MiB card,
  0 failed calls). Record engine budget = ratio × reported total and
  budget − hook-total gap per cell.

## Cell provenance (required per cell — D:170)

Engine git sha (editable tree `~/moei-engine/MoE-Infinity` @
033798811664f5d89cae58049ff16e912ebc5862, moe_infinity 0.2.3.dev58), `_store.so`
sha256 captured at cell start, libcudahook3.so sha256 (above), GPU1 card id +
16,311 MiB total, driver version, co-tenant holders before/after, load-gate reading
at launch (block-until-quiet, 3600 s budget, launch only at load < 2.0; GPU 0
untouched — shared CI runner).

## B4 scope note

B4 (27B MTP budget arithmetic) belongs to the separate MTP design (CD 2026-11-14T21:11
section 4), not this memory-accounting experiment; out of scope here by the ruled order
(CD:84: memory accounting first).

## Extraction discipline

All doc numbers script-computed from frozen cell records and pasted verbatim; ratios
and percentages computed with explicit denominators (direction discipline); no
hand-typed machine-derivable values (panel rule). Battery seal (tgz + sha256) before
any writeup. One receipt, POST-once with readback, ledger re-read before posting.

# ADDENDUM75: exp752 settle. Retire-by-event — replacing `cudaLaunchHostFunc` retirement with CUDA event polling (Winnie WSL2, GPU1)

Settled 2026-11-08 from the gated run 2026-11-07T20:01:11Z → 23:51:31Z on Winnie (WSL2 Ubuntu, RTX 5060 Ti 16 GB on GPU1,
PCIe gen4 x8). Private patched build: moei-engine HEAD `0337988` + `exp752.patch`, `_store…so` sha `95da1b70…`, loaded from
`/home/mfeth/exp752/src` (ENV.txt); shared engine tree and venv untouched. Mode selected at runtime by `MOEI_EXP752_MODE`
(H=upstream hostfn, R=event-poll retirement, RC=R + completion-wait by event query). Spend $0 (owned hardware).

- Freeze `aa3a5f6` (PREREG, patch, frozen scripts, disclosed untimed smoke). AMENDMENT1 `18f3424` + `f5af802` (grouped-path
  coverage check, independent review RUN-SAFE, poll-latency interpretation note) — both committed after runner start (20:01Z)
  but **pre-data**: `out/` held only ENV.txt and RUN_SHA256, and the first cell started 21:31:44Z.
- Independent code review (gpt-6.1-sol, read-only): no blockers; two minor off-success-path defects (R: missed decrement if
  event creation throws → teardown hang; RC: event-handle leak at teardown). Neither affects a normal run; both must be fixed
  before any upstream PR. Full text in `amendment1/REVIEW.md`.
- Every number below is asserted against `raw/` by `gen_addendum75.py`, which prints ALL ASSERTS OK. The frozen analyzer,
  re-run on Mack against pulled `raw/out`, reproduces `raw/out/verdict.txt` byte for byte. Transfer integrity: 55/55 files,
  sha256 computed on Winnie before pull and re-verified on Mack (`raw/MANIFEST.sha256`).
- `RUN_SHA256` matches the freeze artifact hashes for all 9 runner files and the patched `.so`.

## Sealed verdict
`VERDICT RETIRE:NO-CHANGE(PARITY-NA)|COMPL:FASTER(PARITY-NA)|TOTAL:FASTER(PARITY-NA)`

Clean-cell arm means (median ms/tok per prompt, mean over clean cells; bar THR=3.0 ms/tok, Welch-free separation rule per
freeze):

| arm | ms/tok | busy | idle | n | cells |
|---|---|---|---|---|---|
| hf (transformers bf16 reference) | 31.79 | 14.15 | 17.62 | 3 | hf_1..3 CLEAN |
| H (upstream hostfn) | 93.90 | 38.37 | 55.81 | 2 | H_2, H_3 (H_1 excluded) |
| R (event-poll retirement) | 90.98 | 41.28 | 50.82 | 3 | R_1..3 CLEAN |
| RC (R + completion by event) | 85.70 | 39.24 | 47.59 | 2 | RC_2, RC_3 (RC_1 excluded) |

- **RETIRE R−H = −2.92 ms/tok** (idle −4.99, busy +2.91): inside the 3.0 bar → **NO-CHANGE**. The pre-registered 0.30-probability
  branch fired: retirement-callback stalls are mostly hidden behind other critical-path work.
- **COMPL RC−R = −5.28 ms/tok** (idle −3.23, busy −2.04), separated_fast → **FASTER**. The minority (0.30) prediction hit.
- **TOTAL RC−H = −8.20 ms/tok** (idle −8.22, busy +0.87), separated_fast → **FASTER**: 8.7% off the baseline engine.
- **GAP H−hf = 62.11 ms/tok** (consistent with exp746's 60.14 on this host); RC closes **0.132** of it (descriptive). Residual
  gap after RC ≈ 53.9 ms/tok.
- Covariate check: `foreign_other_gpu_max = 0` across all clean cells.

## Per-callback arithmetic (descriptive, from sealed numbers)
- 144 retirement hostfns/token: R−H −2.92 → ≤ ~20 µs effective per callback — mostly overlapped, consistent with exp747's
  finding that the 522 µs no-op stall cannot all serialize (144 × 0.522 = 75.2 ms/tok > whole gap).
- ~16 completion-wait hostfns/token: RC−R −5.28 → ~330 µs effective each. **Host functions on the caller-wait path cost far
  more than async bookkeeping ones.** This is the mechanism the next engine change should exploit.

## PARITY: why NA, and what the tokens actually show
- Frozen rule: greedy token ids must match across arms, with H cells self-consistent first, over all manipulation-valid cells
  (clean or not).
- **H_1 — the contaminated baseline cell — diverges from quiet H_2/H_3 at prompt 5, token 31** (id 0 "!" vs 14 ","; both n_new=64).
  H self-consistency therefore fails and R/RC parity is reported **NA**. The analyzer's `(PARITY-NA)` tags are this rule firing,
  not a patch failure.
- **All 8 quiet engine cells (H_2, H_3, R_1–3, RC_1–3) are byte-identical across all three arms** (6 prompts, greedy). The HF
  reference matches the engine consensus on prompts 0 and 5; prompts 1–4 differ (known engine-vs-HF bf16 numerics; prompt 4
  engine EOS at 21 tokens vs HF 64 — descriptive only, parity is defined between engine arms).
- So the intervention **preserves outputs exactly wherever the baseline is itself reproducible**.

## Secondary observation: baseline contention nondeterminism (new candidate)
H_1 ran at quiet-wait TIMEOUT (5412 s, as designed) under ci-runner + foreign-GPU contamination, load_mean 21.52, sharing GPU1
with another lane's `gen.py` at 99% util. Its greedy output changed (1 of 6 prompts, from token 31) while all dispatcher
counters stayed identical (route_failures 0, stale_quarantined 0, route_batches 1040, completion_events_retired 9924,
grouped_batches 0). **Silent output change under contention in the unpatched baseline path.** Mechanism unknown (candidate:
float-atomic reduction order under preemption); 1 cell / 1 prompt, so this is an observation, not a characterization.
Follow-up candidate: contention-determinism probe (same cell quiet vs contended, N repeats, logit-margin at divergence).

## Integrity, exclusions, timeline
- 12 cells (3 orderings × 4 arms), GPU1, ratio 0.75, stress=0, quiet-gated per exp746 AMENDMENT1 combined wait (GPU + CPU +
  CI-runner + Ollama probes).
- **H_1 EXCLUDED** (ci-runner-active; gpu-contamination; load-mean 21.52 > 4.0) and FLAGGED by the monitor (190 samples).
- **RC_1 EXCLUDED** (ci-runner-active at start; conservative rule; its timing 90.66 was consistent with RC_2/3 but the rule is
  the rule).
- The other 10 cells started QUIET (wait 0–4550 s), load 0.89–2.07, runner workers 0, foreign_any=0, Ollama gate passed.
- AMENDMENT1 coverage check: `grouped_batches = 0` in all 9 engine cells → **A1 ALL-PER-EXPERT** (the patched per-expert path
  was the exercised path; the unpatched grouped path never ran).
- Manipulation check: every engine cell logged exactly its own `exp752 mode=N` banner and `gpu_route_effective=True`.
- Pre-freeze smoke (disclosed, untimed): all modes RC=0, banners correct, H/R/RC token hashes identical; its speeds were
  contaminated and were never used.

## Predictions vs outcome (pre-registered in freeze)
- RETIRE: P(FASTER)=0.60, Δ −8…−30 → **missed**; NO-CHANGE (P=0.30 branch) fired.
- COMPL: P(FASTER)=0.30, ≤ ~8 ms possible → **hit**: −5.28.
- PARITY: expected OK, P(FAIL)=0.05 → no arm broke parity; frozen rule reports NA solely via the contaminated baseline cell.

## What this settles
1. **Completion-wait host functions are a real, removable cost on WSL**: event-query release buys −5.28 ms/tok over R and
   −8.20 over baseline, nearly all of it GPU-idle time, with exact token parity on quiet cells.
2. **Retirement callbacks are largely overlapped** (−2.92, under the bar): removing them alone is not the win. Per AMENDMENT1's
   note, R's NO-CHANGE also cannot be read as "hostfns are free" — single-thread poll ordering may offset part of the gain;
   RC isolates the caller-wait path where polling replaced a callback the caller waits on.
3. The engine-vs-HF gap survives this fix at ~54 ms/tok → next candidates unchanged: `io-overlap-in-engine` (#3),
   `exec-path-handoff`; plus the new contention-determinism probe above.

## Caveats
- WSL2 single host; clean n=2 for H and RC. exp751 suggests native-Linux gains would be smaller (native hostfn stall 108.5 µs
  vs WSL 522 µs) — a native RC replication is the matched follow-up.
- RC has a known teardown-only event leak (review finding 2); not upstream-PR-ready without the two fixes.
- H_1/RC_1 exclusions were rule-driven; the sealed verdicts stand on clean cells only. Descriptively, RC_1's timing (90.66
  ms/tok) sat inside the R range and below the H clean minimum, but no counterfactual verdict is claimed.

## Files
`raw/out/` (54 files: 12 cell JSONs, logs, util.csv, load, FLAGGED, precell, ENV.txt, RUN_SHA256, verdict.txt), `raw/run.log`,
`raw/MANIFEST.sha256` (55 entries, Winnie-side hashes), `gen_addendum75.py` (ALL ASSERTS OK), `freeze/`, `amendment1/`.

# PREREG-769 — unprofiled OS-counter differential: where does the spec-prefetch wall cost land?

**Type:** 2-cell UNPROFILED measurement on Winnie WSL (no py-spy — first measurement able to see the +7.8 s wall cost; exp767/exp768 established it is invisible to in-process 100 Hz sampling).
**Envelope:** verbatim exp762/764/767 (OLMoE-1B-7B-0125-Instruct, src753 @ b7f6ca4, lcnu r=0.75, threads 4, gpu-route off, CUDA_VISIBLE_DEVICES=1, 6 prompts × 64 tok, warmup 1). Cells: OS_LGC (`off off off`), OS_SPEC (`on off off`).
**Instrument:** `sampler769.py` — separate process, 20 Hz procfs reads (/proc/pid stat+status+io), started per cell by the runner; engine gains ONLY an additive `--pidfile` hook (engine_arm769.py = engine_arm767.py 9e874ab2e5a7b66e + 2 lines, diff verified). Sampler overhead lands outside the engine process (no GIL interference); procfs reads ≈ µs.
**Windows:** per arm, epoch [min(win_full[0]), max(win_full[1])] over the 6 prompt rows (warmup excluded by construction). W(arm) = Σ (t_1tok_s + t_full_s).

## Frozen decision rule (tau_wall = 2.0 s; a priori anchors tied to exp763's +7.8 s)
- rc=9 IDENTIFY-FAIL: SRC_HEAD ≠ b7f6ca4
- rc=4 DATA-FAIL: missing/short artifacts (<6 rows, <100 in-window samples/arm)
- DW ≥ τ, in order:
  - rc=1 **D1 CPU-DOMINATED**: Dcpu ≥ 0.8·DW (cost = real CPU work)
  - rc=2 **D2 FAULT-DOMINATED**: Dmajflt ≥ 100,000 or Dminflt ≥ 5,000,000
  - rc=6 **D3 SCHED-CONTENTION**: Dnonvoluntary ≥ 500,000
  - rc=7 **D4 UNATTRIBUTED**: none → successor perf-stat (bandwidth/caches) + strace-c
- DW ≤ −τ: rc=8 D6 REVERSED
- |DW| < τ: rc=5 **D5 NO-REPLICATION** (single-run envelope; successor N-run wall replicate)

Covariates (no gates): RSS peak, io R/W, thread peak, voluntary switches, tok/s means.

## Honest caveats (frozen)
- Single run per arm: exp763's +7.82 s was a 5-run mean; run-to-run variance may swallow it → D5 is a legitimate outcome, not a failure.
- /proc utime/stime aggregates the thread group; per-thread attribution is a successor, not this experiment.
- WSL2 kernel counters (faults, nonvol) are host-kernel values; identical protocol both arms → differential valid.

## Fixture battery (fixtures769.py, pre-freeze on Mack)
Synthetic json+csv pairs per branch: D1, D2, D3, D4, D5, D6, IDENTIFY-FAIL, DATA-FAIL (rows<6), DATA-FAIL (samples<100) → 9 cases, all-PASS required.

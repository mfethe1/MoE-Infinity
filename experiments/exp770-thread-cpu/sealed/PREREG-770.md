# PREREG-770 — per-thread CPU attribution of the spec-prefetch cost

**Question.** exp769 (D1 CPU-DOMINATED) showed the +7 s spec-prefetch wall
cost is real CPU compute process-wide. Which thread class burns it: the main
(GIL/python) thread, an explicit `threading` worker (the prefetch thread), or
the unnamed native pool (torch intraop/comm)?

**Design.** 2 cells, envelope verbatim from exp769 (OLMoE-1B-7B, src753 @
b7f6ca4, lcnu r=0.75, threads 4, 6 prompts × 64 tok, warmup 1, unprofiled —
no py-spy). Cells: `OS_LGC` (off off off) vs `OS_SPEC` (spec-prefetch on).
Instrumentation: engine byte-identical to exp769 (pidfile hook; sha
1f119bd017985083); sampler770.py = sampler769.py process-level CSV **plus**
per-tick `/proc/<pid>/task/*/stat` aggregation by bucket — bucket `MAIN` iff
tid==pid, else thread comm; row = t,bucket,nthreads,utime_sum,stime_sum.

**Frozen decision rule** (analyze770.py, battery 9/9 before staging).
tau_cpu=4.0 s, tau_bucket=2.0 s, f=0.5; windows = [min(win_full[0]),
max(win_full[1])] over 6 prompt rows; bucket delta = last − first in-window
utime+stime occurrence; dbucket = SPEC − LGC.
- rc=9 IDENTIFY-FAIL: SRC_HEAD ≠ b7f6ca4
- rc=4 DATA-FAIL: missing/short artifacts; <100 oscsv in-window samples/arm;
  <50 tidcsv in-window rows/arm; coverage (Σ positive dbucket / Dcpu) ∉ [0.5, 2.0]
- rc=5 NO-SIGNAL: |Dcpu| < tau_cpu
- rc=8 REVERSED: Dcpu ≤ −tau_cpu
- top = argmax dbucket; threshold = max(tau_bucket, f·Dcpu)
  - rc=7 DIFFUSE: top < threshold
  - rc=1 MAIN-BOUND: top == MAIN → GIL/python path; successor: targeted
    main-thread py profile of the spec predictor loop
  - rc=2 THREADED-WORKER: top matches `^Thread-[0-9]+$` → prefetch worker
    class; successor: locate thread func, amortize/batch
  - rc=3 POOL-UNNAMED: otherwise → torch intraop/comm pool; successor: perf
    + thread-name injection

**Void conditions.** Any change to sampler/analyzer after freeze; probe of
live engine env other than liveness (RSS/pid/rows); interference gate tripped
(busy-gate units exp746–exp767 + exp770).

**Success criterion.** A single rc ∈ {1,2,3,7} with coverage in range names
the thread class carrying ≥50% of the CPU cost, or shows it diffuse.

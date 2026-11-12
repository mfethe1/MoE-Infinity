# EXP-797 — DESIGN (preregistered BEFORE run)

## Hypothesis (promoted from exp796)
Inline steal (caller-thread GroupedExec) is host-CPU-contention resilient:
passive-wait decode depends on worker-thread wakeups (starved under load);
steal executes on the caller thread.

## Cells (binary eba566fb; probe795.py verbatim c995fa174be30136; 8 prompts
x 32 tok; grouped; ratio 0.5; CUDA_VISIBLE_DEVICES=1)
- SQ steal ON, quiet      (env unset, no burners)
- SB steal ON, loaded     (env unset, 4 burners pinned cores 0-3)
- PQ passive, quiet       (MOE_INLINE_WAIT=0, no burners)
- PB passive, loaded      (MOE_INLINE_WAIT=0, burners)
Order per rep: SQ, PB, SB, PQ (cell types interleaved); 3 reps = 12 arms.
loadavg logged before/after every arm. Burners: taskset -c 0-3 busy-loops.

## Decision rules (pre-declared)
- G1 resilience: slowdown_passive - slowdown_steal >= 15 pts, where
  slowdown_X = (mean(XQ) - mean(XB)) / mean(XQ) * 100. AND SB >= 1.10 * PB.
- G2 absolute: SB >= 1.10 * PB pooled means.
- G3 quiet-host steal benefit: SQ >= 1.05 * PQ (replicates exp795 obs).
- G4 correctness floors: mean pairwise H within SB <= mean pairwise H
  within PB + 30 (steal adds no nondeterminism beyond passive); report all
  floors vs intrinsic 85/256. Bit equality is NOT a gate (exp796 lesson).
- No promotion on any gate if burner arms show loadavg < 2 (burners failed
  to bite) — re-run instead of interpret.

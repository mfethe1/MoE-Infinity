# EXP-799 — DESIGN (preregistered BEFORE run)

## Question (from exp798)
Does the inline-steal WALL-VARIANCE collapse replicate at n>=5/arm in a
CI-dead window, and does the mean effect clear the gate cleanly?

## Arms (binary eba566fb; probe794 verbatim 073e8f51ad375ff3; ratio 0.5;
        grouped; fresh process each; CUDA_VISIBLE_DEVICES=1)
W (throwaway warmup), then F1 N1 F2 N2 F3 N3 F4 N4 F5 N5
(F = MOE_INLINE_WAIT=0 passive; N = steal ON). 11 processes.

## Decision rules (pre-declared; variance PRIMARY, mean secondary)
- P1 variance (primary): CV(N) <= 0.4 x CV(F), CV = sd/mean of the 5
  decode walls per arm. PASS -> variance collapse replicated.
- S1 mean (secondary): wall(N) <= 0.97 x wall(F).
- S2 refutation: wall(N) >= wall(F) AND CV(N) >= CV(F) -> refuted.
- Env gate: 1-min loadavg < 2.5 at each arm launch AND completion; any arm
  outside -> park without interpretation.
- Wait/enqueue shares recorded for mechanism classification only.

## Claim if P1 and S1 both pass
Inline steal reduces decode-wall variance >=2.5x and mean wall >=3pct on a
quiet host, same binary, env-toggle arms only.

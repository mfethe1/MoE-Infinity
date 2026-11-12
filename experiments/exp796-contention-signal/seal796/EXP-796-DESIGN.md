# EXP-796 — DESIGN (preregistered BEFORE run)

## Premise (from exp795 VOID)
exp795's cross-binary noise floor (64/256 tokens) masked the treatment.
Hypothesis: the grouped kernel's atomicAdd accumulation makes greedy tokens
non-deterministic across runs even on the SAME binary/config; the
MOE_GROUPED_DETERMINISTIC=1 flag (exp788) removes it, enabling a valid
same-binary token gate for the inline-steal patch.

## Arms (ALL on patched binary eba566fb; 8 prompts x 32 tok; fresh process;
       CUDA_VISIBLE_DEVICES=1; grouped; ratio 0.5)
- P1 P2      : MOE_INLINE_WAIT=0, no determinism flag  -> same-config noise floor
- DP1 DP2 DP3: MOE_INLINE_WAIT=0 + MOE_GROUPED_DETERMINISTIC=1 -> control
- DA1 DA2 DA3: inline steal ON (env unset) + MOE_GROUPED_DETERMINISTIC=1 -> treatment

## Decision rules (pre-declared)
- Gate 0 determinism floor: H(P1,P2)>0 AND H(DPi,DPj)==0 for all pairs =>
  flag valid, proceed. H(P1,P2)==0 => kernel already deterministic: then
  exp795's P-vs-A divergence was steal-path-attributable -> treat Gate 1
  failure as real corruption signal. H(DPi,DPj)>0 => flag insufficient ->
  VOID token gates, report.
- Gate 1 correctness: H(DPi, DAi)==0 for all i (and DAi vs DP1). Any
  divergence under the determinism flag = real steal-path corruption =>
  VOID, no perf interpretation.
- Gate 2 perf: promote iff mean(DA) >= 1.05 x mean(DP) over 3 reps each.
  With perfect rep-mean separation -> promote outright; >=1.05 without
  separation -> one confirmatory batch (3+3 more reps) before promotion.
  <1.05 -> NO-MOVE for inline steal under determinism.
- Observational only: DP vs P cost of the determinism flag itself.

Probe: probe795.py verbatim (sha c995fa174be30136; captures token_ids +
pooled mean). Env toggles passed by run script only.

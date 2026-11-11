# PREREG-787 — grouped-decode launch-config sweep on consumer sm_120 (frozen BEFORE launch)

**Question.** Within the shipped `MOE_GROUPED_MOE_CFG` override surface (the 8
instantiated (mt,wr,wk,u) launch configs of `grouped_moe_decode_pro6000.cu`), does
any configuration beat the shipped default table for OLMoE-1B-7B batch-1 decode on
consumer sm_120 (RTX 5060 Ti, 36 SM, 32 MiB L2) at ratio 0.25 with the hw-gate
lifted (`MOE_INFINITY_UNVALIDATED_HW=1`, exp786 regime)? Secondary: does WK=1
(no K-split) reduce the grouped path's run-to-run output nondeterminism
(exp786: default table 14/24 same-sha at ratio 0.25)?

**Arms** (all uhw=on, ratio 0.25, GPU1, threads=4, lcnu, bf16 store, greedy, 24
prompts x 32 new tokens, 2 reps each):
- C = shipped table (default up=(1,1,8,2), down=(1,2,4,4) for T=1, H=2048, I=1024)
- W = `1,8,1,2;1,8,1,2` (WK=1 both projections — K-split localization arm)
- B = `1,2,4,4;1,1,8,2` (best 8-prompt probe hint, +1.4%)

**Primary metric.** Pooled per-prompt mean decode tok/s per arm (48 samples) vs C.
**rc map:** 1 MAJOR-POS delta >= +3.0% / 2 MILD-POS +1.5..+3.0% / 3 NO-MOVE
-1.5..+1.5% / 4 REGRESSION <= -1.5% / 9 DATA-FAIL banner|identity|count violation.
Verdict = best (lowest) rc among W, B. Cross-arm output divergence is ALLOWED
(different launch geometry changes numerics).

**Determinism is DESCRIPTIVE, not gated** (frozen decision, from exp786 evidence:
grouped kernels are nondeterministic via atomic reduction order; requiring
bit-identity would void every grouped cell by construction). Per arm we REPORT
same-sha count between reps a/b. Mechanism read: if det[W] >> det[C], K-split
contributes materially; if det[W] ~ det[C], expert-order atomics dominate.

**Gates.** Per cell: RC=0; `grouped_decode_effective` True; `unvalidated_hw_env`
"1"; `grouped_cfg_env` exactly matches the arm's string (C: absent/None);
24 rows; n_new=32 each. Runner scrubs MOE_GROUPED_MOE_CFG outside cells; engine
sets it before importing moe_infinity. Identity: src753 HEAD b7f6ca4, import path,
_store sha recorded. Quiet gate per cell (allquiet746.sh, 90-min budget).

**Probes disclosed (pre-freeze, 8 prompts x 24 tok, ratio 0.25, 2026-11-11).**
BASE(none) 11.032; A_u4 10.998; A_u8 10.795; A_w242 11.054; A_w244 11.172;
A_w248 11.017; D_1182 11.189; D_1184 10.836; D_1188 10.607; D_d242 10.807;
D_d248 11.100; BASE2(none) 10.669 — baseline drift 3.3% run-to-run at 8-prompt
power, so all single-config deltas are within noise; this run (n=48/arm) resolves
~±1.5%. WK1 pair (11.165/11.084) 6/8 same-sha across fresh processes vs 4/8 vs
default — speed preserved, nondet only partially reduced.

**Void conditions.** Identity fail, engine banner absent, wrong cell count,
scrub leak (grouped_cfg_env set on a C cell), or GPU co-tenant FLAGGED — attempt
is VOID, fresh prereg required. No post-hoc gate edits on sealed data.

# PREREG-780 — attention-implementation wall test (sdpa vs eager)

Registered 2026-11-11 before any exp780 run. Prior chain: expert lane closed
(1% of samples, exp777/exp778); generate machinery exonerated (exp779 rc=7);
attention ~36% of non-load samples is the remaining first-order block.

## Question
Is the attention share addressable by kernel choice (fused sdpa vs eager) at
this workload's context lengths, or is it irreducible math?

## Design (single variable)
- Envelope identical to exp777–779: OLMoE-1B-7B-0125-Instruct via
  MoE-Infinity, src776 AS-BUILT (sha 3571f714c811e1c7), lcnu r=0.75, threads 4,
  gpu-route off, spec-prefetch on/overlap off/policy off, 24 prompts x 64
  tokens (manual-loop greedy decode, DynamicCache), warmup 1,
  CUDA_VISIBLE_DEVICES=1, py-spy 50 Hz + OS sampler both cells.
- PY_SDPA: engine_arm780.py --attn-impl sdpa; PY_EAGER: --attn-impl eager.
  Patch applies to every attention module's _attn_implementation + model
  config; per-module scan must verify the target impl exactly (attn_ok gate)
  and the log banner "exp780 impl=<impl> ... ok=True" must be present.
- flash_attn availability recorded in ENV.txt (report-only; not an arm).
- W(cell) = sum over 24 rows of (t_1tok + t_full); gain = (W_eager −
  W_sdpa)/W_eager.

## Frozen decision rule
- rc=9 IDENTIFY-FAIL: env/src/src776-sha/engine sha mismatch; impl banner
  missing or attn_ok false or attn_impl field wrong in either cell json.
- rc=4 DATA-FAIL: BADIO non-empty; either cell RC!=0/missing/<20 rows; sdpa
  arm outside covariate gate [142.50, 237.50] (exp779 manual-loop ref
  W=190.00 ±25%); any row n_new != 64.
- rc=1 KERNEL-MATTERS: gain >= 0.10 — successor FA2 / compiled attention.
- rc=2 MILD: 0.03 <= gain < 0.10.
- rc=7 NO-KERNEL-GAIN: gain < 0.03 — attention irreducible at this context
  length; redirect lane.
- rc=3 SDPA-REGRESSION: gain <= −0.03 (eager faster) — default impl wrong for
  this envelope; recommend eager.
- rc=5 SDPA-REGRESSION-LARGE: gain <= −0.10.

## Report-only (not gates)
attn_default sets; out_sha agreement between arms; tok/s; flash_attn presence.

Failure discipline: nonzero-RC cells recorded, not voided; VOID only for
premise-false attempts.


## Attempt-2 (2026-11-11, after attempt-1 VOID)

Attempt-1 VOID, premise-false: engine patched per-module `_attn_implementation`
attributes; transformers 5.22.1 attention modules carry no such attribute
(nmod=0, banner gate exit 3 before any cell data). Mechanism corrected, not
the question: implementation is resolved at call time from the shared
`config._attn_implementation` via `ALL_ATTENTION_FUNCTIONS.get_interface`
(with the model's own `eager_attention_forward` as fallback, since "eager"
is not registry-registered).

Attempt-2 engine mechanism (engine_arm780.py sha16 1c6427605f661bc9):
set shared model config `_attn_implementation` post-load; VERIFY (a) config
value equals target, (b) all 16 OlmoeAttention modules share that exact
config object (identity check), (c) registry/fallback resolves the name to
a concrete function (sdpa -> sdpa_attention_forward; eager ->
modeling_olmoe.eager_attention_forward via fallback). Probe evidence
(default='sdpa', nmod=16, shared=True, both impls resolve). Decision rule,
gates, covariate, arms, prompts: UNCHANGED from attempt-1 prereg above.

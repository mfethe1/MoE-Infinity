# exp714 — PREREG: bar-constrained joint BO of CostFit (M × G × HL) with a held-out synthetic split

Lane 79990 / STACK-1001. Successor of exp713 (verdict CLAMP-REPAIRS:NO-GAIN, ADDENDUM57, ledger #236):
the exp669 BO pointer does not transfer even when made safe. exp713's pre-registered next-hint:
"close BO line; next joint 2-trace BO with bar-constrained objective". Frontier item "joint 2-trace BO"
(listed under exp675's later stages; exp675 stage A was a different question — shared-state metadata).

## Question

exp669 optimized the WRONG thing for what later gates test: f = worst deficit on the 2 real traces only.
Its optimum (exp674 BO point) was unsafe on synthetic streams (exp674 SAFETY-BROKEN) and, once gamma-clamped
safe, cost −0.0534pp mean vs center (exp713). exp714 asks: if the BO objective is the paired MEAN gain vs
center, the frozen safety bars are CONSTRAINTS, and the training set includes synthetic streams, does the
optimum (a) have any training headroom over center (≥ +0.05pp), and (b) carry that gain to HELD-OUT
synthetic streams without breaking safety?

## Design (frozen)

- Training set T: (i) both real traces exactly as exp669 (qwen30b 10 caps, granite 5 caps; sealed exp669
  `evaluate`, base CSV standalones); (ii) synthetic streams idx {0,2,4,6,8,10} of exp670's 11 configs,
  6 caps [128..4096], informative cells only (|lcnu − s3fifo| ≥ 0.1pp).
- Held-out set H: synthetic idx {1,3,5,7,9} (one per skew×locality interleave + one E32 stream),
  6 caps, informative cells only. H is never seen by the BO loop.
- Objective (maximize): J(x) = 0.5·mean_real(rate_x − rate_center)·100 + 0.5·mean_T-synth-informative(...)·100.
- Constraints: c(x) = max(real worst deficit vs best standalone, T-synth worst informative deficit) ≤ 0.5pp;
  s(x) = max switches over all T cells ≤ 6; loop==prop accounting at every cell.
- Seeds (5, all evaluated, not cited): exp713's five arms center / bo / clamp / clampM / clampH (params
  parsed at runtime from the sealed exp713 runner, which parses exp674/exp712).
- Search space: exp669 BOUNDS unchanged (M [0.001, 0.02], G [0.0005, 0.01], HL 4096·64^u ∈ [4096, 262144]
  — upper end is the HL cap-ceiling region).
- Surrogate: exp669's sealed GP class (RBF ls 0.25, signal 1, noise 1e-4, fixed) — but inputs are mapped
  to the UNIT CUBE first. DESIGN FIX (disclosed): exp669 fed raw M/G (~1e-3 scale) to an RBF with
  lengthscale 0.25, so its kernel was effectively blind to M and G (consistent with its pearson 0.122).
  Three GPs: −J, c, log1p(s). Acquisition: EI(−J) × P(c ≤ 0.5) × P(s ≤ 6); 2048 uniform candidates per
  iteration; RNG seed 20261105. Budget: 20 BO trials after the 5 seeds.
- x* = feasible point (seeds included) with max J; ties → earliest. x* is then evaluated on H against
  center on H (paired).
- Reused SEALED code imported by path (not copied): exp669 run_bo.py (MODELS, BOUNDS, evaluate, GP, phi,
  to/from_params, base_rows), exp713 run_gclamp.py (gen_stream, stream_sha, make_costfit, evaluate,
  stream_cfgs, PARAMS). All shas in ARTIFACT.sha256.

## Gates

- H0 REPLICATION (hard): (a) every seed arm's T-synth cells == sealed exp713 `cf_<arm>` cells exactly
  (5 arms × 36 cells), T and H standalones lcnu/s3fifo == exp713 exactly, H-center cells == exp713
  `cf_center`; (b) real-trace center == sealed exp668 cell m0.005_g0.0025 and real-trace bo == sealed
  exp669 trial 1 (rate, switches, deficit_pp per cap, 15 caps each). Streams asserted sha8 == exp670.
- H4 ACCOUNTING/DETERMINISM (hard): loop==prop at every evaluated cell (T, real, H); x* re-evaluated
  (real + T + H) in-process and must match exactly.
- H1-train HEADROOM: J(x*) ≥ +0.05pp.
- H1-held SAFETY: on H informative cells, x* worst deficit ≤ 0.5pp, 0 cells over, max switches ≤ 6.
- H2-held GAIN: paired mean delta (x* − center) on H informative cells.

## Verdict ladder (frozen, evaluated top-down)

1. ¬H0 or ¬H4 → ACCOUNTING-FAIL
2. J(x*) < +0.05pp → NO-TRAIN-HEADROOM (center is ~optimal under the bar-constrained mean objective;
   tuning line closes)
3. ¬H1-held → HELDOUT-UNSAFE (the trained point overfits safety to T)
4. H2 ≥ +0.05pp → TRANSFERS-GAIN
5. H2 ≥ −0.05pp → TRANSFERS-NONINFERIOR
6. else → NO-TRANSFER

## Consequences (pre-registered)

- TRANSFERS-GAIN → x* is the first tuned point with held-out gain; next = real-trace confirmation on a
  third trace family + cap-ceiling HL probe at x*.
- TRANSFERS-NONINFERIOR → safe but no measurable gain; prefer center (simpler); close tuning line.
- NO-TRAIN-HEADROOM → center is at the bar-constrained mean optimum within BOUNDS; close tuning line;
  next = shared-state N-way metadata (exp675 stage B economics) — tuning no longer a lever.
- HELDOUT-UNSAFE / NO-TRANSFER → T-overfit; next = leave-one-family-out CV design before any further BO.

## Disclosures

- Synthetic streams only for H (no third real trace available locally); real traces enter only T.
- J weights real and synthetic means equally (0.5/0.5) — frozen choice, not tuned.
- 20 trials is a budget, not a convergence claim. Pearson(pred J, observed J) over trials is reported,
  not gated.
- Interpreter: /Users/mfethe/warp-work/exp650-moei-granite3b-trace-pr/.venv/bin/python (torch needed for
  real-trace load; system python3 lacks torch — smoke attempt 2 failed on that and is retained as
  smoke-attempt2.log). Smoke attempt 1 failed on a smoke-harness bug (expected-cell count 10 vs correct 8
  and a dict-key copy bug), retained as smoke-attempt1.log; neither touched the run logic.
- Smoke (SMOKE=1, disclosed, pre-freeze): S1 sha assertion bites; S2 full-N synth H0 on stream 4 × caps
  {512, 2048} for center/bo + standalones vs exp713 (8 cells); S3 H0 negative control; S4 real-trace H0
  center vs exp668 + bo vs exp669 trial 1 (90 cells); S5 reduced e2e (short streams/traces, 2 trials) run
  twice → identical, well-formed (its verdict/H0 are NOT results — short streams cannot match references);
  S6 stats arithmetic on hand-built cells + ladder 7/7 + T/H partition.

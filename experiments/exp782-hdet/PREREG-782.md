# PREREG-782 — H-vs-RC decode determinism under identical co-tenancy

**Registered before any exp782 run. Not adjustable after data arrive.**

## Question

Does greedy decode output byte-stability under co-tenancy differ between the
legacy host-callback completion path (H, `MOEI_EXP752_MODE` unset → C++ banner
`exp752 mode=0`) and the event-poll path (RC, PR #353, `MOEI_EXP752_MODE=RC` →
`exp752 mode=2`), on the same build, same GPU, same manipulations, same prompts?

## Prior evidence (why this is the missing piece)

- exp752: H_1 (foreign GPU + load 21.5) diverged at prompt 5 token 31; quiet H
  cells byte-identical to anchors (8/8).
- exp758: HB1 (busy co-tenant GPU) H-arm diverged; P34 arm byte-stable under the
  identical co-tenant. n=2 H cells, 1 diverged — incidental, not a powered A/B.
- exp760: RC under Q/C/G/CG contention — 0/10 valid cells diverged; pooled
  one-sided 95% CP upper bound 0.259. RC side measured; H side never powered.

exp782 supplies the H arm under the exp760 protocol, with fresh in-session RC
controls interleaved.

## Design

- Build: `/home/mfeth/exp759/src753` = PR #353 head `b7f6ca4d2caa5229698d78deb03b454fc20947dd` (frozen; runner identity-gates on this HEAD and on the import path).
- Engine: `engine_arm.py` byte-identical to exp760's (6 prompts × 64 new tokens, greedy, `--gpu-route on`, lcnu r=0.75, threads 4, warmup 1, GPU 1, `~/venvs/moei-engine`, torch pinned by venv).
- Only variable: per-cell `MOEI_EXP752_MODE`. H cells: env unset. RC cells: `=RC`. Banner in each cell log verifies which mode actually ran; wrong banner = invalid cell.
- Manipulations byte-identical to exp760: `gcol757.py --device 1 --alloc-gb 2` GPU co-tenant (G, CG); 12 CPU spinners (C, CG); started 10 s before engine load.
- Cells (serial, interleaved): QH1, QR1 (quiet anchors), GH1, GR1, GH2, CH1, CR1, GH3, CGH1, CGR1.
- Samplers/gates: mon760.sh + nvsamp.py 0.05 s; precell contamination CSV; allquiet746 gate; busy-roster of active units.

## Decision rule (analyzer `analyze782.py`, fixtures `fixtures782.py`)

Anchors: QH1 and QR1 must each be byte-identical to the sealed refs
(refs/RC_2.json == RC_3.json, exp760 lineage). A valid anchor diverging =
ANCHOR-FAIL (exit 2), no determinism verdict issued.

- rc=1 H-UNSTABLE-RC-STABLE: ≥1 valid contended H cell diverged, 0 valid contended RC.
- rc=2 BOTH-UNSTABLE: ≥1 each.
- rc=3 RC-UNSTABLE-H-STABLE (contradicts exp760).
- rc=7 BOTH-STABLE: 0 diverged; CP bounds printed per arm.
- rc=9 DATA-FAIL (missing anchor / no valid contended cells in an arm).

Divergence = any prompt's `out_ids` != sealed ref. Validity gates: mode banner,
foreign-app exclusion, manip-fail (C/CG loadavg mean ≥8; G/CG co-tenant present
AND util mean ≥20), precell contamination, short-run, missing out_ids, sampler
minimums. Invalid cells are excluded, never counted as stable.

## Predictions (registered)

- P(rc=1) = 0.55 — H under load diverges (exp752 1/1, exp758 1/2 with weaker perturbations), RC stays stable in-session as in exp760.
- P(rc=7) = 0.30 — both stable at n=5/n=3 (H divergence may need stronger perturbation than 2 GiB co-tenant).
- P(rc=2) = 0.10 — co-tenant strong enough to destabilize both paths.
- P(rc=3) = 0.05.

## Claim discipline

"No divergence observed in n cells under these manipulations" — never
"deterministic". Any rc=N verdict quotes counts and CP bounds. Walls/timing are
reported but are NOT gates in this experiment (determinism is the endpoint).

## Failure/attempt discipline

Attempt cap ~3. Runner bug caught by gates → mechanical fix + fresh freeze
before next attempt; premise change → VOID and fresh prereg. All numbers from
`analyze782.py` on frozen artifacts.

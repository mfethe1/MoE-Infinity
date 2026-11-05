# ADDENDUM 60 — exp714: bar-constrained joint BO of CostFit (M × G × HL) with a held-out synthetic split

Verdict: **NO-TRAIN-HEADROOM** — with the objective corrected to the paired MEAN gain vs center
(J = 0.5·real + 0.5·T-synth informative), the 0.5pp/6-switch safety bars as hard constraints, and
synthetic training streams included, 5 seeds + 20 constrained-BO trials inside the sealed exp669 BOUNDS
produce a best feasible point x* with J(x*) = +0.0301pp — below the frozen +0.05pp training-headroom
bar. Center (0.005, 0.0025, 32768) is at the bar-constrained mean optimum of this space; the CostFit
tuning line is CLOSED. Held-out numbers below are DESCRIPTIVE ONLY (ladder rung 2 fired before the
held-out gates): x* was safe on H (worst 0.094pp ≤ 0.5, 0 over, max switches
2) with mean +0.0441pp vs center on 26
informative cells. H0 replication 432/432 exact (0 mismatches); H4
accounting + in-process determinism held. Exit 0, 14130s.

## Design (frozen PREREG b64f46ea…)
- Training set T: both real traces exactly as exp669 (qwen30b 10 caps + granite 5 caps, base-CSV
  standalones) + synthetic streams {0,2,4,6,8,10} × 6 caps [128…4096], informative cells only
  (|lcnu−s3fifo| ≥ 0.1pp; 33/36). Held-out H: streams {1,3,5,7,9}, never seen by the BO loop
  (26/30 informative).
- Maximize J(x) = 0.5·mean_real(rate_x − rate_center)·100 + 0.5·mean_T-synth(...)·100 subject to
  c(x) = worst deficit vs best standalone ≤ 0.5pp and s(x) = max switches ≤ 6, loop==prop everywhere.
- Seeds: exp713's five arms (params parsed at runtime from the sealed exp713 runner chain). Space:
  exp669 BOUNDS M [0.001, 0.02], G [0.0005, 0.01], HL = 4096·64^u ∈ [4096, 262144]. Surrogate: exp669's
  sealed GP on the UNIT CUBE (disclosed design fix — exp669 fed raw ~1e-3 M/G to an RBF with ls 0.25,
  blinding its kernel to M/G; consistent with its pearson 0.122). Three GPs (−J, c, log1p s),
  acquisition EI(−J)·P(c≤0.5)·P(s≤6), 2048 uniform candidates/iter, RNG seed 20261105, 20 trials.

## Seeds (all evaluated, none cited as winner unless feasible-max)
| arm | margin | gamma | half-life | J pp | c pp | s | feasible |
|---|---|---|---|---|---|---|---|
| center | 0.005000 | 0.002500 | 32768 | +0.0000 | 0.176 | 4 | yes |
| bo | 0.001616 | 0.009990 | 160975 | -0.0615 | 0.779 | 2 | no |
| clamp | 0.001616 | 0.005740 | 160975 | -0.0245 | 0.355 | 2 | yes |
| clampM | 0.001616 | 0.005740 | 32768 | +0.0087 | 0.176 | 3 | yes |
| clampH | 0.005000 | 0.005740 | 160975 | -0.0650 | 0.779 | 2 | no |

## Best feasible points (x* = max J, ties → earliest)
| src | margin | gamma | half-life | J pp | c pp | s |
|---|---|---|---|---|---|---|
| trial:18 | 0.001028 | 0.004609 | 17382 | +0.0301 | 0.113 | 6 |
| trial:6 | 0.001186 | 0.000777 | 45395 | +0.0283 | 0.108 | 6 |
| trial:4 | 0.001021 | 0.003908 | 52468 | +0.0167 | 0.075 | 3 |
| seed:clampM | 0.001616 | 0.005740 | 32768 | +0.0087 | 0.176 | 3 |
| trial:1 | 0.001262 | 0.002239 | 130742 | +0.0070 | 0.091 | 3 |
| trial:16 | 0.001430 | 0.009782 | 4783 | +0.0057 | 0.351 | 6 |

x* = trial:18 — M 0.001028, G 0.004609, HL 17382: near-center gamma and HL at the space
floor region with a small margin; J +0.0301pp (real +0.0113,
T-synth +0.0488), c 0.113pp,
s 6. Runner-up feasible J +0.0283pp (trial:6). Every trial with
J above x* was INFEASIBLE (constraint violation), i.e. under the frozen bars the mean objective has no
exploitable structure beyond noise — 15/25 evaluated points feasible; pearson(pred J,
observed J) over the 20 trials = 0.572 (reported, not gated).

## Held-out H (DESCRIPTIVE — ladder ended at rung 2)
x* vs center on 26 informative H cells: mean +0.0441pp, worst
deficit 0.094pp at stream 3 (s=1.1 lam=0.0
E=128/L=48) cap 4096, 0 cells over the 0.5pp bar, max switches
2, 0 accounting violations. The corrected objective did not reproduce the
exp669→exp674 safety break on held-out streams — but with J(x*) under the training bar there is no
gain claim to transfer.

## Frozen ladder trace
1. ¬H0 ∨ ¬H4 → ACCOUNTING-FAIL — not fired (H0 432 cells, 0 mismatches; H4 det+acct True).
2. J(x*) < +0.05pp → **NO-TRAIN-HEADROOM — FIRES** (+0.0301pp < +0.05pp).
3–6 (HELDOUT-UNSAFE / TRANSFERS-GAIN / TRANSFERS-NONINFERIOR / NO-TRANSFER) not reached.

## What this settles (pre-registered consequence)
- Center is at the bar-constrained mean optimum within BOUNDS; the CostFit tuning line is closed:
  exp669 optimized the wrong objective (worst-deficit, real-only) → exp674 SAFETY-BROKEN → exp711/712/713
  attributed and clamped it (CLAMP-REPAIRS:NO-GAIN) → exp714 re-optimized the RIGHT objective with
  constraints and a held-out split and found no training headroom (best feasible +3.01bp).
  Tuning is no longer a lever on this family.
- Pre-registered next: shared-state N-way metadata economics (exp675 stage B) — the memory/time
  economics line, not the accuracy-tuning line.

## Integrity, determinism, disclosures (follow-up controller re-adjudication)
- run_barbo.py sha256 e21377bf36219ad3…, PREREG.md b64f46ea976481b7…, smoke.log
  8da20488845e30bd…, smoke-attempt1/2 d5009b319e9bbdb3…/8964f3112f08c458…
  == ARTIFACT.sha256 == local run dir; PREREG/runner/ARTIFACT == freeze-commit 07c696a blobs;
  freeze (2026-11-05 06:47:20 EST) precedes result mtime
  (2026-11-05 10:43:27 EST).
- Sealed deps sha-verified at adjudication time: exp669/run_bo.py 35b2498a49a16384…,
  exp713/run_gclamp.py b48e3cac282df532…, policies.py b38c55b86b704d3d…,
  policies_costfit.py 4bfff5bd4ada4b8e…, run_policies_real.py 46690edaaddf2128…,
  and the 4 sealed JSONs (exp668/exp669/exp670/exp713) == ARTIFACT == JSON-embedded sealed_inputs_sha256.
- Independently written adjudicator (this file): re-derived every stored summary (25 point scores,
  x* selection, held-out stats, seed T-synth stats, real center/bo stats) from raw cells and sealed
  refs; re-implemented the frozen ladder (7/7 boundary self-test) and recomputed pearson; parsed
  run.log and matched all 25 evaluation lines to the JSON.
- LIVE third-process re-evaluation through the SEALED code: all 11 streams regenerated and sha8-asserted
  vs exp670; H-side standalones/center/x* reproduced cell-exact vs the stored grids AND the sealed
  exp713 cells (90+ stored-ref comparisons + 150 live H cells); T-side x* summary reproduced;
  seed arms spot-reproduced at caps {128, 4096} on all 6 T streams (60 live cells vs exp713);
  real-trace center re-evaluated vs the sealed exp668 anchor (45/45 fields) and real-trace x*
  re-evaluated → live J +0.030075pp == stored, still < +0.05pp. Verdict-critical numbers are
  reproduced end-to-end outside the runner process.
- Disclosed granularity limits: the JSON stores raw cells only for H; seed T-synth cells and T
  standalones are verified at summary level from sealed exp713 raw cells plus the 60-cell live spot
  (not all 180 T cells live). The in-process x* re-evaluation (H4 det) is a stored boolean; the live
  cross-process reproduction above is the independent witness. pearson recomputes from stored pred_J.
- Launch 1 aborted after ~20 s with no output (missing persist flag); one bounded relaunch, unchanged
  runner (LEDGER.md). Disclosed pre-freeze smoke attempts 1–2 (harness count bug; system python lacks
  torch) retained in ARTIFACT; neither touched run logic. SMOKE_OK pre-freeze (S1–S6).
- Adjudication: 870/870 checks PASS, 1799s, interpreter exp650 venv python
  (torch 2.15.0), host Mack. No sealed artifact was edited or re-launched.

Data: exp714/exp714-barbo.json (+ this generator); PREREG.md / ARTIFACT.sha256 / smoke logs frozen at
07c696a. Follow-up controller re-adjudicated every gate programmatically: verdict
NO-TRAIN-HEADROOM stands.

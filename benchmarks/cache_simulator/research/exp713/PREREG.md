# exp713 — exp674 joint BO point with GAMMA CLAMPED to exp712's certified edge

Lane 79990 / STACK-1001. Pre-registered consequence of exp712 (verdict G-BOUNDARY@g4; its PREREG
G-BOUNDARY@g_j, j>=2 branch: "re-run the exp674 joint transfer with gamma clamped to the certified
edge").

## Question

exp674's BO point (margin M_BO, gamma G_BO, half-life HL_BO) was SAFETY-BROKEN out-of-family.
exp711 attributed the break to gamma (MG-BREAK:G-DRIVEN), and exp712 certified gamma safe at
center M/HL only up to g3 = G_EDGE. **If we keep exp674's BO margin and BO half-life but clamp
gamma to G_EDGE, is the joint point safe?** If it is not, which non-gamma knob makes the certified
gamma edge context-dependent?

## Frozen design

- Streams: EXACTLY exp670/674/710/711/712's 11 streams (seed scheme
  `default_rng(67020261104).spawn(11)`, same cfg order); runner asserts each regenerated stream's
  sha256[:8] equals research/exp670-synth.json. Caps {128..4096} (6); N = 638,208.
- Machinery: gen_stream / stream_sha / make_costfit / evaluate / stream_cfgs / run_all /
  h0_replication are copied byte-for-byte from the sealed exp712 runner, and the runner asserts at
  launch that they are AST-identical to the sealed copy (abort otherwise).
- Params parsed at runtime, never transcribed: (M_BO, G_BO, HL_BO) from sealed exp674
  `bo_params`; G_EDGE from sealed exp712 `certified_gamma_upper_edge` (runner asserts exp712's
  verdict is G-BOUNDARY@g*, G_EDGE is its g_{j-1}, and center gamma < G_EDGE < G_BO).
- Arms (costfit; margin, gamma, half-life), plus lcnu and s3fifo standalones:
  - `center` = (0.005, 0.0025, 32768): bookend, must equal exp674 cf_center
  - `bo` = (M_BO, G_BO, HL_BO): bookend, must equal exp674 cf_bo
  - `clamp` = (M_BO, G_EDGE, HL_BO): **PRIMARY**
  - `clampM` = (M_BO, G_EDGE, 32768): attribution, HL back at center
  - `clampH` = (0.005, G_EDGE, HL_BO): attribution, margin back at center

## Frozen hypotheses (bars identical to exp674/710/711/712)

- Informative cell: |lcnu − s3fifo| ≥ 0.1pp.
- H0 REPLICATION: per cell, cf_center == exp674 cf_center, cf_bo == exp674 cf_bo, and
  lcnu/s3fifo == exp674 (66 cells x 4 = 264 exact dict matches).
- H1 SAFETY (per arm): worst informative-cell deficit vs best standalone ≤ 0.5pp AND switches ≤ 6
  on every informative cell.
- H2 TRANSFER (clamp only): paired mean delta (clamp − center) over informative cells ≥ −0.05pp.
- H4 ACCOUNTING: loop rate == property rate every cell, every arm; two full runs bit-identical.

## Frozen verdict ladder

- ACCOUNTING-FAIL iff ¬H0 ∨ ¬H4.
- Else if H1(clamp): CLAMP-REPAIRS:TRANSFERS if H2, else CLAMP-REPAIRS:NO-GAIN (safe but costs
  more than 0.05pp mean vs center).
- Else CLAMP-INSUFFICIENT:<tag> with tag from (H1(clampM), H1(clampH)):
  (T,F) HL-CONDITIONAL — BO half-life alone shrinks the certified gamma band;
  (F,T) M-CONDITIONAL — BO margin alone shrinks it;
  (T,T) JOINT-ONLY — only the M×HL combination breaks it;
  (F,F) BOTH-CONTEXTS — either non-center knob alone breaks it.
- Descriptive only (no gate): per-arm worst deficit, cells over bar, max switches, mean delta vs
  center; whether `bo` reproduces exp674's worst cell.

## Consequences (pre-registered)

- CLAMP-REPAIRS:TRANSFERS → the BO point is safe under a gamma clamp; next = HL-region probe at the
  cap ceiling with gamma ≤ G_EDGE.
- CLAMP-REPAIRS:NO-GAIN → safety is repaired but the BO point does not beat center; the BO
  pointer does not transfer even when made safe.
- CLAMP-INSUFFICIENT:* → the gamma edge is context-dependent; next = gamma dose line in the
  implicated context (HL_BO and/or M_BO).

## Disclosures

- Synthetic streams only; single clamp level (G_EDGE), no new gamma search.
- Smoke (SMOKE=1, run BEFORE freeze, log in smoke.log): S0 AST identity; S1 sha assertion bites on
  a perturbed seed; S2 full-N H0 replication of the two bookends + standalones vs exp674 on 1
  stream x 2 caps; S3 H0 negative control; S4 reduced-grid determinism, adjudicator well-formed,
  hand-built-cell adjudicator arithmetic, 8/8 ladder branches, parameter provenance. Smoke numbers
  are machinery checks, not results.
- Expected runtime about 1.7 h (5 costfit arms + 2 standalones x 66 cells x 2 passes; exp712 took
  7306 s with 6 costfit arms).
- Sealed inputs only READ: exp670-synth.json, exp674-hl-transfer.json, exp712-gdose.json,
  exp712 run_gdose.py, policies.py (sha recorded in ARTIFACT.sha256).

## Pre-freeze smoke (2026-11-05 04:27–04:28 EST; full output in smoke.log)

SMOKE_OK, exit 0: S0 AST identity True; S1 sha assertion bites; S2 full-N bookend + standalone
replication vs exp674, 8/8 exact (stream 4, caps 512/2048); S3 negative control detects; S4
determinism, well-formed adjudication, hand-cell arithmetic, ladder 8/8, parameter provenance True.

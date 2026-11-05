# ADDENDUM 57 — exp713: exp674 joint BO point with GAMMA CLAMPED to exp712's certified edge

Verdict: **CLAMP-REPAIRS:NO-GAIN** — keeping exp674's BO margin (0.00161648) and BO half-life (160975) but
clamping gamma from the BO value 0.00998964 to exp712's certified edge 0.00573992 makes the joint point
SAFE: worst informative-cell deficit 0.355pp (bar 0.5pp), 0/59 cells over the bar, max
switches 2 (bar 6). But it does not transfer: paired mean delta vs center = -0.0534pp,
just below the frozen H2 bar of -0.05pp — so H2 fails and the ladder lands on NO-GAIN. H0 replication
264/264 exact vs sealed exp674 (cf_center, cf_bo + lcnu/s3fifo standalones); H4 accounting 330/330 + two full
runs bit-identical. Exit 0, 6145s.

## Per-arm results (59 informative cells; bars frozen from exp674/710/711/712)
| arm | role | margin | gamma | half-life | worst deficit pp | worst cell | cells > 0.5pp | max switches | mean delta vs center pp | H1 |
|---|---|---|---|---|---|---|---|---|---|---|
| center | bookend == exp674 cf_center | 0.005 | 0.0025 | 32768 | 0.176 | s=0.8 lam=0.6 E=128/L=48 @512 | 0 | 2 | +0.0000 | PASS |
| bo | bookend == exp674 cf_bo | 0.00161648 | 0.00998964 | 160975 | 0.779 | s=1.4 lam=0.6 E=32/L=32 @256 | 8 | 2 | -0.1234 | **FAIL** |
| clamp | PRIMARY | 0.00161648 | 0.00573992 | 160975 | 0.355 | s=1.4 lam=0.6 E=128/L=48 @512 | 0 | 2 | -0.0534 | PASS |
| clampM | attribution (HL at center) | 0.00161648 | 0.00573992 | 32768 | 0.176 | s=0.8 lam=0.6 E=128/L=48 @512 | 0 | 2 | +0.0077 | PASS |
| clampH | attribution (M at center) | 0.005 | 0.00573992 | 160975 | 0.779 | s=1.1 lam=0.3 E=128/L=48 @512 | 5 | 2 | -0.1094 | **FAIL** |

Descriptive (no gate): `bo` reproduces exp674 exactly (worst 0.779pp at the same cell, same
8-cell violation set, same mean delta -0.1234pp). The attribution arms are not
needed by the ladder (clamp passed) but are informative:
- `clampM` (BO margin, edge gamma, center HL) is safe AND the only arm with a positive mean delta vs center
  (+0.0077pp; worst 0.176pp vs center's 0.176pp).
- `clampH` (center margin, edge gamma, BO HL) **fails** 5/59 cells (worst 0.779pp):
  the certified gamma edge from exp712 (measured at center M/HL, where the same parameters with HL 32768
  passed at worst 0.375pp) does not hold once HL alone moves to the BO value. clampH
  over-bar set nested in bo's = True.
- Reading (descriptive): at BO HL, moving margin from center to BO turns edge gamma from unsafe (clampH)
  to safe (clamp) — consistent with exp711's protective-margin main effect; at BO margin, moving HL from
  center to BO costs mean delta: clampM (+0.0077) -> clamp (-0.0534).

clampH cells over the bar:
| stream | cap | deficit pp | also over in bo? |
|---|---|---|---|
| s=1.1 lam=0.3 E=128/L=48 | 512 | 0.779 | yes |
| s=1.1 lam=0.3 E=128/L=48 | 2048 | 0.533 | yes |
| s=1.1 lam=0.6 E=128/L=48 | 512 | 0.738 | yes |
| s=1.4 lam=0.3 E=128/L=48 | 1024 | 0.540 | yes |
| s=1.4 lam=0.6 E=128/L=48 | 512 | 0.507 | yes |

## What this settles
- Pre-registered consequence of CLAMP-REPAIRS:NO-GAIN: safety at the BO point is repaired by the gamma
  clamp, but the BO pointer does not transfer even when made safe (mean -0.0534pp vs center,
  bar -0.05pp). The exp669->exp674 BO direction is closed as a transfer candidate on this family.
- Descriptive, not a gated claim: the certified gamma band is HL-context-dependent when margin is at
  center (clampH fails), and the best-looking point in this experiment is clampM (BO margin + edge gamma
  at center HL; +0.0077pp mean, safe). Its +0.0077pp is far below any adoption bar; whether
  it is real headroom is a separate pre-registered question.

## Integrity, determinism, disclosures
- run_gclamp.py sha256 b48e3cac282df532..., PREREG.md 4ba2da1363cb2990..., smoke.log
  55cc218d3bb1fa56..., policies.py b38c55b86b704d3d... == ARTIFACT.sha256 == local run dir;
  runner/PREREG/smoke.log/ARTIFACT == freeze-commit f6c2367 blobs. Freeze commit precedes the result mtime.
  Disclosed smoke (S0-S4) passed pre-freeze.
- Published exp674 and exp712 JSONs asserted parse-equal to the local sealed copies the runner read.
- H2 margin is thin: -0.0534pp vs -0.05pp bar (difference -0.0034pp); the frozen
  bar decides — no re-run, no bar change.
- Synthetic streams only (11 cfgs from exp670); single clamp level, no new gamma search.

Data: exp713/exp713-gclamp.json (run.log local, gitignored); PREREG.md / ARTIFACT.sha256 / smoke.log /
LEDGER.md in exp713/. Follow-up controller re-adjudicated every gate with an independently written
adjudicator (39/39 checks): verdict CLAMP-REPAIRS:NO-GAIN stands.

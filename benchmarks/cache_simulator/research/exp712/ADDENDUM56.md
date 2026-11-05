# ADDENDUM 56 — exp712: single-knob GAMMA dose line at center (M, HL) — certified gamma band

Verdict: **G-BOUNDARY@g4** — with margin (0.005) and half-life (32768) held at center,
gamma is certified safe from center 0.0025 up to **g3 = 0.00573992** (2.30x center,
0.57x of the exp674 BO gamma 0.00998964). The first failing dose is g4 = 0.0075723
(3.03x center): 5/59 informative cells over the 0.5pp no-harm bar
(worst 0.730pp). Ladder is monotone (nonmonotone flag = False). H0 bookend
replication 264/264 exact vs sealed exp711 (g0 == cf_000, g5 == cf_0G0, + lcnu/s3fifo standalones);
H4 accounting 396/396 + two full runs bit-identical. Exit 0, 7306s.

## Per-arm results (59 informative cells; bars frozen from exp674/710/711)
| arm | gamma | x center | sealed replica? | worst deficit pp | worst cell | cells > 0.5pp | max switches | mean delta vs g0 pp | H1 |
|---|---|---|---|---|---|---|---|---|---|
| g0 | 0.0025 | 1.00x | exp711 000 | 0.176 | s=0.8 lam=0.6 E=128/L=48 @512 | 0 | 2 | +0.0000 | PASS |
| g1 | 0.00329809 | 1.32x | new | 0.188 | s=0.8 lam=0.6 E=128/L=48 @512 | 0 | 2 | -0.0088 | PASS |
| g2 | 0.00435095 | 1.74x | new | 0.351 | s=1.4 lam=0.0 E=128/L=48 @512 | 0 | 2 | -0.0278 | PASS |
| g3 | 0.00573992 | 2.30x | new | 0.375 | s=1.4 lam=0.3 E=128/L=48 @1024 | 0 | 2 | -0.0490 | PASS |
| g4 | 0.0075723 | 3.03x | new | 0.730 | s=1.4 lam=0.6 E=32/L=32 @256 | 5 | 2 | -0.0783 | **FAIL** |
| g5 | 0.00998964 | 4.00x | exp711 0G0 | 1.145 | s=1.4 lam=0.6 E=32/L=32 @256 | 6 | 2 | -0.1095 | **FAIL** |

Descriptive (no gate): worst deficit monotone in gamma = True (0.176 -> 0.188 -> 0.351 -> 0.375 -> 0.730 -> 1.145 pp);
over-bar count monotone = True (0 -> 0 -> 0 -> 0 -> 5 -> 6); g4 over-bar set nested in g5's = True.
Switches never exceed 2 on any arm (bar 6): every failure is a pure hit-rate
deficit. Mean paired delta vs g0 drifts monotonically negative (+0.0000 / -0.0088 / -0.0278 / -0.0490 / -0.0783 / -0.1095 pp).

First failing arm (g4) cells over the bar:
| stream | cap | deficit pp | also over at g5? |
|---|---|---|---|
| s=1.1 lam=0.3 E=128/L=48 | 512 | 0.513 | yes |
| s=1.1 lam=0.6 E=128/L=48 | 512 | 0.570 | yes |
| s=1.4 lam=0.3 E=128/L=48 | 1024 | 0.540 | yes |
| s=1.4 lam=0.6 E=128/L=48 | 512 | 0.507 | yes |
| s=1.4 lam=0.6 E=32/L=32 | 256 | 0.730 | yes |

## What this settles
- exp711 located exp674's SAFETY-BROKEN break in gamma; exp712 bounds it: at center M/HL the
  certified gamma band is **[0.0025, 0.00573992]**. The exp674 BO gamma sits two geometric steps
  (1.74x) beyond the certified edge.
- Pre-registered consequence (G-BOUNDARY@g_j, j >= 2): re-run the exp674 joint transfer with gamma
  clamped to the certified edge (BO margin + BO HL kept) — tests whether clamping gamma alone
  repairs the BO point. Registered as exp713.

## Integrity, determinism, disclosures
- run_gdose.py sha256 247e09c3e45b3652..., PREREG.md e698df87a1bd656b..., smoke.log
  8f615630c425a816... == ARTIFACT.sha256 == local run dir; runner/PREREG/ARTIFACT == freeze-commit
  d611f02 blobs. smoke.log is matched by the cache_simulator `*.log` gitignore rule, so the freeze
  commit bound it by hash only (inside the committed ARTIFACT.sha256); it is force-added with this
  addendum. Freeze pushed before launch and precedes the result mtime. Disclosed smoke (S1-S4) passed pre-freeze.
- Disclosed in LEDGER: first launch (pid 21498) was a non-persistent session child killed at 4 s with a
  0-byte log and no output; relaunched persistently after re-verifying the runner sha.
- Published exp711 and exp674 JSONs asserted parse-equal to the local sealed copies the runner read.
- Synthetic streams only (11 cfgs from exp670); single-knob line — M/HL interactions are exp711's domain.

Data: exp712/exp712-gdose.json (run.log local, gitignored); PREREG.md / ARTIFACT.sha256 / smoke.log /
LEDGER.md in exp712/. Follow-up controller re-adjudicated every gate with an independently written
adjudicator (39/39 checks): verdict G-BOUNDARY@g4 stands.

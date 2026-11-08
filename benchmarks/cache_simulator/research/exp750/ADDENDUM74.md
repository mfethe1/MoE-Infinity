# ADDENDUM74 — exp750: two-GPU decode timing of the fix749 per-device event-pool build

Lane 79990 · STACK-1001 · admitted #76/1001 · POSTING-LEDGER #253 · published 2026-11-08T00:12:20Z

Sealed verdict (frozen classify750.py, replayed byte-identical at publish):
`VERDICT750 FIX-FASTER|INCOMPLETE|TWO-GPU-SLOWER|PASS|MANIP-OK flags: R1:EXCLUDED(b3_R1:FOREIGN)`

## Provenance and freeze
- Frozen pre-data at exp750-local git commit `1b2cbe0` (2026-11-07T12:32:40Z, 12 s before unit start; local repo has no
  remote — this commit is the first push of the frozen bytes to the fork; pre-data status corroborated by the
  Winnie-recorded RUN_SHA256 matching FROZEN750.sha256 on all 12 overlapping files, and by the Muse review).
- `FROZEN750.sha256` = `ef17795232b43b4ed0abadf628be755db24d4309afe34ead664355d20ed73cc4` (13 files: PREREG, runner, arms, cells, prompts, classifier, quietwait,
  gen_cells, refs, tests). `freeze/` here verifies 13/13.
- PREREG sha256 `c6acada1b7f9420a81e2dc8b50800eed7d6eb859a224b70c037c80cc5b69ac63`; runner sha256
  `6e78b8fed9a316a77d20f2b073bccabf3a6a84d7d76d946bf6bb72aebccde445`; classifier sha256
  `c5c29960075bd4a01caea9d7faa7e04216ec46fda1ea9df9e9a86ea23f26f42b`.
- .so identities as preregistered and unchanged across the run (so_sha_pre == so_sha_post == exp749 ref):
  unpatched `d252620b…`,
  fix749 `baa30e57…`,
  fix740 `72da70e8…`.
- Disclosure: the A1 owner sensitivity analyzer (sens750_a1.py) was written post-freeze during the run
  (commit `0ea6ab4`, pre-result, not a gate); the sealed verdict derives only from the frozen classifier.

## Run
Winnie (WSL2, 2× RTX 5060 Ti: GPU0 PCIe gen3 x2, GPU1 gen4 x8), systemd user unit exp750,
started 12:32:52Z → EXP750-DONE 16:41:28Z 2026-11-07; first monitor sample 2026-11-07T12:35:34Z.
OLMoE-1B-7B bf16, lcnu policy ratio 0.2, batch 1, 6 prompts × 64 tokens, 3 blocks; wall-clock ms/token through
MoE.generate (D = (t64−t1)/63). 21 planned cells + 5 frozen-rule G-F reruns = 26; 26/26 rc=0; 26/26 quietwait QUIET;
link state recorded per cell (gpu0 gen3 x2 / gpu1 gen4 x8, 26/26). Owned hardware; no API spend in the run itself.

## Per-arm record-cell medians (ms/token; parsed from sealed class750.txt, cross-recomputed from raw)
| arm | setup | D b1 | D b2 | b3 | CV(D) |
|---|---|---|---|---|---|
| R1 | unpatched engine, single GPU1 | 99.6 | 100.7 | — | 0.008 |
| S1 | fix749, single GPU1 | 102.8 | 99.8 | 101.5 | 0.015 |
| S0 | fix749, single GPU0 (gen3 x2) | 455.1 | 448.8 | 455.3 | 0.008 |
| P2 | fix749, two-GPU | 201.1 | 199.5 | 202.4 | 0.007 |
| K2 | fix740 + CUDA_LAUNCH_BLOCKING=1, two-GPU | 368.5 | 306.7 | 317.7 | 0.100 |
| C2 | fix740, two-GPU (known-corrupt control; descriptive only) | 268.7 | 194.3 | 275.9 | 0.183 |
| H2 | HF transformers bf16 all-resident (descriptive reference) | 38.3 | 40.7 | 55.7 | 0.210 |

Cells of record: b1_R1→b1_R1_x, b2_K2→b2_K2_x, b3_S0→b3_S0_x, b3_S1→b3_S1_x (frozen G-F rerun rule);
b3_R1 has NO clean cell (b3_R1 and b3_R1_x both FOREIGN — Ollama loaded at the end of b3_R1_x) → R1:EXCLUDED.

## Pre-registered decisions (all recomputed independently from raw and asserted equal to sealed output)
- **D1** q = D(K2)/D(P2) per block = [1.8326, 1.5378, 1.5697] → **FIX-FASTER** (3/3 ≥ 1.10):
  the only other known-correct two-GPU configuration (fix740 + CUDA_LAUNCH_BLOCKING=1) pays a
  1.54–1.83× decode tax relative to fix749.
- **D2** s = D(S1)/D(R1) per block = [1.0316, 0.9902] (blocks 1–2 only; no clean b3 R1)
  → **INCOMPLETE**; both available values sit inside the pre-registered NOREGRESS band [0.95, 1.05]:
  no single-GPU regression from fix749 is visible, but the pre-registered 3/3 requirement is not met.
- **D3** u = D(S1)/D(P2) per block = [0.5112, 0.5001, 0.5014] → **TWO-GPU-SLOWER** (3/3 ≤ 0.91):
  on this host the correct two-GPU split decodes ~2× slower than GPU1 alone.
- **link** D(S0)/D(S1) per block = [4.4273, 4.4992, 4.4874], CV 0.86%:
  GPU0-alone is 4.4–4.5× slower than GPU1-alone, consistent with GPU0's gen3 x2 link (exp704: ~1.56 GB/s H2D
  vs ~14 GB/s). Link state was recorded, not manipulated → decomposition, not a causal test.
- **noise**: R1 across-block CV(D) = 0.77% (< 5% → no NOISY flag).

## Gates
- **G-Q PASS**: all 16 GQ-arm cells (originals + reruns) match the exp749 b1_R reference 6/6 on
  (out_ids, top16_ids, top16_vals). C2 0/6 in all 3 cells as expected; C2-UNEXPECTED-CLEAN not raised.
- **G-T**: timed-64 identity true for every non-C2 cell; false for all 3 C2 (exempt, descriptive).
- **G-V**: every timed rep t64 > t1 > 0 in all 26 cells.
- **G-M MANIP-OK**: .env CUDA_LAUNCH_BLOCKING=1 exactly for the 4 K2 cells, empty elsewhere; 18 prov.json
  (11 fix749 + 7 fix740); arm→build provenance exact; so_sha_pre == so_sha_post == ref.
- **G-F**: independent re-derivation from monitor.csv/precell.csv reproduces the sealed FOREIGN set
  {b1_R1, b2_K2, b3_S0, b3_S1, b3_R1, b3_R1_x} exactly; frozen rerun rule applied; 1 cell (b3_R1) lost.

## A1 sensitivity + owner-independent recompute
- sens750_a1.py replay at admission: **NOT-SENSITIVE** (verdict unchanged when flagged-cell slack is perturbed;
  flags b1_S0, b3_R1).
- indep750_owner.py (reads raw JSON, does not import the classifier) replay rc=0, 0 disagreements
  (SHOULD-FIX from the Muse review applied: unprinted b3_R1_x no longer counted as a disagreement).

## Admission review
- **Muse Code** (muse-wonder-1.0, read-only, attempt 2; attempt 1 killed at 17 min on an out-of-workspace write
  approval, MUSE_EXIT=143, no output): `ADMIT750 ADMIT-WITH-CAVEATS`, 0 BLOCKER, MUSE_EXIT=0 2026-11-07T18:55:31Z.
  Reviewer independently recomputed all 26 D from raw (max abs diff 0.0), replayed the classifier byte-identically
  (`d52a7541…`), reproduced the G-F FOREIGN set, and checked .env/.prov/.so/rc/quietwait/link and position
  effects (none plausible). Full text: `settle/review-muse-answer.md`.
- **Coordinator re-adjudication (this publication)**: `settle/verify750_staged.py` — 44/44 PASS on the staged tree
  (independent recompute of every gate/decision from raw, byte-identical classifier replay, manifest/tarball/RUN_SHA256
  integrity, A1 + owner-indep replays, Muse artifacts). Log: `settle/ADMISSION-VERIFY.log`.

## Findings (from sealed settle/RESULT.md)
1. Among correct two-GPU configurations, the per-device event pool fix (fix749) decodes at ~200 ms/token vs 307-369 ms/token
   for the only other known-correct configuration (fix740 + CUDA_LAUNCH_BLOCKING=1). The CLB workaround is therefore a
   1.5-1.8x decode tax, and fix749 is both the correctness fix and the faster option.
2. Correctness costs nothing measurable against the corrupt build: C2/P2 = 1.34 / 0.97 / 1.36 (descriptive; C2 is
   noisy, CV 18%).
3. On this host the correct two-GPU split is 2x slower than running on GPU1 alone (P2 ~200 vs S1 ~101 ms/token), and
   GPU0 alone is 4.4-4.5x slower than GPU1 alone. GPU0's gen3 x2 link (exp704: ~1.56 GB/s H2D vs ~14 GB/s on GPU1) is the
   consistent explanation; link state was recorded, not manipulated, so this is a decomposition, not a causal test.
   Practical decision for Winnie: run MoE-Infinity single-GPU on GPU1; two-GPU only after the GPU0 link is fixed.
4. Single-GPU fix749 vs unpatched: 1.03 / 0.99 in the two clean blocks (no regression visible, verdict INCOMPLETE).
5. The engine remains 2.4-2.7x slower than HF bf16 all-resident on two GPUs (S1/H2 in blocks 1-2; block 3 is 1.82, H2 CV 21%), consistent with the
   exp726/exp746/exp751 engine-overhead line (different envelope: HF has the whole model resident).

## Limits and pre-committed consequence (from sealed settle/RESULT.md)
One host (WSL2, asymmetric PCIe, no P2P), one model (OLMoE-1B-7B), one policy/ratio (lcnu, 0.2), batch 1, 6 prompts x
64 tokens, 3 blocks. Wall-clock through MoE.generate incl. host overhead. Not full-model parity, not other topologies; the
two-GPU slowdown is specific to this link asymmetry. Foreign activity (Ollama, other lanes) on Winnie caused 5 FOREIGN
cells; handled by the frozen G-F rerun rule; block 3 R1 lost twice (Ollama loaded at the end of b3_R1_x).
Pre-committed consequence: FIX-FASTER with G-Q PASS -> draft upstream issue/PR text (fix737+fix740+fix749 series,
qualified at the actual upstream head) after independent admission review and POSTING-LEDGER dedup; no external post
from this result alone.

Publication status of the consequence: upstream draft v3 (fix737+fix740+fix749 series, qualified at the actual
upstream head) is written and double-reviewed (Muse review#1 FIX-FIRST 5B→v2 all-addressed; review#2 delta
0-BLOCKER 2SF→v3 all-addressed with sealed sources); sha256 `e672c2b1eb144a787334b9250ee3afd09bd0c9068304655cbd293ebe4ab533a1`. It is **APPROVAL-GATED: not posted** —
external publication requires Michael's explicit approval of the exact text. POSTING-LEDGER dedup at publish: no
prior ledger header for exp749/exp750 timing claims. No quiet upstream thread was bumped (warp #78, MoE-Infinity #321,
colibri #2552 untouched).

## Artifacts (this directory)
- `freeze/` — the 13 frozen files + FROZEN750.sha256 (verifies 13/13).
- `raw/` — sealed Winnie bundle: `out/` (109 files: 26 cell JSONs, .env, .prov.json, monitor.csv, precell.csv,
  rc.csv, quietwait.csv, link.csv, so_sha_pre/post, ENV.txt, RUN_SHA256, class750.txt), `winnie_out_sha.txt`
  (109/109 verified), `exp750-final.tgz` (sha256 `c69474c0effa3f8ce9132dd3a9ec30b25c37e579ebe59b5be2e149fab12d9678`, contents == raw/out), `run.log`,
  `FROZEN750.sha256` (bundle copy).
- `raw/out/class750.txt` sha256 `d52a75412003eb3bee73db5aaf3a3d7cf9e8ca9797440068ca35de143d2adfc1`.
- `settle/` — RESULT.md (sealed), sens750_a1.py, indep750_owner.py, review-muse-answer.md, review-muse-exit,
  verify750_staged.py, ADMISSION-VERIFY.log.
- Generator: `gen_addendum74.py` (this file's producer; every number above parsed or recomputed at runtime).

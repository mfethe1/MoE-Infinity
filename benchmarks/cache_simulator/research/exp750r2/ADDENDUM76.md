# ADDENDUM76 — exp750r2: pre-registered replication (R2) of exp750 — D2 resolution

Lane 79990 · STACK-1001 · replication of admitted #76/1001 (repair of its INCOMPLETE D2; no new credit item) · published 2026-11-10T00:34:40Z

Sealed verdict (frozen classify750.py, byte-identical on host and in tarball):
`VERDICT750 FIX-FASTER|NOREGRESS-T|TWO-GPU-SLOWER|PASS|MANIP-OK`

## Provenance and freeze
- Protocol UNCHANGED from exp750 run-1: pre-run RUN_SHA256 (computed on Winnie before launch) shows
  all 12 protocol files byte-identical to FROZEN750 and binds FROZEN750.sha256 itself; freeze/ here
  re-verifies 13/13 (shasum -c, incl. tests/test_classify750.py).
  Runner sha256 `6e78b8fed9a316a77d20f2b073bccabf3a6a84d7d76d946bf6bb72aebccde445`, classifier sha256 `c5c29960075bd4a01caea9d7faa7e04216ec46fda1ea9df9e9a86ea23f26f42b`,
  PREREG.md sha256 `c6acada1b7f9420a81e2dc8b50800eed7d6eb859a224b70c037c80cc5b69ac63` — identical to the run-1 freeze.
- R2 addendum prereg `PREREG-R2.md` sha256 `de78901b7cebbca69a0218101068f1a364b7b6b72b03f391ed3d0c98cfd59616` (exact match to the full 64-hex pin in the
  1846Z replication receipt; 1912Z receipt: "frozen pre-launch"), unit launch 18:46:42Z —
  prereg frozen before any cell ran.
- Tarball byte-identity: exp750r2-final.tgz sha256 `cd362bc2d88afbaaf95623cfd1e800288911e512318c3579c0e6f1e3cc3ceb93` computed on Mack == computed on Winnie at
  terminal-state probe 2026-11-10T00:21:39Z (settle/winnie-probe). Unit `exp750.service` terminal:
  Result=success, ExecMainStatus=0.
- .so identities unchanged across the run (so_sha_pre == so_sha_post; fix749 == exp749 ref):
  unpatched `d252620b…`, fix749 `baa30e57…`, fix740 `72da70e8…`.

## Run
Winnie (WSL2, 2× RTX 5060 Ti), systemd user unit exp750 second launch 2026-11-09T18:46:42Z →
EXP750-DONE 2026-11-09T22:49:18Z (4h02m;
journal: 6h14m CPU, 47.2 GiB memory peak). Run-1 out/ (109 files) preserved on host as
out-R1-archive-20261109T1845Z and verified intact after the run. 21 planned cells + 7 frozen-rule
reruns = 28 executed; 28/28 rc=0 (rc.csv). Identical arms/prompts/policy as run-1 (OLMoE-1B-7B bf16,
lcnu r=0.2, batch 1, 6 prompts × 64 tokens, 3 blocks, D = (t64−t1)/63).

## Per-arm record-cell medians, ms/token (run-2 | run-1)
| arm | setup | R2 b1 | R2 b2 | R2 b3 | CV(D) | med-rep-spread | R1-run b1 | b2 | b3 |
|---|---|---|---|---|---|---|---|---|---|
| R1 | unpatched engine, single GPU1 | 98.458 | 98.437 | 98.645 | 0.0012 | 0.034 | 99.643 | 100.741 | — |
| S1 | fix749, single GPU1 | 98.104 | 98.748 | 97.244 | 0.0077 | 0.022 | 102.788 | 99.758 | 101.466 |
| S0 | fix749, single GPU0 (gen3 x2) | 450.450 | 451.350 | 450.935 | 0.0010 | 0.035 | 455.075 | 448.835 | 455.324 |
| P2 | fix749, two-GPU | 197.882 | 201.453 | 199.042 | 0.0091 | 0.024 | 201.087 | 199.468 | 202.374 |
| K2 | fix740 + CUDA_LAUNCH_BLOCKING=1, two-GPU | 312.090 | 307.910 | 308.893 | 0.0071 | 0.032 | 368.514 | 306.747 | 317.669 |
| C2 | fix740, two-GPU (corrupt control) | 197.561 | 197.572 | 201.520 | 0.0115 | 0.041 | 268.654 | 194.331 | 275.872 |
| H2 | HF transformers bf16 all-resident (reference) | 37.970 | 38.088 | 38.305 | 0.0045 | 0.018 | 38.308 | 40.728 | 55.739 |
Cells of record per frozen G-F rerun rule: b1_C2→b1_C2_x, b1_P2→b1_P2_x, b2_C2→b2_C2_x, b2_S1→b2_S1_x, b2_K2→b2_K2_x, b3_K2→b3_K2_x, b3_R1→b3_R1_x.
All 7 FOREIGN originals (5× ollama=1, 2× foreign-GPU mem gain) recovered by clean _x reruns —
0 cells-of-record lost (run-1 had lost b3_R1; R2's b3_R1_x is clean).

## Pre-registered decisions (each recomputed independently from raw and asserted == sealed)
- **D1** q = D(K2)/D(P2) = [1.577, 1.528, 1.552] → **FIX-FASTER** (3/3 ≥ 1.10).
  Run-1 [1.833, 1.538, 1.570] — label replicates.
- **D2** s = D(S1)/D(R1) = [0.996, 1.003, 0.986] → **NOREGRESS-T** (3/3 ∈ [0.95, 1.05]).
  Run-1 was INCOMPLETE (2 clean blocks, [1.032, 0.990]); **the R2 primary question is RESOLVED**:
  no single-GPU decode regression from fix749, now on 3/3 clean blocks.
- **D3** u = D(S1)/D(P2) = [0.496, 0.490, 0.489] → **TWO-GPU-SLOWER** (3/3 ≤ 0.91).
  Run-1 [0.511, 0.500, 0.501] — label replicates.
- **link** D(S0)/D(S1) = [4.592, 4.571, 4.637] (descriptive; GPU0 gen3 x2).
- **noise** R1 across-block CV(D) = 0.001161 (run-1: 0.007747).

## Gates
- **G-Q PASS**: every gated cell-of-record (R1,S1,S0,P2,K2) matches the exp749 b1_R reference
  6/6 on (out_ids, top16_ids, top16_vals); recomputed here from raw.
- **G-T/G-V**: timed-64 identity and t64 > t1 > 0 hold for every non-C2 cell (C2 exempt, corrupt control).
- **G-M MANIP-OK**: CUDA_LAUNCH_BLOCKING=1 exactly for the 5 K2 cells that ran (empty elsewhere);
  11 fix749 prov.json (S*/P2 arms), 10 fix740 (K2/C2); arm→build provenance exact;
  so_sha_pre == so_sha_post == refs.
- **G-F**: FOREIGN set re-derived == sealed ['b1_C2', 'b1_P2', 'b2_C2', 'b2_K2', 'b2_S1', 'b3_K2', 'b3_R1'];
  frozen rerun rule applied; zero loss.

## Replication + pooled sensitivity (PREREG-R2 rule 2 — sensitivity only, never overrides)
- Pooled s over 5 clean blocks (run-1 b1,b2 + R2 b1..b3), D-median ratio = **1.001052** ∈ [0.95, 1.05]
  (settle transcript cross-check exact). D1/D3 labels unchanged; no decision is SENSITIVE.
- Run-1 vs run-2 arm medians agree within ~1–4% (table above); R1/S1 absolute levels moved <2 ms/token.

## Kill criteria (rule 4) — none triggered
(a) FROZEN750 13/13; (b) 0% cells-of-record lost (limit >50%); (c) G-Q PASS all gated arms;
(d) all decisions from 3 clean blocks.

## Limitations
Single host, one model (OLMoE-1B-7B), 6 prompts, 3 blocks; GPU0's gen3 x2 link makes S0/P2 levels
host-specific (link recorded, not manipulated); C2 is a known-corrupt control, descriptive only;
pooled view combines two runs on the same host 2 days apart (same GPUs, same builds — .so ids equal).

## Settle evidence
settle/recompute750r2.py (owner-independent recompute, no classify750 import) + transcript;
settle/winnie-probe-20261110T0021Z.txt (terminal state, tgz sha, R1 archive intact);
settle/winnie-journal-750r2-tail.txt (rerun sequence, EXP750-DONE). Generated by gen_addendum76.py
(224 runtime asserts, all PASS; zero hand-transcribed measurements).

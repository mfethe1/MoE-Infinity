# exp750 RESULT — the correct two-GPU MoE-Infinity build (fix749) is 1.54-1.83x faster than the CLB workaround; on this host two GPUs are 2x slower than one

Lane 79990 Tier1 (cron 7687a6bf1295). Tier: native end-to-end CUDA decode timing, Winnie (2x RTX 5060 Ti 16 GB, WSL2,
PCIe, GPU0 gen3 x2 / GPU1 gen4 x8 in all 26 cells per link.csv), MoE-Infinity 0337988-based trees, OLMoE-1B-7B-0125-Instruct
bf16, lcnu, device_memory_ratio 0.2, batch 1 greedy, 6 prompts x 64 tokens, timed reps=3 per prompt, 3 blocks x 7 arms.
Frozen at 1b2cbe0 (FROZEN750.sha256, 13 files); PREREG + Amendments A1/A2 written before any cell ran. A1 analyzer
sens750_a1.py committed 0ea6ab4 before results were read.

## Run
- systemd user unit exp750: started 12:32:52Z (waited 0 min), 21 cells + 5 reruns (_x), EXP750-DONE 16:41:28Z; 26/26 rc=0;
  quietwait QUIET 26/26. Unit consumed 5h44m CPU, 50.4G memory peak.
- FROZEN750.sha256 OK on Winnie (sha256sum -c) and on Mack. out/RUN_SHA256 (13 entries) lists FROZEN750.sha256 itself and
  omits tests/test_classify750.py, so it is not set-equal to the frozen list; all 12 overlapping hashes match.
- Raw tarball winnie-final-20261107T1832Z/exp750-final.tgz sha256 c69474c0…9678 (Winnie sha256sum == Mack shasum);
  109/109 out/ files match the Winnie-side per-file manifest (winnie_out_sha.txt).
- .so identities pre == post == exp749 so_sha_post: unpatched d252620b…38da, fix740 72da70e8…a4ba4, fix749 baa30e57…4507.
- Provenance: 11 fix749 cells (S1/S0/P2 incl. _x) and 7 fix740 cells (K2/C2 incl. _x) by *.prov.json; CLB=1 in exactly the
  4 K2 .env files, empty in the other 22.

## Sealed verdict (frozen classify750.py; re-run on Mack byte-identical to out/class750.txt, sha256 d52a7541…)
`VERDICT750 FIX-FASTER|INCOMPLETE|TWO-GPU-SLOWER|PASS|MANIP-OK flags: R1:EXCLUDED(b3_R1:FOREIGN)`

Cell metric D = median over 6 prompts of median-over-3-reps (t64 - t1)/63, ms/token (cells of record):
- R1 unpatched, GPU1: 99.64 / 100.74 / — (b3_R1 and b3_R1_x both FOREIGN)
- S1 fix749, GPU1: 102.79 / 99.76 / 101.47
- S0 fix749, GPU0 (gen3 x2): 455.08 / 448.83 / 455.32
- P2 fix749, GPU0+1: 201.09 / 199.47 / 202.37
- K2 fix740 + CUDA_LAUNCH_BLOCKING=1, GPU0+1: 368.51 / 306.75 / 317.67
- C2 fix740 no CLB (known corrupt, descriptive): 268.65 / 194.33 / 275.87
- H2 HF bf16 all-resident, GPU0+1 (descriptive): 38.31 / 40.73 / 55.74

Decisions:
- D1 q = D(K2)/D(P2) = 1.833 / 1.538 / 1.570 -> FIX-FASTER (bar >= 1.10 in 3/3; min margin 0.44 over the bar).
- D2 s = D(S1)/D(R1) = 1.032 / 0.990 / — -> INCOMPLETE (block 3 has no clean R1). Both available blocks sit inside the
  NOREGRESS band [0.95, 1.05]; not a verdict.
- D3 u = D(S1)/D(P2) = 0.511 / 0.500 / 0.501 -> TWO-GPU-SLOWER. Link component D(S0)/D(S1) = 4.43 / 4.50 / 4.49.
- G-Q PASS: every R1/S1/S0/P2/K2 cell that ran (originals and _x) equals exp749 b1_R on 6/6 prompts (out_ids, top16_ids,
  top16_vals). C2 0/6 in all 3 blocks and its timed runs drift from its own quality pass (C2-UNEXPECTED-CLEAN not raised).
- Noise: R1 across-block CV(D) 0.77% (< 5%, no NOISY flag); S1 1.5%, S0 0.8%, P2 0.7%, K2 10.0%, C2 18.3%, H2 21.0%.

## Amendment A1 sensitivity (owner, result time; not a gate)
OWN-GPU-ANOMALY cells: b1_S0 (GPU0 peak 16007 vs arm median 9754 MiB) and b3_R1 (GPU1 15955 vs 10084, already excluded).
D1-D3 recomputed with them dropped: unchanged. `A1 RESULT: NOT-SENSITIVE`. This is partly vacuous: b1_S0 enters only the
descriptive link ratio and b3_R1 was already excluded, so dropping them cannot move D1-D3 (block-1 link ratio would be missing).

## Owner independent recompute (indep750_owner.py; reads raw JSON, does not import the classifier)
All 25 classifier-printed cell D values agree with class750.txt to 1e-9; b3_R1_x is not printed by the classifier (its
own D = 99.70, reported as not-printed, not a disagreement). Quality 6/6 and timed identity true for every non-C2/H2 cell; C2 timed identity false in
all 3 cells. Ratios reproduce D1/D2/D3 above.

## Predictions (pre-data)
D1 FIX-FASTER 0.55 -> confirmed. D2 NOREGRESS-T 0.70 -> untested (INCOMPLETE). D3 TWO-GPU-SLOWER 0.45 -> confirmed.

## Findings
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

## Limits
One host (WSL2, asymmetric PCIe, no P2P), one model (OLMoE-1B-7B), one policy/ratio (lcnu, 0.2), batch 1, 6 prompts x
64 tokens, 3 blocks. Wall-clock through MoE.generate incl. host overhead. Not full-model parity, not other topologies; the
two-GPU slowdown is specific to this link asymmetry. Foreign activity (Ollama, other lanes) on Winnie caused 5 FOREIGN
cells; handled by the frozen G-F rerun rule; block 3 R1 lost twice (Ollama loaded at the end of b3_R1_x).
Pre-committed consequence: FIX-FASTER with G-Q PASS -> draft upstream issue/PR text (fix737+fix740+fix749 series,
qualified at the actual upstream head) after independent admission review and POSTING-LEDGER dedup; no external post
from this result alone.

## Independent post-run admission review
Muse Code (muse-wonder-1.0, read-only, MUSE_EXIT=0 18:55:31Z; attempt 1 killed at 17 min, blocked on an out-of-workspace
write approval, MUSE_EXIT=143, no output): review-post-muse/answer.md -> `ADMIT750 ADMIT-WITH-CAVEATS`. 0 BLOCKER.
Reviewer independently recomputed all 26 D from raw (max abs diff 0.0), replayed the classifier byte-identically
(d52a7541…), reproduced G-F FOREIGN set, checked .env/.prov/.so/rc/quietwait/link and position effects (none plausible).
SHOULD-FIX applied: owner script no longer counts unprinted b3_R1_x as a disagreement; RUN_SHA256 wording corrected.
NITs folded into text: A1 partly vacuous; G-F blind to same-GPU compute/PCIe contention without memory change (bounded by
P2 CV 0.7%, S1 1.5%); block-1 K2 elevation sits in prompts 1-2 (516.6, 513.5 ms/token) but every one of 18 per-prompt
K2/P2 ratios is >= 1.43; the S1/H2 block-3 value. Systemd CPU/memory figures are not in the raw archive (non-decision).
Admission to the program ledger is coordinator280597a49d2f's.

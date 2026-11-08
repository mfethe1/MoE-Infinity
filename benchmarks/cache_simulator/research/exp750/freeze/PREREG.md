# exp750 PREREG — what does the correct two-GPU MoE-Infinity cost? fix749 vs the CLB workaround, timed validly

Lane 79990 Tier1 (cron 7687a6bf1295, owner hermes@mack). Written BEFORE any exp750 code, cell or timing exists.
Pre-committed consequence of exp749 (PREREG line 59): FIXED-* -> "a timing-qualified repeat (valid timer) before any
upstream PR". exp749 sealed `VERDICT749 FIXED-BITWISE|CTRL-REPRO|NOREGRESS|MANIP-OK|ENV-SAME|ENVH-SAME`, Muse
post-run review ADMIT-WITH-CAVEATS (exp749 repo ac52199).

## Question
On Winnie (2x RTX 5060 Ti 16 GB, WSL2, 12 vCPU, 94 GiB), OLMoE-1B-7B-0125-Instruct bf16, MoE-Infinity 0337988-based
trees, lcnu, device_memory_ratio 0.2, batch 1 greedy:
- Q1 (primary, matched envelope): among CORRECT two-GPU configurations, is fix749 (per-device event pools, async) faster
  than the only other known-correct one, fix740 + CUDA_LAUNCH_BLOCKING=1 (exp748)? Same GPUs, model, ratio, policy,
  threads; only the .so and CLB differ.
- Q2: does fix749 cost single-GPU decode speed vs the unpatched build (exp749 showed bitwise NOREGRESS, not speed)?
- Q3 (descriptive decomposition): is two-GPU fix749 faster or slower than one GPU, and how much of that is GPU0's link?
  Live state 2026-11-07T10:5xZ: GPU0 PCIe gen3 x2 (max gen3, width max 16), GPU1 gen4 x8 (exp704: GPU0 ~1.56 GB/s H2D,
  GPU1 ~14 GB/s). Link state is recorded per cell as a covariate, not controlled.

## Why the exp742/748/749 timer is invalid (fixed here)
decode_tok_s there = (n-1)/(t_full - t_1tok) where t_full is a 64-token run WITH per-step logits capture
(.detach().float() + list append via a _sample hook) and t_1tok a separate 1-token run; one sample per prompt; and
torch.cuda.synchronize() syncs only the current device. exp750: quality pass (with logits) is NOT timed; timed passes run
with NO capture hook, synchronize EVERY visible device before and after, and are repeated.

## Arms (r = 0.2, lcnu, MoE-Infinity native engine unless noted)
- R1: unpatched ~/moei-engine (.so d252620b…), gpus=1, CLB unset
- S1: fix749 ~/moei-fix749 (.so baa30e57…), gpus=1, CLB unset
- S0: fix749, gpus=0 (the gen3 x2 card), CLB unset — Q3 decomposition only
- P2: fix749, gpus=0,1, CLB unset
- K2: fix740 ~/moei-fix740 (.so 72da70e8…), gpus=0,1, CUDA_LAUNCH_BLOCKING=1
- C2: fix740, gpus=0,1, CLB unset — known corrupt (exp742/749); descriptive speed only, never a baseline
- H2: HF transformers bf16 all-resident, gpus=0,1 — descriptive reference only
No rebuild: the three .so files must hash-equal exp749 so_sha_post (runner aborts otherwise). 3 blocks x 7 arms = 21
cells; order within each block is a fixed random permutation generated with seed 750 and committed in cells750.json at
freeze (not re-drawn at run time).

## Per-cell protocol (fresh process per cell)
1 warmup ("Say hello.", 8 tokens). For each of the 6 exp742 prompts (prompts.json, unchanged):
1. Quality pass: 64 greedy tokens with logits capture (exactly the exp742 path) -> out_ids, top16_ids, top16_vals.
2. Timed passes, reps=3, no capture hook: for rep in 1..3: t1 = timed gen(p, 1 token); t64 = timed gen(p, 64 tokens);
   each timing = sync all visible devices; perf_counter; generate; sync all visible devices; perf_counter.
   Record every raw t1/t64 and each timed 64-token run's out_ids.
Per-prompt decode metric d_p = median_rep((t64 - t1) / 63) [ms/token]; e2e metric e_p = median_rep(t64 / 64).
Cell metric D = median over the 6 prompts of d_p (E likewise). All raw values are kept.

## Gates (evaluated before any timing decision)
- G-Q quality: R1, S1, S0, P2, K2 quality passes must equal the exp749 b1_R reference (out_ids, top16_ids, top16_vals)
  on 6/6 prompts. A failing cell -> that arm is QUALITY-FAIL and every decision using it is VOID. C2 is expected to fail
  (descriptive; if C2 matches 6/6 in all blocks, flag C2-UNEXPECTED-CLEAN).
- G-T timed identity: each timed 64-token run's out_ids must equal that cell's quality-pass out_ids (C2 exempt). Any
  mismatch -> cell TIMED-DRIFT, excluded from timing.
- G-V timer sanity: every rep must have t64 > t1 > 0; otherwise cell TIMER-INVALID, excluded from timing.
- G-M manipulation: every cell's .env records the CLB value its arm requires (K2 "1", all others empty) and its
  provenance (store_so path for engine arms); mismatch -> MANIP-FAIL (whole run VOID).
- G-F foreign activity (exclusion, decided by the classifier from monitor.csv, 5 s samples): a cell is FOREIGN if any
  sample during it has ollama_loaded_models >= 1, or any GPU NOT assigned to the cell shows memory > its precell value
  + 512 MiB. FOREIGN, TIMED-DRIFT or TIMER-INVALID cells are re-run ONCE after all 21 cells (id suffix _x, same arm/
  block); the _x cell replaces the original only if it is itself clean. A decision needs a clean cell for each involved
  arm in all 3 blocks; otherwise that decision is INCOMPLETE.

## Decisions (ratios of cell metric D within a block; >1 means the second-named arm is faster)
- D1 (Q1): q_b = D(K2)/D(P2). FIX-FASTER if q_b >= 1.10 in 3/3 blocks; WORKAROUND-FASTER if q_b <= 0.91 in 3/3;
  EQUIVALENT if 0.95 <= q_b <= 1.05 in 3/3; else MIXED.
- D2 (Q2): s_b = D(S1)/D(R1). NOREGRESS-T if 0.95 <= s_b <= 1.05 in 3/3; REGRESS-T if s_b > 1.05 in 3/3;
  FASTER-T if s_b < 0.95 in 3/3; else UNRESOLVED-T.
- D3 (Q3, descriptive): u_b = D(S1)/D(P2): TWO-GPU-FASTER if >= 1.10 in 3/3, TWO-GPU-SLOWER if <= 0.91 in 3/3, else
  NEUTRAL/MIXED. Link component reported as D(S0)/D(S1) per block (no verdict).
- Noise floor reported: per-arm across-block CV of D and median within-prompt rep spread; if the R1 across-block CV
  exceeds 5%, every 3/3-block verdict is additionally flagged NOISY (verdict text kept).
Final line: `VERDICT750 <D1>|<D2>|<D3>|<G-Q summary>|<G-M>` plus per-arm EXCLUDED/INCOMPLETE flags.

## Predictions (owner, pre-data)
D1: FIX-FASTER 0.55 (CLB serializes every launch on a launch-heavy decode), EQUIVALENT 0.20, MIXED 0.15,
WORKAROUND-FASTER 0.10. D2: NOREGRESS-T 0.70. D3: TWO-GPU-SLOWER 0.45 (gen3 x2 GPU0 link), NEUTRAL/MIXED 0.35,
TWO-GPU-FASTER 0.20.

## Consequences
- D1 FIX-FASTER or EQUIVALENT with G-Q pass: fix749 is a qualified correctness fix with a measured speed position;
  draft an upstream issue/PR text for EfficientMoE/MoE-Infinity (fix737+fix740+fix749 series, at actual upstream head,
  with exp742/748/749/750 evidence), via standing approval only after POSTING-LEDGER dedup; readback exact.
- WORKAROUND-FASTER: report as negative; investigate where per-device pools add cost before any post.
- Any G-Q fail on P2 or S1: exp749's FIXED-BITWISE does not replicate under the new harness -> stop, no post.

## Limits (fixed in advance)
One host (WSL2, PCIe, asymmetric links, no NVLink/P2P per exp704), one model, one policy and ratio, batch 1, 6 prompts x
64 tokens, 3 blocks. Not full-model parity, not other topologies. Timing is wall-clock end-to-end through MoE.generate,
including host overhead. Ollama/other lanes may share Winnie; handled only by G-F.

## Implementation ownership
Harness/runner/classifier: separate implementer session (Muse Code; Claude Code weekly limit and Kimi monthly quota
exhausted at 2026-11-07T10:3xZ). Classifier tests: a separate test-author session. Pre-freeze review: a third separate
session. Owner (Hermes) writes this PREREG and the brief, verifies diffs and runs the checks, and does not author the
harness.

## Amendment A1 (2026-11-07T12:0xZ, before freeze and before any exp750 cell; owner)
Gap found by replaying G-F on exp749 raw: G-F only sees foreign memory on GPUs NOT assigned to a cell. exp749 b3_P2 ran
29 min with assigned-GPU peaks 15807/14531 MiB vs ~9.0/4.5 GiB in b1/b2_P2 — foreign work on the cell's own GPUs, which
G-F cannot see. The classifier is NOT changed (G-F stays the only exclusion rule). Added, preregistered sensitivity
analysis done by the owner from monitor.csv at RESULT time: a cell is OWN-GPU-ANOMALY if on any assigned GPU its peak
memory exceeds the median over the arm's 3 effective cells of that GPU's peak by > 2048 MiB. D1-D3 are recomputed with
OWN-GPU-ANOMALY cells dropped (decision -> INCOMPLETE if that removes a block); if any decision changes, it is reported
as SENSITIVE(<D>) next to the sealed verdict, and the sealed verdict text stays as the classifier printed it.

## Amendment A2 (2026-11-07T12:3xZ, before freeze and before any exp750 cell; owner, from pre-freeze review)
Resolves two readings flagged by the independent pre-freeze review (REVIEW-PREFREEZE.md, MiMo v2.6 Pro):
- G-Q strict: every G-Q-arm cell that ran (original AND its _x) must match the reference; the _x replacement rule is a
  timing-exclusion device only and never forgives a quality mismatch (a mismatch under foreign load is still evidence
  of a race). This replaces the lenient "cell of record" reading used in fix round 1.
- G-M provenance: recorded in <id>.json.prov.json (fixrun) and the cell JSON store_so (engine), both checked by the
  classifier; the .env records CLB and CUDA_DEVICE_ORDER only. ("its provenance" in G-M refers to these files.)
- Runner writes an allowlisted environment snapshot out/env_start.txt (audit only, no gate).

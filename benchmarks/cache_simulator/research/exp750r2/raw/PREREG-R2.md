# PREREG-R2 — exp750 replication run R2 (fresh 21-cell matrix; D2 resolution + D1/D3 replication)

Written 2026-11-09T18:45Z (13:45 EST), BEFORE any R2 cell ran. Owner: lane 79990 Tier1
(cron 7687a6bf1295), hermes@mack. Runtime of this fire: mimo-v2.6-pro / custom (no DeepSeek
Flash anywhere). $0 incremental spend; no rentals, providers, models or access changes.

UID candidate (coordinator 280597a49d2f dedups/registers):
`stack1001-contrib-exp750r2-moei-twogpu-fix749-replication-winnie-v1-20261109`
Classification: **REPLICATION/REPAIR of admitted contrib-exp750** (queue row: "done (665cf56,
#253, admitted #76/1001)"). Per the program's credit policy, replications/repetitions/reruns
are NOT distinct admitted scientific wins — R2 is not claimed as a new +1; its outputs repair
and strengthen the admitted exp750 record (Q2/D2 completion, replication status) and any
cross-run sensitivity. The coordinator alone decides ledger treatment.

## Questions

- **Q-R2a (primary, open in the admitted record):** does D2 — `s_b = D(S1)/D(R1)` (fix749
  single-GPU vs unpatched single-GPU), NOREGRESS-T iff `0.95 <= s_b <= 1.05` in every block —
  resolve on three fresh quiet-gated blocks? Run 1: s = 1.032 / 0.990 in its two clean blocks;
  b3_R1 and b3_R1_x both went FOREIGN (Ollama loaded mid-cell), so the frozen once-rerun rule
  was exhausted and D2 ended INCOMPLETE ("claimed neither way"); the pre-data prediction
  "D2 NOREGRESS-T 0.70" is therefore untested.
- **Q-R2b (replication):** do D1 (FIX-FASTER: `q_b = D(K2)/D(P2) >= 1.10` in every block) and
  D3 (TWO-GPU-SLOWER: `u_b = D(S1)/D(P2) <= 0.90` in every block) reproduce their run-1 labels
  on fresh cells?
- **Q-R2c (descriptive):** per-arm cell D values, CVs, link state (link.csv) vs run 1.

## Method — the frozen exp750 protocol, executed with ZERO deviation

Everything in `PREREG.md` (sha256 c6acada1b7f9420a81e2dc8b50800eed7d6eb859a224b70c037c80cc5b69ac63)
and `FROZEN750.sha256` (13 files) applies verbatim and unmodified:

- `cells750.json`: 3 blocks x 7 arms (R1/S1/S0/P2/K2/C2/H2), frozen permutation; 6 prompts x
  64 new tokens; warmup 1; timed reps 3 + one quality pass per cell; per-cell
  CUDA_LAUNCH_BLOCKING = 1 only for K2.
- Runner `run_exp750.sh` executed **unchanged** (it self-hash-checks FROZEN750.sha256 and
  aborts on any mismatch): quietwait.sh pre-cell (5400 s cap, SKIP-NOTQUIET otherwise),
  per-cell out/<id>.env / .json / .log, precell.csv, link.csv, monitor.csv, ollama preflight,
  .so hash gates (abort on mismatch), venv provenance gate, out/RUN_SHA256, so_sha_pre/post,
  then the frozen rerun pass (FOREIGN/TIMED-DRIFT/TIMER-INVALID -> one `<id>_x` rerun) and
  `classify750.py` -> out/class750.txt (VERDICT750 line).
- Gates unchanged and computed by the frozen classifier: G-F (foreign = any GPU memory gain
  > 512 MiB on a GPU not assigned to the cell, or ollama_loaded_models >= 1 at cell start),
  G-Q (quality pass out_ids/top16 identical to ref/exp749_b1_R.json for R1/S1/S0/P2/K2),
  G-M (provenance: fix749 cells via ~/moei-fix749, fix740 via ~/moei-fix740; CLB=1 only in
  K2 .env), G-P (prompts.json hash == 6d06ff56...), G-L (link.csv recorded per cell).
- Identity: model `~/models/OLMoE-1B-7B-0125-Instruct` bf16 (pre-verified present); trees
  ~/moei-engine (unpatched d252620b...38da), ~/moei-fix740 (72da70e8...a4ba4), ~/moei-fix749
  (baa30e57...4507) — all three verified == ref/exp749_so_sha_post.txt at 2026-11-09T18:4xZ
  (the runner re-checks and aborts otherwise); venv ~/venvs/moei-engine (torch 2.11.0+cu128,
  moe_infinity import path under ~/moei-engine — verified); offload ~/moe-offload; policy lcnu,
  device_memory_ratio 0.2, batch 1 greedy, timed passes (1+64) tokens, ms/tok = (t64-t1)/63;
  Winnie WSL2, 2x RTX 5060 Ti, PCIe link state recorded per cell (not manipulated).
- **Execution-state handling (recorded, not a protocol change):** run 1's `out/` (109 files)
  is renamed `out-R1-archive-20261109T1845Z` (preserved in place; the authoritative raw was
  already archived to Mack as `winnie-final-20261107T1832Z/exp750-final.tgz`, sha256
  c69474c0effa3f8ce9132dd3a9ec30b25c37e579ebe59b5be2e149fab12d9678, re-verified on Mack at
  2026-11-09T18:45Z). A fresh empty `out/` receives R2. No frozen file is created, edited or
  deleted in ~/exp750 (FROZEN750.sha256 -c verified OK immediately before launch; PREREG-R2.md
  is an additional file, not part of the frozen set). The transient systemd unit name `exp750`
  is reused because the runner's busy() self-exclusion is hardwired to `exp750.service`; runs
  are distinguished by out/ dir name, timestamps and RUN_SHA256. No exp7* unit existed at
  launch (systemctl list-units --all 'exp7*' empty).

## Pre-data predictions (informed by run 1 — replication predictions, not novel)

- D1 FIX-FASTER: high confidence (run 1: q = 1.833/1.538/1.570; every one of 18 per-prompt
  K2/P2 ratios >= 1.43).
- D2 NOREGRESS-T: moderate confidence (run 1 clean blocks 1.032/0.990; run-1 prediction 0.70).
- D3 TWO-GPU-SLOWER: high confidence (run 1 u ~ 0.50; GPU0 gen3 x2 link asymmetry).
- S1/H2 engine-vs-HF gap stays descriptive-only (envelope mismatch; no decision).

## Decision rules (pre-registered, evaluated only on clean cells of record)

1. **Primary (D2 / Q-R2a):** RESOLVED-NOREGRESS-T iff R2 yields clean R1 and S1 cells in all
   3 blocks AND 0.95 <= s_b <= 1.05 in every block. RESOLVED-REGRESS-T iff all 3 blocks have
   clean R1+S1 and some s_b > 1.05 (report magnitude). NOT-RESOLVED (INCOMPLETE again) if any
   block lacks a clean R1 or S1 after the frozen rerun pass. The frozen once-rerun rule is
   exhausted in each run; there is no further attempt in this UID.
2. **Pooled sensitivity (secondary):** recompute s with all clean blocks of run 1 (b1, b2) plus
   R2's clean blocks pooled, and report per-run vs pooled values side by side. Explicit
   cross-run caveat (different day, uncontrolled host load); the pooled view NEVER overrides
   rule 1 and never merges runs into a single gate decision.
3. **Replication status (D1/D3, Q-R2b):** label agreement = "replicated"; label disagreement
   on clean data = "SENSITIVE / non-replicated", reported honestly in both directions. Neither
   run's sealed record is suppressed, edited or retro-fitted by the other.
4. **Kill criteria:** (a) FROZEN750 or .so hash mismatch at any point -> runner ABORTS, R2
   invalid, zero claims; (b) after the frozen rerun pass, if > 50% of the 21 cells are not
   clean cells of record (FOREIGN / SKIP-NOTQUIET / TIMER-INVALID / timeout) -> RUN-INCOMPLETE,
   report clean cells descriptively only, no decision claimed; (c) any G-Q failure on an
   R1/S1/S0/P2/K2 cell -> that cell invalid per frozen rules and a CORRECTNESS finding is
   raised against the fix series (quality gate is the standing "quality first" gate); (d) no
   decision is claimed from fewer clean blocks than the frozen rule requires.

## Attribution and limits (unchanged from run 1, plus replication caveat)

One host (Winnie WSL2, asymmetric PCIe — GPU0 gen3 x2 ~1.56 GB/s H2D vs GPU1 gen4 x8, no P2P),
one model (OLMoE-1B-7B-0125-Instruct bf16), one policy/ratio (lcnu, 0.2), batch 1, 6 prompts x
64 tokens, 3 blocks, wall-clock through MoE.generate including host overhead. Not full-model
parity, not other topologies; TWO-GPU-SLOWER is specific to this link asymmetry. Cross-run
comparisons carry day/host-load noise the gates cannot see (G-F blind to CPU/disk-only
interference; same limitation as run 1). Cross-lane mitigation: the Winnie window is announced
in PEER_INDEX.md before launch (coordination mechanism used by stack1001-0034's quiet-window
rule 3). CPU/mock or source-only evidence does NOT substitute for these native cells; nothing
in R2 licenses CUDA/native-serving claims beyond this exact rig.

## Publication gate (unchanged)

No external post from R2 alone. The fix737+fix740+fix749 upstream draft
(drafts/2026-11-07-moe-infinity-multigpu-stream-race-fix737-740-749-DRAFT.md v3) keeps its
existing gate: Michael's approval of the exact text + fresh head qualification + dedupe
re-check + exact-target readback. R2 numbers may be added to that draft's evidence addenda
only after coordinator admission and only in a new revision with its own readback.

## Deliverables at run end

Raw tgz + sha256 copied to Mack (Winnie sha256sum == Mack shasum required), out/class750.txt
verdict line, owner independent recompute (no classifier import), and a fire receipt returning
this UID with path/tier/findings/limitations to coordinator 280597a49d2f. Findings are
reported whether positive or negative; run-1 evidence stays untouched.

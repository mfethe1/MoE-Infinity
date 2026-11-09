# exp753p4c PREREG — p4-clean-clearance: forced step-past-EOS replication of the exp753 engine cells

- Program: STACK-1001-79990, lane 79990-tier1-7687a6bf1295 (sole owner; hermes@mack cron fire 2026-11-09T1430Z)
- Working id: **exp753p4c** (coordinator may renumber in the STACK ledger; candidate UID below is stable)
- UID: stack1001-contrib-exp753p4c-p4-clean-clearance-winnie-v1-20261109
- Origin: FIRE-2026-11-09T1035Z adjudication (P4-ADJUDICATION-20261109.md): exp753's sole parity
  failure (p4, 6 engine rows) is an INSTRUMENT defect — engine_arm753.py passed `min_new_tokens=64`
  but the MoE-Infinity native generate ignores it (generation_loop.py stops at
  `output_ids[-1] == self.eos_token_id`); the frozen §10.4/§10.14 gate (operative; §4 was amended
  pre-data) requires n_new==64 ∧ len==64 ∧ out_ids[:21]==engine_ref[4]. The gate is SATISFIABLE only
  with step-past-EOS forcing (EOS stays in-stream at index 20). This experiment does exactly that.
- Host: Winnie (WSL2), GPU1 = RTX 5060 Ti 16GB (gen4 x8) — same GPU/model/config/env as exp752/753.
- Model: OLMoE-1B-7B-0125-Instruct (~/models), offload ~/moe-offload, policy lcnu, ratio 0.75,
  threads 4, gpu-route on, max_new 64, greedy, prompts.json (6 sealed prompts), TF32 OFF (R6).
- Engine binary: the SAME private instrumented build exp753 used: PYTHONPATH=/home/mfeth/exp753/src
  (_store.so sha256 27ee904b..., src_patched/expert_dispatcher.cpp b72febcb..., upstream 0337988).
  No rebuild, no engine source change. ~/moei-engine untouched.
- $0 spend; no new models/providers/rentals/access. EPU unarmed. Model rule: no DeepSeek Flash in
  any runtime/review/delegation route (reviewer instrument recorded in the receipt).
- Sealed artifacts of exp753 (~/exp753 on Winnie, raw + verdicts) are NOT touched. This run lives
  in a new directory ~/exp753p4.

## 1. Question

Q: With the only instrument defect fixed (forced 64-step decode on the engine path), do the exp753
engine cells reproduce the frozen parity gate (48/48 rows), clearing the sole p4 PARITY-FAIL and
yielding un-suppressed D1 (attribution) / D3 (observer overhead) labels on the FROZEN decision
rules of exp753 PREREG §6 + §10 amendments (which remain the operative contract)?

## 2. Predictions (registered before any measurement)

- P1 (parity): all 8 measurement cells pass parity 6/6 under the UNCHANGED analyzer
  (analyze753.py sha256 18e1d399...): hf rows strict 64/64 vs hf_ref; engine strict prompts
  64/64 vs engine_ref; engine p4: n_new==64 ∧ len==64 ∧ out_ids[:21]==engine_ref[4] (21-ID prefix,
  EOS 50279 at index 20). Confidence 0.9 (mechanism source-verified; greedy determinism sealed).
- P2 (flag inertness): the forced path changes nothing on prompts 0-3,5 — streams byte-equal to
  refs_v2 (greedy argmax per step; the only behavioral delta is suppressing the EOS stop-break).
  Confidence 0.9.
- P3 (drift): median(A cells) within 93.90 ± 10 % ms/tok (P4 drift band, upstream #254 contention
  nondeterminism). Confidence 0.7 (WSL/foreign-load variance).
- P4 (D3): trace arms within 5 % of A (as exp753 previewed). Confidence 0.8.

## 3. Instrument delta vs exp753 (the ONLY change)

engine_arm753_p4.py = engine_arm753.py (sha256 9eeed9a6...) + minimal diff:
1. new flag `--force-steps`;
2. after build(): read `model._native_generation_engine.eos_token_id` (recorded `eos_before`),
   set it to −1 (recorded `eos_after`), abort on mismatch;
3. top-level provenance `res["force_steps"] = {cls, eos_before, eos_after, row_lens}` per engine
   cell json (extra top-level keys are analyzer-safe; ROW-SCHEMA keys are per-row and untouched).

Mechanism (source-verified 2026-11-09 on the exact build): the decode loop
(moe_infinity/engine/generation_loop.py `_generate_standard`) has exactly ONE early-stop check,
`if output_ids[-1] == self.eos_token_id: break`; there is NO logits masking anywhere (no
MinNewTokens processor on this path). `GenerationEngine.eos_token_id` is a plain attribute set at
construction (big_modeling.py:656 from model config eos 50279). Flipping it to −1 ⇒ exactly
max_tokens decode steps with sampled tokens kept in-stream, EOS at index 20 preserved.

**Asymmetry (disclosed, by design):** engine p4 streams keep EOS at index 20 (step-past-EOS, forced
continuation 21..63 = post-EOS greedy output). The HF arm is UNCHANGED (byte-identical hf_arm.py,
HF generate(min_new_tokens=64) EOS-masks at step 20 ⇒ hf_ref[4] token 20 ≠ EOS). The two arms'
p4 streams differ at index 20 by construction (KNOWN-BASELINE-TIE class of exp753 §4/§8); each arm
is judged ONLY against its own ref. Cross-arm comparison is timing-only (ms/tok), as in exp753.

**Post-EOS tokens are textually meaningless** (greedy continuation after EOS); tokens ≥21 on p4
carry NO quality interpretation. The p4 row enters timing medians as exactly 64 forced steps
(per frozen §10.14 the row is valid iff n_new==64 — which the forced path now satisfies).

## 4. Design (frozen)

Cells (palindromic interleave, same as exp753): hf_1, a_1, b_1, c_1, g_probe, c_2, b_2, a_2, hf_2.
All GPU1, serial, one process per cell, quiet-gated (allquiet746.sh ≤5400 s), precell.csv covariate
row, mon753.sh foreign-kill watcher (FLAGGED ⇒ timing excluded, parity kept), nvsamp.py 0.05 s,
timeout 1800 (G: 1200), CUDA_VISIBLE_DEVICES=1. Engine cells run with `--force-steps`; hf cell and
G probe unchanged. Per-prompt protocol identical to exp744-753: 1-token probe then 64-token run;
ms/tok = 1000·(t_full−t_1tok)/63; cell = median over 6 prompts; arm = median over replicates.

Arms: hf (HF reference, byte-identical), A (engine, tracer dormant), B (+timeline trace), C (+compute
timing), G (graph-capture probe — RERUN for analyzer completeness + D2 replication only; exp753's
D2 answer CAPTURE-FAIL@CAPTURED already stands sealed).

Refs anchor: **refs_v2** from reclass753 (7-cell consensus; engine_ref[4] = the same frozen 21-ID
prefix in both refs and refs_v2; hf_ref byte-copy). RUN_SHA256 records the actual ref hashes.

## 5. Gates & decision rules (frozen — analyzer UNCHANGED)

- Parity (G-P): analyze753.py predicates verbatim (§3 of this file). PARITY FAIL ⇒ no timing
  verdict; result recorded as-is (program rule: keep negatives).
- Manipulation (G-M): analyzer's frozen checks (TF32, TRACE-SPAN, KERN-COVERAGE, site map, SHA
  recompute of RUN_SHA256 entries) + new: `force_steps` provenance present on ALL engine cells with
  eos_before==50279, eos_after==−1 and all row_lens==64; ABSENT on hf cells.
- D1/D3/D2 labels: exp753 PREREG §6 formulas + §10 amendments 1,2,3,5,6,15 verbatim (gap =
  med(A)−med(hf); ratio=kernel_busy/gap; KERNEL-BOUND ≥0.5 / HANDOFF-BOUND ≤0.3 / MIXED; D3 |Δ|/A
  ≤0.05 OK else PERTURBS; P4 drift ⇒ ;SUSPENDED-P4-DRIFT). p4 rows now VALID and enter medians
  (frozen §10.14) — medians therefore include prompt 4 for the first time; disclosed.
- Determinism: analyze753.py run twice on the same out/ → verdicts byte-identical (R2-style);
  additionally one cross-anchor run against the original refs/ for comparison (expected: parity
  results identical; only provenance-hash lines may differ — reported either way).
- Exclusions/kill (frozen rules reused): FLAGGED/precell ⇒ timing excluded, parity kept; RC≠0 ⇒
  FAILED cell; both A excluded ⇒ D1/D3 INCONCLUSIVE-no-clean-cells; quiet-gate exhaustion ⇒
  SKIPPED-QUIET; smoke (below) fails ⇒ abort BEFORE any measurement cell (BLOCKED-MECHANISM class),
  sealed exp753 state unchanged.

## 6. Pre-freeze smoke (disclosed; NO timing claims)

smoke753p4.sh, prompts [p0, p4], GPU1, quiet-gated, two engine processes:
- S1 WITH --force-steps: RC=0; provenance eos_before=50279/eos_after=−1; p0 strict 64/64 == ref[0]
  (flag inertness); p4 n_new==64 ∧ len==64 ∧ out_ids[:21]==ref[4] ∧ out_ids[20]==50279 (mechanism).
- S2 WITHOUT --force-steps (deliberate single-edit mutation ⇒ metric must BITE): p4 n_new==21 ∧
  out_ids==ref[4] (the sealed exp753 behavior reproduced).
Smoke results are NOT measurement cells and enter no median. S1+S2 pass ⇒ freeze ⇒ run.

## 7. Claims (pre-committed) & consequences

- C1 (primary, parity): 48/48 parity under the frozen gate ⇒ exp753's p4 PARITY-FAIL was an
  instrument artifact (ignored min_new_tokens), NOT a stream divergence; the corrected-anchor gate
  is achievable and the engine streams reproduce refs_v2 exactly on the available prefix.
- C2 (secondary): D1 attribution + D3 overhead labels computed on the frozen formulas (values
  reported whatever they are; direction only as strong as the formulas).
- C3 (replication): P3/P4 drift bands reported; outside ⇒ SUSPENDED labels per frozen rules.
- If P1 fails on any row: negative result sealed; PARITY-FAIL stands; no timing claim.
- Limitations: single host/GPU/model/envelope (RTX 5060 Ti, WSL2, OLMoE-1B-7B, lcnu 0.75); post-EOS
  continuation uninterpretable; HF/engine p4 index-20 asymmetry by construction; forced decode is a
  harness-level attribute flip, not an engine feature; medians include p4 rows (differs from
  exp753's excluded-p4 medians — do NOT compare medians across the two runs without this note).

## 8. Implementation, review, freeze

- Harness/runner/smoke author: lane owner (this fire) — small-fix class (one flag + attribute flip),
  per the recorded exp753 §10 precedent the mechanics are source-verified, not assumed.
- Independent substantive review BEFORE freeze: separate reviewer instrument (recorded in the
  receipt; exp753 §10 used `pi --print --provider mimo --no-tools`), read-only, of this prereg +
  engine_arm753_p4.py diff + smoke753p4.sh; findings dispositioned in REVIEW-P4C.md; P0/P1 must
  clear before the freeze. Test-author boundary disclosed: analyzer (the real judge) is frozen
  byte-identical from exp753 (already multi-reviewer); smoke checks reviewed, not separately
  re-authored.
- Freeze: git commit (this prereg + harness + runner + smoke) in ~/warp-work/moei-granite3b-rebuilt
  branch exp651/qwen30b-results (remote mfethe1), FREEZE file records commit sha + file shas,
  BEFORE the first measurement cell (smoke is pre-freeze, disclosed).
- Raw per-cell: json, log, util.csv, precell.csv, FLAGGED, RUN_SHA256, ENV.txt, verdict.txt (+ G:
  g_probe.json/log) — all retained and fetched to Mack at settle. Candidate evidence returned in
  the fire output; coordinator280597a49d2f alone maintains the STACK ledger/admission.

## 8.5 Pre-freeze amendments (independent review REVIEW-P4C, 2026-11-09; findings F1–F11)
Frozen BEFORE any measurement-cell execution (the §6 smoke is not a measurement). Dispositions:
- **F2 (warmup also forced; second-order footprint):** accepted as part of the single defined
  intervention — every engine step in a forced cell runs exactly 64 decode steps. All engine rows
  (warmup + p0..p5) are forced; warmup budget is 8 tokens in both exp753 and p4c (warmup output
  unused). No frozen LABEL consumes cache stats, routing deltas or per-row latency; those fields
  are descriptive-only. Medians for C2 include p4 rows (differs from exp753's excluded-p4 medians)
  — cross-run median comparison is prohibited (§7). Probe/full timing denominators use the frozen
  analyzer formula on every row alike.
- **F3 (HF-vs-engine regime mismatch at index ≥20):** confirmed and quarantined explicitly: the
  engine p4 suffix (stream indices 21..63) is post-EOS continuation and is QUARANTINED from any
  downstream consumer; no cross-arm token comparison at indices ≥20 appears in any claim; the
  frozen predicate judges engine p4 on the 21-ID prefix exactly because of this.
- **F5 (coupling/flip coverage):** smoke v2 now exercises BOTH engine construction paths used by
  the measurement (S1 A-style, S3 C-style trace+timing on) plus the unforced control (S2). The
  runner adds a per-cell fail-fast check: any forced engine row with n_new≠64 is recorded in
  out/ANOMALY (handled mechanically by the frozen INVALID-ROW-NNEW + parity rules; fail-closed).
- **F6 (prefix-flake disposition — FROZEN RULE):** exactly ONE attempt per cell as listed in §5;
  no selective rerun is permitted. A failing row/cell is recorded as-is. If a documented external
  event invalidates the run (e.g. foreign GPU kill → FLAGGED-file semantics), the run is void in
  whole and any rerun requires a new prereg addendum + new UID suffix; partial cell reruns are
  prohibited. "Re-run until pass" is not an available move.
- **F10 (smoke hygiene):** smoke v2 matches rows by prompt identity (sha256 of applied prompt
  text), asserts explicit `force_steps` presence in the unforced control, asserts the forced-path
  banner is ABSENT from the no-force control, records prompt fixture hashes, and checks the C-style
  path. Flag-inertness at p0 rests on the fact that ref[0] IS the sealed unforced stream (all
  ref streams except ref[4] never emitted EOS inside 64 tokens, so the flip cannot alter any
  non-p4 stream) — the p0 strict check is a valid control, not a missing one.
- **F4 (build pinning):** out/RUN_SHA256 now additionally pins
  moe_infinity/engine/generation_loop.py and moe_infinity/entrypoints/big_modeling.py (the exact
  Python build under test) and the smoke's derived prompt fixtures are hash-recorded.
- **F8/F11 (finish_reason + sticky mutation):** the harness consumes only `output_token_ids`
  (finish_reason never read or written to rows); the eos flip persists for the process lifetime —
  each arm runs its own process and no later phase in a cell process depends on EOS behavior.
- **F7 (top-level analyzer safety):** analyze753.py accesses row and summary dicts only via
  `get`/item reads with no top-level key whitelist; an extra `force_steps` summary key cannot
  change any label (verified by grep of the analyzer at freeze).

## 9. Threats to validity

- WSL2 quiet-gate is best-effort (same machinery as exp746-753; FLAGGED rule bounds it).
- The forced path assumes the engine's greedy per-step argmax is prefix-deterministic — sealed
  exp752/753 evidence (6/6 prompts replicated across 7+ cells) supports this; p4 continuation
  tokens after EOS are a new unmeasured regime (only the 21-token prefix is anchored).
- G cell re-run may reproduce CAPTURE-FAIL@CAPTURED or not; either way exp753's sealed D2 stands
  and this run's D2 is a replication note (secondary).
- Reviewer availability: if no independent reviewer instrument is available after bounded retries,
  the run does NOT launch (disclosed blocker; nothing measured).

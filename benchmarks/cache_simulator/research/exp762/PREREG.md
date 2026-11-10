# exp762 PREREG attempt-3 - FROZEN 2026-11-10T20:43:27Z (attempts 1-2 void, zero cells each)
# Shas at freeze:
# exp762 FREEZE attempt-3 2026-11-10T20:43:27Z (attempt-1 identity-grep void, attempt-2 SP-collision void; zero measurements in both)
# unit exp762run; busy-gated units + /proc foreign-runner scan
9e874ab2e5a7b66e60fb8424b165c6862de9e9902a8c63f816e5996206d1414e  engine_arm762.py
d5270dd28290224488e65ad6bf11b315a95535b408ff02fe944a1ea15208f6f5  cells762.json
c273c9b2710288d5a872b14bb933a3109f86996655f65faa31fb03f18127fcb1  run_exp762.sh
ba2cf1f482c84eb5568815613decfce39bea0f3bb9975c58d1d719b063fea0dc  analyze762.py
6d06ff563dd9f24ec17da9e7ea5b9910f76dfaebc536d638bff45dddad7f4468  prompts.json
3c98d2bc2f1a5f8eff09eec8acdc875f0fa5d0fa11c25edefedf75f2066e6bc6  DECISION-TREE-762.md

# PREREG-DRAFT v3 exp762 — engine-level speculative prefetch overlap (io_overlap direction)
STATUS: DRAFT v3, LAUNCH-READY pending exp761 settle. Freeze (sha-lock -> PREREG.md + FREEZE-762.txt) at push time on Winnie.

## Question
Does firing speculative expert prefetch BEFORE the layer-L barrier (PCIe transfer overlapped with layer compute) improve cold-cache decode throughput vs after-barrier (legacy), and does budgeted byte-admission (enforce) change the outcome?

## Design (4 arms x n=3 = 12 cells, interleaved fixed order)
- LGC:  speculative_prefetch=False; overlap=False; policy=off  (legacy reactive serial baseline)
- SPEC: speculative_prefetch=True;  overlap=False; policy=off  (prefetch fires AFTER barrier)
- OVR:  speculative_prefetch=True;  overlap=True;  policy=off  (fires BEFORE barrier — the lever)
- ENF:  OVR + overlap_prefetch_policy=enforce (budgeted admission; defaults ewma 0.2, safety 0.8, window 256MB, inflight 512MB)

Held fixed: gpu-route OFF in ALL arms. Rationale: ArcherConfig.__post_init__ raises on explicit gpu_only_expert_routing=True combined with overlap modes (auto-mutex sets it False when None); gpu-route is a separately measured factor (exp744) and must not confound. device_memory_ratio 0.75, lcnu, threads 4, OLMoE-1B-7B-0125-Instruct, 6 prompts x 64 tok greedy, warmup 1, one fresh process per cell (cold VRAM residency; NVMe staging ~/moe-offload warm on disk).

Build: PR #353 head b7f6ca4 (/home/mfeth/exp759/src753, MOEI_EXP752_MODE=RC banner) — same build as exp759/exp760; only config differs between arms. MOE_INFINITY_PROFILE_IO=1 all arms (out/$ID.io.jsonl).

## Key contrasts
- PRIMARY OVR-vs-LGC >= 5% ms/tok reduction (one-sided bootstrap 95% lower bound over 3v3 cells, 10000 resamples, seed 762) -> direction claim at engine level.
- SPEC-vs-LGC isolates speculative prefetch; OVR-vs-SPEC isolates barrier timing alone; ENF-vs-OVR isolates budgeting.

## Gates (fail-closed per cell, frozen analyzer analyze762.py)
- no FAILED / BANNER-FAIL ("exp752 mode=RC" in log) / BADIO (io profile non-empty)
- config echo: spec_prefetch/spec_overlap/overlap_policy effective == requested; gpu_route_effective falsy
- >=5/6 prompts with n_new==64 and decode_tok_s>0
- TOKEN-IDENTITY (added pre-freeze 2026-11-10T20:4xZ, before any cell ran; motivated by exp753
  root-cause family lesson: engine generate ignores min_new_tokens, and a config A/B on the
  generation path must prove it did not alter decode numerics): greedy decode with identical
  weights => byte-identical out_ids per prompt across ALL valid cells (early-EOS rows included,
  compared at full available length). Any divergence => exit 9 IDENTIFY-FAIL
  TOKEN-DIVERGENCE, A/B invalid, lane halts (DECISION-TREE B5).
Exit codes: 0 OVERLAP-GAIN (CI95lo>=5) | 1 NO-GAIN | 3 INCONCLUSIVE (valid<3 any arm -> one rerun of failed cells) | 9 IDENTIFY-FAIL (echo mismatch OR token divergence).

## Monitored covariates (recorded, not gates)
"All cached expert locked" warning count per cell (cache-pressure failure mode per config help); policy stats; hit rate; cold (prompt-0) vs warm (prompts 1-5) ms/tok split; mem_alloc_gb.

## Pre-freeze validations DONE (2026-11-10)
- Build-presence on runtime build (0337988 base): ArcherConfig exposes all 7 overlap fields; speculative_prefetch_overlap help text confirms before/after-barrier semantics; .sisyphus feasibility doc ABSENT (stale ref) — first A/B.
- py_compile + bash -n pass on all artifacts.
- Analyzer E2E fixture (synthetic 12 cells): clean -> correct verdict path (exit 0, CI consistent); echo-mismatch -> INCONCLUSIVE exit 3. Fixture CAUGHT a real CI bug (bootstrap diffs used sums not means -> CI 3x point) — fixed, re-validated CI 13.92 [13.61, 14.28].

## Settle
- No BELIEFS admission before verdict + seal. io_overlap append w=0.75 if OVERLAP-GAIN; w=1 if OVR-vs-LGC point gain >= 15%; w=0.25 if only SPEC-vs-LGC supports. Artifacts: tar+base64 pull, replay byte-match, SEAL-762.md, path-scoped commit, FIRE receipt, POSTING-LEDGER.

## Sequencing
Launch ONLY after exp761 (warp-lane-7687a6bf1295) settles in running.json; busy-gate includes exp761 units. Staging: cp allquiet746.sh mon752.sh nvsamp.py prompts.json from ~/exp759 to ~/exp762; freeze; systemd user unit exp762run.

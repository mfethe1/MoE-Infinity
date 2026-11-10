# SETTLEMENT-764 — SPEC-policy CPU attribution (py-spy sampling)

Written 2026-11-10T23:1xZ after VERDICT; all numbers from frozen `analyze764.py` output
(`out/verdict.txt`) and leaf greps over the frozen `.pyspy` artifacts (commands in file).

## Chain of custody
- Build: `/home/mfeth/exp759/src753` @ b7f6ca4d2caa5229698d78deb03b454fc20947dd (same as exp762).
- FREEZE-764.txt (pre-run, 2026-11-10T22:44:36Z): PREREG-764.md 23cb1214…, analyze764.py 0016f0fc…,
  run_exp764.sh e8bc3f79…, engine_arm764.py 9e874ab2… (byte-identical to exp762's engine_arm762.py,
  frozen there as c273c9b2-class artifact), prompts.json 6d06ff56…, py-spy 0.4.3, SRC_HEAD b7f6ca4.
- Cells (GPU1, CUDA_VISIBLE_DEVICES=1, lcnu r=0.75, 6 prompts × 64 tok, warmup 1):
  PROF_LGC (sp=off so=off op=off), PROF_SPEC (sp=on so=off op=off) — exp762 cell classes 1:1.
- Run 1 (22:50–22:55Z): both cells RC=0, DONE; combined samples 21,056 < frozen 30k gate →
  INCONCLUSIVE (analyzer rc=3) with zero family numbers emitted (gate precedes table).
- Extension (run_exp764b.sh sha 4b3e7364…, body = frozen run_cell verbatim, appended to FREEZE-764
  pre-execution): repeat 2 of both cells; collapsed stacks APPENDED to PROF_LGC/PROF_SPEC.pyspy;
  SAME frozen analyzer re-run. No edits to PREREG/analyzer/runner.
- Identity: env proven via cell JSON `env_exp752_mode: "RC"`, `env_profile_io: "1"`,
  `env_profile_io_out: /home/mfeth/exp764/out/…`. BANNER-FAIL for both cells is a KNOWN template
  artifact identical to exp762 (exp762/out/BANNER-FAIL lists all 12 cells; engine prints
  `exp752 mode=2` while the legacy grep expects `mode=RC`).

## VERDICT (frozen analyzer, rc=0)
- Samples: LGC 19,923 (199.2s) / SPEC 20,447 (204.5s); combined 40,370 ≥ 30,000.
- Family deltas (SPEC−LGC, self-time seconds): F1_spec_policy +0.06; F2_verify +0.00;
  F3_reshape_sched +1.26; F4_kernel_glue −3.94; F5_other +7.86. Positive total P = 9.18s.
- **VERDICT: ATTRIBUTED-A5 F5_other (85.6% of positive delta).**

## Leaf-level attribution (grep over frozen .pyspy; per-arm self-time)
- `ExpertPrefetcher.speculative_prefetch (moe_infinity/memory/expert_prefetcher.py:450)`:
  LGC 0.00s → SPEC 7.53s (**+7.53s; function exists only in the SPEC arm**).
- `DistributedExpertExecutor.wait_dispatch_local (…/expert_executor.py:1033)`: 34.75 → 29.44 (−5.31s).
- `DistributedExpertExecutor._dispatch_eager_local (…/expert_executor.py:438)`: 11.17 → 17.28 (+6.11s).
- `OffloadEngine.setup_archer_hooks (…/model_offload.py:2519)` (load-phase): 43.54 → 44.25 (cancels).

## Interpretation (evidence-bounded)
- Frozen-rule verdict is A5/F5_other; the frozen F1 rule keyed `spec_decode/` file paths and the
  prefetch policy loop physically lives in `memory/expert_prefetcher.py` — reported as-is, NO
  post-hoc re-familying of the verdict. Leaf evidence: the added SPEC-arm cost is the prefetch
  policy's own Python self-time (+7.53s ≈ exp763's untraced +7.82s/cell), partially offset in the
  wait path (−5.31s, consistent with exp763 dispatch coverage 4.34→2.45s) and shifted into eager
  dispatch (+6.11s). Mechanism for exp763's D4 (policy-CPU) is now directly measured at the
  function level; wall-clock comparisons vs exp762 are NOT made (profiler overhead acknowledged).

## Limitations
- 100 Hz sampling, two repeats per arm, self-time (leaf) attribution; no wall-clock or traffic claims.
- py-spy overhead present in both arms equally (spawn-mode, same rate); family shares are relative.

## Admission
exp764 ADMITTED (descriptive, w=0.5) — mechanism evidence for exec-path/policy-CPU thread;
receipt #81 (posting to follow under standing approval).

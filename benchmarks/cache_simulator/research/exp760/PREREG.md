# exp760 — RC-arm contention determinism (protocol replication of exp757, different build)

## Identity
- Question: is OUR event-poll implementation (PR #353 head `b7f6ca4d2caa5229698d78deb03b454fc20947dd`, retire-by-event + completion queue, env `MOEI_EXP752_MODE=RC`) byte-deterministic under the same contention manipulations under which the H arm diverged (exp752 H_1; exp758 HB1) and the P34 arm (PR #354 head `827019db`) did not (exp757)?
- This closes the correctness matrix cell RC-under-contention. exp759 established RC==P34==refs byte-identical in quiet.
- Build: `/home/mfeth/exp759/src753` (built in exp759, `_store.so` sha `f54e5756…` per SEAL-759; re-hashed in RUN_SHA256 at run start). No rebuild, no source change.
- Protocol: EXACT mirror of exp757 (A2 analyzer, A1 runner fix), except: PYTHONPATH/identity gates point at src753, `MOEI_EXP752_MODE=RC` is SET (not unset), and a per-cell RC-banner identity check (`exp752 mode=2` must appear in every cell log; absence ⇒ cell invalid, fail-closed).

## Envelope (byte-identical exp752/756/759)
OLMoE-1B-7B-0125-Instruct, `~/moe-offload`, policy lcnu ratio 0.75, 6 prompts × 64 new tokens greedy, warmup 1, threads 4, gpu-route on, GPU1, serial. Harness `engine_arm.py` (`fee327fe…`), `prompts.json` (`6d06ff56…`), `nvsamp.py`, `allquiet746.sh`, `gcol757.py` — all sha-gated byte-identical reuses; `mon760.sh` is a byte-copy of `mon757.sh` renamed.

## Cells (12, n=3 per arm)
- **Q** quiet (anchor): must byte-match sealed refs `refs/RC_2.json`+`refs/RC_3.json` (same vector; exp759 RC cells matched both).
- **C**: 12 CPU spinners started 10 s pre-engine; valid only if loadavg(1m) mean ≥ 8.
- **G**: GPU1 co-tenant `gcol757.py --alloc-gb 2` 10 s pre-engine; valid only if co-tenant PID observed AND NVML util mean ≥ 20%.
- **CG**: both; both manip checks required.
Run order in `cells760.json` (differs from exp757's draw; arms are independent cells, order carries no information in this design).

## Validity gates (fail-closed; from exp757 A2)
Row validity judged against sealed refs' shape (prompt-4 EOS at 21 tokens is natural; n_new<64 ≠ invalid). Missing out_ids ⇒ invalid. Foreign compute-app at any sample ⇒ invalid in every arm (only our registered manipulations are treatment). precell exclusions: Runner.Worker>0, foreign-prestart>0, gpu-prestart>1024 MiB, ollama≠0. util samples<10, mon samples<3 ⇒ invalid. Q loadavg mean>4 ⇒ invalid. Missing RC banner ⇒ invalid (exp760 addition).

## Verdicts
- **ANCHOR-FAIL** (exit 2): any valid Q cell not byte-identical to refs (includes Q-vs-Q disagreement). No determinism verdict; raw stands.
- **DIVERGENCE-REPRODUCED**: ≥1 valid C/G/CG cell with any prompt vector ≠ refs. Report first divergence (prompt, token index, expected vs got), per-prompt out_sha, counters, seam-mates. One pre-authorized REPEAT cell in the same arm (flagged, not counted in n).
- **CONTENTION-SAFE (bounded)**: 0 divergent valid cells; report per-arm + pooled one-sided 95% Clopper-Pearson upper bounds. Claim only "no divergence observed in n cells under these manipulations", never "deterministic".
- Timing descriptive only — NO perf claim from this run (contention cells expected slower; quiet timing already admitted in exp759).

## Statistics
n=3/arm, 12 cells; Clopper-Pearson one-sided 95% per arm + pooled. No timing tests. Single-cell events reported as events.

## Stop policy
Pre-authorized REPEAT only on DIVERGENCE-REPRODUCED (same arm). Stop after: 2 mechanical failures (same signature) or smoke gate failing twice — keep raw, report blocker, no unchanged retry.

## Provenance (per attempt)
Per-cell out/<ID>.json (out_ids, out_sha, counters, env), .log, .util.csv (NVML 0.05 s), .mon.csv (loadavg+apps 5 s), precell.csv, FLAGGED*, RUN_SHA256, ENV.txt (paths, torch, GPU, git HEAD b7f6ca4…), journal. Analyzer + this PREREG + fixture note in FREEZE-760.txt. Raw pulled to Mack `~/warp-work/exp760-rc-contention-determinism/out/` and hashed.

## Fixture policy
Analyzer derived from exp757 A2, whose verdict paths (DIVERGENCE-REPRODUCED / CONTENTION-SAFE / ANCHOR-FAIL / invalid-cell labels) are covered by exp757's fixture suites. The single new code path (no-rc-banner / no-log) verified locally by construction-synthetic test before freeze (recorded in FREEZE).

## Honest limitations (pre-declared)
One model, one GPU (RTX 5060 Ti 16 GB, WSL2), 64-token greedy, one build (#353 head) — same bounds as exp757. Spinners/co-tenant approximate, do not reproduce exp752's actual contamination mixture. If DIVERGENCE-REPRODUCED, mechanism attribution NOT claimed without separate instrumentation. n=3 bounds only rare-event rates coarsely (pooled 0/12 ⇒ CP upper ≈ 0.22/cell).

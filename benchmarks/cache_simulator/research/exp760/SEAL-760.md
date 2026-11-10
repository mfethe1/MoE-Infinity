# SEAL-760 — exp760 RC contention determinism

- Verdict: **CONTENTION-SAFE (bounded; no divergence observed)** — frozen analyzer exit 4, per PREREG-760 line 25.
- Launched 2026-11-10T16:53:31Z (`systemd-run --user -u exp760run`, Winnie WSL GPU1); unit inactive at 19:21Z check.
- Build: PR #353 head `b7f6ca4d2caa` (`_store.so` f54e5756), `MOEI_EXP752_MODE=RC` — identical provenance to SEAL-759.
- Gates passed:
  - Banner identity `exp752 mode=2` present in **12/12** cell logs (fail-closed; incl. the 2 excluded CG cells).
  - Anchor: valid Q cells Q1/Q2/Q3 **byte-identical** to sealed refs (`refs/RC_2.json` da15254592de, `refs/RC_3.json` 95dd72dd0f7d — sha-verified vs FREEZE-760).
  - Envelope shas per FREEZE-760 (engine_arm fee327fe, gcol fadf519f, mon760 ab8f319c, nvsamp 12c1f05f, allquiet 1dfc07c5, prompts 6d06ff56).
- Cells: Q 3/3, C 3/3, G 3/3 valid clean; **CG 1/3 valid** — CG1+CG3 excluded fail-closed `manip-fail-gpu(co-tenant absent)` (spinner never attached; qw=0 vs CG2 qw=112; not counted, per PREREG).
- Contention evidence: C arm loadavg 9.60–10.70 (target >=9); G arm util 71.4–73.9%; CG valid cell loadavg 12.25 + util 61.0%.
- Divergence: 0/10 valid cells, 0 diverged prompts, route_failures 0, comp_retired 0, foreign GPU procs 0 (own-only pids).
- Bounds (one-sided 95% Clopper-Pearson): per-arm 0/3 -> 0.632; CG 0/1 -> 0.950; **pooled 0/10 -> 0.259**.
- Claim limit (PREREG): "no divergence observed in n cells under these manipulations" — never "deterministic". Spinners approximate, do not reproduce exp752's exact H_1 conditions.
- Timing descriptive only, NO perf claim (Q ~11.5 tok/s, C ~5.0, G ~3.6, CG ~1.7).
- Local replay: frozen analyze760.py on pulled out/ + sha-verified refs/ -> **byte-identical** to out/verdict.txt (2026-11-10T19:2xZ).
- Sealed file shas: PREREG 512b11be..., cells760 ed7cdedb..., run_exp760 e2da640e..., analyze760 412e3f82... (per FREEZE-760); verdict.txt 06779af55f0d5746; out/runner.log 222b9ffaf665b6d6.
- Env: {}

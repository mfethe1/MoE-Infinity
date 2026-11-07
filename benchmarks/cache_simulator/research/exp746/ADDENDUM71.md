# ADDENDUM71 — exp746 settle: host-CPU contention control and a load-controlled replication of the routing A/B

Settled 2026-11-07 from the sealed run on Winnie (WSL2 Ubuntu, GPU1 = RTX 5060 Ti sm_120), freeze `d3b0dd4`, AMENDMENT1 `e33f77a`.
Run 2026-11-07T03:09:35Z (first scored cell) → EXP746-DONE 2026-11-07T04:46:24Z. Every number below is computed from `raw/` by
`gen_addendum71.py`, which asserts it against the raw files and the sealed verdict and writes nothing on any mismatch. PREREG,
AMENDMENT1 and the frozen analyzer are unchanged.

## Sealed verdict
`VERDICT SPLIT:GAP-IS-GPU-IDLE|ROUTE-Q:OFF-FASTER(PARITY-FAIL)|SENS:INCONCLUSIVE|ROUTE-S:INCONCLUSIVE`

The frozen `analyze.py` re-run on the pulled `raw/out` (PYTHONDONTWRITEBYTECODE=1) is byte-identical to `raw/out/verdict.txt`.

## Integrity
- `raw/ARTIFACT.sha256` == `freeze/ARTIFACT.sha256`; `raw/AMENDMENT1.sha256` == `freeze/AMENDMENT1.sha256`; committed freeze bytes match both.
- `out/RUN_SHA256` (11 files): `run_exp746.sh` and `allquiet746.sh` match AMENDMENT1, the other 9 match the original freeze.
- `raw/SHA256SUMS` lists 65 files; all verify.

## AMENDMENT1 and the aborted attempt (not used in any comparison)
The first q_hf_1 attempt (started 2026-11-07T02:55:25Z) passed the GPU wait at once, then waited 3397 s for CPU load; meanwhile a
foreign process from another lane (`gen.py`) started on GPU1. Pre-start GPU1 memory was 10260 MiB and HF decoded at
3.63–3.85 tok/s (quiet HF here: 29.0 tok/s). The frozen rule had already FLAGGED it. AMENDMENT1
replaced the two sequential waits with one combined wait (`allquiet746.sh`, same thresholds), moved the attempt to `out/aborted-A1/`
and reran q_hf_1. The rerun was also FLAGGED (a foreign `gen.py` from the same other lane was alive mid-cell, although pre-start GPU memory was
996 MiB), so it is excluded too. `aborted-A1` data is excluded from every speed number.

## Per-cell (sealed analyzer; ms/token = median over 6 prompts; busy/idle = NVML split; wait = combined pre-cell wait, s)
| cell | arm | spinners | ms/tok | busy | idle | load mean | PSI some avg10 | wait | status |
|---|---|---|---|---|---|---|---|---|---|
| q_hf_1 | hf | 0 | 33.12 | 14.12 | 18.95 | 1.18 | 0.10 | 578 | EXCLUDED: gpu-contamination |
| q_on_1 | on | 0 | 95.53 | 39.70 | 57.33 | 1.21 | 1.81 | 0 | CLEAN |
| q_off_1 | off | 0 | 91.16 | 38.86 | 50.85 | 1.33 | 2.09 | 0 | CLEAN |
| s_hf_1 | hf | 12 | 48.27 | 14.27 | 33.78 | 7.00 | 3.27 | 0 | EXCLUDED: row4-samples=0 |
| s_on_1 | on | 12 | 289.95 | 39.40 | 254.31 | 15.51 | 29.69 | 86 | EXCLUDED: ci-runner-active |
| s_off_1 | off | 12 | 150.34 | 37.47 | 114.99 | 9.93 | 9.28 | 971 | CLEAN |
| s_off_2 | off | 12 | 226.67 | 40.59 | 186.75 | 13.63 | 24.47 | 111 | EXCLUDED: ci-runner-active |
| s_on_2 | on | 12 | 406.37 | 56.45 | 352.92 | 32.52 | 61.11 | 715 | EXCLUDED: ci-runner-active; gpu-contamination; load-mean=32.52>18.0 |
| s_hf_2 | hf | 12 | 49.79 | 14.22 | 35.72 | 7.71 | 3.55 | 1213 | CLEAN |
| q_off_2 | off | 0 | 90.09 | 38.60 | 50.91 | 1.73 | 1.51 | 113 | CLEAN |
| q_on_2 | on | 0 | 93.80 | 39.61 | 57.20 | 1.47 | 1.93 | 0 | CLEAN |
| q_hf_2 | hf | 0 | 34.53 | 14.20 | 20.32 | 1.30 | 0.59 | 1 | CLEAN |

Every combined wait ended QUIET (none timed out); total pre-cell waiting 3788 s, max 1213 s (s_hf_2). Spinner median was
12 in every stress cell and 0 in every quiet cell. Exclusions: foreign `gen.py` on GPU1 mid-cell (q_hf_1, s_on_2), a GitHub Actions
Runner.Worker during the cell (s_on_1, s_off_2, s_on_2), loadavg mean above the stress cap (s_on_2: 32.52 > 18.0), and one prompt
window with no NVML samples (s_hf_1).

## Arms (means of CLEAN cells)
| arm | spinners | n | ms/tok | busy | idle | load |
|---|---|---|---|---|---|---|
| hf | 0 | 1 | 34.53 | 14.20 | 20.32 | 1.30 |
| hf | 12 | 1 | 49.79 | 14.22 | 35.72 | 7.71 |
| on | 0 | 2 | 94.67 | 39.66 | 57.27 | 1.34 |
| on | 12 | 0 | — | — | — | — |
| off | 0 | 2 | 90.62 | 38.73 | 50.88 | 1.53 |
| off | 12 | 1 | 150.34 | 37.47 | 114.99 | 9.93 |

## Manipulation and parity
- MANIP: `gpu_route_effective` matched the request in all 8 engine cells (True).
- PARITY (frozen rule, all engine cells): FAIL. Localized: 7 of 8 engine cells, on and off, produce identical token ids; only
  **s_on_2** differs, in all 6 prompts (first divergent token index 1–29). s_on_2 is the most contaminated
  cell in the run (foreign GPU process, CI runner, load mean 32.52). Among the other engine cells, routing on vs off does not change
  the generated tokens (as in exp744). Why one contaminated on-arm cell decoded differently is not explained by this run (n=1).
  The frozen rule tags ROUTE-Q with PARITY-FAIL, and the tag stands.
- HF cells are self-identical across all 4 runs.

## Registered predictions
- SPLIT:GAP-IS-GPU-IDLE (p=0.6): **confirmed.** Quiet gap on − hf = 60.14 ms/tok = idle 36.95 + busy 25.45 (idle share
  0.614). Only one clean quiet HF cell (q_hf_2).
- ROUTE-Q:OFF-FASTER (p=0.6): **confirmed as sealed, with PARITY-FAIL.** off − on = -4.04 ms/tok (-4.3%, n=2 vs 2;
  both off cells 90.09–91.16 are faster than both on cells 93.80–95.53). That clears the 3 ms bar
  by about 1 ms. exp744's sealed -18.83 ms/tok was mostly host load: under load control the effect is roughly a fifth as large.
- SENS:SIMILAR (p=0.5): **untested** (INCONCLUSIVE; no clean stressed `on` cell).
- ROUTE-S:OFF-FASTER (p=0.55): **untested** (INCONCLUSIVE; no clean stressed `on` cell).

## Descriptive, not registered
- Under 12 spinners, HF slowed 44.2% (n=1 each side; load 7.71) and the routing-off engine arm slowed
  65.9% (n=1 stressed; load 9.93). SENS compares the `on` arm, so this is not a SENS result.
- GPU-busy time is unchanged by host load: HF 14.20–14.22 and engine 37.47–39.70
  ms/tok across clean quiet and stressed cells. The added time is GPU-idle time, consistent with the load sensitivity seen in exp743/exp744.

## Pre-decided consequences (freeze/PREREG.md)
- ROUTE-Q:OFF-FASTER "replicated → report on upstream #315". Not acted on: the settle gate required no PARITY-FAIL, and the frozen tag
  is present. Nothing posted upstream. The routing result stands as a small (~4%) load-controlled effect, much weaker than exp744 reported.
- SPLIT:GAP-IS-GPU-IDLE → the host-side handoff is the larger term; next work targets per-layer retirement (exp744 HOSTFN:COSTLY).
  exp747 (freeze 06e6100) measures the device-side cudaLaunchHostFunc stall under CPU contention first.
- Program rule: every timed prereg records and gates on host CPU load (done in this run's runner; carried forward).

## Caveats
WSL2, not native Linux; one GPU (RTX 5060 Ti, PCIe gen4 x8), one model (OLMoE-1B-7B bf16), batch 1, lcnu at device_memory_ratio 0.75,
num_threads 4. NVML utilization is a ~sampled kernel-active fraction (50 ms sampler; the driver's window is coarser), not a timeline.
Spinners load only the Linux side; Windows-side load was not controlled. Clean replicates are small (n=1 or 2 per arm), and both
stressed `on` cells were excluded, so stress sensitivity of the default configuration is unmeasured.

# ADDENDUM72 — exp747 settle: device-side stream stall of one cudaLaunchHostFunc on WSL2, quiet vs CPU-contended

Settled 2026-11-07 from the sealed run on Winnie (WSL2 Ubuntu, GPU1 = RTX 5060 Ti sm_120), freeze `06e6100`. Run 2026-11-07T04:47:27Z (start) →
EXP747-DONE 2026-11-07T05:39:14Z. Model-free. Every number below is computed from `raw/` by `gen_addendum72.py`, which asserts it against the raw
files and the sealed verdict and writes nothing on any mismatch. PREREG and the frozen analyzer are unchanged.

## Sealed verdict
`VERDICT QUIET:HOSTFN-STALL-EXCEEDS-SYNC|CONTENTION:HOSTFN-ROBUST`

The frozen `analyze.py` (sha256 `9ad8dba0f925…`) re-run on the pulled `raw/out` (PYTHONDONTWRITEBYTECODE=1) is byte-identical to
`raw/out/verdict.txt`.

## Integrity
- `raw/ARTIFACT.sha256` == `freeze/ARTIFACT.sha256`; committed freeze bytes match it; `out/RUN_SHA256` (the 6 executed files) == their ARTIFACT hashes.
  PREREG.md sha256 `71f3ef263d08…` (committed in the freeze).
- `raw/SHA256SUMS` lists 38 files; all verify. No FLAGGED or FAILED file; all 8 cells RC=0.
- Every frozen exclusion was re-checked from the raw monitor/precell files: every combined wait ended QUIET (total 2755 s, max 1259 s),
  pre-start GPU1 ≤1024 MiB, no Ollama model, no Runner.Worker, spinner median == K, gate overrun 0 (base span medians ≤ 6.1 µs).
- After the run no PID in `out/*.spinpids` (72 recorded) was alive on Winnie.

## Per-cell (µs; hostfn_stall = device-side stall added by one host func; kern_sync = tiny kernel + cudaStreamSynchronize host wall)
| cell | spinners | stall med | p90 | p99 | frac >1 ms | kern_sync med | p90 | notify med | load mean | PSI some avg10 | spinners (median) | wait s | pre-start MiB | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k0_1 | 0 | 524.8 | 556.0 | 624.7 | 0.001 | 48.2 | 59.5 | -7.6 | 1.45 | 0.04 | 0 | 1188 | 300 | CLEAN |
| k6_1 | 6 | 541.8 | 647.6 | 879.6 | 0.002 | 66.8 | 89.3 | 2.6 | 2.41 | 0.03 | 6 | 1 | 300 | CLEAN |
| k12_1 | 12 | 470.0 | 606.3 | 3970.4 | 0.029 | 82.0 | 153.9 | 9.3 | 5.33 | 1.80 | 12 | 23 | 300 | CLEAN |
| k18_1 | 18 | 391.6 | 533.5 | 4345.8 | 0.049 | 76.2 | 118.3 | 91.2 | 7.14 | 36.94 | 18 | 61 | 303 | CLEAN |
| k18_2 | 18 | 519.0 | 1878.4 | 6523.3 | 0.111 | 71.8 | 90.0 | 10.8 | 6.90 | 38.07 | 18 | 85 | 303 | CLEAN |
| k12_2 | 12 | 382.0 | 514.0 | 2386.0 | 0.017 | 73.9 | 91.4 | 86.5 | 4.81 | 1.64 | 12 | 92 | 303 | CLEAN |
| k6_2 | 6 | 535.6 | 605.2 | 700.5 | 0.002 | 59.9 | 87.4 | 3.4 | 3.07 | 0.04 | 6 | 1259 | 303 | CLEAN |
| k0_2 | 0 | 519.2 | 548.9 | 671.7 | 0.001 | 44.5 | 53.6 | -9.7 | 1.74 | 0.00 | 0 | 46 | 303 | CLEAN |

## Per-level (means of the 2 clean cells per level)
| spinners | n | stall med | p90 | p99 | frac >1 ms | kern_sync med | p90 | notify med | load mean | PROJ ms/token (upper bound) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2 | 522.0 | 552.4 | 648.2 | 0.001 | 46.3 | 56.6 | -8.6 | 1.59 | 75.2 |
| 6 | 2 | 538.7 | 626.4 | 790.1 | 0.002 | 63.4 | 88.4 | 3.0 | 2.74 | 77.6 |
| 12 | 2 | 426.0 | 560.2 | 3178.2 | 0.023 | 77.9 | 122.7 | 47.9 | 5.07 | 61.3 |
| 18 | 2 | 455.3 | 1206.0 | 5434.5 | 0.080 | 74.0 | 104.1 | 51.0 | 7.02 | 65.6 |

- QUIET: stall / kern_sync = 11.26 (bar ≥2) → HOSTFN-STALL-EXCEEDS-SYNC.
- CONTENTION: r_h = stall(12)/stall(0) = 0.82 (< 1.3 → HOSTFN-ROBUST); r_s = kern_sync(12)/kern_sync(0) = 1.68. At 18 spinners
  r_h = 0.87.

## Registered predictions
- QUIET:HOSTFN-STALL-EXCEEDS-SYNC (p=0.75): **confirmed.** One host callback stalls the stream 522.0 µs (median, quiet) — 11.3× a
  complete kernel+sync round trip (46.3 µs). Cell medians span 382.0–541.8 µs across all levels.
- CONTENTION:HOSTFN-FRAGILE (p=0.55): **refuted** (sealed HOSTFN-ROBUST). The median stall did not grow with Linux-side CPU contention
  (538.7 µs at 6 spinners, 426.0 at 12, 455.3 at 18, vs 522.0 quiet), while kern_sync rose 1.68×. What contention does
  grow is the tail: the fraction of callbacks stalling >1 ms rises monotonically 0.001 → 0.002 → 0.023 →
  0.080 (0/6/12/18 spinners), and p99 goes from 648.2 to 5434.5 µs. The tail is descriptive, not a
  registered bar.

## PROJ lines (descriptive upper bounds, not measurements)
144 callbacks/token (16 route + 128 retirement) × stall, if fully serialized on the critical path: 75.2 ms/token quiet,
61.3 at 12 spinners. This exceeds the whole engine-vs-HF gap measured in exp746 (60.14 ms/token), so the callbacks cannot all
be serialized; the true per-token cost is some fraction of the bound.

## Interaction with exp746 (settled, ADDENDUM71)
- exp746 ROUTE-Q: routing off − on = -4.04 ms/token (idle -6.39), tagged PARITY-FAIL. Routing on adds 16 route callbacks/token
  (8.4 ms if serialized at the quiet median) and routing off replaces them with 16 blocking syncs (~0.74 ms at the
  kern_sync median). The hostfn-derived bound on the routing difference is therefore ≤ 7.6 ms/token; the measured
  4.04 ms sits inside it with the predicted sign (its GPU-idle component, -6.39 ms, is the larger part). This is arithmetic consistency, not a test.
- HOSTFN-ROBUST says the callback median does not explain exp744's large load sensitivity (~5.2 ms/token per load unit). The growing tail
  could contribute some of it; this run does not measure how much.
- The 128 retirement callbacks/token are present with routing on AND off, so the larger priced term (66.8 ms/token upper bound,
  quiet) is untouched by the routing flag.

## Pre-decided consequences (freeze/PREREG.md)
- HOSTFN-STALL-EXCEEDS-SYNC → fires. The per-expert retirement and per-layer route callbacks are a priced WSL cost (≈522.0 µs each,
  quiet median). Next: an engine change measured against exp744/exp746 — retire per layer with ONE host func, or poll completion events
  from the exec thread instead of host funcs. Upstream-relevant, but must be checked on native Linux before anyone claims it in general.
- HOSTFN-FRAGILE → does NOT fire (sealed ROBUST). No recommendation of `gpu_only_expert_routing=False` on WSL follows from this run.
- HOSTFN-CHEAP → does not fire.
- No upstream post from this settle (model-free, WSL-only).

## Caveats
- WSL2 only (kernel 6.6.87.1-microsoft-standard-WSL2), NOT native Linux; WSL's paravirtualized GPU path may be what makes a host
  callback ~0.5 ms. One GPU (RTX 5060 Ti on PCIe gen4 x8), torch 2.11.0+cu128, CUDA 12.8.
- The callback is a no-op C function (`free(NULL)`, no GIL); MoE-Infinity's real callbacks do work (queue push, condition-variable
  wake), so this stall is a lower bound per callback.
- Spinners load only the Linux side; Windows-side load was not controlled. 1-min loadavg lags the spinners (each cell's monitor spans 39–47 s, including the 30 s settle), so
  "load mean" under-reads the imposed contention; the controlled variable is the spinner count, verified by its median.
- n=2 cells per level; N=1500 samples per cell. PROJ and the exp746 interaction are arithmetic, not measurements.

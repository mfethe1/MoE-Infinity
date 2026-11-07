# ADDENDUM73: exp751 settle. Native-Linux replication of the hostfn stall (exp747) and the engine-vs-HF gap (exp746)

Settled 2026-11-07 from the sealed run on vast.ai instance 59597907. The machine was native Linux (not WSL) with an RTX 5060 Ti 16 GB
(driver 595.91.07, PCIe gen4 x16), an AMD EPYC 7552 slice with a cgroup v1 quota of 23.04 cores, torch 2.11.0+cu128 and CUDA 12.8.
- Freeze `008fd5b`. Amendments 1–4, all written before the data they affect: `3d708fa`, `cb26d87`, `201382d`, `fb7206b`.
- Phase A and HF cells ran from 17:42Z. The four engine cells re-ran at 18:10–18:15Z under AMENDMENT4.
- Every number below is asserted against `raw/` by `gen_addendum73.py`, which prints ALL ASSERTS OK.
- Rental cost was about $0.31: account credit went from 79.478 to 79.171. The instance was destroyed and the account shows 0 instances.

## Sealed verdict
`VERDICT HOSTFN:WSL-INFLATED|GAP:PARTIAL|ROUTE:OFF-FASTER`

- The analyzer is the AMENDMENT1 version (sha256 `2a76dca6…`). It differs from the freeze only by the cgroup-PSI exclusion.
- Re-run on the pulled `raw/out`, it reproduces `raw/out/verdict.txt` byte for byte.
- `cells.json` matches the freeze ARTIFACT.
- The executed runner (`out/RUN_SHA256`) is the AMENDMENT4 runner (`e15cef24…`) with `ENGINE_RATIO=0.60`.
- All 93 manifest files, hashed on the instance before the pull, verify.

## Integrity and exclusions
- **All 10 cells CLEAN.** Every pre-start gate ended QUIET: GPU at 2 MiB, container cores ≤0.04. No FLAGGED file, and all cells
  RC=0 on the final run.
- **Shared host.** Host loadavg was 34–47 throughout, and host PSI some avg10 was 61% at start. That load belongs to other tenants:
  our cgroup was idle between cells and is gated on its own usage (AMENDMENT1/2).
- **Not controlled:** cgroup v1 has no per-cgroup PSI, so that exclusion could not fire (AMENDMENT2). Memory-bandwidth and LLC
  interference from other tenants is not controlled.
- **Engine OOM at 0.75.** At the pre-registered ratio, all four engine cells failed with CUDA OOM (`out/a3_oom/`). The untimed
  diagnostic (`diag/info2.txt`) gave 0.70 OOM, 0.65 OOM and 0.60 RC=0 with a 15242 MiB peak.
  - WSL's exp746 engine cells peaked at 16199/16310 MiB, because WDDM can oversubscribe VRAM into system memory instead of failing.
  - The native card also reports 461 MiB less usable memory.
  - So the native engine runs with a smaller expert cache than WSL. That biases the GAP comparison against native.

## HOSTFN: the device-side stall of one `cudaLaunchHostFunc`
| level | stall med µs | p90 | frac >1 ms | kern_sync med µs | notify med µs |
|---|---|---|---|---|---|
| spin=0 (n=2) | **108.5** | 115.2 | 0.000 | 27.5 | 23.8 |
| spin=6 (n=2) | 85.0 | 91.1 | 0.000 | 28.1 | 24.2 |

- Native/WSL stall = **0.208**: 108.5 µs vs 522.0 µs. kern_sync native/WSL = 0.593.
- Native stall/kern_sync = 3.95, against 11.3 on WSL.
- The ≤150 µs bar is met → **WSL-INFLATED**: about 80% of the per-callback stall measured on Winnie is a WSL2/dxgkrnl cost.
- The callback still costs about 4× a kernel round trip natively and is not free.
- Upper-bound projection: 144 serialized callbacks/token × 109 µs = **15.6 ms/token** natively, against 75.2 on WSL.

## GAP: engine (gpu-route on) minus HF, quiet, ms/token
| arm | native ms/tok | busy | idle | WSL ms/tok (exp746) |
|---|---|---|---|---|
| HF | 22.38 | 14.19 | 8.16 | 34.53 |
| engine on | 60.85 | 22.24 | 37.89 | 94.67 |
| engine off | 54.10 | 24.08 | 29.55 | — |

- Native gap = **38.47 ms/tok**, split into idle 29.73 and busy 8.05 (idle share 0.773).
- Native/WSL gap = 0.640, between the bars (≤0.5 and ≥0.8) → **PARTIAL**.
- The engine/HF ratio is **2.72 natively vs 2.74 on WSL**. This is descriptive, not a bar. Everything got about 35% faster: HF
  dropped from 34.5 to 22.4 and the engine from 94.7 to 60.9. The engine's overhead relative to HF did not change.
- Because the native engine ran with a smaller cache (ratio 0.60), the like-for-like ratio is at most this.

## ROUTE: off minus on
- **−6.75 ms/tok, so gpu-route off is faster.** That is idle −8.34 and busy +1.85.
- Engine token-id parity holds across all 4 engine cells (WSL exp746 had PARITY-FAIL). HF parity also holds.
- The sign matches exp746's ROUTE-Q of −4.04. Natively, turning off the routing callbacks recovers about 8 ms of GPU-idle time
  per token.

## What this settles
1. **The 522 µs per-callback stall is mostly WSL.** The pre-decided consequence for "WSL-INFLATED" fires: report it as a WSL
   deployment caveat for anyone running MoE-Infinity on Windows/WSL.
2. **The engine-vs-HF gap is not a WSL artifact.** Natively it is still 38 ms/tok, 2.7× HF, and 77% of it is GPU-idle time. The
   15.6 ms/tok callback upper bound explains at most about half of that idle time, so exp748 (per-layer retirement or polling)
   remains worth running as an engine-level fix.
3. **Turning routing off helps on native Linux too** (−6.75 ms/tok, with parity), so the routing-callback path has a real cost
   outside WSL.

## Caveats
- One host and n=2 per arm.
- Different CPU (EPYC slice vs Ryzen 3700X) and host driver (595.91 native vs 591.86 Windows/WSL), so these are environment
  differences, not only WSL on vs off.
- The engine ratio is 0.60 natively vs 0.75 on WSL. The matched follow-up, Winnie at ratio 0.60, would remove that confound.
- The no-op callback gives a lower bound on per-callback cost.

## Files
`raw/out/` (cells, verdict, ENV, precell, RUN_SHA256, `a3_oom/`), `raw/diag/` (the AMENDMENT4 ratio diagnostic),
`raw/MANIFEST.sha256`, setup/run logs, `gen_addendum73.py`.

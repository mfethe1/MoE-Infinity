# exp751 AMENDMENT4: engine cells run at ratio 0.60 because native Linux has no VRAM spill (Phase B only)

Written 2026-11-07 ~18:15Z, after Phase A and the HF cells completed and **before any successful engine cell**. No engine timing had
been observed. The finished Phase A, HF and micro cells are kept unchanged.

## What happened
- All four engine cells (q_on_1, q_off_1, q_off_2, q_on_2) failed at ratio 0.75 with
  `CUDA error 2 … device_caching_allocator.cpp:28 allocate_and_cache: out of memory`.
- An NVML sampler showed GPU memory climbing to the ceiling (15838 MiB) before the failure.
- The untimed diagnostic (16 tokens, prompts.json, gpu-route on) gave:
  - ratio 0.70: OOM.
  - ratio 0.65: OOM.
  - ratio 0.60: RC=0, peak 15242 MiB.
- The diagnostic outputs stay under `diag/` and are not cells.

## Why WSL fit and native does not
- On Winnie (WSL2), the exp746 engine cells already peaked at 16199/16310 MiB. That is at the physical limit.
- WDDM/dxgkrnl lets device allocations oversubscribe into shared system memory instead of returning OOM. Native Linux returns OOM.
- The native card also reports 461 MiB less usable total: 15849 vs 16310 MiB from `cudaMemGetInfo`.
- **New hypothesis, not tested here:** some of the WSL engine time at ratio 0.75 may be VRAM spill traffic. That would make part of
  the 60 ms gap a WSL memory-oversubscription cost, separate from the callback stall.

## Change
- `run_exp751.sh` takes `ENGINE_RATIO`, default 0.75. The re-run uses `ENGINE_RATIO=0.60` for all four engine cells. The value is
  recorded in `out/RUN_SHA256`.
- The failed cells' logs, the FAILED file and the first ENV.txt and RUN_SHA256 move to `out/a3_oom/`.
- Cells that already have JSON are skipped by the existing rule (m0_1, m6_1, m6_2, m0_2, q_hf_1, q_hf_2).

## Effect on verdicts
- **HOSTFN**: unaffected. Phase A is complete and was analyzed under the frozen code.
- **GAP**: now compares native engine at 0.60 with the WSL engine at 0.75. A smaller expert cache can mean more misses and more
  callbacks, which biases toward a larger native gap. Because of that bias, a MOSTLY-ENV result is conservative, and a
  PERSISTS-NATIVE result is tagged **RATIO-CONFOUNDED**. A matched ratio-0.60 run on Winnie is the follow-up that settles it.
- **ROUTE**: on and off run at the same ratio, so the within-native comparison is unaffected.

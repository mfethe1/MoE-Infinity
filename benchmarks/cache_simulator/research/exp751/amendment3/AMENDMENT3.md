# exp751 AMENDMENT3: NVTX v3 header path for the engine build (build fix, pre-data)

Written 2026-11-07 ~17:30Z. The engine build on instance 59597907 failed at the compile step, before any cell ran. No data had been
collected.

## Why
- The build stopped with `fatal error: nvtx3/nvtx3.hpp: No such file or directory`.
- The CUDA 12.8 devel image ships only the legacy NVTX C headers (`/usr/local/cuda/include/nvtx3/nvToolsExt*.h`).
- Winnie has the same CUDA layout. Its `~/moei-engine/rebuild.sh` exported
  `CPATH=...:/opt/nvidia/nsight-systems/2024.6.2/target-linux-x64/nvtx/include`, which supplies the header-only NVTX v3 C++ API.
  `setup751.sh` did not reproduce that step.

## Change (setup751.sh only)
- Before the `pip install -e .` build, find the first `*/nvtx/include/nvtx3/nvtx3.hpp` under `/opt/nvidia` or `/usr/local/cuda/`,
  export its include root as `CPATH`, and log the path and sha256.
- On this instance that is `/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nvtx/include`.
- The header's sha256 is `db716da5…66c89b2`, **byte-identical** to Winnie's nsight-systems copy (NVTX3 C++ v1.0). NVTX stays
  enabled, as on Winnie, so the instrumented engine is unchanged.

## Unchanged
Everything else, including the AMENDMENT1/2 gating, the cells, the analyzer, the bars and the source commit plus 22-line diff.

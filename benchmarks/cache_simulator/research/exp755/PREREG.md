# exp755: does the retire-by-event + completion-queue decode win (−8.20 ms/tok on WSL) replicate on native Linux? (rented vast.ai RTX 5060 Ti)

Frozen 2026-11-09 before any rental. Lane 79990, STACK-1001-79990. Authorization: Michael, Telegram thread 79990, 2026-11-07:
"you have access to vast.ai ... your fine to rent through vast with my account and get this experiment and learnings figured out so we can
speed things up" (standing, exp751-exp755 series) + 2026-11-08 "I approve posting and engagements as needed to keep making progress."

## Question
On Winnie (WSL2, RTX 5060 Ti 16 GB, gen4 x8, Ryzen 7 3700X), exp752 (ADDENDUM75, admitted #77/1001) measured with quiet-gated cells:
- H (upstream `cudaLaunchHostFunc` retirement): **93.90 ms/tok**
- R (per-expert retirement by CUDA event poll): **90.98** (R−H −2.92, no-change within the 3 ms bar)
- RC (R + completion events released by query instead of caller-stream host callback): **85.70** (RC−R −5.28, RC−H **−8.20, −8.7%**)
Byte-identical greedy outputs across all three modes on every quiet cell.

exp751 (ADDENDUM73) measured the single-`cudaLaunchHostFunc` device-side stall on this same GPU model on native Linux: **WSL-INFLATED**
(native stall far below the 522 µs WSL value). If the RC win is mostly removal of WSL-specific hostfn stalls, it should attenuate sharply
on native Linux. If it survives, the mechanism is queueing/serialization in the dispatch path, not raw hostfn latency — which strengthens
upstream PR #353 (already posted, promises native numbers in-thread).

## Design
- **Hardware:** one rented vast.ai RTX 5060 Ti 16 GB (same GPU model as Winnie GPU1 and exp751's host), verified, reliability ≥0.99,
  single GPU with full tenancy. Native Linux Docker container (`nvidia/cuda:12.8.1-devel-ubuntu24.04`); `ENV.txt` records the
  WSLInterop probe to prove not-WSL. Fallback classes (recorded as confounds if used): RTX 4060 Ti 16 GB, RTX 3090 24 GB.
- **Software:** identical to Winnie's moei-engine venv and to the exp752fix build:
  - torch 2.11.0+cu128, transformers 5.22.1, pinned freeze (`requirements-pinned.txt`, `--no-deps`), moe-store `096f51f9`, CUTLASS `954c8d7b`,
    flags `MOE_ENABLE_SM120=1 MOE_ENABLE_SM90=0`, NVTX v3 header on CPATH (exp751 AMENDMENT3).
  - MoE-Infinity `033798811664f5d89cae58049ff16e912ebc5862` + Winnie's 22-line local diff (`winnie-local.diff`)
    + **the exp752-fixups sources** overlaid: `core/parallel/expert_dispatcher.{cpp,h}` ← `src_fixed/`
    (sha256 prefixes `8341bb3f…` / `9936b82f…` — byte-identical to the compile-verified Winnie exp752fix build and to PR #353's content).
  - Arms differ ONLY in `MOEI_EXP752_MODE`: H=0, R=1, RC=2. Harness `engine_arm.py` byte-identical to exp752's (sha `fee327fe…`).
- **Model:** OLMoE-1B-7B-0125-Instruct, all files must match Winnie's sha256 (`model.sha256`), else setup fails.
- **Fit ladder (untimed, pre-data):** probe ratios 0.75 → 0.70 → 0.65 → 0.60 with 1-prompt loads into throwaway offload stores
  (exp751 AMENDMENT4: native fit ratio 0.60 expected). First ratio that fits becomes THE ratio for every timed cell (paired across arms);
  the choice is written to `out/RATIO755` + `out/AMENDMENT-ratio.txt` before any timed cell runs.
- **Prep (untimed):** one `engine_arm.py` run on `prep_prompts.json` (2 prompts, 8 tokens) at the chosen ratio builds the real
  offload store `/root/moe-offload` once; all timed cells reuse it (matches Winnie, where the store pre-existed).
- **Cells (timed):** 9 engine cells, drift-balanced order H,R,RC | RC,R,H | H,R,RC (n=3 per arm), serial, one model process per cell,
  `timeout 1800` each. All cells: lcnu policy, ratio from ladder, `--threads 4 --gpu-route on`, 6 prompts × 64 new tokens, warmup 1.
- **Per-cell gating (native):** GPU ≤1024 MiB used and zero foreign compute apps before start (wait ≤600 s, else proceed FLAGGED);
  cgroup `cpu.stat` usage delta over a 10 s window <15% of wall (container sees host loadavg — exp751 AMENDMENT1; v1 fallback `cpuacct.usage`).
  Samplers: `nvsamp.py` 0.05 s util/mem + `mon755.sh` (loadavg, cgroup delta, foreign GPU procs) for every cell.

## Exclusions (frozen in analyze755.py)
- Pre-start GPU >1024 MiB or any foreign compute app (contamination flag; excluded entirely).
- NVML util baseline (first 8 s) mean >5%.
- Any prompt row with <10 util samples; non-zero return code.
- Host loadavg mean >4.0 during the cell; cgroup CPU delta >30% during the cell (`cpu-contaminated`).
- Manipulation check: banner `exp752 mode=N` must match the arm and `gpu_route_effective is True`, else `manip-fail`.

## Verdicts and priors
- **PARITY:** greedy token ids must match across arms per cell; H cells must be self-consistent first (≥2 H cells). Any mismatch →
  PARITY-FAIL → all speed verdicts UNSAFE.
- **REPLICATE (RC−H, quiet clean-cell means, ms/tok):**
  - Δ ≤ 0.5 × (−8.20) = **−4.10 → REPLICATED** (at least half the WSL effect survives native).
  - −4.10 < Δ < 0 → **DIRECTION-ONLY**.
  - Δ ≥ 0 → **NOT-REPLICATED-NATIVE**.
  - Prior: REPLICATED 0.25, DIRECTION-ONLY 0.45, NOT-REPLICATED-NATIVE 0.30 (exp751's WSL-INFLATED hostfn prior says part of the win is
    hostfn-stall-specific; the completion-wait *serialization* term may still be native-real).
- **RETIRE (R−H):** |Δ| < 3 ms → NO-CHANGE (expected; matches WSL −2.92 no-change).
- **COMPL (RC−R)** reported with the same 3 ms practical bar.
- Reference constants (WSL, ADDENDUM75): H 93.90 / R 90.98 / RC 85.70; RC−H −8.20.
- **Decision consequences:**
  - REPLICATED or DIRECTION-ONLY → post native numbers to PR #353 discussion (approved engagement), framing magnitude honestly.
  - NOT-REPLICATED-NATIVE → post the attenuation to PR #353, scope the PR's claim to WSL deployments, and redirect engine work to
    the busy-time term (exp751 GAP:PARTIAL direction).

## Confounds disclosed up front
- CPU differs (server slice vs Ryzen 7 3700X); driver stack differs from Winnie's Windows/WSL — these are environment differences
  beyond WSL-vs-native (same disclosure as exp751).
- Fit ratio may differ from WSL's 0.75 (expected 0.60) — all arms share one ratio, so within-host pairing holds; absolute ms/tok
  is NOT comparable to Winnie's numbers, only deltas are.
- n=3 cells per arm on one host; a second host would be a follow-up.
- No Winnie timing data is re-used beyond the sealed reference constants.

## Budget and safety
- Bound to exactly ONE instance via `rental_authorization.json`: approved_experiment=exp755, max_dph $0.25, max_total_spend $5.00,
  deadline 8 h. The warp-vast-reaper enforces these caps independently.
- After artifacts are pulled to Mack and hashed (SHA256SUMS), the instance is destroyed and verified gone; authorization returns to IDLE.

## Freeze manifest (sha256, first 16 hex)
engine_arm.py fee327fe1ab3ab33 · nvsamp.py 12c1f05fa112e9f6 · prompts.json 6d06ff563dd9f24e ·
src_fixed/expert_dispatcher.cpp 8341bb3f7afa3719 · src_fixed/expert_dispatcher.h 9936b82f97feb165 ·
winnie-local.diff 19a1284028042add · prep_prompts.json fd51e5a82c9298ad ·
(runner/analyzer/cells/setup shas recorded in the repo commit; sealed copies under research/exp755/freeze/)

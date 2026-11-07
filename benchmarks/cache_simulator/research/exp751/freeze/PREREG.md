# exp751: is the host-callback stall and engine-vs-HF gap a WSL artifact? (native-Linux replication, rented vast.ai RTX 5060 Ti)

Frozen 2026-11-07 before any rental. Lane 79990, STACK-1001-79990. Authorization: Michael, Telegram thread 79990, 2026-11-07: "you're fine to rent
through vast with my account and get this experiment and learnings figured out so we can speed things up."

## Question
On Winnie (WSL2, RTX 5060 Ti on GPU1 PCIe gen4 x16, Ryzen 7 3700X):
- exp747 (ADDENDUM72) measured that one `cudaLaunchHostFunc` adds a device-side stream stall of **522.0 µs**. A tiny kernel plus
  sync costs **46.3 µs** (ratio 11.3).
- exp746 (ADDENDUM71) measured the quiet MoE-Infinity engine at **94.67 ms/token** (gpu-route on) vs HF at **34.53 ms/token**.
  The gap is 60.14 ms/token, of which GPU idle is 36.95 ms.

Both results could be WSL artifacts: WSL's paravirtualized GPU path (dxgkrnl) adds host-side latency to driver callbacks. Before we
change the engine (per-layer retirement, worker-thread polling) or report upstream, we need the same measurement on native Linux with
the same GPU model.

## Design
- **Hardware:** one rented vast.ai RTX 5060 Ti 16 GB, verified, PCIe 4.0. Native Linux Docker container, not a VM, and not WSL;
  `ENV.txt` records the WSLInterop probe. Image `nvidia/cuda:12.8.1-devel-ubuntu24.04`.
- **Software:** identical to Winnie's moei-engine venv.
  - torch 2.11.0+cu128 and transformers 5.22.1.
  - MoE-Infinity `033798811664f5d89cae58049ff16e912ebc5862` plus Winnie's 22-line local diff (`winnie-local.diff`).
  - moe-store `096f51f9` and CUTLASS `954c8d7b`.
  - Build flags `MOE_ENABLE_SM120=1 MOE_ENABLE_SM90=0`.
  - All other Python packages pinned to Winnie's freeze (`requirements-pinned.txt`, installed with `--no-deps`).
- **Model:** OLMoE-1B-7B-0125-Instruct. All 9 files must match Winnie's sha256 (`model.sha256`), otherwise setup fails.
- **Phase A:** exp747's `micro2.py`, unchanged, 1500 reps. Cells: m0_1, m6_1, m6_2, m0_2 (0 or 6 CPU spinners, palindromic).
- **Phase B:** exp746's arms, unchanged: `hf_arm.py` and `engine_arm.py` with lcnu, ratio 0.75, 4 threads and gpu-route on/off,
  6 prompts and 64 new tokens. Busy/idle is split via NVML (`nvsamp.py` at 0.05 s). Cells: q_hf_1, q_on_1, q_off_1, q_off_2,
  q_on_2, q_hf_2. Before the cells, an untimed prep run builds the offload store once.
- **Pre-cell wait:** each cell waits for GPU ≤1024 MiB and loadavg1 <3.0, for at most 600 s. The rented container has no Ollama and
  no CI runners.

## Exclusions (frozen in analyze.py)
- The cell's GPU shows >1024 MiB before it starts (contamination flag).
- A quiet cell has mean loadavg >4.0. A quiet cell has spinners present, or a spinner cell has fewer spinners than intended.
- The NVML idle baseline is >5% (another GPU tenant).
- Any prompt row has <10 util samples.
- Micro: gate overrun on more than 5% of reps.
- A non-zero return code.

## Verdicts and priors
- **HOSTFN**, from the spin=0 native stall median:
  - ≤150 µs → **WSL-INFLATED**: the stall is a WSL cost. Prior 0.50.
  - ≥350 µs → **NATIVE-ALSO-SLOW**: the stall is in the CUDA driver or runtime itself. Prior 0.35.
  - Otherwise → PARTIAL.
- **GAP**, from native engine-on minus HF, quiet:
  - ≤0.5 × 60.14 → **MOSTLY-ENV**.
  - ≥0.8 × 60.14 → **PERSISTS-NATIVE**. Prior 0.55: about 25 ms of the WSL gap is GPU-busy time, which no OS fix removes.
  - Otherwise → PARTIAL.
- **ROUTE**, from off minus on:
  - |Δ| <3 ms → NO-CHANGE; otherwise OFF-FASTER or OFF-SLOWER.
  - The result is tagged PARITY-FAIL if engine token ids differ across engine cells, as they did in exp746.
- **Decision consequences:**
  - WSL-INFLATED plus MOSTLY-ENV: report it as a WSL deployment caveat and move the engine work to the busy-time term.
  - NATIVE-ALSO-SLOW: exp748 (per-layer retirement and polling) is an engine-level fix worth upstreaming, with this data as the
    native evidence.

## Confounds disclosed up front
- **CPU:** a slice of a server CPU, not a Ryzen 3700X. The host driver also differs from Winnie's Windows 591.86 / WSL stack.
  These are environment differences, not just WSL on vs off.
- **Replication:** n=2 cells per arm. One rental means one host. A second host would be a follow-up, not part of this run.
- **Data use:** no Winnie data is re-used beyond the sealed reference constants.

## Budget and safety
- Bound to exactly one instance through `rental_authorization.json`: approved_experiment=exp751, max_dph $0.20, max_total_spend
  $3.00, deadline 6 h. The warp-vast-reaper enforces these.
- After artifacts are pulled and hashed, the instance is destroyed and verified gone.

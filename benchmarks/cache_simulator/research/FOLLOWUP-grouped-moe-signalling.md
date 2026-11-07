# Grouping the expert math isn't enough at batch 1: group the signalling too

A follow-up to NVIDIA's post [Efficient MoE Training for Biological Foundation Models](https://developer.nvidia.com/blog/efficient-moe-training-for-biological-foundation-models/),
shared by [@PyTorch](https://x.com/PyTorch/status/2118342695491879027) on 2026-11-05.

The post makes a point we agree with. A naive MoE layer loops over its experts and launches separate work for each one. Grouped
execution submits all the experts' work together and removes most of that launch and scheduling overhead. The post measures this
for large-batch training on B200s.

We have been measuring the other end: **single-user, batch-1 decoding with experts offloaded to system RAM, on a 16 GB consumer
GPU.** In that setting, per-expert overhead is still the problem, but it isn't in the matrix multiplies. Every number below comes from
a preregistered experiment with frozen analysis code and published raw data.

## Setup

- RTX 5060 Ti 16 GB (consumer Blackwell, SM120) under WSL2 on Windows, Ryzen 7 3700X.
- OLMoE-1B-7B-0125-Instruct, bf16, greedy, 64 new tokens, 6 prompts.
- Engine: [MoE-Infinity](https://github.com/EfficientMoE/MoE-Infinity) 0337988, with experts offloaded to host RAM.
- Baseline: Hugging Face transformers 5.22.1 with the whole model resident on the GPU. In this version, OLMoE's experts resolve to
  the `grouped_mm` implementation by default (checked on the test host with torch 2.11, which provides
  `torch.nn.functional.grouped_mm`). So the baseline is already the grouped path the post recommends, not the per-expert Python loop.

## What we measured

1. **A grouped expert kernel made no difference at batch 1** ([exp738, ADDENDUM68](exp738/ADDENDUM68.md)).
   - With MoE-Infinity's grouped decode kernel switched on: 93.10 ms/token.
   - Without it: 92.35 ms/token, on clean cells.
   - At batch 1 each expert sees one token, so little launch overhead is left to remove.

2. **Most of the engine's extra time is the GPU sitting idle** ([exp746, ADDENDUM71](exp746/ADDENDUM71.md)).
   - Under load-controlled, quiet-host conditions the engine runs at 94.67 ms/token and HF at 34.53, a 60.14 ms/token gap.
   - Splitting that gap with NVML: **36.95 ms (61%) is GPU-idle time** and 25.45 ms is busy time.
   - The GPU is waiting on the host, not computing.

3. **One host callback stalls the CUDA stream for about half a millisecond** ([exp747, ADDENDUM72](exp747/ADDENDUM72.md)).
   - This was a model-free microbenchmark of `cudaLaunchHostFunc`.
   - On a quiet host, inserting one host function adds a **522 µs median device-side stall**. A complete tiny-kernel plus
     `cudaStreamSynchronize` round trip takes 46 µs, so the callback costs 11.3× as much.
   - The median did not grow with CPU contention: 0.82× at 12 busy spinner threads. The tail did grow: the share of callbacks over
     1 ms went from 0.1% to 8% at 18 spinners.

4. **The engine issues about 144 such callbacks per token**: 16 for routing and 128 for expert retirement.
   - If they were fully serialized, the cost would be 75 ms/token. That is more than the entire gap, so they partly overlap, but this
     is the largest overhead we have priced.

## The point for MoE inference

The post groups the **math**. For offloaded batch-1 decoding, the **synchronization** also has to be grouped. A per-expert host
callback costs more than the expert's own matmul.

The fix is the same idea applied one layer down: retire experts once per layer instead of once per expert, or poll CUDA events from
a worker thread instead of calling back into the host.

## Caveats

- All of these measurements were taken under **WSL2**. We have not yet shown how much of the 522 µs stall is WSL's paravirtualized
  GPU path rather than CUDA itself. A native-Linux replication on the same GPU model is preregistered and frozen (exp751, freeze
  008fd5b) but has not yet run.
- One GPU, one model, batch 1. The HF baseline keeps the whole model on the GPU, while the engine offloads experts. That trade buys a
  much smaller VRAM footprint, which is the point of offloading.
- The `grouped_mm` resolution was checked from the installed library's dispatch logic and a construction test. The timed HF runs did
  not log it.
- The per-layer retirement change (exp748) has not been measured yet. Until it is, the ~37 ms/token of idle time is an upper bound
  on what fixing callbacks can recover, not a demonstrated gain.

## Reproduce

Every experiment directory holds `freeze/` (the preregistration and frozen runner and analyzer, committed before any cell ran),
`raw/` (all outputs plus SHA256SUMS) and a generator script that recomputes each addendum from the raw rows. To check an addendum,
re-run the frozen `analyze.py` on `raw/out`; its output should be byte-identical to the sealed `verdict.txt`.

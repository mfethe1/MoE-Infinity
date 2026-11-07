# exp746 PREREG — host CPU contention as a confound, and a load-controlled replication of the routing A/B

Lane 79990, program STACK-1001-79990. Written 2026-11-06 ~21:00 EST, BEFORE any exp746 cell. Namespace check: no exp746 on Mack
or Winnie (exp745-m4-moe-sync-reduction exists locally and is a different lane's id; not reused), and no running.json or queue entry.

## Why (from exp743 and exp744 raw outputs; both are unsettled at the time of writing, so their numbers here are motivation, not evidence)
Both exp743 and exp744 finished. The GPU-contamination rule passed most cells, but mon.sh's loadavg column shows the WSL host CPU was
heavily and unevenly loaded (1-min loadavg means of 1.4 to 24 on 12 logical CPUs). The load came from other lanes' CPU work, which no
exclusion rule covered. Speed tracked that load:
- exp743 HF: 62.4 ms/tok at load 23.4 (counted CLEAN) vs 32.5 ms/tok at load 1.35 (excluded on GPU baseline). Its sealed
  `GAP-IS-GPU-BUSY` verdict compares engine t4_2 (load 2.2) against the loaded HF cell. Pairing it with the quiet HF cell instead
  gives a gap of ~67 ms/tok, and ~59% of that gap is GPU-idle. So the verdict flips with host load.
- exp744 engine: ms/tok fits 84.3 + 5.21·load − 28.7·[routing off] (4 cells, residual ±7). The sealed `ROUTE:OFF-FASTER` (−18.8 ms/tok)
  says the default sync-free GPU routing (`gpu_only_expert_routing=True`) is SLOWER than eager routing. That would be an
  upstream-relevant result. But the load fit is post hoc on 4 cells, so it must be replicated under controlled load before anyone is told.
- Across both: the engine shows a GPU-busy time of ~40 ms/tok versus ~14–16 for HF, independent of load. That is real extra device work
  (prior: exp726 aten::copy_ = 46% → expert H2D at ratio 0.75), separate from the host-side idle term.

## Design (frozen), serial on Winnie GPU1, palindromic, 12 cells
q_hf_1, q_on_1, q_off_1, s_hf_1, s_on_1, s_off_1, s_off_2, s_on_2, s_hf_2, q_off_2, q_on_2, q_hf_2.
- q_* = quiet host: before the cell, `loadwait.sh` waits ≤5400 s for 1-min loadavg <3.0 and no GitHub Actions Runner.Worker.
- s_* = controlled stress: the same wait, then 12 busy-loop processes (argv tag `exp746-spin`, one per logical CPU) start 60 s before the
  model process and are killed after the cell.
- hf = exp743 `hf_arm.py` (transformers bf16). on/off = exp744 `engine_arm.py` verbatim (lcnu @ 0.75, threads 4, `--gpu-route on|off`,
  read back as `gpu_route_effective`, grouped env unset). OLMoE-1B-7B, 6 prompts, max_new 64, warmup 1.
- Everything from exp744 is kept: NVML sampler at 50 ms with a 10 s idle baseline, GPU quietwait ≤5400 s, Ollama/foreign-PID monitor.
  mon.sh adds CPU PSI some-avg10 and a spinner-count column.

## Exclusions
exp744's rules (GPU pre-start >1024 MiB, a loaded Ollama model or failed probe, a mid-cell foreign GPU process, idle baseline mean >5%,
a prompt window with <10 util samples, RC≠0), plus:
- any Runner.Worker sample during the cell;
- loadavg mean >4.0 (quiet cells) or >18.0 (stress cells);
- stress cells whose median spinner count is below 12;
- quiet cells with any spinner present;
- no load samples.

## Decision rules (analyze.py, frozen). Dry-run on 7 synthetic cases (win/flat/insens/ci/eng/hfs/manip) hit the intended branches,
including exclusions, MANIP-fail → INCONCLUSIVE and PARITY-FAIL tagging.
- SPLIT (quiet): gap = on − hf. If the idle part is ≥50% of the gap → GAP-IS-GPU-IDLE. If the busy part is ≥50% → GAP-IS-GPU-BUSY.
  Otherwise GAP-MIXED.
- ROUTE-Q / ROUTE-S: off − on ms/tok, quiet / stressed. |Δ|<3 → NO-CHANGE, otherwise OFF-FASTER / OFF-SLOWER. INCONCLUSIVE unless
  `gpu_route_effective` matches the request in every engine cell. "(PARITY-FAIL)" is appended if engine token ids differ across cells.
- SENS: relative slowdown under stress, engine(on) vs hf. One must be ≥10% and ≥2× the other → ENGINE- or HF-MORE-SENSITIVE.
  Both <10% → BOTH-INSENSITIVE. Otherwise SIMILAR.
- `VERDICT SPLIT:..|ROUTE-Q:..|SENS:..|ROUTE-S:..`

## Predictions (registered)
- SPLIT:GAP-IS-GPU-IDLE, p=0.6.
- ROUTE-Q:OFF-FASTER, p=0.6.
- SENS:SIMILAR, p=0.5. The load slopes (engine ~5.2 ms per load unit vs HF ~1.4) give relative slowdowns of ~68% vs ~51% at +12 load,
  which is under the 2× bar.
- ROUTE-S:OFF-FASTER, p=0.55.

## Consequences
- ROUTE-Q:OFF-FASTER replicated → report on upstream #315 that the sync-free routing default costs time at batch 1 on this platform,
  with both experiments. Then instrument why: candidates are the extra device-side discovery kernels and the per-expert host funcs.
  If NO-CHANGE → exp744's ROUTE result was a load artifact; say so in its addendum and post nothing.
- SPLIT:GAP-IS-GPU-IDLE → the host-side handoff is the bigger term, so next work targets per-layer retirement (exp744 HOSTFN:COSTLY,
  ~95 µs per host func). GAP-IS-GPU-BUSY → target the ~25 ms/tok of extra device work (expert H2D copies), e.g. by measuring the ratio ladder.
- Program rule from here on: every timed prereg records and gates on host CPU load, not only GPU state. Add this to the
  inference-lane skill after settle.

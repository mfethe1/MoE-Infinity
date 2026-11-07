# exp751 AMENDMENT1: gate CPU on the container's cgroup, not host loadavg; MAX_JOBS 16

Written 2026-11-07 ~13:30Z, after instance 59573928 booted and before any cell or engine build ran. No data had been collected.

## Why
- The rented machine is a shared host: AMD EPYC 7B12, 128 logical CPUs visible. Our container gets a cgroup quota of 15.36 cores
  (`cpu.max 1536000 100000`) and 85.4 GiB of memory.
- `/proc/loadavg` in the container reports the host's load, which includes other tenants: 7.68 at boot, with our container idle.
- The frozen gate (loadavg1 <3.0) and quiet-cell exclusion (mean loadavg >4.0) therefore measure strangers' load, not contention on
  our CPUs. The gate would time out on every cell, and the exclusion would discard every quiet cell for reasons that don't apply to us.
- `MAX_JOBS=$(nproc)` would start 128 nvcc jobs under a 15-core quota and an 85 GiB memory cap.

## Change
- **CPU "load" now means this container's cores in use**: the delta of the cgroup's `cpu.stat usage_usec` over a 2 s window (5 s for
  the pre-cell gate).
  - Pre-cell gate: GPU ≤1024 MiB and container cores <1.0, max 600 s.
  - Quiet-cell exclusion: mean container cores >4.0, the same threshold as before.
- **New quiet-cell exclusion**: mean cgroup `cpu.pressure` "some avg10" >20%. This catches our tasks waiting for CPU, whether from
  quota throttling or host contention.
- **Monitor columns**: `time cores 0 cgroup_psi spinners host_loadavg1 nr_throttled`. Host loadavg and throttle counts are recorded as
  information only.
- **Setup**: `MAX_JOBS=16`. The non-existent `hf_transfer` extra is dropped from the tool install; the model download had already
  finished and passes its sha check.
- **Unchanged**: cells, arms, micro2.py, engine/HF arms, spinners, the verdict bars and the Winnie reference constants.
- Freeze: `AMENDMENT1.sha256`.

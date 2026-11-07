# exp751 AMENDMENT2: support cgroup v1 hosts in the container-CPU gate

Written 2026-11-07 ~16:45Z, after instance 59597907 (attempt b) booted and before setup, the engine build or any cell ran. No data
had been collected.

## Why
- The attempt-b host uses **cgroup v1**. It is an AMD EPYC 7552 with 192 logical CPUs visible, a CFS quota of 2304000/100000 (23.04
  cores) and a 160 GiB memory limit.
- AMENDMENT1 read only the cgroup v2 files `/sys/fs/cgroup/cpu.stat` (usage_usec) and `/sys/fs/cgroup/cpu.pressure`. Neither file
  exists on v1, so the gate would have read 0 cores on every check. The CPU gate would then always pass and the core exclusion could
  never trigger: the check would fail silently.
- At boot the host load average was about 44, with our container idle. Like attempt a, this machine is shared with other tenants.

## Change (run_exp751.sh only)
- **The cgroup version is detected at start** and recorded in ENV.txt as `cgroup v1|v2`.
  - v2: unchanged from AMENDMENT1.
  - v1: container cores = delta of `/sys/fs/cgroup/cpuacct/cpuacct.usage` (ns → µs) over the same windows. Throttle count comes
    from `/sys/fs/cgroup/cpu/cpu.stat`. Limits come from cfs_quota_us, cfs_period_us and memory.limit_in_bytes.
- **On v1 the cgroup PSI column is `NA`**, because v1 has no per-cgroup pressure file. The analyzer already treats NA as absent, so
  the AMENDMENT1 PSI exclusion **cannot fire on this host**. That is disclosed here rather than replaced with host-wide PSI, which
  would include other tenants. Host `/proc/pressure/cpu` is recorded once in ENV.txt as information only.
- **Unchanged**: gate thresholds (GPU ≤1024 MiB and container cores <1.0, max 600 s), the >4.0-core quiet exclusion, cells, arms,
  analyzer, setup (MAX_JOBS=16 is under the 23-core quota), verdict bars and reference constants.

## Disclosure carried into the verdict
- This is a shared host with high other-tenant load. Our cgroup is not CPU-starved (its quota is above our use and nr_throttled is
  logged), but memory-bandwidth and LLC interference from other tenants is not controlled.
- The GPU is exclusive to us: preflight showed no foreign compute PIDs.

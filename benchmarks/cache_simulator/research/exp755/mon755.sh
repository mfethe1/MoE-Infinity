#!/bin/bash
# exp755 monitor (native rental). One line per sample:
#   HH:MM:SS loadavg1 runner_workers psi_some_avg10 cgroup_cpu_rate_pct foreign_other_gpu_procs
# Container loadavg is HOST load (exp751 AMENDMENT1) -> CPU gate is the cgroup rate; PSI may be NA on cgroup v1.
CG=/sys/fs/cgroup
cg_usage(){ # prints usage in usec (v2 preferred, v1 fallback)
  if [ -r $CG/cpu.stat ]; then awk '/^usage_usec/{print $2}' $CG/cpu.stat
  elif [ -r $CG/cpuacct/cpuacct.usage ]; then awk '{print int($1/1000)}' $CG/cpuacct/cpuacct.usage
  else echo NA; fi; }
U0=$(cg_usage); T0=$(date +%s)
while sleep 2; do
  U=$(cg_usage); T=$(date +%s); DT=$((T-T0))
  if [ "$U" = NA ] || [ "$U0" = NA ] || [ "$DT" -lt 1 ]; then RATE=NA; else RATE=$(( (U-U0)/DT/10000 )); fi  # (usec/s)/1e4 = % of one core
  U0=$U; T0=$T
  RW=$(pgrep -fc Runner.Worker || true)
  PSI=$(awk '/^some avg10/{print $2}' $CG/cpu.pressure 2>/dev/null || echo NA)
  FA=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | sort -u | grep -c . )
  echo "$(date +%H:%M:%S) $(cut -d' ' -f1 /proc/loadavg) ${RW:-0} $PSI $RATE $FA"
done

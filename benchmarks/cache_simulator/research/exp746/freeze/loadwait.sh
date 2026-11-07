#!/bin/bash
# exp746: before a timed cell, wait (bounded) until the host CPU is quiet: 1-min loadavg < 3.0 (12 logical CPUs)
# and no GitHub Actions Runner.Worker process. Usage: loadwait.sh MAX_SECONDS -> prints "waited QUIET|TIMEOUT"; never fails.
MAX=${1:-5400}; t0=$(date +%s)
quiet(){ awk '{exit !($1<3.0)}' /proc/loadavg && [ "$(pgrep -fc Runner.Worker)" -eq 0 ]; }
while ! quiet; do [ $(( $(date +%s) - t0 )) -ge $MAX ] && { echo "$(( $(date +%s) - t0 )) TIMEOUT"; exit 0; }; sleep 30; done
echo "$(( $(date +%s) - t0 )) QUIET"

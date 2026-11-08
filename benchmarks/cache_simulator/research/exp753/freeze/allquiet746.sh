#!/bin/bash
# exp746 AMENDMENT1: ONE combined bounded wait (replaces the sequential quietwait.sh then loadwait.sh). Holds until, at the
# same instant: GPU $1 <=1024 MiB used, Ollama reports no loaded model, 1-min loadavg < 3.0, and no Runner.Worker.
# Usage: allquiet746.sh GPU MAX_S -> prints "waited QUIET|TIMEOUT"; never fails the cell.
G=$1; MAX=${2:-5400}; t0=$(date +%s); NS=/usr/lib/wsl/lib/nvidia-smi
quiet(){ local o m; o=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) || return 1
  [ "$(grep -o '"name"' <<<"$o" | wc -l)" -eq 0 ] || return 1
  m=$($NS --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' '); [ "$m" -le 1024 ] || return 1
  awk '{exit !($1<3.0)}' /proc/loadavg || return 1; [ "$(pgrep -fc Runner.Worker)" -eq 0 ]; }
while ! quiet; do [ $(( $(date +%s) - t0 )) -ge $MAX ] && { echo "$(( $(date +%s) - t0 )) TIMEOUT"; exit 0; }; sleep 20; done
echo "$(( $(date +%s) - t0 )) QUIET"

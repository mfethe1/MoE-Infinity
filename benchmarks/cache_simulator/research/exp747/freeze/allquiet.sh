#!/bin/bash
# exp747: ONE combined bounded wait until, at the same instant, GPU $1 shows <=1024 MiB used, Ollama reports no loaded model,
# host 1-min loadavg < 3.0 (12 logical CPUs) and no GitHub Actions Runner.Worker process. Usage: allquiet.sh GPU MAX_S
G=$1; MAX=${2:-5400}; t0=$(date +%s); NS=/usr/lib/wsl/lib/nvidia-smi
quiet(){ local o m; o=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) || return 1
  [ "$(grep -o '"name"' <<<"$o" | wc -l)" -eq 0 ] || return 1
  m=$($NS --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' '); [ "$m" -le 1024 ] || return 1
  awk '{exit !($1<3.0)}' /proc/loadavg || return 1; [ "$(pgrep -fc Runner.Worker)" -eq 0 ]; }
while ! quiet; do [ $(( $(date +%s) - t0 )) -ge $MAX ] && { echo "$(( $(date +%s) - t0 )) TIMEOUT"; exit 0; }; sleep 20; done
echo "$(( $(date +%s) - t0 )) QUIET"

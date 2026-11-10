#!/bin/bash
# exp728 AMENDMENT2: before a timed cell, wait (bounded) until the GPUs it will use are quiet:
# every listed GPU shows <=1024 MiB used (our process is not yet running, so any usage is foreign) and the Ollama
# API reports no loaded model (exp742: an unreachable Ollama API counts as zero loaded models; the GPU memory check
# still guards the cards).
# Usage: quietwait.sh "0,1" MAX_SECONDS  -> prints waited seconds and QUIET|TIMEOUT; never fails the cell.
GPUS=$1; MAX=${2:-2700}; NS=/usr/lib/wsl/lib/nvidia-smi; t0=$(date +%s)
quiet(){ local o; o=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) || o=""
  [ "$(grep -o '"name"' <<<"$o" | wc -l)" -eq 0 ] || return 1
  for g in ${GPUS//,/ }; do m=$($NS --query-gpu=memory.used --format=csv,noheader,nounits -i $g | tr -d ' ')
    [ "$m" -le 1024 ] || return 1; done; return 0; }
while ! quiet; do [ $(( $(date +%s) - t0 )) -ge $MAX ] && { echo "$(( $(date +%s) - t0 )) TIMEOUT"; exit 0; }; sleep 30; done
echo "$(( $(date +%s) - t0 )) QUIET"

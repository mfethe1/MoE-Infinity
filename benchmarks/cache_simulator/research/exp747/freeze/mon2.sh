#!/bin/bash
# exp747 during-cell monitor (2 s): epoch loadavg1 runner_workers psi_some_avg10 own_spinners gpu_mem_used_mib ollama_loaded
G=$1; OUT=$2; PIDF=$3; NS=/usr/lib/wsl/lib/nvidia-smi
while true; do
  PSI=$(awk '/^some/{sub("avg10=","",$2);print $2}' /proc/pressure/cpu 2>/dev/null)
  O=$(curl -sf -m 1 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  SP=0; [ -s "$PIDF" ] && for p in $(cat $PIDF); do [ -d /proc/$p ] && SP=$((SP+1)); done
  echo "$(date +%s) $(cut -d' ' -f1 /proc/loadavg) $(pgrep -fc Runner.Worker) ${PSI:-NA} $SP $($NS --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ') $OL" >> $OUT
  sleep 2
done

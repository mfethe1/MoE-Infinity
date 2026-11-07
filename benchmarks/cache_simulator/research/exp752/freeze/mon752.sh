#!/bin/bash
# exp752 during-cell monitor (from exp746 mon.sh). Adds: foreign-process match on GPU UUID as well as index (exp752 found a
# foreign gen.py pinned by UUID), and a column counting compute processes pinned to OTHER GPUs (covariate, not an exclusion).
# Usage: mon752.sh GPU FLAGFILE CELLID   (runs until killed; polls 10s). Columns: HH:MM:SS loadavg1 runner_workers psi_avg10 0 foreign_any
G=$1; F=$2; C=$3; NS=/usr/lib/wsl/lib/nvidia-smi
U=$($NS --query-gpu=uuid --format=csv,noheader -i $G | tr -d ' ')
while true; do
  for p in $(pgrep -f "gen.py|ollama runner|llama-server|vllm|sglang" 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    v=$(tr '\0' '\n' < /proc/$p/environ 2>/dev/null | sed -n 's/^CUDA_VISIBLE_DEVICES=//p')
    case ",$v," in *",$G,"*|*",$U,"*) echo "$C mid-cell foreign pid $p $(ps -o args= -p $p | cut -c1-80)" >> ${F}.why; echo $C >> $F;; esac
  done
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && [ "$(grep -o '"name"' <<<"$O" | wc -l)" -ne 0 ] && { echo "$C mid-cell ollama model loaded" >> ${F}.why; echo $C >> $F; }
  PSI=$(awk '/^some/{sub("avg10=","",$2);print $2}' /proc/pressure/cpu 2>/dev/null)
  FA=0; for p in $($NS --query-compute-apps=pid --format=csv,noheader 2>/dev/null | sort -u); do
    v=$(tr '\0' '\n' < /proc/$p/environ 2>/dev/null | sed -n 's/^CUDA_VISIBLE_DEVICES=//p')
    case ",$v," in *",$G,"*|*",$U,"*) ;; *) FA=$((FA+1));; esac
  done
  echo "$(date -u +%T) $(cut -d' ' -f1 /proc/loadavg) $(pgrep -fc Runner.Worker) ${PSI:-NA} 0 ${FA:-NA}" >> out/$C.load
  sleep 10
done

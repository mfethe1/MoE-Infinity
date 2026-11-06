#!/bin/bash
# exp736 during-cell contamination monitor. Usage: mon.sh GPU FLAGFILE CELLID  (runs until killed; polls 10s)
G=$1; F=$2; C=$3
while true; do
  for p in $(pgrep -f "gen.py|ollama runner|llama-server" 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    v=$(tr '\0' '\n' < /proc/$p/environ 2>/dev/null | sed -n 's/^CUDA_VISIBLE_DEVICES=//p')
    case ",$v," in *",$G,"*) echo "$C mid-cell foreign pid $p $(ps -o args= -p $p | cut -c1-80)" >> ${F}.why; echo $C >> $F;; esac
  done
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && [ "$(grep -o '"name"' <<<"$O" | wc -l)" -ne 0 ] && { echo "$C mid-cell ollama model loaded" >> ${F}.why; echo $C >> $F; }
  echo "$(date -u +%T) $(cut -d' ' -f1 /proc/loadavg) $(pgrep -fc Runner.Worker)" >> out/$C.load
  sleep 10
done

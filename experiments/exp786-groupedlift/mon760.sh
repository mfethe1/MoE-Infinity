#!/bin/bash
# exp757 monitor: per-cell samples (5 s) of loadavg + GPU1 compute-apps + foreign ollama count.
# usage: bash mon757.sh <gpu> <outfile.csv>
G=${1:-1}; OUT=$2; : > "$OUT"
while :; do
  LA=$(cut -d' ' -f1-3 /proc/loadavg | tr ' ' ';')
  APPS=$(/usr/lib/wsl/lib/nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr '\n' '|' | tr -d ' ')
  OL=$(curl -sf -m 1 http://127.0.0.1:11434/api/ps 2>/dev/null | grep -o '"name"' | wc -l)
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i "$G" 2>/dev/null | tr -d ' ')
  echo "$(date -u +%FT%TZ),$LA,$MG,$OL,$APPS" >> "$OUT"
  sleep 5
done

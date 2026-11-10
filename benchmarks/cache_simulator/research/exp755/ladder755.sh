#!/bin/bash
# exp755 untimed fit ladder v2 (2026-11-10 fix: probe = EXACT cell workload; v1's 2x8-token prep probes
# false-passed at 0.75 while real 10x64-token cells OOMed during load/warmup).
# First ratio whose FULL prompts.json max-new 64 pass exits 0 wins; recorded BEFORE any timed cell.
set -uo pipefail
W=/root/exp755; cd $W; P=/root/venv/bin; M=/root/models/OLMoE-1B-7B-0125-Instruct
[ -s out/RATIO755 ] && { echo "ladder already run: $(cat out/RATIO755)"; exit 0; }
for R in 0.75 0.70 0.65 0.60; do
  S=/root/ladder-$R; rm -rf $S; mkdir -p $S
  echo "== $(date -u +%FT%TZ) ladder probe ratio=$R (full cell workload)" | tee -a out/ladder.log
  if env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE MOEI_EXP752_MODE=RC \
     timeout 1800 $P/python engine_arm.py --model $M --offload $S --policy lcnu --ratio $R \
       --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 \
       --out out/ladder-$R.json > out/ladder-$R.log 2>&1 </dev/null; then
    # rc=0 alone false-passed before: require all rows present AND no OOM anywhere in the log
    ROWS=$($P/python -c "import json;print(len(json.load(open('out/ladder-$R.json'))['rows']))" 2>/dev/null || echo 0)
    if [ "$ROWS" -ge 10 ] && ! grep -q "out of memory" out/ladder-$R.log; then
      echo "$R" > out/RATIO755
      echo "ratio $R FITS full workload (rows=$ROWS) at $(date -u +%FT%TZ); host=$(hostname); gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader -i 0)" > out/AMENDMENT-ratio.txt
      cat out/AMENDMENT-ratio.txt; break
    else
      echo "ratio $R rc=0 but rows=$ROWS or OOM in log -> NOT a fit" | tee -a out/ladder.log
    fi
  else
    echo "ratio $R did not fit (rc=$?)" | tee -a out/ladder.log
  fi
  rm -rf $S; rm -f out/ladder-$R.json
done
[ -s out/RATIO755 ] || { echo "LADDER-FAILED: no ratio fits"; exit 1; }
for S in /root/ladder-*; do [ -d "$S" ] && rm -rf "$S"; done
echo "ladder done: $(cat out/RATIO755)"

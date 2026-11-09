#!/bin/bash
# exp755 untimed fit ladder (exp751 AMENDMENT4: native fit ratio expected 0.60 vs WSL 0.75).
# First ratio that loads + generates without OOM wins; recorded BEFORE any timed cell. Throwaway stores.
set -uo pipefail
W=/root/exp755; cd $W; P=/root/venv/bin; M=/root/models/OLMoE-1B-7B-0125-Instruct
[ -s out/RATIO755 ] && { echo "ladder already run: $(cat out/RATIO755)"; exit 0; }
for R in 0.75 0.70 0.65 0.60; do
  S=/root/ladder-$R; rm -rf $S; mkdir -p $S
  echo "== $(date -u +%FT%TZ) ladder probe ratio=$R" | tee -a out/ladder.log
  if env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE MOEI_EXP752_MODE=RC \
     timeout 900 $P/python engine_arm.py --model $M --offload $S --policy lcnu --ratio $R \
       --threads 4 --gpu-route on --prompts prep_prompts.json --max-new 8 --warmup 1 \
       --out out/ladder-$R.json > out/ladder-$R.log 2>&1 </dev/null; then
    echo "$R" > out/RATIO755
    echo "ratio $R FITS (chosen) at $(date -u +%FT%TZ); host=$(hostname); gpu=$($P/python -c 'import torch;print(torch.cuda.get_device_name(0))' 2>/dev/null)" > out/AMENDMENT-ratio.txt
    cat out/AMENDMENT-ratio.txt; break
  else
    echo "ratio $R did not fit (rc=$?)" | tee -a out/ladder.log
  fi
  rm -rf $S
done
[ -s out/RATIO755 ] || { echo "LADDER-FAILED: no ratio fits" ; exit 1; }
for S in /root/ladder-*; do [ -d "$S" ] && rm -rf "$S"; done
echo "ladder done: $(cat out/RATIO755)"

#!/bin/bash
# exp725 runner (Winnie). Waits for exp724 to release the GPUs (serial engine runs only), then runs cells.json.
cd ~/exp725
source ~/venvs/moei-engine/bin/activate
mkdir -p out
while systemctl --user is-active -q exp724; do sleep 60; done
echo "== $(date -u +%FT%TZ) exp724 released; start"
sha256sum engine_arm.py prompts.json cells.json analyze.py run_exp725.sh > out/RUN_SHA256
/usr/lib/wsl/lib/nvidia-smi --query-gpu=index,memory.used --format=csv,noheader > out/gpu_pre.csv
python3 -c "import json;[print(c['id'],c['gpus'],c['policy'],c['ratio']) for c in json.load(open('cells.json'))]" |
while read ID GPUS POL RAT; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  echo "== $(date -u +%FT%TZ) $ID gpus=$GPUS $POL r=$RAT $(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader | tr '\n' ' ')"
  CUDA_VISIBLE_DEVICES=$GPUS timeout 1800 python3 engine_arm.py --model ~/models/OLMoE-1B-7B-0125-Instruct \
    --offload ~/moe-offload --policy $POL --ratio $RAT --prompts prompts.json --max-new 64 --warmup 1 \
    --out out/$ID.json > out/$ID.log 2>&1
  RC=$?; echo "$ID RC=$RC"; grep -E "prompt [0-9]:" out/$ID.log | tail -6
  [ $RC -ne 0 ] && { tail -3 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done
python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP725-DONE"

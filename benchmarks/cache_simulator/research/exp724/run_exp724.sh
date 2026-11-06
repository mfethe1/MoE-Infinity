#!/bin/bash
# exp724 runner (Winnie). Executes cells.json serially, one fresh engine process per cell.
# Resume-safe: a cell whose out/<id>.json exists is skipped. Never edits results.
cd ~/exp724
source ~/venvs/moei-engine/bin/activate
mkdir -p out
nvidia-smi --query-gpu=index,name,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max --format=csv > out/gpus.csv
sha256sum engine_arm.py prompts.json cells.json analyze.py run_exp724.sh > out/RUN_SHA256
python3 -c "import json;[print(c['id'],c['gpu'],c['policy'],c['ratio']) for c in json.load(open('cells.json'))]" |
while read ID GPU POL RAT; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  echo "== $(date -u +%FT%TZ) $ID gpu=$GPU $POL r=$RAT"
  CUDA_VISIBLE_DEVICES=$GPU timeout 1800 python3 engine_arm.py --model ~/models/OLMoE-1B-7B-0125-Instruct \
    --offload ~/moe-offload --policy $POL --ratio $RAT --prompts prompts.json --max-new 64 --warmup 1 \
    --out out/$ID.json > out/$ID.log 2>&1
  RC=$?; echo "$ID RC=$RC"; grep -E "prompt [0-9]:" out/$ID.log | tail -6
  [ $RC -ne 0 ] && { tail -3 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done
python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP724-DONE"

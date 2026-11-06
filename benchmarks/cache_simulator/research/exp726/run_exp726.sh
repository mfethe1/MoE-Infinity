#!/bin/bash
# exp726 runner (Winnie GPU1 only). Waits for exp724 AND exp725 to finish (serial engine runs only).
cd ~/exp726; source ~/venvs/moei-engine/bin/activate; mkdir -p out
while systemctl --user is-active -q exp724 || systemctl --user is-active -q exp725; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
sha256sum AMENDMENT1.md quietwait.sh engine_arm.py hf_arm.py prof_arm.py prompts.json cells.json analyze.py run_exp726.sh > out/RUN_SHA256
export CUDA_VISIBLE_DEVICES=1
M=~/models/OLMoE-1B-7B-0125-Instruct
python3 -c "import json;[print(c['id'],c['arm'],c['ratio']) for c in json.load(open('cells.json'))]" |
while read ID ARM RAT; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(bash quietwait.sh 1 2700)   # AMENDMENT1: bounded quiet-GPU wait + pre-start record
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  M1=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 1 | tr -d ' ')
  echo "$ID,$QW,$M1,$OL" >> out/precell.csv; { [ "$M1" -gt 1024 ] || [ "$OL" -ne 0 ]; } && echo "$ID" >> out/FLAGGED
  echo "== $(date -u +%FT%TZ) $ID $(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader | tr '\n' ' ')"
  if [ $ARM = hf ]; then
    timeout 1800 python3 hf_arm.py --model $M --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1
  else
    timeout 1800 python3 engine_arm.py --model $M --offload ~/moe-offload --policy lcnu --ratio $RAT --prompts prompts.json \
      --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1
  fi
  RC=$?; echo "$ID RC=$RC"; grep -E "prompt [0-9]:" out/$ID.log | tail -6
  [ $RC -ne 0 ] && { tail -3 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done
timeout 1800 python3 prof_arm.py $M ~/moe-offload 0.75 out/profile_r75.txt > out/profile.log 2>&1; echo PROF_RC=$?
python3 analyze.py out > out/verdict.txt 2>&1; echo "FLAGGED(AMENDMENT1): $(sort -u out/FLAGGED 2>/dev/null | tr '\n' ' ')" >> out/verdict.txt; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP726-DONE"

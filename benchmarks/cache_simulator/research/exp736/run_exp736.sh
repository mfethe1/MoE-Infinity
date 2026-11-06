#!/bin/bash
# exp736 runner (Winnie). Serial; one model process at a time. Restores Windows power plan Balanced on any exit.
cd ~/exp736; source ~/venvs/moei-engine/bin/activate; mkdir -p out
PC=/mnt/c/Windows/System32/powercfg.exe; BAL=381b4222-f694-41f0-9685-ff5bb260df2e; HIP=8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
trap '$PC /setactive $BAL; echo "== restored Balanced: $($PC /getactivescheme | tr -d "\r")"' EXIT
while systemctl --user is-active -q exp734 || systemctl --user is-active -q exp735 || systemctl --user is-active -q exp727g1; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
sha256sum quietwait.sh mon.sh micro.py prof2.py engine_arm.py hf_arm.py prompts.json cells.json analyze.py run_exp736.sh > out/RUN_SHA256
M=~/models/OLMoE-1B-7B-0125-Instruct
python3 -c "import json;[print(c['id'],c['arm'],c['gpu'],c['plan']) for c in json.load(open('cells.json'))]" |
while read ID ARM G PLAN; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  if [ $PLAN = B ]; then $PC /setactive $HIP; else $PC /setactive $BAL; fi; sleep 20
  PS=$($PC /getactivescheme | grep -oE '\(.*\)' | tr -d '()\r ')
  QW=$(bash quietwait.sh $G 2700)
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  echo "$ID,$PS,$QW,$MG,$OL,$(cut -d' ' -f1 /proc/loadavg)" >> out/precell.csv
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ]; } && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL" >> out/FLAGGED.why; }
  [ "$PLAN" = B ] && [ "$PS" != "Highperformance" ] && { echo "$ID" >> out/FLAGGED; echo "$ID plan not applied: $PS" >> out/FLAGGED.why; }
  [ "$PLAN" = A ] && [ "$PS" != "Balanced" ] && { echo "$ID" >> out/FLAGGED; echo "$ID plan not applied: $PS" >> out/FLAGGED.why; }
  bash mon.sh $G out/FLAGGED $ID & MP=$!
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM gpu=$G plan=$PS"
  case $ARM in
    micro)    timeout 900 python3 micro.py out/$ID.json > out/$ID.log 2>&1 ;;
    prof_hf)  timeout 1800 python3 prof2.py hf $M ~/moe-offload 0 out/$ID.json cuda:0 16 > out/$ID.log 2>&1 ;;
    prof_eng) timeout 1800 python3 prof2.py engine $M ~/moe-offload 0.75 out/$ID.json cuda:0 16 > out/$ID.log 2>&1 ;;
    hf)       timeout 1800 python3 hf_arm.py --model $M --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 ;;
    eng)      timeout 1800 python3 engine_arm.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 --prompts prompts.json \
                --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 ;;
  esac
  RC=$?; kill $MP 2>/dev/null; wait $MP 2>/dev/null
  echo "$ID RC=$RC"; grep -E "prompt [0-9]:|PROF2|launch" out/$ID.log | tail -6 | cut -c1-300
  [ $RC -ne 0 ] && { tail -5 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done
python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP736-DONE"

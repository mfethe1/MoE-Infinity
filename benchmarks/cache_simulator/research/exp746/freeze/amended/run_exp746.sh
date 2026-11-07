#!/bin/bash
# exp746 runner (Winnie, WSL). Serial; one model process at a time; GPU1 only; no power-plan changes (plan recorded only).
# Stress cells start K busy-loop processes (argv tag exp746-spin) 60 s before the model process; all are killed after the cell.
cd ~/exp746; source ~/venvs/moei-engine/bin/activate; mkdir -p out
PCX=/mnt/c/Windows/System32/powercfg.exe
pc() { local s o; for s in $(ls -tr /run/WSL/*_interop); do o=$(WSL_INTEROP=$s $PCX "$@" 2>&1 </dev/null) && { printf '%s\n' "$o"; return 0; }; done; echo "powercfg-failed" ; return 0; }
busy(){ local u; for u in exp740 exp741 exp742 exp743 exp744; do systemctl --user is-active -q $u && return 0; done; return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
[ -e out/RUN_SHA256 ] && mv out/RUN_SHA256 out/RUN_SHA256.prev-$(date -u +%H%M%S)
sha256sum allquiet746.sh quietwait.sh loadwait.sh mon.sh nvsamp.py engine_arm.py hf_arm.py prompts.json cells.json analyze.py run_exp746.sh > out/RUN_SHA256
python3 -c "import moe_infinity;print('moei', moe_infinity.__file__)" > out/ENV.txt 2>&1
git -C ~/moei-engine/MoE-Infinity rev-parse HEAD >> out/ENV.txt 2>&1; git -C ~/moei-engine/MoE-Infinity status --short | wc -l >> out/ENV.txt; nproc >> out/ENV.txt
M=~/models/OLMoE-1B-7B-0125-Instruct
spin(){ local k; for k in $(seq 1 $1); do setsid python3 -c "import sys; sys.argv=['exp746-spin']
while True: pass" exp746-spin </dev/null >/dev/null 2>&1 & done; }
unspin(){ pkill -f "exp746-spin" 2>/dev/null; sleep 2; pkill -9 -f "exp746-spin" 2>/dev/null; true; }
trap unspin EXIT
while read -u 3 ID ARM K G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  PS=$(pc /getactivescheme | grep -oE '\(.*\)' | tr -d '()\r ')
  QW=$(bash allquiet746.sh $G 5400 </dev/null); LW="$QW"   # AMENDMENT1: one combined wait; precell columns qw and lw both carry it
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  LA=$(cut -d' ' -f1 /proc/loadavg); RW=$(pgrep -fc Runner.Worker)
  echo "$ID,$PS,$QW,$LW,$MG,$OL,$LA,$RW" >> out/precell.csv
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ]; } && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL" >> out/FLAGGED.why; }
  bash mon.sh $G out/FLAGGED $ID </dev/null & MP=$!
  [ "$K" -gt 0 ] && { spin $K; sleep 60; }
  python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10   # 10 s GPU-idle baseline before the model process
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM stress=$K gpu=$G plan=$PS qw=$QW lw=$LW la=$LA"
  case $ARM in
    hf) timeout 1800 python3 hf_arm.py --model $M --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    on|off) env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE timeout 1800 python3 engine_arm.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
           --threads 4 --gpu-route $ARM --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
  esac
  RC=$?; sleep 3; unspin; kill $MP $SP 2>/dev/null; wait $MP $SP 2>/dev/null
  echo "$ID RC=$RC"; grep -E "prompt [0-9]:" out/$ID.log | tail -6 | cut -c1-200
  [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done 3< <(python3 -c "import json;[print(c['id'],c['arm'],c['stress'],c['gpu']) for c in json.load(open('cells.json'))]")
python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP746-DONE"

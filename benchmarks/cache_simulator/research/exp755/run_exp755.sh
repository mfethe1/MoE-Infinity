#!/bin/bash
# exp755 runner (native vast.ai rental). Serial; one model process at a time; GPU 0 (single-GPU full tenancy).
# Arms differ ONLY in MOEI_EXP752_MODE: H=0 (upstream cudaLaunchHostFunc retirement), R=1 (event-poll retirement),
# RC=2 (R + completion events by query). All arms: lcnu, ratio from the frozen ladder, gpu-route on, threads 4.
# Adapted from exp752's Winnie runner: no systemd/Ollama (single-tenant container); CPU gate is cgroup-based
# (exp751 AMENDMENT1: container loadavg = host load). Logs to /root/exp755/out/run.log.
cd /root/exp755; P=/root/venv/bin; export PATH=$P:$PATH; mkdir -p out; M=/root/models/OLMoE-1B-7B-0125-Instruct
exec >> out/run.log 2>&1
echo "== $(date -u +%FT%TZ) exp755 runner start"
bash ladder755.sh || { echo LADDER-FAILED; exit 1; }
R=$(cat out/RATIO755); echo "ratio=$R (frozen ladder)"
# untimed prep: build the real offload store once at the chosen ratio
[ -s out/PREP.json ] || env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE MOEI_EXP752_MODE=RC \
  timeout 900 $P/python engine_arm.py --model $M --offload /root/moe-offload --policy lcnu --ratio $R \
    --threads 4 --gpu-route on --prompts prep_prompts.json --max-new 8 --warmup 1 --out out/PREP.json \
    > out/PREP.log 2>&1 </dev/null || { echo PREP-FAILED; tail -8 out/PREP.log; exit 1; }
echo "prep done $(date -u +%FT%TZ)"
[ -e out/RUN_SHA256 ] && mv out/RUN_SHA256 out/RUN_SHA256.prev-$(date -u +%H%M%S)
sha256sum engine_arm.py nvsamp.py mon755.sh ladder755.sh prompts.json prep_prompts.json cells755.json analyze755.py run_exp755.sh \
  src_fixed/expert_dispatcher.cpp src_fixed/expert_dispatcher.h /root/MoE-Infinity/moe_infinity/_store*.so > out/RUN_SHA256
$P/python -c "import torch, moe_infinity, moe_infinity._store as s;print('moei', moe_infinity.__file__, s.__file__)" > out/ENV.txt 2>&1
git -C /root/MoE-Infinity rev-parse HEAD >> out/ENV.txt 2>&1; nproc >> out/ENV.txt; nvidia-smi -L >> out/ENV.txt 2>&1
quiet(){ # GPU <=1024 MiB, no foreign compute apps, cgroup rate <15% of one core; <=600 s; prints seconds waited
  local w=0 mg fa u0 u1 t0 t1 rate
  while :; do
    mg=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' ')
    fa=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | sort -u | grep -c . )
    u0=$(awk '/^usage_usec/{print $2}' /sys/fs/cgroup/cpu.stat 2>/dev/null || echo NA); t0=$(date +%s%N)
    sleep 10
    u1=$(awk '/^usage_usec/{print $2}' /sys/fs/cgroup/cpu.stat 2>/dev/null || echo NA); t1=$(date +%s%N)
    if [ "$u0" = NA ] || [ "$u1" = NA ]; then rate=0; else rate=$(( (u1-u0)*100/((t1-t0)/1000)/10000 )); fi
    [ "$mg" -le 1024 ] && [ "$fa" -eq 0 ] && [ "$rate" -lt 15 ] && break
    w=$((w+10)); [ $w -ge 600 ] && break
  done; echo $w; }
while read -u 3 ID ARM K G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(quiet)
  MG=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 | tr -d ' ')
  FA=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | sort -u | grep -c . )
  LA=$(cut -d' ' -f1 /proc/loadavg)
  echo "$ID,$QW,$MG,NA,$LA,$FA" >> out/precell.csv
  { [ "$MG" -gt 1024 ] || [ "$FA" -ne 0 ]; } && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG foreign=$FA waited=$QW" >> out/FLAGGED.why; }
  bash mon755.sh > out/$ID.load </dev/null & MP=$!
  $P/python nvsamp.py 0 out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM gpu=$G qw=$QW la=$LA foreign=$FA ratio=$R"
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE MOEI_EXP752_MODE=$ARM \
    timeout 1800 $P/python engine_arm.py --model $M --offload /root/moe-offload --policy lcnu --ratio $R \
      --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null
  RC=$?; sleep 3; kill $MP $SP 2>/dev/null; wait $MP $SP 2>/dev/null
  echo "$ID RC=$RC"; grep -E "exp752 mode=|prompt [0-9]:" out/$ID.log | tail -7 | cut -c1-200
  [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done 3< <($P/python -c "import json;[print(c['id'],c['arm'],c['stress'],c['gpu']) for c in json.load(open('cells755.json'))]")
$P/python analyze755.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP755-DONE"

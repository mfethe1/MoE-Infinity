#!/bin/bash
# exp753 runner (Winnie, WSL). Serial; one model process at a time; GPU1 only (gen4 x8; exp746/747/752 baseline GPU).
# Arms: hf (HF reference), A (engine, tracer dormant), B (+env-gated timeline trace), C (+existing compute-timing hook,
# KERN samples), G (CUDA-graph capture feasibility probe, disposable process). Engine arms load the PRIVATE build
# (PYTHONPATH=/home/mfeth/exp753/src; ~/moei-engine untouched). All engine arms: lcnu, ratio 0.75, gpu-route on, threads 4.
cd ~/exp753; source ~/venvs/moei-engine/bin/activate; mkdir -p out
busy(){ local u; for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753build exp753smoke; do systemctl --user is-active -q $u && return 0; done; return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
[ -e out/RUN_SHA256 ] && mv out/RUN_SHA256 out/RUN_SHA256.prev-$(date -u +%H%M%S)
sha256sum allquiet746.sh mon753.sh nvsamp.py engine_arm753.py hf_arm.py graph_probe.py prompts.json cells.json \
  analyze753.py run_exp753.sh PREREG.md FREEZE src_patched/expert_dispatcher.cpp infra753.inc src/moe_infinity/_store*.so \
  refs/engine_ref.json refs/hf_ref.json > out/RUN_SHA256
PYTHONPATH=/home/mfeth/exp753/src python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei', moe_infinity.__file__, s.__file__)" > out/ENV.txt 2>&1
git -C src rev-parse HEAD >> out/ENV.txt 2>&1; nproc >> out/ENV.txt; /usr/lib/wsl/lib/nvidia-smi -L >> out/ENV.txt
M=~/models/OLMoE-1B-7B-0125-Instruct
while read -u 3 ID ARM K G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(bash allquiet746.sh $G 5400 </dev/null)
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  FA=$(/usr/lib/wsl/lib/nvidia-smi --query-compute-apps=pid --format=csv,noheader | sort -u | grep -c .)
  LA=$(cut -d' ' -f1 /proc/loadavg); RW=$(pgrep -fc Runner.Worker)
  echo "$ID,$QW,$MG,$OL,$LA,$RW,$FA" >> out/precell.csv
  # Pre-committed covariate thresholds (PREREG §10h): FLAGGED iff any fires.
  BADCOV=""
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ] || [ "$RW" -ge 1 ] || [ "$FA" -ge 1 ] || \
    awk -v l="$LA" 'BEGIN{exit !(l+0>=8)}'; } && BADCOV="cov"
  [ -n "$BADCOV" ] && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL la=$LA rw=$RW fa=$FA" >> out/FLAGGED.why; }
  bash mon753.sh $G out/FLAGGED $ID </dev/null & MP=$!
  python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM gpu=$G qw=$QW la=$LA foreign_any=$FA"
  case $ARM in
    hf) timeout 1800 python3 hf_arm.py --model $M --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    A) env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
       timeout 1800 python3 engine_arm753.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
       --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --arm-name A --timing off \
       --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    B|C) T=off; [ "$ARM" = C ] && T=on
       env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
       MOEI_EXP753_TRACE=1 MOEI_EXP753_TRACE_FILE=/home/mfeth/exp753/out/$ID.trace.jsonl \
       timeout 1800 python3 engine_arm753.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
       --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --arm-name $ARM --timing $T \
       --out out/$ID.json > out/$ID.log 2>&1 </dev/null
       [ -s out/$ID.trace.jsonl ] && head -1 out/$ID.trace.jsonl > out/$ID.tracemeta ;;
    G) timeout 1200 env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
       python3 graph_probe.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 --threads 4 \
       --gpu-route on --prompts prompts.json --max-new 64 --out out/g_probe.json > out/g_probe.log 2>&1 </dev/null ;;
  esac
  RC=$?; sleep 3; kill $MP $SP 2>/dev/null; wait $MP $SP 2>/dev/null
  pkill -f "graph_probe.py --step" 2>/dev/null; true  # orphan sweep if timeout fired
  echo "$ID RC=$RC"
  [ "$ARM" != G ] && grep -E "exp753 mode=|prompt [0-9]:" out/$ID.log | tail -7 | cut -c1-200
  [ $RC -ne 0 ] && { tail -8 out/${ARM:+$ID}.log 2>/dev/null; echo "$ID FAILED" >> out/FAILED; }
done 3< <(python3 -c "import json;[print(c['id'],c['arm'],c['stress'],c['gpu']) for c in json.load(open('cells.json'))]")
python3 analyze753.py out refs > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP753-DONE"

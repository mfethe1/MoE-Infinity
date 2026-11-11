#!/bin/bash
# exp785 runner (Winnie, WSL). Serial; GPU1 only; all cells QUIET; bf16 store both arms.
# Question: does archer_config.speculative_prefetch=True (L+1 expert prefetch from router
# logits) change batch-1 decode throughput vs off, at ratio 0.75 (saturated) and 0.25
# (miss-heavy)? Probes suggest massive regression (native sync-free routing conflict).
cd ~/exp785 || exit 1
source ~/venvs/moei-engine/bin/activate
mkdir -p out
busy(){ local u; for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756 exp756build exp756build2 exp757 exp759 exp759build exp759run exp760 exp777 exp778 exp779 exp780 exp781 exp782 exp783 exp784; do systemctl --user is-active -q $u && return 0; done; return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
sha256sum engine_arm785.py cells785.json analyze785.py run_exp785.sh PREREG-785.md prompts24.json \
  allquiet746.sh mon760.sh nvsamp.py /home/mfeth/exp759/src753/moe_infinity/_store*.so > out/RUN_SHA256
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
git -C /home/mfeth/exp759/src753 rev-parse HEAD >> out/ENV.txt 2>&1
nproc >> out/ENV.txt; /usr/lib/wsl/lib/nvidia-smi -L >> out/ENV.txt
grep -q "moei-RC753 /home/mfeth/exp759/src753/.* /home/mfeth/exp759/src753/moe_infinity/_store" out/ENV.txt \
  || { echo "IDENTITY-FAIL: import path is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
grep -q "b7f6ca4d2caa5229698d78deb03b454fc20947dd" out/ENV.txt \
  || { echo "IDENTITY-FAIL: src753 HEAD is not b7f6ca4"; cat out/ENV.txt; exit 9; }
M=~/models/OLMoE-1B-7B-0125-Instruct

while read -u 3 ID SPEC RATIO G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(bash allquiet746.sh $G 5400 </dev/null)
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  LA=$(cut -d' ' -f1 /proc/loadavg)
  echo "$ID,$QW,$MG,$LA" >> out/precell.csv
  [ "$MG" -gt 1024 ] && { echo "$ID gpu=$MG" >> out/FLAGGED.why; }
  bash mon760.sh $G out/$ID.mon.csv </dev/null & MP=$!
  python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID spec=$SPEC ratio=$RATIO gpu=$G qw=$QW la=$LA"
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE -u MOEI_EXP752_MODE PYTHONPATH=/home/mfeth/exp759/src753 \
    timeout 1800 python3 engine_arm785.py --model $M --offload ~/moe-offload --policy lcnu --ratio $RATIO \
      --threads 4 --gpu-route on --prompts prompts24.json --max-new 32 --warmup 1 \
      --resident-mode legacy --spec-prefetch $SPEC --out out/$ID.json > out/$ID.log 2>&1 </dev/null & WPID=$!
  sleep 2; EPID=$(pgrep -P $WPID -f engine_arm785 | head -1)
  [ -n "$EPID" ] && echo "$EPID" > out/$ID.eng.pid
  wait $WPID; RC=$?
  sleep 3; kill $MP $SP 2>/dev/null; wait $MP $SP 2>/dev/null
  echo "$ID RC=$RC spec=$SPEC ratio=$RATIO"; grep -E "prompt [0-9]+:" out/$ID.log | tail -2 | cut -c1-120
  [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done 3< <(python3 -c "import json;[print(c['id'],c['spec'],c['ratio'],c['gpu']) for c in json.load(open('cells785.json'))]")
python3 analyze785.py . > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP785-DONE"

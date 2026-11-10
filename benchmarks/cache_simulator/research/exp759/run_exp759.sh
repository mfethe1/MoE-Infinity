#!/bin/bash
# exp759 runner (Winnie, WSL). Serial; one model process at a time; GPU1 only. Head-to-head: our PR #353 vs
# upstream PR #354 vs sealed H control in ONE envelope.
# Arms:
#   H   = sealed exp752 build (/home/mfeth/exp752/src, MOEI_EXP752_MODE=H) -- drift control + anchor
#   RC  = OUR PR #353 head b7f6ca4 build (/home/mfeth/exp759/src753, MOEI_EXP752_MODE=RC)
#   P34 = upstream PR #354 head 827019db build (/home/mfeth/exp756/src, MOEI_EXP752_MODE unset; no banner)
#   hf  = transformers bf16 reference (drift anchor)
# Envelope identical to exp752/exp756: OLMoE-1B-7B-0125-Instruct, lcnu 0.75, ~/moe-offload, 6 prompts x 64 tok
# greedy, warmup 1, threads 4, gpu-route on. Exclusion gates as exp746 AMENDMENT1 / exp751 / exp752 / exp756.
cd ~/exp759 || exit 1; source ~/venvs/moei-engine/bin/activate; mkdir -p out
busy(){ local u; for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756build exp756build2 exp759build; do systemctl --user is-active -q $u && return 0; done; return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
[ -e out/RUN_SHA256 ] && mv out/RUN_SHA256 out/RUN_SHA256.prev-$(date -u +%H%M%S)
sha256sum allquiet746.sh mon752.sh nvsamp.py engine_arm.py hf_arm.py prompts.json cells759.json analyze759.py run_exp759.sh \
  grouped_moe_prefill_local.diff refs/H_2.json refs/H_3.json refs/RC_2.json refs/RC_3.json \
  /home/mfeth/exp759/src753/moe_infinity/_store*.so /home/mfeth/exp752/src/moe_infinity/_store*.so /home/mfeth/exp756/src/moe_infinity/_store*.so > out/RUN_SHA256
git -C src753 rev-parse HEAD > out/SRC_HEAD.txt 2>&1
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
PYTHONPATH=/home/mfeth/exp752/src python3 -c "import moe_infinity._store as s;print('moei-H', s.__file__)" >> out/ENV.txt 2>&1
PYTHONPATH=/home/mfeth/exp756/src python3 -c "import moe_infinity._store as s;print('moei-P34', s.__file__)" >> out/ENV.txt 2>&1
git -C src753 log -1 >> out/ENV.txt 2>&1; nproc >> out/ENV.txt; /usr/lib/wsl/lib/nvidia-smi -L >> out/ENV.txt
# identity gates: each arm must import from its own private tree (banner alone cannot prove the build)
grep -q "moei-RC753 /home/mfeth/exp759/src753/.* /home/mfeth/exp759/src753/moe_infinity/_store" out/ENV.txt \
  || { echo "IDENTITY-FAIL: RC753 import path is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
grep -q "moei-H /home/mfeth/exp752/src/moe_infinity/_store" out/ENV.txt \
  || { echo "IDENTITY-FAIL: H import path is not /home/mfeth/exp752/src"; cat out/ENV.txt; exit 9; }
grep -q "moei-P34 /home/mfeth/exp756/src/moe_infinity/_store" out/ENV.txt \
  || { echo "IDENTITY-FAIL: P34 import path is not /home/mfeth/exp756/src"; cat out/ENV.txt; exit 9; }
M=~/models/OLMoE-1B-7B-0125-Instruct
while read -u 3 ID ARM K G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(bash allquiet746.sh $G 5400 </dev/null)
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  FA=$(/usr/lib/wsl/lib/nvidia-smi --query-compute-apps=pid --format=csv,noheader | sort -u | grep -c .)
  LA=$(cut -d' ' -f1 /proc/loadavg); RW=$(pgrep -fc Runner.Worker)
  echo "$ID,$QW,$MG,$OL,$LA,$RW,$FA" >> out/precell.csv
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ]; } && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL" >> out/FLAGGED.why; }
  bash mon752.sh $G out/FLAGGED $ID </dev/null & MP=$!
  python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM gpu=$G qw=$QW la=$LA foreign_any=$FA"
  case $ARM in
    hf)  timeout 1800 python3 hf_arm.py --model $M --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    H)   env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp752/src MOEI_EXP752_MODE=H \
             timeout 1800 python3 engine_arm.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
             --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    RC)  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp759/src753 MOEI_EXP752_MODE=RC \
             timeout 1800 python3 engine_arm.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
             --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    P34) env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE -u MOEI_EXP752_MODE PYTHONPATH=/home/mfeth/exp756/src \
             timeout 1800 python3 engine_arm.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
             --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
  esac
  RC=$?; sleep 3; kill $MP $SP 2>/dev/null; wait $MP $SP 2>/dev/null
  echo "$ID RC=$RC"; grep -E "exp752 mode=|prompt [0-9]:" out/$ID.log | tail -7 | cut -c1-200
  [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
  # a successful (re-)run clears any stale FAILED entry for this cell
  [ $RC -eq 0 ] && [ -s out/$ID.json ] && [ -f out/FAILED ] && sed -i "/^$ID /d" out/FAILED
done 3< <(python3 -c "import json;[print(c['id'],c['arm'],c['stress'],c['gpu']) for c in json.load(open('cells759.json'))]")
python3 analyze759.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP759-DONE"

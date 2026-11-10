#!/bin/bash
# exp760 runner (Winnie, WSL). Serial; one model process at a time; GPU1 only.
# All cells: RC753 build (/home/mfeth/exp759/src753 = OUR PR #353 head b7f6ca4d2caa, MOEI_EXP752_MODE=RC),
# OLMoE, lcnu 0.75, ~/moe-offload, 6 prompts x 64 tok greedy, warmup 1, threads 4, gpu-route on
# (byte-identical exp752/756/759 envelope). Protocol mirrors exp757 (A2) exactly; only the build and
# mode banner differ. Arms differ ONLY in the manipulation: Q=quiet, C=12 CPU spinners, G=GPU1 co-tenant
# (gcol757.py byte-identical reuse), CG=both. Gates/verdicts in PREREG.md (FREEZE-760.txt).
cd ~/exp760 || exit 1
source ~/venvs/moei-engine/bin/activate
mkdir -p out
busy(){ local u; for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756 exp756build exp756build2 exp757 exp759 exp759build exp759run; do systemctl --user is-active -q $u && return 0; done; return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
sha256sum engine_arm.py prompts.json allquiet746.sh mon760.sh nvsamp.py gcol757.py cells760.json analyze760.py run_exp760.sh PREREG.md \
  refs/RC_2.json refs/RC_3.json /home/mfeth/exp759/src753/moe_infinity/_store*.so > out/RUN_SHA256
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
git -C /home/mfeth/exp759/src753 rev-parse HEAD >> out/ENV.txt 2>&1
git -C /home/mfeth/exp759/src753 log -1 >> out/ENV.txt 2>&1
nproc >> out/ENV.txt; /usr/lib/wsl/lib/nvidia-smi -L >> out/ENV.txt
grep -q "moei-RC753 /home/mfeth/exp759/src753/.* /home/mfeth/exp759/src753/moe_infinity/_store" out/ENV.txt \
  || { echo "IDENTITY-FAIL: RC753 import path is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
grep -q "b7f6ca4d2caa5229698d78deb03b454fc20947dd" out/ENV.txt \
  || { echo "IDENTITY-FAIL: src753 HEAD is not PR #353 head b7f6ca4d2caa"; cat out/ENV.txt; exit 9; }
M=~/models/OLMoE-1B-7B-0125-Instruct

manip_start(){ # $1=arm; sets SPINPIDS COLPID
  SPINPIDS=""; COLPID=""
  case $1 in
    C|CG)
      for i in $(seq 12); do bash -c 'while :; do :; done' </dev/null & SPINPIDS="$SPINPIDS $!"; done
      ;;
  esac
  case $1 in
    G|CG)
      env -u CUDA_VISIBLE_DEVICES python3 gcol757.py --device 1 --alloc-gb 2 --pidfile out/$ID.col.pid </dev/null > out/$ID.col.log 2>&1 &
      COLPID=$!
      ;;
  esac
}
manip_stop(){
  [ -n "$COLPID" ] && kill $COLPID 2>/dev/null
  [ -n "$SPINPIDS" ] && kill $SPINPIDS 2>/dev/null
  if [ -n "$COLPID" ] || [ -n "$SPINPIDS" ]; then wait $COLPID $SPINPIDS 2>/dev/null; fi
  COLPID=""; SPINPIDS=""
}

while read -u 3 ID ARM K G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(bash allquiet746.sh $G 5400 </dev/null)
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  FA=$(/usr/lib/wsl/lib/nvidia-smi --query-compute-apps=pid --format=csv,noheader | sort -u | grep -c .)
  LA=$(cut -d' ' -f1 /proc/loadavg); RW=$(pgrep -fc Runner.Worker)
  echo "$ID,$QW,$MG,$OL,$LA,$RW,$FA" >> out/precell.csv
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ] || [ "$FA" -gt 0 ]; } && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL foreign_any=$FA" >> out/FLAGGED.why; }
  bash mon760.sh $G out/$ID.mon.csv </dev/null & MP=$!
  python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10
  manip_start $ARM; sleep 10   # manipulation runs 10 s before the engine load (pre-registered)
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM gpu=$G qw=$QW la=$LA foreign_any=$FA manip=spin:[$SPINPIDS] colpid:$COLPID"
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE MOEI_EXP752_MODE=RC PYTHONPATH=/home/mfeth/exp759/src753 \
      timeout 1800 python3 engine_arm.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
      --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null &
  WPID=$!; sleep 2
  EPID=$(pgrep -P $WPID -f engine_arm | head -1)
  [ -n "$EPID" ] && echo "$EPID" > out/$ID.eng.pid
  wait $WPID; RC=$?
  manip_stop; sleep 3; kill $MP $SP 2>/dev/null; wait $MP $SP 2>/dev/null
  echo "$ID RC=$RC"; grep -E "exp752 mode=|prompt [0-9]:" out/$ID.log | tail -7 | cut -c1-200
  [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
  [ $RC -eq 0 ] && [ -s out/$ID.json ] && [ -f out/FAILED ] && sed -i "/^$ID /d" out/FAILED
done 3< <(python3 -c "import json;[print(c['id'],c['arm'],c['stress'],c['gpu']) for c in json.load(open('cells760.json'))]")
python3 analyze760.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP760-DONE"

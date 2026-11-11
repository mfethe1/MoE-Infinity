#!/bin/bash
# exp777 runner (Winnie, WSL): residency-ratio wall ceiling.
# 4 cells on src776 AS-BUILT (shipped DB path = PR #358 behavior; EXP776
# logging dormant — no log env set): r in {0.75, 0.90, 0.975, 1.0}.
# r=0.75 is the covariate cell (gate vs exp775 DB ref 182.66 +/-25%).
# A cell that OOMs/fails is marked and skipped; r* = max feasible r.
cd /home/mfeth/exp777 || exit 1; source ~/venvs/moei-engine/bin/activate; mkdir -p out
export CUDA_VISIBLE_DEVICES=1
PY=$(command -v py-spy) || { echo "PYSPY-FAIL: py-spy not on PATH"; exit 4; }
$PY --version 2>&1 | head -1 > out/PYSPY.txt
M=~/models/OLMoE-1B-7B-0125-Instruct
busy(){ local u p c
  for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756build exp756build2 exp759build exp761 exp761run exp762 exp766 exp767 exp771 exp772 exp773 exp774 exp775 exp776 exp777; do
    systemctl --user is-active -q $u 2>/dev/null && return 0; done
  for p in $(pgrep -f '/home/mfeth/exp7[0-9][0-9]/run_exp7[0-9][0-9]\.sh' 2>/dev/null) $(pgrep -f 'engine_arm7[0-9][0-9]\.py' 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
    case "$c" in *exp777*) continue ;; esac
    [ -n "$c" ] && return 0; done
  return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
git -C /home/mfeth/exp759/src753 rev-parse HEAD > out/SRC_HEAD.txt 2>&1
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
grep -q "^moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py" out/ENV.txt || { echo "IDENTITY-FAIL: build is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
PYTHONPATH=/home/mfeth/exp776/src776 python3 -c "import moe_infinity; print('moei-776', moe_infinity.__file__)" >> out/ENV.txt 2>&1
grep -q "^moei-776 /home/mfeth/exp776/src776/moe_infinity/__init__.py" out/ENV.txt \
  || { echo "IDENTITY-FAIL: src776 not importable"; exit 9; }
F776=/home/mfeth/exp776/src776/moe_infinity/memory/expert_prefetcher.py
[ "$(grep -c 'exp776 routedlog' $F776)" = "1" ] && [ "$(grep -c 'EXP773_DB' $F776)" = "1" ] \
  || { echo "PATCH-FAIL: src776 markers wrong"; exit 9; }
sha256sum $F776 | cut -c1-16 > out/SRC776_FILE_SHA.txt
[ "$(cat out/SRC776_FILE_SHA.txt)" = "3571f714c811e1c7" ] \
  || { echo "IDENTITY-FAIL: src776 file sha != 3571f714c811e1c7"; exit 9; }
run_cell(){ # ID RATIO
  local ID=$1 R=$2
  [ -s out/$ID.json ] && { echo "skip $ID"; return 0; }
  rm -f out/$ID.pid out/$ID.rl.jsonl
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp776/src776 EXP773_DB=1 MOEI_EXP752_MODE=RC \
      MOE_INFINITY_PROFILE_IO=1 MOE_INFINITY_PROFILE_IO_OUT=/home/mfeth/exp777/out/$ID.io.jsonl \
      timeout 3600 $PY record -r 50 -f raw -o out/$ID.pyspy -- python3 /home/mfeth/exp776/engine_arm776.py --model $M \
      --offload ~/moe-offload --policy lcnu --ratio $R --threads 4 --gpu-route off \
      --spec-prefetch on --spec-overlap off --overlap-policy off \
      --prompts /home/mfeth/exp776/prompts774.json --max-new 64 --warmup 1 --out out/$ID.json --pidfile out/$ID.pid \
      > out/$ID.log 2>&1 </dev/null &
  local EPID=$!
  python3 /home/mfeth/exp776/sampler776.py out/$ID.pid out/$ID.oscsv out/$ID.tidcsv 20 > out/$ID.sampler.log 2>&1 &
  local SPID=$!
  wait $EPID; local RC=$?
  sleep 1; kill $SPID 2>/dev/null; wait $SPID 2>/dev/null
  echo "$ID RC=$RC"
  echo "$ID RC=$RC" >> out/CELL_RC.txt
  [ $RC -ne 0 ] && { echo "$ID failed rc=$RC (ratio $R)" >> out/CELL_FAIL.txt; return 0; }
  grep -q "exp752 mode=2" out/$ID.log || echo "$ID banner-absent" >> out/BANNER-FAIL
  [ -s out/$ID.oscsv ] || { echo "$ID oscsv-empty RC=$RC" >> out/BADIO; }
  [ -s out/$ID.tidcsv ] || { echo "$ID tidcsv-empty RC=$RC" >> out/BADIO; }
  [ -s out/$ID.pyspy ] || { echo "$ID pyspy-empty RC=$RC" >> out/BADIO; }
  grep -E "prompt [0-9]+ of|DONE" out/$ID.log | tail -3 | cut -c1-160
  return 0
}
run_cell PY_R075 0.75
run_cell PY_R090 0.90
run_cell PY_R0975 0.975
run_cell PY_R100 1.0
echo "== done $(date -u +%FT%TZ) =="

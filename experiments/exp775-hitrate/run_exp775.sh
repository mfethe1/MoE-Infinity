#!/bin/bash
# exp775 runner (Winnie, WSL): prefetch hit-rate retention under the exp773
# async double-buffer's one-call-staler predictions.
# 2 cells, BOTH on src775 (= src753 + patch775.py, the instrumented superset
# of the exp773 patch; async-dbuf logic byte-identical):
#   PY_SPEC: EXP773_DB unset  -> blocking path, logs fresh "issued" lists
#   PY_DB:   EXP773_DB=1      -> double-buffer, logs "consumed" lists
# Metric (frozen, offline): coverage of the next call's need.
#   SPEC hit(t) = |L_t n L_{t+1}|/|L_{t+1}|            (lag-1, from issued log)
#   DB   hit(t) = |C_t n C_{t+2}|/|C_{t+2}|            (lag-2, C_t = L_{t-1})
# Pairs spanning >1.0s call gaps (prompt boundaries) are excluded.
# Walls recorded as covariates and gated against exp774 sealed references
# (SPEC 212.13s, DB 179.72s; +-25%) to prove instrumentation didn't perturb.
# Derived from frozen run_exp774.sh (9168802c453bbd0d): 2 cells; roster adds
# exp774; EXP775_LOG_OUT per cell; prompts774.json byte-identical workload.
cd /home/mfeth/exp775 || exit 1; source ~/venvs/moei-engine/bin/activate; mkdir -p out
export CUDA_VISIBLE_DEVICES=1
PY=$(command -v py-spy) || { echo "PYSPY-FAIL: py-spy not on PATH"; exit 4; }
PYV=$($PY --version 2>&1 | head -1); echo "$PYV" > out/PYSPY.txt
M=~/models/OLMoE-1B-7B-0125-Instruct
busy(){ local u p c
  for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756build exp756build2 exp759build exp761 exp761run exp762 exp766 exp767 exp771 exp772 exp773 exp774 exp775; do
    systemctl --user is-active -q $u 2>/dev/null && return 0; done
  for p in $(pgrep -f '/home/mfeth/exp7[0-9][0-9]/run_exp7[0-9][0-9]\.sh' 2>/dev/null) $(pgrep -f 'engine_arm76[0-9]\.py' 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
    case "$c" in *exp775*) continue ;; esac
    [ -n "$c" ] && return 0; done
  return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
git -C /home/mfeth/exp759/src753 rev-parse HEAD > out/SRC_HEAD.txt 2>&1
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
grep -q "^moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py" out/ENV.txt && grep -q " /home/mfeth/exp759/src753/moe_infinity/_store\." out/ENV.txt \
  || { echo "IDENTITY-FAIL: build is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
PYTHONPATH=/home/mfeth/exp775/src775 python3 -c "import moe_infinity; print('moei-775', moe_infinity.__file__)" >> out/ENV.txt 2>&1
grep -q "^moei-775 /home/mfeth/exp775/src775/moe_infinity/__init__.py" out/ENV.txt \
  || { echo "IDENTITY-FAIL: src775 not importable"; exit 9; }
F775=/home/mfeth/exp775/src775/moe_infinity/memory/expert_prefetcher.py
[ "$(grep -c 'exp775 hitlog' $F775)" = "1" ] && [ "$(grep -c 'exp773 async-dbuf' $F775)" = "1" ] \
  || { echo "PATCH-FAIL: hitlog/dbuf markers not exactly 1 each"; exit 9; }
[ "$(git -C /home/mfeth/exp775/src775 rev-parse HEAD)" = "$(cat out/SRC_HEAD.txt)" ] \
  || { echo "HEAD-MISMATCH: src775 != src753 HEAD"; exit 9; }
run_cell(){ # ID SP SO OP DB
  local ID=$1 SP=$2 SO=$3 OP=$4 DB=$5
  [ -s out/$ID.json ] && { echo "skip $ID"; return 0; }
  rm -f out/$ID.pid out/$ID.hits.jsonl
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp775/src775 EXP773_DB=$DB EXP775_LOG_OUT=/home/mfeth/exp775/out/$ID.hits.jsonl MOEI_EXP752_MODE=RC \
      MOE_INFINITY_PROFILE_IO=1 MOE_INFINITY_PROFILE_IO_OUT=/home/mfeth/exp775/out/$ID.io.jsonl \
      timeout 3600 $PY record -r 50 -f raw -o out/$ID.pyspy -- python3 engine_arm775.py --model $M \
      --offload ~/moe-offload --policy lcnu --ratio 0.75 --threads 4 --gpu-route off \
      --spec-prefetch $SP --spec-overlap $SO --overlap-policy $OP \
      --prompts prompts774.json --max-new 64 --warmup 1 --out out/$ID.json --pidfile out/$ID.pid \
      > out/$ID.log 2>&1 </dev/null &
  local EPID=$!
  python3 sampler775.py out/$ID.pid out/$ID.oscsv out/$ID.tidcsv 20 > out/$ID.sampler.log 2>&1 &
  local SPID=$!
  wait $EPID; local RC=$?
  sleep 1; kill $SPID 2>/dev/null; wait $SPID 2>/dev/null
  echo "$ID RC=$RC"
  grep -q "exp752 mode=2" out/$ID.log || echo "$ID banner-absent" >> out/BANNER-FAIL
  [ -s out/$ID.oscsv ] || { echo "$ID oscsv-empty RC=$RC" >> out/BADIO; }
  [ -s out/$ID.tidcsv ] || { echo "$ID tidcsv-empty RC=$RC" >> out/BADIO; }
  [ -s out/$ID.pyspy ] || { echo "$ID pyspy-empty RC=$RC" >> out/BADIO; }
  [ -s out/$ID.hits.jsonl ] || { echo "$ID hits-empty RC=$RC" >> out/BADIO; }
  grep -E "prompt [0-9]+ of|DONE" out/$ID.log | tail -3 | cut -c1-160
  return 0
}
run_cell PY_SPEC on off off 0
run_cell PY_DB   on off off 1
echo "== done $(date -u +%FT%TZ) =="

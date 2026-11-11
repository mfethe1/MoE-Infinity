#!/bin/bash
# exp772 runner (Winnie, WSL): k-stride speculative prediction — amortize the
# per-token .indices.cpu() D2H sync found at expert_prefetcher.py:450 (exp772).
# 3 cells: PY_LGC (src753, off/off/off), PY_SPEC (src753, on/off/off),
#          PY_K4 (src772 = src753 + k-stride guard, on, EXP772_K=4).
# Derived from frozen run_exp772.sh (3436e48b4a32e31c) with additive changes:
#   1. paths exp772 -> exp772; engine/sampler renamed (bytes identical)
#   2. run_cell gains SRC K args -> per-cell PYTHONPATH + EXP772_K
#   3. identity block adds src772 checks (marker + HEAD == src753 HEAD)
#   4. third cell PY_K4; busy-gate roster adds exp772
# Same envelope/build/flags as exp762/764/767 cells (src753 @ b7f6ca4).
cd /home/mfeth/exp772 || exit 1; source ~/venvs/moei-engine/bin/activate; mkdir -p out
export CUDA_VISIBLE_DEVICES=1
PY=$(command -v py-spy) || { echo "PYSPY-FAIL: py-spy not on PATH"; exit 4; }
PYV=$($PY --version 2>&1 | head -1); echo "$PYV" > out/PYSPY.txt
M=~/models/OLMoE-1B-7B-0125-Instruct
busy(){ local u p c
  for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756build exp756build2 exp759build exp761 exp761run exp762 exp766 exp767 exp771 exp772; do
    systemctl --user is-active -q $u 2>/dev/null && return 0; done
  for p in $(pgrep -f '/home/mfeth/exp7[0-9][0-9]/run_exp7[0-9][0-9]\.sh' 2>/dev/null) $(pgrep -f 'engine_arm76[0-9]\.py' 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
    case "$c" in *exp772*) continue ;; esac
    [ -n "$c" ] && return 0; done
  return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
git -C /home/mfeth/exp759/src753 rev-parse HEAD > out/SRC_HEAD.txt 2>&1
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
grep -q "^moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py" out/ENV.txt && grep -q " /home/mfeth/exp759/src753/moe_infinity/_store\." out/ENV.txt \
  || { echo "IDENTITY-FAIL: build is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
PYTHONPATH=/home/mfeth/exp772/src772 python3 -c "import moe_infinity; print('moei-772', moe_infinity.__file__)" >> out/ENV.txt 2>&1
grep -q "^moei-772 /home/mfeth/exp772/src772/moe_infinity/__init__.py" out/ENV.txt \
  || { echo "IDENTITY-FAIL: src772 not importable"; exit 9; }
grep -q "exp772 k-stride" /home/mfeth/exp772/src772/moe_infinity/memory/expert_prefetcher.py \
  || { echo "PATCH-FAIL: k-stride marker absent"; exit 9; }
[ "$(git -C /home/mfeth/exp772/src772 rev-parse HEAD)" = "$(cat out/SRC_HEAD.txt)" ] \
  || { echo "HEAD-MISMATCH: src772 != src753 HEAD"; exit 9; }
run_cell(){ # ID SP SO OP SRC K
  local ID=$1 SP=$2 SO=$3 OP=$4 SRC=$5 K=$6
  [ -s out/$ID.json ] && { echo "skip $ID"; return 0; }
  rm -f out/$ID.pid
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=$SRC EXP772_K=$K MOEI_EXP752_MODE=RC \
      MOE_INFINITY_PROFILE_IO=1 MOE_INFINITY_PROFILE_IO_OUT=/home/mfeth/exp772/out/$ID.io.jsonl \
      timeout 1500 $PY record -r 50 -f raw -o out/$ID.pyspy -- python3 engine_arm772.py --model $M \
      --offload ~/moe-offload --policy lcnu --ratio 0.75 --threads 4 --gpu-route off \
      --spec-prefetch $SP --spec-overlap $SO --overlap-policy $OP \
      --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json --pidfile out/$ID.pid \
      > out/$ID.log 2>&1 </dev/null &
  local EPID=$!
  python3 sampler772.py out/$ID.pid out/$ID.oscsv out/$ID.tidcsv 20 > out/$ID.sampler.log 2>&1 &
  local SPID=$!
  wait $EPID; local RC=$?
  sleep 1; kill $SPID 2>/dev/null; wait $SPID 2>/dev/null
  echo "$ID RC=$RC"
  grep -q "exp752 mode=2" out/$ID.log || echo "$ID banner-absent" >> out/BANNER-FAIL
  [ -s out/$ID.oscsv ] || { echo "$ID oscsv-empty RC=$RC" >> out/BADIO; }
  [ -s out/$ID.tidcsv ] || { echo "$ID tidcsv-empty RC=$RC" >> out/BADIO; }
  [ -s out/$ID.pyspy ] || { echo "$ID pyspy-empty RC=$RC" >> out/BADIO; }
  grep -E "prompt [0-9]:|DONE" out/$ID.log | tail -3 | cut -c1-160
  return 0
}
run_cell PY_LGC  off off off /home/mfeth/exp759/src753 1
run_cell PY_SPEC on  off off /home/mfeth/exp759/src753 1
run_cell PY_K4   on  off off /home/mfeth/exp772/src772 4
echo "== done $(date -u +%FT%TZ) =="
